from __future__ import annotations

import uuid
from datetime import datetime
from statistics import pvariance
from typing import Any

from ..extensions import db
from ..models import (
    CognitiveDiagnosis,
    KnowledgeRelation,
    LearningEvent,
    Profile,
    QuizResult,
    TeachingIntervention,
    TeachingStrategyDecision,
    TeachingStrategyStat,
    UserKnowledgeMastery,
    UserMisconception,
)
from .learning_event_service import LearningEventService
from .path_service import StructuredPathService
from .teaching_strategy_service import STRATEGY_LABELS


class TeachingEffectService:
    @classmethod
    def observe_after_assessment(
        cls,
        *,
        user_id: int,
        record: QuizResult,
        mastery_changes: list[dict],
    ) -> list[TeachingIntervention]:
        change_by_point = {
            int(change["knowledge_point_id"]): change
            for change in mastery_changes
        }
        if not change_by_point:
            return []
        rows = (
            TeachingIntervention.query.filter(
                TeachingIntervention.user_id == user_id,
                TeachingIntervention.status == "active",
                TeachingIntervention.knowledge_point_id.in_(
                    list(change_by_point)
                ),
                TeachingIntervention.assessment_before != record.id,
            )
            .order_by(TeachingIntervention.started_at)
            .all()
        )
        completed = []
        for row in rows:
            mastery = UserKnowledgeMastery.query.filter_by(
                user_id=user_id,
                knowledge_point_id=row.knowledge_point_id,
            ).first()
            if not mastery:
                continue
            row.mastery_after = mastery.mastery_score
            row.confidence_after = mastery.confidence
            row.assessment_after = record.id
            row.observed_gain = round(
                float(row.mastery_after)
                - float(row.mastery_before or row.mastery_after),
                4,
            )
            row.status = "completed"
            row.finished_at = datetime.utcnow()
            completed.append(row)
        for strategy_type in {row.strategy_type for row in completed}:
            cls._refresh_strategy_stat(user_id, strategy_type)
        db.session.flush()
        return completed

    @staticmethod
    def _refresh_strategy_stat(user_id: int, strategy_type: str) -> None:
        interventions = TeachingIntervention.query.filter_by(
            user_id=user_id,
            strategy_type=strategy_type,
        ).all()
        completed = [
            row
            for row in interventions
            if row.status == "completed" and row.observed_gain is not None
        ]
        gains = [float(row.observed_gain) for row in completed]
        stat = TeachingStrategyStat.query.filter_by(
            user_id=user_id,
            strategy_type=strategy_type,
        ).first()
        if not stat:
            stat = TeachingStrategyStat(
                user_id=user_id,
                strategy_type=strategy_type,
            )
            db.session.add(stat)
        stat.use_count = len(interventions)
        stat.completed_count = len(completed)
        stat.average_observed_gain = (
            round(sum(gains) / len(gains), 4) if gains else 0.0
        )
        stat.gain_variance = (
            round(pvariance(gains), 4) if len(gains) > 1 else 0.0
        )
        stat.confidence = round(
            len(completed) / (len(completed) + 3.0),
            4,
        )
        if len(completed) < 3:
            stat.stability = "insufficient"
        elif stat.gain_variance <= 16:
            stat.stability = "high"
        elif stat.gain_variance <= 49:
            stat.stability = "medium"
        else:
            stat.stability = "low"

    @staticmethod
    def strategy_response(user_id: int) -> list[dict]:
        rows = (
            TeachingStrategyStat.query.filter_by(user_id=user_id)
            .order_by(
                TeachingStrategyStat.completed_count.desc(),
                TeachingStrategyStat.average_observed_gain.desc(),
            )
            .all()
        )
        result = []
        for row in rows:
            payload = row.to_dict()
            payload["strategy_label"] = STRATEGY_LABELS.get(
                row.strategy_type,
                row.strategy_type,
            )
            payload["statement"] = (
                f"完成 {row.completed_count} 次该策略干预后，"
                f"后续测评平均观察到 Mastery 变化 "
                f"{row.average_observed_gain:+.2f} 个百分点"
                if row.completed_count
                else "尚无干预后的测评证据"
            )
            result.append(payload)
        return result


