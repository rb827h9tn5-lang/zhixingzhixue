from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from ..extensions import db
from ..models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgePoint,
    KnowledgeRelation,
    LearningEvent,
    LearningPath,
    LearningPathNode,
    LearningPathVersion,
    NodeResource,
    Profile,
    Resource,
    UserKnowledgeMastery,
)
from .learning_event_service import LearningEventService
from .mastery_service import MasteryService
from .question_mapping import knowledge_point_candidates
from .rag_store import format_source_citation


class StructuredPathService:
    @classmethod
    def create_version(
        cls,
        *,
        profile: Profile,
        legacy_content: str,
        reason_event_id: int | None = None,
        replanning_reason: str = "",
        remediation_point_ids: list[int] | None = None,
        remediation_only: bool = False,
    ) -> tuple[LearningPath, LearningPathVersion]:
        path = (
            LearningPath.query.filter_by(user_id=profile.user_id)
            .order_by(LearningPath.created_at.desc(), LearningPath.id.desc())
            .first()
        )
        if not path:
            path = LearningPath(
                user_id=profile.user_id,
                title=f"{profile.topic} 动态学习路径",
                content=legacy_content,
            )
            db.session.add(path)
            db.session.flush()

        latest = cls.latest_version(path.id)
        version_number = (latest.version_number + 1) if latest else 1
        version = LearningPathVersion(
            path_id=path.id,
            version_number=version_number,
            parent_version_id=latest.id if latest else None,
            reason_event_id=reason_event_id,
            replanning_reason=replanning_reason,
        )
        db.session.add(version)
        db.session.flush()

        if remediation_point_ids and remediation_only:
            cls._build_remediation_nodes(
                profile=profile,
                version=version,
                remediation_point_ids=remediation_point_ids,
                replanning_reason=replanning_reason,
            )
        elif latest and remediation_point_ids:
            cls._clone_with_remediation(
                profile=profile,
                source=latest,
                target=version,
                remediation_point_ids=remediation_point_ids,
                replanning_reason=replanning_reason,
            )
        else:
            cls._build_initial_nodes(profile, version)

        path.content = cls.render_markdown(path, version, legacy_content)
        db.session.flush()
        return path, version

    @staticmethod
    def latest_version(path_id: int) -> LearningPathVersion | None:
        return (
            LearningPathVersion.query.filter_by(path_id=path_id)
            .order_by(LearningPathVersion.version_number.desc(), LearningPathVersion.id.desc())
            .first()
        )

    @staticmethod
    def latest_user_path(user_id: int) -> tuple[LearningPath | None, LearningPathVersion | None]:
        path = (
            LearningPath.query.filter_by(user_id=user_id)
            .order_by(LearningPath.created_at.desc(), LearningPath.id.desc())
            .first()
        )
        return path, StructuredPathService.latest_version(path.id) if path else None

    @classmethod
    def open_node(cls, *, user_id: int, node_id: int) -> tuple[LearningPathNode, LearningEvent, bool]:
        node = cls._owned_node(user_id, node_id)
        if node.status == "locked":
            previous = (
                LearningPathNode.query.filter_by(path_version_id=node.path_version_id)
                .filter(LearningPathNode.node_order < node.node_order)
                .order_by(LearningPathNode.node_order.desc())
                .first()
            )
            if previous and previous.status != "completed":
                raise ValueError("请先完成前一个学习节点")
            node.status = "ready"
        if node.status == "ready":
            node.status = "learning"
        event, created = LearningEventService.record_event(
            user_id=user_id,
            event_type="node_open",
            event_key=f"node:{node.id}:open",
            knowledge_point_id=node.knowledge_point_id,
            path_id=node.path_version.path_id,
            path_version_id=node.path_version_id,
            node_id=node.id,
            source_type="learning_path_node",
            source_id=str(node.id),
            value={"node_order": node.node_order, "node_type": node.node_type},
        )
        return node, event, created

    @classmethod
    def complete_node(cls, *, user_id: int, node_id: int) -> tuple[LearningPathNode, list[LearningEvent], list[dict]]:
        node = cls._owned_node(user_id, node_id)
        node.status = "completed"
        events = []
        node_event, _ = LearningEventService.record_event(
            user_id=user_id,
            event_type="node_complete",
            event_key=f"node:{node.id}:complete",
            knowledge_point_id=node.knowledge_point_id,
            path_id=node.path_version.path_id,
            path_version_id=node.path_version_id,
            node_id=node.id,
            source_type="learning_path_node",
            source_id=str(node.id),
            value={"node_order": node.node_order, "node_type": node.node_type},
        )
        events.append(node_event)

        primary_resource = node.resources[0] if node.resources else None
        if primary_resource:
            resource_event, _ = LearningEventService.record_event(
                user_id=user_id,
                event_type="resource_complete",
                event_key=f"node:{node.id}:resource:{primary_resource.resource_id}:complete",
                knowledge_point_id=node.knowledge_point_id,
                path_id=node.path_version.path_id,
                path_version_id=node.path_version_id,
                node_id=node.id,
                resource_id=primary_resource.resource_id,
                source_type="node_resource",
                source_id=str(primary_resource.id),
                value={"resource_type": primary_resource.resource_type},
            )
            events.append(resource_event)

        next_node = (
            LearningPathNode.query.filter_by(path_version_id=node.path_version_id)
            .filter(LearningPathNode.node_order > node.node_order)
            .order_by(LearningPathNode.node_order)
            .first()
        )
        if next_node and next_node.status == "locked":
            next_node.status = "ready"
        changes = MasteryService.apply_events(events)
        return node, events, changes

    @classmethod
    def diff_versions(
        cls,
        *,
        user_id: int,
        from_version_id: int,
        to_version_id: int,
    ) -> dict:
        from_version = cls._owned_version(user_id, from_version_id)
        to_version = cls._owned_version(user_id, to_version_id)
        if from_version.path_id != to_version.path_id:
            raise ValueError("只能比较同一学习路径的版本")

        old_map = cls._node_map(from_version.nodes)
        new_map = cls._node_map(to_version.nodes)
        added = [
            node.to_dict(include_resources=True)
            for key, node in new_map.items()
            if key not in old_map
        ]
        removed = [
            node.to_dict(include_resources=True)
            for key, node in old_map.items()
            if key not in new_map
        ]
        moved = []
        changed = []
        for key in old_map.keys() & new_map.keys():
            old = old_map[key]
            new = new_map[key]
            if old.node_order != new.node_order:
                moved.append({
                    "knowledge_point_id": new.knowledge_point_id,
                    "knowledge_point": new.knowledge_point.name if new.knowledge_point else "",
                    "node_type": new.node_type,
                    "from_order": old.node_order,
                    "to_order": new.node_order,
                })
            changes = {}
            for field in ("status", "difficulty", "mastery_before", "mastery_target", "estimated_minutes"):
                if getattr(old, field) != getattr(new, field):
                    changes[field] = {"old": getattr(old, field), "new": getattr(new, field)}
            if changes:
                changed.append({
                    "knowledge_point_id": new.knowledge_point_id,
                    "knowledge_point": new.knowledge_point.name if new.knowledge_point else "",
                    "node_type": new.node_type,
                    "changes": changes,
                })

        reason_event = (
            db.session.get(LearningEvent, to_version.reason_event_id)
            if to_version.reason_event_id
            else None
        )
        return {
            "path_id": from_version.path_id,
            "from_version": from_version.version_number,
            "to_version": to_version.version_number,
            "added_nodes": added,
            "removed_nodes": removed,
            "moved_nodes": moved,
            "changed_nodes": changed,
            "reason": to_version.replanning_reason or "",
            "mastery_change": (reason_event.value_json or {}).get("mastery_change") if reason_event else None,
        }

    @classmethod
    def render_markdown(
        cls,
        path: LearningPath,
        version: LearningPathVersion,
        legacy_content: str = "",
    ) -> str:
        lines = [
            f"## {path.title}",
            f"- 路径版本：v{version.version_number}",
            f"- 动态策略：{version.replanning_reason or '依据画像、知识掌握证据和先修关系生成结构化路径'}",
            "",
        ]
        for node in version.nodes:
            title = node.knowledge_point.name if node.knowledge_point else f"学习节点 {node.node_order}"
            resource_text = "、".join(
                item.resource.title
                for item in node.resources
                if item.resource
            ) or "等待绑定真实课程资源"
            lines.extend([
                f"### 阶段 {node.node_order}：{title}",
                f"- 预估时间：{node.estimated_minutes} 分钟",
                f"- 学习目标：将“{title}”掌握度提升到 {round(node.mastery_target)}%",
                f"- 学习任务：{node.reason or '学习真实课程材料并完成知识检查'}",
                "- 操作入口：知识学习",
                f"- 推荐资源：{resource_text}",
                f"- 学习产出：完成该知识点的学习记录与测评证据",
                f"- 完成标准：节点状态完成，后续通过测评更新 Mastery",
                "",
            ])
        if not version.nodes and legacy_content:
            lines.extend(["### 原路径内容", legacy_content])
        return "\n".join(lines).strip()

    @classmethod
    def _build_initial_nodes(cls, profile: Profile, version: LearningPathVersion) -> None:
        points = knowledge_point_candidates(profile.topic)
        mastery_by_point = {
            item.knowledge_point_id: item
            for item in UserKnowledgeMastery.query.filter_by(user_id=profile.user_id).all()
        }
        candidates = [
            point
            for point in points
            if (
                point.id not in mastery_by_point
                or mastery_by_point[point.id].mastery_score < 70
            )
            and cls._has_grounding_source(profile.user_id, point)
        ]
        ordered = cls._order_by_prerequisites(candidates[:8])
        for index, point in enumerate(ordered, start=1):
            mastery = mastery_by_point.get(point.id)
            node = LearningPathNode(
                path_version_id=version.id,
                knowledge_point_id=point.id,
                node_order=index,
                status="ready" if index == 1 else "locked",
                difficulty=point.difficulty or "beginner",
                mastery_before=mastery.mastery_score if mastery else None,
                mastery_target=70.0,
                estimated_minutes=cls._estimated_minutes(profile, remediation=False),
                reason=cls._initial_reason(point, mastery),
                node_type="normal",
            )
            db.session.add(node)
            db.session.flush()
            cls._bind_grounded_resource(profile, node, remediation=False)

    @classmethod
    def _clone_with_remediation(
        cls,
        *,
        profile: Profile,
        source: LearningPathVersion,
        target: LearningPathVersion,
        remediation_point_ids: list[int],
        replanning_reason: str,
    ) -> None:
        target_ids = set(remediation_point_ids)
        sequence: list[tuple[str, LearningPathNode | None, int | None]] = []
        existing_target_ids = {node.knowledge_point_id for node in source.nodes}
        for old in source.nodes:
            sequence.append(("clone", old, old.knowledge_point_id))
            if old.knowledge_point_id in target_ids:
                sequence.append(("remediation", None, old.knowledge_point_id))
                sequence.append(("assessment", None, old.knowledge_point_id))
        for point_id in sorted(target_ids - existing_target_ids):
            sequence.insert(0, ("remediation", None, point_id))
            sequence.insert(1, ("assessment", None, point_id))

        mastery_by_point = {
            item.knowledge_point_id: item
            for item in UserKnowledgeMastery.query.filter_by(user_id=profile.user_id).all()
        }
        for index, (kind, old, point_id) in enumerate(sequence, start=1):
            point = db.session.get(KnowledgePoint, point_id) if point_id else None
            mastery = mastery_by_point.get(point_id)
            if kind == "clone" and old:
                node = LearningPathNode(
                    path_version_id=target.id,
                    knowledge_point_id=old.knowledge_point_id,
                    node_order=index,
                    status=old.status,
                    difficulty=old.difficulty,
                    mastery_before=mastery.mastery_score if mastery else old.mastery_before,
                    mastery_target=old.mastery_target,
                    estimated_minutes=old.estimated_minutes,
                    reason=old.reason,
                    node_type=old.node_type,
                )
            else:
                node_type = "assessment" if kind == "assessment" else "remediation"
                label = point.name if point else "薄弱知识点"
                node = LearningPathNode(
                    path_version_id=target.id,
                    knowledge_point_id=point_id,
                    node_order=index,
                    status="remediation" if kind == "remediation" else "locked",
                    difficulty="beginner" if kind == "remediation" else (point.difficulty if point else "beginner"),
                    mastery_before=mastery.mastery_score if mastery else None,
                    mastery_target=60.0 if kind == "remediation" else 70.0,
                    estimated_minutes=cls._estimated_minutes(profile, remediation=True),
                    reason=(
                        f"{replanning_reason}；插入“{label}”补救学习"
                        if kind == "remediation"
                        else f"完成“{label}”补救学习后进行节点复测"
                    ),
                    node_type=node_type,
                )
            db.session.add(node)
            db.session.flush()
            if old and old.resources:
                for binding in old.resources:
                    db.session.add(NodeResource(
                        node_id=node.id,
                        resource_id=binding.resource_id,
                        resource_type=binding.resource_type,
                        priority=binding.priority,
                        personalization_reason=binding.personalization_reason,
                    ))
            else:
                cls._bind_grounded_resource(profile, node, remediation=True)

        first_incomplete = (
            LearningPathNode.query.filter_by(path_version_id=target.id)
            .filter(LearningPathNode.status != "completed")
            .order_by(LearningPathNode.node_order)
            .first()
        )
        if first_incomplete and first_incomplete.status == "locked":
            first_incomplete.status = "ready"

    @classmethod
    def _build_remediation_nodes(
        cls,
        *,
        profile: Profile,
        version: LearningPathVersion,
        remediation_point_ids: list[int],
        replanning_reason: str,
    ) -> None:
        seen = set()
        points = []
        for point_id in remediation_point_ids:
            if point_id in seen:
                continue
            point = db.session.get(KnowledgePoint, point_id)
            if point:
                points.append(point)
                seen.add(point_id)
        points = cls._order_by_prerequisites(points)
        mastery_by_point = {
            row.knowledge_point_id: row
            for row in UserKnowledgeMastery.query.filter_by(
                user_id=profile.user_id
            ).all()
        }
        node_order = 1
        for point in points:
            mastery = mastery_by_point.get(point.id)
            node = LearningPathNode(
                path_version_id=version.id,
                knowledge_point_id=point.id,
                node_order=node_order,
                status="ready" if node_order == 1 else "locked",
                difficulty="beginner",
                mastery_before=mastery.mastery_score if mastery else None,
                mastery_target=60.0,
                estimated_minutes=cls._estimated_minutes(
                    profile,
                    remediation=True,
                ),
                reason=(
                    f"{replanning_reason}；先学习“{point.name}”的课程材料并完成练习"
                ),
                node_type="remediation",
            )
            db.session.add(node)
            db.session.flush()
            cls._bind_grounded_resource(profile, node, remediation=True)
            node_order += 1

        target = points[-1] if points else None
        if target:
            mastery = mastery_by_point.get(target.id)
            assessment = LearningPathNode(
                path_version_id=version.id,
                knowledge_point_id=target.id,
                node_order=node_order,
                status="locked",
                difficulty=target.difficulty or "beginner",
                mastery_before=mastery.mastery_score if mastery else None,
                mastery_target=70.0,
                estimated_minutes=max(
                    10,
                    cls._estimated_minutes(profile, remediation=True) // 2,
                ),
                reason=f"补救学习后复测“{target.name}”，用新证据更新掌握度",
                node_type="assessment",
            )
            db.session.add(assessment)
            db.session.flush()
            cls._bind_grounded_resource(profile, assessment, remediation=True)

    @staticmethod
    def _order_by_prerequisites(points: list[KnowledgePoint]) -> list[KnowledgePoint]:
        if not points:
            return []
        point_by_id = {point.id: point for point in points}
        relations = KnowledgeRelation.query.filter(
            KnowledgeRelation.relation_type == "prerequisite",
            KnowledgeRelation.source_knowledge_point_id.in_(point_by_id),
            KnowledgeRelation.target_knowledge_point_id.in_(point_by_id),
        ).all()
        outgoing: dict[int, list[int]] = defaultdict(list)
        indegree = {point_id: 0 for point_id in point_by_id}
        for relation in relations:
            outgoing[relation.source_knowledge_point_id].append(relation.target_knowledge_point_id)
            indegree[relation.target_knowledge_point_id] += 1
        queue = deque(sorted(
            (point_id for point_id, degree in indegree.items() if degree == 0),
            key=lambda point_id: (point_by_id[point_id].code, point_id),
        ))
        ordered_ids = []
        while queue:
            point_id = queue.popleft()
            ordered_ids.append(point_id)
            for target_id in sorted(outgoing[point_id]):
                indegree[target_id] -= 1
                if indegree[target_id] == 0:
                    queue.append(target_id)
        if len(ordered_ids) != len(point_by_id):
            remaining = sorted(
                set(point_by_id) - set(ordered_ids),
                key=lambda point_id: (point_by_id[point_id].code, point_id),
            )
            ordered_ids.extend(remaining)
        return [point_by_id[point_id] for point_id in ordered_ids]

    @classmethod
    def _bind_grounded_resource(
        cls,
        profile: Profile,
        node: LearningPathNode,
        *,
        remediation: bool,
    ) -> None:
        if not node.knowledge_point_id:
            return
        chunks = (
            KnowledgeChunk.query.join(KnowledgeDocument)
            .filter(
                KnowledgeDocument.user_id == profile.user_id,
                KnowledgeChunk.knowledge_point_id == node.knowledge_point_id,
            )
            .order_by(KnowledgeChunk.page_start, KnowledgeChunk.chunk_index)
            .limit(2)
            .all()
        )
        grounding_scope = "知识点直接绑定"
        if not chunks and node.knowledge_point:
            chunks = (
                KnowledgeChunk.query.join(KnowledgeDocument)
                .filter(
                    KnowledgeDocument.user_id == profile.user_id,
                    KnowledgeChunk.chapter_id == node.knowledge_point.chapter_id,
                )
                .order_by(KnowledgeChunk.page_start, KnowledgeChunk.chunk_index)
                .limit(2)
                .all()
            )
            grounding_scope = "同章真实课程材料"
        if not chunks and node.knowledge_point:
            chunks = (
                KnowledgeChunk.query.join(KnowledgeDocument)
                .filter(
                    KnowledgeDocument.user_id == profile.user_id,
                    KnowledgeChunk.course_id == node.knowledge_point.course_id,
                )
                .order_by(KnowledgeChunk.page_start, KnowledgeChunk.chunk_index)
                .limit(2)
                .all()
            )
            grounding_scope = "同课程真实材料"
        if not chunks:
            return
        point = node.knowledge_point
        excerpts = []
        for chunk in chunks:
            source = chunk.to_dict()
            excerpts.append(
                f"> {(chunk.chunk_text or '')[:800]}\n\n来源：{format_source_citation(source)}"
            )
        resource_type = "remediation" if remediation else "node_grounding"
        title = f"{point.name}{'补救材料' if remediation else '学习材料'}"
        content = "\n\n".join([
            f"## {title}",
            f"材料范围：{grounding_scope}。内容仅来自当前知识库的真实 Chunk。",
            *excerpts,
        ])
        resource = Resource(
            user_id=profile.user_id,
            resource_type=resource_type,
            title=title,
            content=content,
        )
        db.session.add(resource)
        db.session.flush()
        mastery = UserKnowledgeMastery.query.filter_by(
            user_id=profile.user_id,
            knowledge_point_id=point.id,
        ).first()
        mastery_text = (
            f"当前掌握度 {round(mastery.mastery_score)}%，置信度 {round(mastery.confidence, 2)}"
            if mastery
            else "当前尚无足够测评证据"
        )
        reason = (
            f"{mastery_text}；画像学习风格为 {profile.learning_style or 'mixed'}；"
            f"因此绑定{grounding_scope}"
        )
        db.session.add(NodeResource(
            node_id=node.id,
            resource_id=resource.id,
            resource_type=resource_type,
            priority=1,
            personalization_reason=reason,
        ))

    @staticmethod
    def _has_grounding_source(user_id: int, point: KnowledgePoint) -> bool:
        return (
            KnowledgeChunk.query.join(KnowledgeDocument)
            .filter(
                KnowledgeDocument.user_id == user_id,
                (
                    (KnowledgeChunk.knowledge_point_id == point.id)
                    | (KnowledgeChunk.chapter_id == point.chapter_id)
                    | (KnowledgeChunk.course_id == point.course_id)
                ),
            )
            .first()
            is not None
        )

    @staticmethod
    def _estimated_minutes(profile: Profile, *, remediation: bool) -> int:
        weekly = profile.weekly_time_minutes or 300
        base = max(20, min(60, round(weekly / 10)))
        return min(45, base) if remediation else base

    @staticmethod
    def _initial_reason(
        point: KnowledgePoint,
        mastery: UserKnowledgeMastery | None,
    ) -> str:
        if not mastery:
            return f"“{point.name}”尚未评估，按课程顺序安排诊断性学习"
        return (
            f"“{point.name}”当前掌握度 {round(mastery.mastery_score)}%，"
            f"置信度 {round(mastery.confidence, 2)}，低于目标 70%"
        )

    @staticmethod
    def _owned_node(user_id: int, node_id: int) -> LearningPathNode:
        node = (
            LearningPathNode.query.join(LearningPathVersion)
            .join(LearningPath)
            .filter(LearningPathNode.id == node_id, LearningPath.user_id == user_id)
            .first()
        )
        if not node:
            raise LookupError("学习节点不存在")
        return node

    @staticmethod
    def _owned_version(user_id: int, version_id: int) -> LearningPathVersion:
        version = (
            LearningPathVersion.query.join(LearningPath)
            .filter(LearningPathVersion.id == version_id, LearningPath.user_id == user_id)
            .first()
        )
        if not version:
            raise LookupError("学习路径版本不存在")
        return version

    @staticmethod
    def _node_map(nodes: list[LearningPathNode]) -> dict[str, LearningPathNode]:
        counts: dict[tuple[int | None, str], int] = defaultdict(int)
        result = {}
        for node in nodes:
            base = (node.knowledge_point_id, node.node_type)
            counts[base] += 1
            result[f"{node.knowledge_point_id}:{node.node_type}:{counts[base]}"] = node
        return result


