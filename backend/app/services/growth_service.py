from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from ..models import (
    LearningEvent,
    LearningPath,
    LearningPathVersion,
    MasteryEvidence,
    QuizResult,
    RemediationPlan,
    UserKnowledgeMastery,
)
from .intervention_service import LearningInterventionService, TeachingEffectService
from .teaching_strategy_service import TeachingStrategyEngine
from .transfer_service import (
    CapabilityGateService,
    MasteryDimensionService,
    MetacognitiveCalibrationService,
)


class GrowthService:
    @classmethod
    def build(
        cls,
        *,
        user_id: int,
        period_days: int | None = 30,
    ) -> dict[str, Any]:
        since = (
            datetime.utcnow() - timedelta(days=period_days)
            if period_days
            else None
        )
        mastery_rows = (
            UserKnowledgeMastery.query.filter_by(user_id=user_id)
            .order_by(UserKnowledgeMastery.knowledge_point_id)
            .all()
        )
        mastery_ids = [row.id for row in mastery_rows]
        evidence_query = MasteryEvidence.query.filter(
            MasteryEvidence.mastery_id.in_(mastery_ids or [-1])
        )
        if since:
            evidence_query = evidence_query.filter(
                MasteryEvidence.created_at >= since
            )
        evidence_rows = evidence_query.order_by(
            MasteryEvidence.created_at,
            MasteryEvidence.id,
        ).all()
        evidence_by_mastery: dict[int, list[MasteryEvidence]] = {}
        for evidence in evidence_rows:
            evidence_by_mastery.setdefault(evidence.mastery_id, []).append(evidence)

        knowledge_growth = []
        for mastery in mastery_rows:
            rows = evidence_by_mastery.get(mastery.id, [])
            current = round(float(mastery.mastery_score), 2)
            initial = round(float(rows[0].old_score), 2) if rows else current
            timeline = [
                {
                    "event_id": row.event_id,
                    "score": round(float(row.new_score), 2),
                    "delta": round(float(row.delta), 2),
                    "evidence_type": row.evidence_type,
                    "description": row.description or "",
                    "created_at": (
                        row.created_at.isoformat() if row.created_at else None
                    ),
                }
                for row in rows
            ]
            capability = CapabilityGateService.evaluate(
                user_id=user_id,
                knowledge_point_id=mastery.knowledge_point_id,
            )
            knowledge_growth.append({
                "knowledge_point_id": mastery.knowledge_point_id,
                "knowledge_point": (
                    mastery.knowledge_point.name
                    if mastery.knowledge_point
                    else ""
                ),
                "initial_mastery": initial,
                "current_mastery": current,
                "improvement": round(current - initial, 2),
                "confidence": round(float(mastery.confidence), 4),
                "attempt_count": mastery.attempt_count,
                "timeline": timeline,
                "dimensions": MasteryDimensionService.get_dimensions(
                    user_id,
                    mastery.knowledge_point_id,
                ),
                "capability": capability,
            })
        knowledge_growth.sort(
            key=lambda item: (
                -item["improvement"],
                item["current_mastery"],
                item["knowledge_point_id"],
            )
        )

        event_query = LearningEvent.query.filter_by(user_id=user_id)
        if since:
            event_query = event_query.filter(LearningEvent.created_at >= since)
        events = event_query.order_by(
            LearningEvent.created_at,
            LearningEvent.id,
        ).all()
        event_counts = Counter(event.event_type for event in events)
        answer_events = [
            event
            for event in events
            if event.event_type in {
                "question_correct",
                "question_wrong",
                "question_partial",
            }
        ]
        correct_weight = sum(
            1.0 if event.event_type == "question_correct" else
            0.5 if event.event_type == "question_partial" else 0.0
            for event in answer_events
        )
        improvement_values = [
            item["improvement"]
            for item in knowledge_growth
            if item["timeline"]
        ]
        remediation_plans = RemediationPlan.query.filter_by(user_id=user_id).all()
        completed_plans = [
            plan
            for plan in remediation_plans
            if plan.status == "completed"
            or (
                plan.to_dict(include_steps=False).get("current_mastery") is not None
                and plan.to_dict(include_steps=False)["current_mastery"]
                >= plan.target_mastery
            )
        ]

        path_ids = [
            path_id
            for (path_id,) in LearningPath.query.with_entities(LearningPath.id)
            .filter_by(user_id=user_id)
            .all()
        ]
        version_query = LearningPathVersion.query.filter(
            LearningPathVersion.path_id.in_(path_ids or [-1])
        )
        if since:
            version_query = version_query.filter(
                LearningPathVersion.created_at >= since
            )
        version_count = version_query.count()

        quiz_query = QuizResult.query.filter_by(user_id=user_id)
        if since:
            quiz_query = quiz_query.filter(QuizResult.created_at >= since)
        quizzes = [
            result
            for result in quiz_query.order_by(QuizResult.created_at).all()
            if isinstance(result.answers, dict) and result.answers.get("submitted")
        ]
        score_trend = [
            {
                "result_id": result.id,
                "score": round(float(result.score or 0), 2),
                "category": result.category,
                "created_at": (
                    result.created_at.isoformat() if result.created_at else None
                ),
            }
            for result in quizzes
        ]

        highlights = cls._highlights(
            knowledge_growth=knowledge_growth,
            answer_count=len(answer_events),
            accuracy=(
                round(correct_weight / len(answer_events) * 100, 2)
                if answer_events
                else None
            ),
            completed_plans=len(completed_plans),
        )
        current_strategy = TeachingStrategyEngine.current(user_id)
        current_intervention = LearningInterventionService.current(user_id)
        return {
            "period_days": period_days,
            "period_start": since.isoformat() if since else None,
            "generated_at": datetime.utcnow().isoformat(),
            "metrics": {
                "learning_event_count": len(events),
                "question_count": len(answer_events),
                "accuracy": (
                    round(correct_weight / len(answer_events) * 100, 2)
                    if answer_events
                    else None
                ),
                "assessment_count": event_counts["assessment_complete"],
                "completed_node_count": len({
                    event.node_id
                    for event in events
                    if event.event_type == "node_complete" and event.node_id
                }),
                "completed_resource_count": len({
                    event.resource_id
                    for event in events
                    if event.event_type == "resource_complete"
                    and event.resource_id
                }),
                "average_mastery_improvement": (
                    round(
                        sum(improvement_values) / len(improvement_values),
                        2,
                    )
                    if improvement_values
                    else 0.0
                ),
                "improved_knowledge_point_count": sum(
                    1 for value in improvement_values if value > 0
                ),
                "remediation_plan_count": len(remediation_plans),
                "completed_remediation_count": len(completed_plans),
                "path_version_count": version_count,
                "replan_count": event_counts["replan_trigger"],
            },
            "knowledge_growth": knowledge_growth,
            "score_trend": score_trend,
            "event_distribution": dict(event_counts),
            "current_strategy": TeachingStrategyEngine.payload(current_strategy),
            "current_intervention": (
                current_intervention.to_dict()
                if current_intervention
                else None
            ),
            "interventions": LearningInterventionService.list_user(
                user_id,
                limit=20,
            ),
            "strategy_response": TeachingEffectService.strategy_response(
                user_id
            ),
            "metacognitive_calibration": (
                MetacognitiveCalibrationService.report(user_id)
            ),
            "highlights": highlights,
            "report": "；".join(highlights),
        }

    @staticmethod
    def _highlights(
        *,
        knowledge_growth: list[dict],
        answer_count: int,
        accuracy: float | None,
        completed_plans: int,
    ) -> list[str]:
        highlights = []
        improved = [item for item in knowledge_growth if item["improvement"] > 0]
        if improved:
            top = improved[0]
            highlights.append(
                f"“{top['knowledge_point']}”掌握度提升 "
                f"{top['improvement']} 个百分点"
            )
        if answer_count:
            highlights.append(
                f"完成 {answer_count} 次知识点作答，综合正确率 {accuracy}%"
            )
        if completed_plans:
            highlights.append(f"已有 {completed_plans} 个补救计划达到目标")
        if not highlights:
            highlights.append("当前周期学习证据较少，完成一次测评后即可生成成长对比")
        return highlights
