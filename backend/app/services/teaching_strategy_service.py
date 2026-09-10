from __future__ import annotations

from collections import Counter
from typing import Any

from ..extensions import db
from ..models import (
    CognitiveDiagnosis,
    KnowledgeRelation,
    LearningEvent,
    MasteryDimension,
    Misconception,
    Profile,
    TeachingStrategyDecision,
    TeachingStrategyStat,
    UserKnowledgeMastery,
    UserMisconception,
)
from .diagnosis_service import DiagnosisService


STRATEGY_LABELS = {
    "FOUNDATION_REBUILD": "基础重构",
    "CONCEPT_CORRECTION": "概念纠错",
    "VISUAL_EXPLANATION": "图解讲解",
    "SOCRATIC_GUIDANCE": "苏格拉底引导",
    "WORKED_EXAMPLE": "例题拆解",
    "DELIBERATE_PRACTICE": "专项刻意练习",
    "TRANSFER_TRAINING": "迁移训练",
    "REVIEW_REFRESH": "快速复习",
}

STRATEGY_ACTIONS = {
    "FOUNDATION_REBUILD": [
        "pause_high_difficulty",
        "insert_prerequisite_review",
        "add_foundation_example",
        "add_micro_assessment",
    ],
    "CONCEPT_CORRECTION": [
        "pause_high_difficulty",
        "insert_concept_explanation",
        "add_contrast_example",
        "add_micro_assessment",
    ],
    "VISUAL_EXPLANATION": [
        "insert_visual_explanation",
        "add_concept_map",
        "reduce_abstract_text",
        "add_micro_assessment",
    ],
    "SOCRATIC_GUIDANCE": [
        "reduce_direct_answer",
        "ask_small_step_questions",
        "check_reasoning_chain",
        "add_reflection",
    ],
    "WORKED_EXAMPLE": [
        "insert_worked_example",
        "annotate_each_step",
        "add_faded_example",
        "add_process_check",
    ],
    "DELIBERATE_PRACTICE": [
        "add_targeted_variations",
        "increase_feedback_frequency",
        "track_error_pattern",
        "add_mastery_check",
    ],
    "TRANSFER_TRAINING": [
        "add_new_context_problem",
        "add_variation_problem",
        "require_strategy_explanation",
        "add_transfer_assessment",
    ],
    "REVIEW_REFRESH": [
        "schedule_spaced_review",
        "add_recall_prompt",
        "add_short_quiz",
    ],
}