class ReplanningService:
    MASTERY_THRESHOLD = 45.0
    CONSECUTIVE_WRONG_THRESHOLD = 2

    @classmethod
    def maybe_replan(
        cls,
        *,
        profile: Profile,
        mastery_changes: list[dict],
        assessment_id: int,
    ) -> dict:
        path, current_version = StructuredPathService.latest_user_path(profile.user_id)
        if not path or not current_version:
            return {"triggered": False, "reason": "当前没有结构化学习路径"}

        triggers = []
        for change in mastery_changes:
            point_id = int(change["knowledge_point_id"])
            low_after_drop = change["new"] < cls.MASTERY_THRESHOLD and change["delta"] < 0
            consecutive_wrong = cls._consecutive_wrong_count(profile.user_id, point_id) >= cls.CONSECUTIVE_WRONG_THRESHOLD
            if low_after_drop or consecutive_wrong:
                triggers.append(change)
        if not triggers:
            return {"triggered": False, "reason": "Mastery 未达到自动重规划阈值"}

        point_names = [item["knowledge_point"] for item in triggers]
        reason = (
            f"Assessment #{assessment_id} 后检测到薄弱知识点：{'、'.join(point_names)}；"
            f"Mastery 低于 {round(cls.MASTERY_THRESHOLD)}% 或出现连续错误"
        )
        trigger_event, created = LearningEventService.record_event(
            user_id=profile.user_id,
            event_type="replan_trigger",
            event_key=f"assessment:{assessment_id}:replan",
            path_id=path.id,
            path_version_id=current_version.id,
            assessment_id=assessment_id,
            source_type="mastery_rule",
            source_id=str(assessment_id),
            value={"reason": reason, "mastery_change": triggers},
        )
        if not created:
            next_version = (
                LearningPathVersion.query.filter_by(
                    path_id=path.id,
                    reason_event_id=trigger_event.id,
                )
                .order_by(LearningPathVersion.version_number.desc())
                .first()
            )
            return {
                "triggered": bool(next_version),
                "idempotent": True,
                "reason": reason,
                "version": next_version.to_dict(include_nodes=True) if next_version else None,
            }

        path, next_version = StructuredPathService.create_version(
            profile=profile,
            legacy_content=path.content,
            reason_event_id=trigger_event.id,
            replanning_reason=reason,
            remediation_point_ids=[int(item["knowledge_point_id"]) for item in triggers],
        )
        diff = StructuredPathService.diff_versions(
            user_id=profile.user_id,
            from_version_id=current_version.id,
            to_version_id=next_version.id,
        )
        return {
            "triggered": True,
            "idempotent": False,
            "reason": reason,
            "version": next_version.to_dict(include_nodes=True),
            "diff": diff,
        }

    @staticmethod
    def _consecutive_wrong_count(user_id: int, knowledge_point_id: int) -> int:
        events = (
            LearningEvent.query.filter_by(
                user_id=user_id,
                knowledge_point_id=knowledge_point_id,
            )
            .filter(LearningEvent.event_type.in_([
                "question_correct",
                "question_wrong",
                "question_partial",
            ]))
            .order_by(LearningEvent.created_at.desc(), LearningEvent.id.desc())
            .limit(10)
            .all()
        )
        count = 0
        for event in events:
            if event.event_type != "question_wrong":
                break
            count += 1
        return count