class LearningInterventionService:
    CONSECUTIVE_WRONG_THRESHOLD = 3
    SIGNIFICANT_DROP = -10.0

    @classmethod
    def maybe_trigger(
        cls,
        *,
        user_id: int,
        profile: Profile,
        record: QuizResult,
        mastery_changes: list[dict],
        cognitive_diagnoses: list[CognitiveDiagnosis],
        misconceptions: list[UserMisconception],
        strategy_decision: TeachingStrategyDecision,
    ) -> dict[str, Any]:
        target_id = strategy_decision.knowledge_point_id
        if not target_id:
            return {"triggered": False, "reason": "没有可干预的知识点"}
        change = next(
            (
                item
                for item in mastery_changes
                if int(item["knowledge_point_id"]) == target_id
            ),
            None,
        )
        consecutive_wrong = cls._consecutive_wrong_count(
            user_id,
            target_id,
        )
        confirmed = any(
            item.status == "confirmed"
            and item.misconception.knowledge_point_id == target_id
            for item in misconceptions
        )
        process_error = any(
            item.root_cause_knowledge_point_id == target_id
            and item.overall_status == "root_error"
            for item in cognitive_diagnoses
        )
        block_type = None
        evidence = {}
        if confirmed:
            block_type = "MISCONCEPTION"
            evidence["confirmed_misconception"] = True
        elif consecutive_wrong >= cls.CONSECUTIVE_WRONG_THRESHOLD:
            block_type = "REPEATED_FAILURE"
            evidence["consecutive_wrong"] = consecutive_wrong
        elif change and float(change.get("delta") or 0) <= cls.SIGNIFICANT_DROP:
            block_type = "KNOWLEDGE_GAP"
            evidence["mastery_change"] = change
        elif process_error and consecutive_wrong >= 2:
            block_type = "PROCESS_ERROR"
            evidence["first_error_step"] = next(
                (
                    item.first_error_step
                    for item in cognitive_diagnoses
                    if item.root_cause_knowledge_point_id == target_id
                ),
                None,
            )
        if not block_type:
            return {
                "triggered": False,
                "reason": "当前 Evidence 未达到主动干预阈值",
                "evidence": {
                    "consecutive_wrong": consecutive_wrong,
                    "confirmed_misconception": confirmed,
                    "process_error": process_error,
                },
            }

        existing = (
            TeachingIntervention.query.filter_by(
                user_id=user_id,
                knowledge_point_id=target_id,
                status="active",
            )
            .order_by(TeachingIntervention.started_at.desc())
            .first()
        )
        if existing:
            return {
                "triggered": True,
                "reused": True,
                "reason": "已有进行中的教学干预",
                "intervention": existing.to_dict(),
                "path_diff": cls._path_diff(user_id, existing),
                "evidence": evidence,
            }

        path, current_version = StructuredPathService.latest_user_path(user_id)
        if not path or not current_version:
            path, current_version = StructuredPathService.create_version(
                profile=profile,
                legacy_content="",
                replanning_reason="根据画像和课程知识结构生成初始路径",
            )
        mastery = UserKnowledgeMastery.query.filter_by(
            user_id=user_id,
            knowledge_point_id=target_id,
        ).first()
        reason = (
            f"检测到 {block_type}；当前策略切换为 "
            f"{STRATEGY_LABELS.get(strategy_decision.strategy_type, strategy_decision.strategy_type)}；"
            f"依据：{evidence}"
        )
        trigger_event, _ = LearningEventService.record_event(
            user_id=user_id,
            event_type="learning_block_detected",
            event_key=f"intervention:{record.id}:{target_id}",
            knowledge_point_id=target_id,
            path_id=path.id,
            path_version_id=current_version.id,
            assessment_id=record.id,
            source_type="learning_intervention_rule",
            source_id=str(record.id),
            value={
                "block_type": block_type,
                "strategy": strategy_decision.strategy_type,
                "evidence": evidence,
            },
        )
        point_ids = [
            *cls._weak_prerequisites(user_id, target_id),
            target_id,
        ]
        _, next_version = StructuredPathService.create_version(
            profile=profile,
            legacy_content=path.content,
            reason_event_id=trigger_event.id,
            replanning_reason=reason,
            remediation_point_ids=point_ids,
            remediation_only=True,
        )
        target_node = next(
            (
                node
                for node in next_version.nodes
                if node.knowledge_point_id == target_id
                and node.node_type == "remediation"
            ),
            next_version.nodes[0] if next_version.nodes else None,
        )
        resource_binding = (
            target_node.resources[0]
            if target_node and target_node.resources
            else None
        )
        intervention = TeachingIntervention(
            user_id=user_id,
            knowledge_point_id=target_id,
            strategy_decision_id=strategy_decision.id,
            resource_id=(
                resource_binding.resource_id if resource_binding else None
            ),
            path_node_id=target_node.id if target_node else None,
            path_version_id=next_version.id,
            trigger_event_id=trigger_event.id,
            assessment_before=record.id,
            strategy_type=strategy_decision.strategy_type,
            block_type=block_type,
            status="active",
            mastery_before=mastery.mastery_score if mastery else None,
            confidence_before=mastery.confidence if mastery else 0.0,
        )
        db.session.add(intervention)
        db.session.flush()
        TeachingEffectService._refresh_strategy_stat(
            user_id,
            strategy_decision.strategy_type,
        )
        diff = StructuredPathService.diff_versions(
            user_id=user_id,
            from_version_id=current_version.id,
            to_version_id=next_version.id,
        )
        return {
            "triggered": True,
            "reused": False,
            "reason": reason,
            "block_type": block_type,
            "evidence": evidence,
            "intervention": intervention.to_dict(),
            "path_version": next_version.to_dict(include_nodes=True),
            "path_diff": diff,
        }

    @staticmethod
    def list_user(user_id: int, limit: int = 30) -> list[dict]:
        rows = (
            TeachingIntervention.query.filter_by(user_id=user_id)
            .order_by(
                TeachingIntervention.started_at.desc(),
                TeachingIntervention.id.desc(),
            )
            .limit(max(1, min(limit, 100)))
            .all()
        )
        return [row.to_dict() for row in rows]

    @staticmethod
    def current(user_id: int) -> TeachingIntervention | None:
        return (
            TeachingIntervention.query.filter_by(
                user_id=user_id,
                status="active",
            )
            .order_by(
                TeachingIntervention.started_at.desc(),
                TeachingIntervention.id.desc(),
            )
            .first()
        )

    @staticmethod
    def _consecutive_wrong_count(user_id: int, point_id: int) -> int:
        events = (
            LearningEvent.query.filter_by(
                user_id=user_id,
                knowledge_point_id=point_id,
            )
            .filter(
                LearningEvent.event_type.in_([
                    "question_correct",
                    "question_wrong",
                    "question_partial",
                ])
            )
            .order_by(LearningEvent.created_at.desc(), LearningEvent.id.desc())
            .limit(12)
            .all()
        )
        count = 0
        for event in events:
            if event.event_type != "question_wrong":
                break
            count += 1
        return count

    @staticmethod
    def _weak_prerequisites(user_id: int, target_id: int) -> list[int]:
        relations = KnowledgeRelation.query.filter_by(
            target_knowledge_point_id=target_id,
            relation_type="prerequisite",
        ).all()
        mastery = {
            row.knowledge_point_id: row
            for row in UserKnowledgeMastery.query.filter(
                UserKnowledgeMastery.user_id == user_id,
                UserKnowledgeMastery.knowledge_point_id.in_(
                    [relation.source_knowledge_point_id for relation in relations]
                    or [-1]
                ),
            ).all()
        }
        return [
            relation.source_knowledge_point_id
            for relation in relations
            if (
                relation.source_knowledge_point_id not in mastery
                or mastery[relation.source_knowledge_point_id].mastery_score < 60
            )
        ]

    @staticmethod
    def _path_diff(
        user_id: int,
        intervention: TeachingIntervention,
    ) -> dict | None:
        version = intervention.path_version
        if not version or not version.parent_version_id:
            return None
        return StructuredPathService.diff_versions(
            user_id=user_id,
            from_version_id=version.parent_version_id,
            to_version_id=version.id,
        )
