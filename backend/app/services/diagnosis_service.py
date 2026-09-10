from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import func

from ..extensions import db
from ..models import (
    KnowledgeDocument,
    KnowledgePoint,
    KnowledgeRelation,
    LearningEvent,
    LearningPathNode,
    Profile,
    UserKnowledgeMastery,
)
from .path_service import StructuredPathService
from .question_mapping import knowledge_point_candidates


class DiagnosisService:
    """Build a diagnosis strictly from the current user's persisted evidence."""

    STABLE_SCORE = 75.0
    CONSOLIDATE_SCORE = 60.0

    @classmethod
    def build(cls, *, user_id: int, profile: Profile) -> dict[str, Any]:
        points = cls._scoped_points(user_id, profile)
        point_ids = [point.id for point in points]
        masteries = {
            row.knowledge_point_id: row
            for row in UserKnowledgeMastery.query.filter(
                UserKnowledgeMastery.user_id == user_id,
                UserKnowledgeMastery.knowledge_point_id.in_(point_ids or [-1]),
            ).all()
        }
        event_counts = {
            point_id: count
            for point_id, count in (
                db.session.query(
                    LearningEvent.knowledge_point_id,
                    func.count(LearningEvent.id),
                )
                .filter(
                    LearningEvent.user_id == user_id,
                    LearningEvent.knowledge_point_id.in_(point_ids or [-1]),
                )
                .group_by(LearningEvent.knowledge_point_id)
                .all()
            )
        }

        rows = []
        state_counts: Counter[str] = Counter()
        chapter_rows: dict[int, list[dict]] = defaultdict(list)
        assessed_scores = []
        for point in points:
            mastery = masteries.get(point.id)
            state = cls.state_for(mastery)
            score = round(float(mastery.mastery_score), 2) if mastery else None
            confidence = round(float(mastery.confidence), 4) if mastery else 0.0
            row = {
                "knowledge_point_id": point.id,
                "code": point.code,
                "name": point.name,
                "description": point.description or "",
                "difficulty": point.difficulty,
                "course_id": point.course_id,
                "course": point.course.title if point.course else "",
                "chapter_id": point.chapter_id,
                "chapter": point.chapter.title if point.chapter else "",
                "mastery_score": score,
                "confidence": confidence,
                "state": state,
                "attempt_count": mastery.attempt_count if mastery else 0,
                "correct_count": mastery.correct_count if mastery else 0,
                "wrong_count": mastery.wrong_count if mastery else 0,
                "evidence_count": int(event_counts.get(point.id, 0)),
                "updated_at": (
                    mastery.updated_at.isoformat()
                    if mastery and mastery.updated_at
                    else None
                ),
            }
            rows.append(row)
            chapter_rows[point.chapter_id].append(row)
            state_counts[state] += 1
            if score is not None:
                assessed_scores.append(score)

        weaknesses = sorted(
            [row for row in rows if row["state"] in {"focus", "consolidate"}],
            key=lambda row: (
                0 if row["state"] == "focus" else 1,
                row["mastery_score"] if row["mastery_score"] is not None else 101,
                -row["wrong_count"],
                row["knowledge_point_id"],
            ),
        )
        unknown = [row for row in rows if row["state"] == "unknown"]
        ranking = weaknesses + unknown
        recommended = ranking[0] if ranking else (rows[0] if rows else None)

        chapters = []
        for chapter_id, items in chapter_rows.items():
            first = items[0]
            chapters.append({
                "chapter_id": chapter_id,
                "chapter": first["chapter"],
                "course_id": first["course_id"],
                "course": first["course"],
                "knowledge_points": items,
            })
        chapters.sort(
            key=lambda item: (
                item["course_id"],
                min(
                    point.chapter.chapter_order
                    for point in points
                    if point.chapter_id == item["chapter_id"] and point.chapter
                ),
                item["chapter_id"],
            )
        )

        path, version = StructuredPathService.latest_user_path(user_id)
        current_node = cls._current_node(version.nodes if version else [])
        latest_diff = None
        if version and version.parent_version_id:
            latest_diff = StructuredPathService.diff_versions(
                user_id=user_id,
                from_version_id=version.parent_version_id,
                to_version_id=version.id,
            )

        recent_events = (
            LearningEvent.query.filter_by(user_id=user_id)
            .order_by(LearningEvent.created_at.desc(), LearningEvent.id.desc())
            .limit(12)
            .all()
        )
        summary = cls._summary(
            total=len(rows),
            state_counts=state_counts,
            recommended=recommended,
        )
        return {
            "summary": summary,
            "overall": {
                "knowledge_point_count": len(rows),
                "assessed_count": len(assessed_scores),
                "coverage": (
                    round(len(assessed_scores) / len(rows), 4) if rows else 0.0
                ),
                "average_mastery": (
                    round(sum(assessed_scores) / len(assessed_scores), 2)
                    if assessed_scores
                    else None
                ),
                "stable_count": state_counts["stable"],
                "consolidate_count": state_counts["consolidate"],
                "focus_count": state_counts["focus"],
                "unknown_count": state_counts["unknown"],
            },
            "knowledge_map": chapters,
            "weakness_ranking": ranking,
            "recommended_target": recommended,
            "current_path": {
                "id": path.id if path else None,
                "title": path.title if path else "",
                "version_id": version.id if version else None,
                "version_number": version.version_number if version else None,
                "replanning_reason": version.replanning_reason if version else "",
                "current_node": (
                    current_node.to_dict(include_resources=True)
                    if current_node
                    else None
                ),
                "latest_diff": latest_diff,
            },
            "closed_loop": {
                "evidence_events": sum(event_counts.values()),
                "recent_events": [event.to_dict() for event in recent_events],
                "next_action": (
                    f"优先处理“{recommended['name']}”，随后用节点测评验证掌握度变化"
                    if recommended
                    else "先完成一次诊断测评，建立知识点掌握度基线"
                ),
            },
        }

    @classmethod
    def detail(
        cls,
        *,
        user_id: int,
        profile: Profile,
        knowledge_point_id: int,
    ) -> dict[str, Any]:
        allowed_ids = {point.id for point in cls._scoped_points(user_id, profile)}
        if knowledge_point_id not in allowed_ids:
            raise LookupError("知识点不在当前用户的学习范围内")
        point = db.session.get(KnowledgePoint, knowledge_point_id)
        if not point:
            raise LookupError("知识点不存在")

        mastery = UserKnowledgeMastery.query.filter_by(
            user_id=user_id,
            knowledge_point_id=knowledge_point_id,
        ).first()
        events = (
            LearningEvent.query.filter_by(
                user_id=user_id,
                knowledge_point_id=knowledge_point_id,
            )
            .order_by(LearningEvent.created_at.desc(), LearningEvent.id.desc())
            .limit(30)
            .all()
        )
        relations = KnowledgeRelation.query.filter(
            (
                KnowledgeRelation.source_knowledge_point_id == knowledge_point_id
            )
            | (
                KnowledgeRelation.target_knowledge_point_id == knowledge_point_id
            )
        ).all()
        mastery_by_point = {
            row.knowledge_point_id: row
            for row in UserKnowledgeMastery.query.filter(
                UserKnowledgeMastery.user_id == user_id
            ).all()
        }

        prerequisites = []
        dependents = []
        related = []
        for relation in relations:
            if (
                relation.relation_type == "prerequisite"
                and relation.target_knowledge_point_id == knowledge_point_id
            ):
                prerequisites.append(
                    cls._relation_payload(relation.source, mastery_by_point)
                )
            elif (
                relation.relation_type == "prerequisite"
                and relation.source_knowledge_point_id == knowledge_point_id
            ):
                dependents.append(
                    cls._relation_payload(relation.target, mastery_by_point)
                )
            else:
                other = (
                    relation.target
                    if relation.source_knowledge_point_id == knowledge_point_id
                    else relation.source
                )
                item = cls._relation_payload(other, mastery_by_point)
                item["relation_type"] = relation.relation_type
                related.append(item)

        event_types = Counter(event.event_type for event in events)
        score = round(float(mastery.mastery_score), 2) if mastery else None
        state = cls.state_for(mastery)
        reasons = []
        if mastery:
            reasons.append(
                f"共作答 {mastery.attempt_count} 次，其中错误 {mastery.wrong_count} 次"
            )
            reasons.append(
                f"当前掌握度 {score}%，证据置信度 {round(float(mastery.confidence) * 100)}%"
            )
        else:
            reasons.append("尚无该知识点的答题或学习证据")
        weak_prerequisites = [
            item
            for item in prerequisites
            if item["mastery_score"] is None or item["mastery_score"] < cls.CONSOLIDATE_SCORE
        ]
        if weak_prerequisites:
            reasons.append(
                "存在薄弱先修知识："
                + "、".join(item["name"] for item in weak_prerequisites)
            )

        return {
            "knowledge_point": point.to_dict(),
            "mastery": (
                mastery.to_dict(include_evidence=True)
                if mastery
                else {
                    "knowledge_point_id": point.id,
                    "knowledge_point": point.name,
                    "mastery_score": None,
                    "confidence": 0.0,
                    "state": "unassessed",
                    "evidence": [],
                }
            ),
            "diagnosis_state": state,
            "reasons": reasons,
            "event_summary": dict(event_types),
            "recent_events": [event.to_dict() for event in events[:12]],
            "prerequisites": prerequisites,
            "weak_prerequisites": weak_prerequisites,
            "dependents": dependents,
            "related": related,
            "recommendations": cls._recommendations(
                point.name,
                state,
                weak_prerequisites,
            ),
        }

    @classmethod
    def state_for(cls, mastery: UserKnowledgeMastery | None) -> str:
        if not mastery or mastery.attempt_count == 0:
            return "unknown"
        score = float(mastery.mastery_score)
        if score >= cls.STABLE_SCORE:
            return "stable"
        if score >= cls.CONSOLIDATE_SCORE:
            return "consolidate"
        return "focus"

    @staticmethod
    def _scoped_points(user_id: int, profile: Profile) -> list[KnowledgePoint]:
        points = knowledge_point_candidates(profile.topic)
        document_course_ids = {
            course_id
            for (course_id,) in (
                db.session.query(KnowledgeDocument.course_id)
                .filter(
                    KnowledgeDocument.user_id == user_id,
                    KnowledgeDocument.course_id.isnot(None),
                )
                .distinct()
                .all()
            )
            if course_id
        }
        if document_course_ids:
            scoped = [point for point in points if point.course_id in document_course_ids]
            if scoped:
                return scoped
        return points

    @staticmethod
    def _current_node(nodes: list[LearningPathNode]) -> LearningPathNode | None:
        for status in ("learning", "remediation", "ready"):
            node = next((item for item in nodes if item.status == status), None)
            if node:
                return node
        return next((item for item in nodes if item.status != "completed"), None)

    @staticmethod
    def _relation_payload(
        point: KnowledgePoint,
        mastery_by_point: dict[int, UserKnowledgeMastery],
    ) -> dict:
        mastery = mastery_by_point.get(point.id)
        return {
            "knowledge_point_id": point.id,
            "code": point.code,
            "name": point.name,
            "mastery_score": (
                round(float(mastery.mastery_score), 2) if mastery else None
            ),
            "confidence": (
                round(float(mastery.confidence), 4) if mastery else 0.0
            ),
        }

    @staticmethod
    def _summary(
        *,
        total: int,
        state_counts: Counter[str],
        recommended: dict | None,
    ) -> str:
        if not total:
            return "当前课程还没有可诊断的知识点，请先导入课程资料。"
        if recommended:
            return (
                f"已分析 {total} 个知识点：{state_counts['stable']} 个稳定掌握，"
                f"{state_counts['focus']} 个需要重点补强。下一步建议学习"
                f"“{recommended['name']}”。"
            )
        return f"已分析 {total} 个知识点，当前没有明显薄弱项。"

    @staticmethod
    def _recommendations(
        point_name: str,
        state: str,
        weak_prerequisites: list[dict],
    ) -> list[str]:
        recommendations = []
        if weak_prerequisites:
            recommendations.append(
                "先复习先修知识："
                + "、".join(item["name"] for item in weak_prerequisites)
            )
        if state == "unknown":
            recommendations.append(f"先完成“{point_name}”诊断题以建立掌握度基线")
        elif state == "focus":
            recommendations.append(f"学习“{point_name}”补救材料并完成即时练习")
        elif state == "consolidate":
            recommendations.append(f"通过变式练习巩固“{point_name}”")
        else:
            recommendations.append(f"保持“{point_name}”的间隔复习")
        recommendations.append("完成节点测评后根据新证据自动更新掌握度")
        return recommendations
