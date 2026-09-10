from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from ..extensions import db
from ..models import (
    AgentRun,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgePoint,
    KnowledgeRelation,
    Profile,
    RemediationPlan,
    RemediationPlanStep,
    UserKnowledgeMastery,
)
from .agent_trace_service import AgentTraceService
from .diagnosis_service import DiagnosisService
from .learning_event_service import LearningEventService
from .path_service import StructuredPathService


class RemediationService:
    @classmethod
    def create(
        cls,
        *,
        user_id: int,
        profile: Profile,
        knowledge_point_id: int | None = None,
    ) -> dict[str, Any]:
        diagnosis = DiagnosisService.build(user_id=user_id, profile=profile)
        recommended = diagnosis.get("recommended_target")
        target_id = knowledge_point_id or (
            recommended["knowledge_point_id"] if recommended else None
        )
        if not target_id:
            raise ValueError("当前没有可补救的知识点，请先完成诊断测评")

        existing = (
            RemediationPlan.query.filter(
                RemediationPlan.user_id == user_id,
                RemediationPlan.target_knowledge_point_id == target_id,
                RemediationPlan.status.in_(["ready", "active"]),
            )
            .order_by(RemediationPlan.created_at.desc(), RemediationPlan.id.desc())
            .first()
        )
        if existing:
            return {
                "plan": existing.to_dict(include_steps=True),
                "path_version": (
                    existing.path_version.to_dict(include_nodes=True)
                    if existing.path_version
                    else None
                ),
                "diff": cls._plan_diff(user_id, existing),
                "agent_run": (
                    existing.agent_run.to_dict(include_steps=True)
                    if existing.agent_run
                    else None
                ),
                "reused": True,
            }

        target = db.session.get(KnowledgePoint, target_id)
        if not target:
            raise LookupError("知识点不存在")
        run = AgentTraceService.start(
            user_id=user_id,
            task_type="remediation_plan",
            input_data={"knowledge_point_id": target_id},
        )
        db.session.commit()
        try:
            detail = DiagnosisService.detail(
                user_id=user_id,
                profile=profile,
                knowledge_point_id=target_id,
            )
            AgentTraceService.record_step(
                run,
                agent_name="Diagnostician",
                action="读取掌握度、错题和先修关系",
                input_data={"knowledge_point_id": target_id},
                output_data={
                    "state": detail["diagnosis_state"],
                    "reasons": detail["reasons"],
                },
                evidence_count=sum(detail["event_summary"].values()),
            )

            prerequisite_ids = cls._weak_prerequisites(user_id, target_id)
            ordered_point_ids = [*prerequisite_ids, target_id]
            AgentTraceService.record_step(
                run,
                agent_name="Planner",
                action="依据先修关系生成补救顺序",
                input_data={"target_knowledge_point_id": target_id},
                output_data={
                    "ordered_knowledge_point_ids": ordered_point_ids,
                    "prerequisite_count": len(prerequisite_ids),
                },
                evidence_count=len(prerequisite_ids),
            )

            source_count = cls._grounding_source_count(
                user_id,
                ordered_point_ids,
            )
            AgentTraceService.record_step(
                run,
                agent_name="Retriever",
                action="检索当前用户知识库中的真实课程片段",
                input_data={"knowledge_point_ids": ordered_point_ids},
                output_data={"matched_chunk_count": source_count},
                evidence_count=source_count,
                status="passed" if source_count else "revised",
            )

            path, current_version = StructuredPathService.latest_user_path(user_id)
            if not path or not current_version:
                path, current_version = StructuredPathService.create_version(
                    profile=profile,
                    legacy_content="",
                    replanning_reason="根据画像和课程知识结构生成初始学习路径",
                )
            reason = cls._reason(detail, prerequisite_ids)
            trigger_event, _ = LearningEventService.record_event(
                user_id=user_id,
                event_type="replan_trigger",
                event_key=f"remediation:{uuid.uuid4().hex}",
                knowledge_point_id=target_id,
                path_id=path.id,
                path_version_id=current_version.id,
                source_type="manual_remediation",
                source_id=str(target_id),
                value={
                    "reason": reason,
                    "knowledge_point_ids": ordered_point_ids,
                },
            )
            _, next_version = StructuredPathService.create_version(
                profile=profile,
                legacy_content=path.content,
                reason_event_id=trigger_event.id,
                replanning_reason=reason,
                remediation_point_ids=ordered_point_ids,
                remediation_only=True,
            )
            AgentTraceService.record_step(
                run,
                agent_name="Generator",
                action="创建可执行补救节点和路径新版本",
                input_data={
                    "from_version_id": current_version.id,
                    "knowledge_point_ids": ordered_point_ids,
                },
                output_data={
                    "path_version_id": next_version.id,
                    "node_count": len(next_version.nodes),
                },
                evidence_count=len(next_version.nodes),
            )

            resource_count = sum(len(node.resources) for node in next_version.nodes)
            verified = bool(next_version.nodes) and resource_count == len(
                next_version.nodes
            )
            AgentTraceService.record_step(
                run,
                agent_name="Verifier",
                action="校验节点顺序、课程资源绑定和复测闭环",
                input_data={"path_version_id": next_version.id},
                output_data={
                    "node_count": len(next_version.nodes),
                    "bound_resource_count": resource_count,
                    "has_assessment": any(
                        node.node_type == "assessment"
                        for node in next_version.nodes
                    ),
                    "verified": verified,
                },
                evidence_count=resource_count,
                status="passed" if verified else "revised",
            )

            target_mastery = UserKnowledgeMastery.query.filter_by(
                user_id=user_id,
                knowledge_point_id=target_id,
            ).first()
            plan = RemediationPlan(
                user_id=user_id,
                target_knowledge_point_id=target_id,
                path_version_id=next_version.id,
                agent_run_id=run.id,
                status="ready",
                initial_mastery=(
                    target_mastery.mastery_score if target_mastery else None
                ),
                target_mastery=70.0,
                estimated_minutes=sum(
                    node.estimated_minutes for node in next_version.nodes
                ),
                reason=reason,
            )
            db.session.add(plan)
            db.session.flush()
            for node in next_version.nodes:
                db.session.add(RemediationPlanStep(
                    plan_id=plan.id,
                    node_id=node.id,
                    step_order=node.node_order,
                    step_type=node.node_type,
                    title=(
                        f"{'复测' if node.node_type == 'assessment' else '补救'}："
                        f"{node.knowledge_point.name if node.knowledge_point else '学习节点'}"
                    ),
                    estimated_minutes=node.estimated_minutes,
                    reason=node.reason,
                ))

            diff = StructuredPathService.diff_versions(
                user_id=user_id,
                from_version_id=current_version.id,
                to_version_id=next_version.id,
            )
            AgentTraceService.finish(
                run,
                output_data={
                    "plan_id": plan.id,
                    "path_version_id": next_version.id,
                    "verified": verified,
                },
                status="passed" if verified else "revised",
            )
            db.session.commit()
            return {
                "plan": plan.to_dict(include_steps=True),
                "path_version": next_version.to_dict(include_nodes=True),
                "diff": diff,
                "agent_run": run.to_dict(include_steps=True),
                "reused": False,
            }
        except Exception as exc:
            run_id = run.id
            db.session.rollback()
            persisted_run = db.session.get(AgentRun, run_id)
            AgentTraceService.fail(persisted_run, exc)
            db.session.commit()
            raise

    @classmethod
    def start(cls, *, user_id: int, plan_id: int) -> dict:
        plan = RemediationPlan.query.filter_by(
            id=plan_id,
            user_id=user_id,
        ).first()
        if not plan:
            raise LookupError("补救计划不存在")
        if not plan.steps:
            raise ValueError("补救计划没有可执行步骤")
        first_incomplete = next(
            (
                step
                for step in plan.steps
                if step.node and step.node.status != "completed"
            ),
            None,
        )
        if not first_incomplete or not first_incomplete.node:
            plan.status = "completed"
            plan.completed_at = datetime.utcnow()
            db.session.commit()
            return {"plan": plan.to_dict(), "current_node": None}
        node, event, created = StructuredPathService.open_node(
            user_id=user_id,
            node_id=first_incomplete.node.id,
        )
        plan.status = "active"
        db.session.commit()
        return {
            "plan": plan.to_dict(include_steps=True),
            "current_node": node.to_dict(include_resources=True),
            "event": event.to_dict(),
            "event_created": created,
        }

    @staticmethod
    def list_user(user_id: int) -> list[dict]:
        plans = (
            RemediationPlan.query.filter_by(user_id=user_id)
            .order_by(
                RemediationPlan.created_at.desc(),
                RemediationPlan.id.desc(),
            )
            .limit(30)
            .all()
        )
        changed = False
        for plan in plans:
            current = UserKnowledgeMastery.query.filter_by(
                user_id=user_id,
                knowledge_point_id=plan.target_knowledge_point_id,
            ).first()
            if (
                plan.status != "completed"
                and current
                and current.mastery_score >= plan.target_mastery
            ):
                plan.status = "completed"
                plan.completed_at = datetime.utcnow()
                changed = True
        if changed:
            db.session.commit()
        return [plan.to_dict(include_steps=True) for plan in plans]

    @staticmethod
    def _weak_prerequisites(user_id: int, target_id: int) -> list[int]:
        masteries = {
            row.knowledge_point_id: row
            for row in UserKnowledgeMastery.query.filter_by(user_id=user_id).all()
        }
        ordered = []
        visited = set()

        def visit(point_id: int) -> None:
            relations = (
                KnowledgeRelation.query.filter_by(
                    target_knowledge_point_id=point_id,
                    relation_type="prerequisite",
                )
                .order_by(KnowledgeRelation.id)
                .all()
            )
            for relation in relations:
                source_id = relation.source_knowledge_point_id
                if source_id in visited:
                    continue
                visited.add(source_id)
                visit(source_id)
                mastery = masteries.get(source_id)
                if not mastery or mastery.mastery_score < 60:
                    ordered.append(source_id)

        visit(target_id)
        return ordered

    @staticmethod
    def _grounding_source_count(
        user_id: int,
        point_ids: list[int],
    ) -> int:
        points = KnowledgePoint.query.filter(
            KnowledgePoint.id.in_(point_ids or [-1])
        ).all()
        course_ids = {point.course_id for point in points}
        chapter_ids = {point.chapter_id for point in points}
        return (
            KnowledgeChunk.query.join(KnowledgeDocument)
            .filter(
                KnowledgeDocument.user_id == user_id,
                (
                    KnowledgeChunk.knowledge_point_id.in_(point_ids or [-1])
                    | KnowledgeChunk.chapter_id.in_(chapter_ids or [-1])
                    | KnowledgeChunk.course_id.in_(course_ids or [-1])
                ),
            )
            .count()
        )

    @staticmethod
    def _reason(detail: dict, prerequisite_ids: list[int]) -> str:
        mastery = detail["mastery"].get("mastery_score")
        base = (
            f"“{detail['knowledge_point']['name']}”当前掌握度 "
            f"{mastery if mastery is not None else '未测评'}，"
            f"诊断状态为 {detail['diagnosis_state']}"
        )
        if prerequisite_ids:
            return f"{base}；检测到 {len(prerequisite_ids)} 个薄弱先修知识点"
        return f"{base}；直接安排课程材料、练习和节点复测"

    @staticmethod
    def _plan_diff(user_id: int, plan: RemediationPlan) -> dict | None:
        version = plan.path_version
        if not version or not version.parent_version_id:
            return None
        return StructuredPathService.diff_versions(
            user_id=user_id,
            from_version_id=version.parent_version_id,
            to_version_id=version.id,
        )