class TeachingStrategyEngine:
    MINIMUM_HISTORY_EVIDENCE = 3

    @classmethod
    def select(
        cls,
        *,
        user_id: int,
        profile: Profile,
        knowledge_point_id: int | None = None,
        assessment_id: int | None = None,
        agent_run_id: int | None = None,
    ) -> TeachingStrategyDecision:
        if not knowledge_point_id:
            diagnosis = DiagnosisService.build(user_id=user_id, profile=profile)
            target = diagnosis.get("recommended_target")
            knowledge_point_id = (
                target["knowledge_point_id"] if target else None
            )
        if not knowledge_point_id:
            raise ValueError("当前没有可选择教学策略的知识点")

        mastery = UserKnowledgeMastery.query.filter_by(
            user_id=user_id,
            knowledge_point_id=knowledge_point_id,
        ).first()
        weak_prerequisites = cls._weak_prerequisites(
            user_id,
            knowledge_point_id,
        )
        misconceptions = (
            UserMisconception.query.join(Misconception)
            .filter(
                UserMisconception.user_id == user_id,
                Misconception.knowledge_point_id == knowledge_point_id,
                UserMisconception.status.in_(
                    ["suspected", "confirmed", "improving"]
                ),
            )
            .all()
        )
        recent_process = (
            CognitiveDiagnosis.query.filter_by(
                user_id=user_id,
                knowledge_point_id=knowledge_point_id,
            )
            .order_by(
                CognitiveDiagnosis.created_at.desc(),
                CognitiveDiagnosis.id.desc(),
            )
            .first()
        )
        transfer = MasteryDimension.query.filter_by(
            user_id=user_id,
            knowledge_point_id=knowledge_point_id,
            dimension="transfer",
        ).first()
        recent_events = (
            LearningEvent.query.filter_by(
                user_id=user_id,
                knowledge_point_id=knowledge_point_id,
            )
            .order_by(LearningEvent.created_at.desc(), LearningEvent.id.desc())
            .limit(20)
            .all()
        )
        strategy, reasons = cls._rule_select(
            profile=profile,
            mastery=mastery,
            weak_prerequisites=weak_prerequisites,
            misconceptions=misconceptions,
            recent_process=recent_process,
            transfer=transfer,
            recent_events=recent_events,
            history_preference=cls._historical_preference(user_id),
        )
        previous = (
            TeachingStrategyDecision.query.filter_by(user_id=user_id)
            .order_by(
                TeachingStrategyDecision.created_at.desc(),
                TeachingStrategyDecision.id.desc(),
            )
            .first()
        )
        snapshot = {
            "mastery_score": (
                round(float(mastery.mastery_score), 2) if mastery else None
            ),
            "mastery_confidence": (
                round(float(mastery.confidence), 4) if mastery else 0.0
            ),
            "weak_prerequisite_ids": weak_prerequisites,
            "misconceptions": [
                {
                    "id": item.id,
                    "status": item.status,
                    "confidence": item.confidence,
                    "name": item.misconception.name,
                }
                for item in misconceptions
            ],
            "reasoning_status": (
                recent_process.overall_status if recent_process else None
            ),
            "first_error_step": (
                recent_process.first_error_step if recent_process else None
            ),
            "transfer_score": (
                round(float(transfer.mastery_score), 2) if transfer else None
            ),
            "recent_event_types": dict(
                Counter(event.event_type for event in recent_events)
            ),
            "learning_style": profile.learning_style,
            "learning_goal": profile.learning_goal,
        }
        decision = TeachingStrategyDecision(
            user_id=user_id,
            knowledge_point_id=knowledge_point_id,
            assessment_id=assessment_id,
            agent_run_id=agent_run_id,
            strategy_type=strategy,
            previous_strategy_type=(
                previous.strategy_type if previous else ""
            ),
            reason_codes_json=reasons,
            actions_json=STRATEGY_ACTIONS[strategy],
            input_snapshot_json=snapshot,
            switched=bool(previous and previous.strategy_type != strategy),
        )
        db.session.add(decision)
        db.session.flush()
        return decision

    @staticmethod
    def current(user_id: int) -> TeachingStrategyDecision | None:
        return (
            TeachingStrategyDecision.query.filter_by(user_id=user_id)
            .order_by(
                TeachingStrategyDecision.created_at.desc(),
                TeachingStrategyDecision.id.desc(),
            )
            .first()
        )

    @staticmethod
    def history(user_id: int, limit: int = 30) -> list[dict]:
        rows = (
            TeachingStrategyDecision.query.filter_by(user_id=user_id)
            .order_by(
                TeachingStrategyDecision.created_at.desc(),
                TeachingStrategyDecision.id.desc(),
            )
            .limit(max(1, min(limit, 100)))
            .all()
        )
        return [TeachingStrategyEngine.payload(row) for row in rows]

    @staticmethod
    def payload(decision: TeachingStrategyDecision | None) -> dict | None:
        if not decision:
            return None
        payload = decision.to_dict()
        payload["strategy_label"] = STRATEGY_LABELS.get(
            decision.strategy_type,
            decision.strategy_type,
        )
        payload["action_labels"] = [
            TeachingStrategyEngine._action_label(action)
            for action in decision.actions_json or []
        ]
        return payload

    @classmethod
    def _rule_select(
        cls,
        *,
        profile: Profile,
        mastery: UserKnowledgeMastery | None,
        weak_prerequisites: list[int],
        misconceptions: list[UserMisconception],
        recent_process: CognitiveDiagnosis | None,
        transfer: MasteryDimension | None,
        recent_events: list[LearningEvent],
        history_preference: str | None,
    ) -> tuple[str, list[str]]:
        score = float(mastery.mastery_score) if mastery else None
        confirmed = [
            item for item in misconceptions if item.status == "confirmed"
        ]
        repeated_wrong = sum(
            1 for event in recent_events[:5] if event.event_type == "question_wrong"
        )
        if confirmed:
            return "CONCEPT_CORRECTION", [
                "confirmed_misconception",
                "repeated_error" if repeated_wrong >= 2 else "misconception_evidence",
            ]
        if weak_prerequisites and (score is None or score < 60):
            return "FOUNDATION_REBUILD", [
                "low_mastery",
                "weak_prerequisite",
            ]
        if transfer and score is not None and score >= 65 and transfer.mastery_score < 55:
            return "TRANSFER_TRAINING", [
                "overall_mastery_ready",
                "transfer_dimension_below_gate",
            ]
        if recent_process and recent_process.first_error_step:
            if str(profile.learning_style or "").lower() in {
                "visual",
                "visual_reading",
            }:
                return "VISUAL_EXPLANATION", [
                    "reasoning_step_error",
                    "visual_learning_preference",
                ]
            if score is not None and score >= 60:
                return "SOCRATIC_GUIDANCE", [
                    "partial_foundation",
                    "incomplete_reasoning",
                ]
            return "WORKED_EXAMPLE", [
                "reasoning_step_error",
                "step_by_step_support_needed",
            ]
        if score is not None and score >= 80:
            return "REVIEW_REFRESH", [
                "high_mastery",
                "maintenance_review",
            ]
        if history_preference:
            return history_preference, [
                "minimum_history_evidence_met",
                "positive_observed_response",
            ]
        return "DELIBERATE_PRACTICE", [
            "concept_baseline_available",
            "fluency_evidence_needed",
        ]

    @staticmethod
    def _weak_prerequisites(user_id: int, point_id: int) -> list[int]:
        relations = KnowledgeRelation.query.filter_by(
            target_knowledge_point_id=point_id,
            relation_type="prerequisite",
        ).all()
        mastery_by_point = {
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
                relation.source_knowledge_point_id not in mastery_by_point
                or mastery_by_point[
                    relation.source_knowledge_point_id
                ].mastery_score
                < 60
            )
        ]

    @classmethod
    def _historical_preference(cls, user_id: int) -> str | None:
        rows = TeachingStrategyStat.query.filter(
            TeachingStrategyStat.user_id == user_id,
            TeachingStrategyStat.completed_count
            >= cls.MINIMUM_HISTORY_EVIDENCE,
            TeachingStrategyStat.average_observed_gain > 0,
        ).order_by(
            TeachingStrategyStat.average_observed_gain.desc(),
            TeachingStrategyStat.confidence.desc(),
            TeachingStrategyStat.strategy_type,
        ).all()
        return rows[0].strategy_type if rows else None

    @staticmethod
    def _action_label(action: str) -> str:
        labels = {
            "pause_high_difficulty": "暂停高难任务",
            "insert_prerequisite_review": "插入先修知识复习",
            "add_foundation_example": "增加基础例题",
            "add_micro_assessment": "增加小步骤复测",
            "insert_concept_explanation": "返回核心概念",
            "add_contrast_example": "增加正误对比例子",
            "insert_visual_explanation": "增加图解讲解",
            "add_concept_map": "增加概念关系图",
            "reduce_abstract_text": "减少抽象文字",
            "reduce_direct_answer": "减少直接答案",
            "ask_small_step_questions": "增加小步骤追问",
            "check_reasoning_chain": "检查推理链",
            "add_reflection": "增加解题反思",
            "insert_worked_example": "插入完整例题拆解",
            "annotate_each_step": "逐步标注",
            "add_faded_example": "增加半完成例题",
            "add_process_check": "增加过程检查",
            "add_targeted_variations": "增加专项变式练习",
            "increase_feedback_frequency": "提高反馈频率",
            "track_error_pattern": "追踪同类错误",
            "add_mastery_check": "增加掌握度检查",
            "add_new_context_problem": "增加新场景迁移题",
            "add_variation_problem": "增加变式题",
            "require_strategy_explanation": "要求解释所用策略",
            "add_transfer_assessment": "增加迁移能力测评",
            "schedule_spaced_review": "安排间隔复习",
            "add_recall_prompt": "增加主动回忆",
            "add_short_quiz": "增加快速测验",
        }
        return labels.get(action, action)
