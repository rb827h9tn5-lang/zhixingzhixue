from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from ..extensions import db
from ..models import (
    AdaptiveExam,
    KnowledgeRelation,
    MasteryDimension,
    QuizResult,
    SelfConfidenceRecord,
    TransferAssessment,
    UserKnowledgeMastery,
)
from .misconception_service import MisconceptionService


DIMENSIONS = (
    "conceptual_understanding",
    "procedural_application",
    "reasoning",
    "coding",
    "transfer",
)


class MasteryDimensionService:
    @classmethod
    def apply_assessment(
        cls,
        *,
        user_id: int,
        record: QuizResult,
        quiz: dict,
        details: list[dict],
        cognitive_diagnoses: list | None = None,
    ) -> list[dict]:
        question_by_id = {
            str(question.get("id")): question
            for question in quiz.get("questions") or []
            if isinstance(question, dict)
        }
        grouped: dict[tuple[int, str], list[float]] = defaultdict(list)
        for detail in details:
            question = question_by_id.get(str(detail.get("id")), {})
            point_id = question.get("primary_knowledge_point_id")
            if not point_id:
                continue
            dimension = question.get("cognitive_dimension") or cls._dimension(
                question.get("transfer_level")
            )
            grouped[(int(point_id), dimension)].append(
                float(detail.get("score_fraction") or 0)
            )
        for diagnosis in cognitive_diagnoses or []:
            observed_steps = [
                step
                for step in diagnosis.steps
                if step.status in {"correct", "incorrect"}
            ]
            if not observed_steps or not diagnosis.knowledge_point_id:
                continue
            grouped[(
                int(diagnosis.knowledge_point_id),
                "reasoning",
            )].extend(
                1.0 if step.status == "correct" else 0.0
                for step in observed_steps
            )

        changes = []
        for (point_id, dimension), scores in grouped.items():
            row = MasteryDimension.query.filter_by(
                user_id=user_id,
                knowledge_point_id=point_id,
                dimension=dimension,
            ).first()
            if row and row.last_assessment_id == record.id:
                changes.append(row.to_dict())
                continue
            if not row:
                row = MasteryDimension(
                    user_id=user_id,
                    knowledge_point_id=point_id,
                    dimension=dimension,
                )
                db.session.add(row)
                db.session.flush()
            old = float(row.mastery_score)
            positive = sum(scores)
            negative = len(scores) - positive
            row.alpha = float(row.alpha) + positive
            row.beta = float(row.beta) + negative
            row.evidence_count += len(scores)
            row.mastery_score = round(
                row.alpha / (row.alpha + row.beta) * 100,
                4,
            )
            row.confidence = round(
                row.evidence_count / (row.evidence_count + 3.0),
                4,
            )
            row.last_assessment_id = record.id
            payload = row.to_dict()
            payload["old_score"] = round(old, 2)
            payload["delta"] = round(float(row.mastery_score) - old, 2)
            changes.append(payload)
        db.session.flush()
        return changes

    @staticmethod
    def get_dimensions(user_id: int, knowledge_point_id: int) -> dict:
        rows = {
            row.dimension: row
            for row in MasteryDimension.query.filter_by(
                user_id=user_id,
                knowledge_point_id=knowledge_point_id,
            ).all()
        }
        return {
            dimension: (
                rows[dimension].to_dict()
                if dimension in rows
                else {
                    "dimension": dimension,
                    "mastery_score": None,
                    "confidence": 0.0,
                    "evidence_count": 0,
                    "state": "unknown",
                }
            )
            for dimension in DIMENSIONS
        }

    @staticmethod
    def _dimension(transfer_level: str | None) -> str:
        return {
            "L1": "conceptual_understanding",
            "L2": "procedural_application",
            "L3": "transfer",
        }.get(str(transfer_level or "").upper(), "conceptual_understanding")


class CapabilityGateService:
    @classmethod
    def evaluate(cls, *, user_id: int, knowledge_point_id: int) -> dict:
        overall = UserKnowledgeMastery.query.filter_by(
            user_id=user_id,
            knowledge_point_id=knowledge_point_id,
        ).first()
        dimensions = MasteryDimensionService.get_dimensions(
            user_id,
            knowledge_point_id,
        )
        transfer = dimensions["transfer"]["mastery_score"]
        procedure = dimensions["procedural_application"]["mastery_score"]
        overall_score = (
            round(float(overall.mastery_score), 2) if overall else None
        )
        confidence = round(float(overall.confidence), 4) if overall else 0.0
        weak_prerequisites = cls._weak_prerequisites(
            user_id,
            knowledge_point_id,
        )
        if overall_score is None:
            state = "FOUNDATION_GAP"
        elif overall_score < 45:
            state = "FOUNDATION_GAP"
        elif overall_score < 60 or confidence < 0.35:
            state = "BASIC_UNSTABLE"
        elif overall_score < 70:
            state = "BASIC_MASTERED"
        elif transfer is None or transfer < 55:
            state = "TRANSFER_WEAK"
        elif procedure is None or procedure < 55:
            state = "BASIC_MASTERED"
        elif confidence >= 0.6 and not weak_prerequisites:
            state = "TRANSFER_READY"
        else:
            state = "APPLICATION_READY"

        requirements = [
            {
                "name": "总体掌握度",
                "current": overall_score,
                "required": 70,
                "passed": overall_score is not None and overall_score >= 70,
            },
            {
                "name": "迁移能力",
                "current": transfer,
                "required": 55,
                "passed": transfer is not None and transfer >= 55,
            },
            {
                "name": "证据置信度",
                "current": round(confidence * 100, 2),
                "required": 60,
                "passed": confidence >= 0.6,
            },
            {
                "name": "先修知识",
                "current": 0 if weak_prerequisites else 1,
                "required": 1,
                "passed": not weak_prerequisites,
                "weak_knowledge_point_ids": weak_prerequisites,
            },
        ]
        gaps = [
            item for item in requirements if not item["passed"]
        ]
        return {
            "knowledge_point_id": knowledge_point_id,
            "overall_mastery": overall_score,
            "overall_confidence": confidence,
            "dimensions": dimensions,
            "capability_state": state,
            "advanced_gate_passed": not gaps,
            "requirements": requirements,
            "gaps": gaps,
            "conclusion": cls._conclusion(state),
            "recommendations": cls._recommendations(state, gaps),
        }

    @staticmethod
    def _weak_prerequisites(user_id: int, point_id: int) -> list[int]:
        relations = KnowledgeRelation.query.filter_by(
            target_knowledge_point_id=point_id,
            relation_type="prerequisite",
        ).all()
        rows = {
            row.knowledge_point_id: row
            for row in UserKnowledgeMastery.query.filter(
                UserKnowledgeMastery.user_id == user_id,
                UserKnowledgeMastery.knowledge_point_id.in_(
                    [item.source_knowledge_point_id for item in relations]
                    or [-1]
                ),
            ).all()
        }
        return [
            relation.source_knowledge_point_id
            for relation in relations
            if (
                relation.source_knowledge_point_id not in rows
                or rows[relation.source_knowledge_point_id].mastery_score < 60
            )
        ]

    @staticmethod
    def _conclusion(state: str) -> str:
        return {
            "FOUNDATION_GAP": "基础知识仍有缺口",
            "BASIC_UNSTABLE": "基础理解尚不稳定",
            "BASIC_MASTERED": "基础已掌握，应用证据仍需补充",
            "APPLICATION_READY": "可以进入标准应用训练",
            "TRANSFER_WEAK": "基础已掌握，但迁移能力不足",
            "TRANSFER_READY": "基础、应用与迁移证据达到当前能力门槛",
        }[state]

    @staticmethod
    def _recommendations(state: str, gaps: list[dict]) -> list[str]:
        result = []
        if state == "TRANSFER_WEAK":
            result.extend(["完成新场景迁移题", "解释解题策略", "完成代码或真实场景实践"])
        elif state in {"FOUNDATION_GAP", "BASIC_UNSTABLE"}:
            result.extend(["复习先修知识", "完成概念对比例题", "进行小步骤检查"])
        elif state == "BASIC_MASTERED":
            result.extend(["完成变式题", "补充标准应用证据"])
        if any(item["name"] == "证据置信度" for item in gaps):
            result.append("增加不同题型的有效 Evidence")
        return list(dict.fromkeys(result))


class TransferAssessmentService:
    @classmethod
    def record_result(
        cls,
        *,
        user_id: int,
        exam: AdaptiveExam,
        record: QuizResult,
        quiz: dict,
        details: list[dict],
    ) -> list[TransferAssessment]:
        question_by_id = {
            str(question.get("id")): question
            for question in quiz.get("questions") or []
            if isinstance(question, dict)
        }
        grouped: dict[int, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for detail in details:
            question = question_by_id.get(str(detail.get("id")), {})
            point_id = question.get("primary_knowledge_point_id")
            level = str(question.get("transfer_level") or "").upper()
            if not point_id or level not in {"L1", "L2", "L3"}:
                continue
            grouped[int(point_id)][level].append(
                float(detail.get("score_fraction") or 0)
            )
        results = []
        for point_id, levels in grouped.items():
            existing = TransferAssessment.query.filter_by(
                user_id=user_id,
                result_id=record.id,
                knowledge_point_id=point_id,
            ).first()
            if existing:
                results.append(existing)
                continue
            level_payload = {}
            all_scores = []
            for level in ("L1", "L2", "L3"):
                scores = levels.get(level, [])
                all_scores.extend(scores)
                level_payload[level] = {
                    "question_count": len(scores),
                    "score": (
                        round(sum(scores) / len(scores) * 100, 2)
                        if scores
                        else None
                    ),
                    "state": "assessed" if scores else "unknown",
                }
            passed = bool(
                level_payload["L1"]["score"] is not None
                and level_payload["L1"]["score"] >= 70
                and level_payload["L2"]["score"] is not None
                and level_payload["L2"]["score"] >= 60
                and level_payload["L3"]["score"] is not None
                and level_payload["L3"]["score"] >= 60
            )
            capability = CapabilityGateService.evaluate(
                user_id=user_id,
                knowledge_point_id=point_id,
            )
            row = TransferAssessment(
                user_id=user_id,
                knowledge_point_id=point_id,
                adaptive_exam_id=exam.id,
                result_id=record.id,
                status="completed",
                levels_json=level_payload,
                score=(
                    round(sum(all_scores) / len(all_scores) * 100, 2)
                    if all_scores
                    else None
                ),
                passed=passed,
                capability_state=capability["capability_state"],
                completed_at=datetime.utcnow(),
            )
            db.session.add(row)
            db.session.flush()
            MisconceptionService.resolve_after_transfer(
                user_id=user_id,
                knowledge_point_id=point_id,
                assessment_id=record.id,
                passed=passed,
                confidence=min(0.95, len(all_scores) / 5),
            )
            results.append(row)
        return results


class MetacognitiveCalibrationService:
    @classmethod
    def record_submission(
        cls,
        *,
        user_id: int,
        record: QuizResult,
        quiz: dict,
        details: list[dict],
        self_confidence: dict[str, Any] | None,
    ) -> list[SelfConfidenceRecord]:
        if not self_confidence:
            return []
        question_by_id = {
            str(question.get("id")): question
            for question in quiz.get("questions") or []
            if isinstance(question, dict)
        }
        rows = []
        for detail in details:
            question_id = str(detail.get("id"))
            raw = self_confidence.get(
                question_id,
                self_confidence.get(detail.get("id")),
            )
            if raw is None:
                continue
            confidence = max(0, min(int(raw), 100))
            actual = float(detail.get("score_fraction") or 0)
            if confidence >= 80 and actual < 0.5:
                signal = "overconfidence"
            elif confidence <= 40 and actual >= 0.8:
                signal = "underconfidence"
            else:
                signal = "calibrated"
            existing = SelfConfidenceRecord.query.filter_by(
                user_id=user_id,
                assessment_id=record.id,
                question_id=question_id,
            ).first()
            if existing:
                rows.append(existing)
                continue
            question = question_by_id.get(question_id, {})
            row = SelfConfidenceRecord(
                user_id=user_id,
                assessment_id=record.id,
                question_id=question_id,
                knowledge_point_id=question.get(
                    "primary_knowledge_point_id"
                ),
                self_confidence=confidence,
                actual_score=actual,
                calibration_signal=signal,
            )
            db.session.add(row)
            rows.append(row)
        db.session.flush()
        return rows

    @staticmethod
    def report(user_id: int) -> dict:
        rows = (
            SelfConfidenceRecord.query.filter_by(user_id=user_id)
            .order_by(
                SelfConfidenceRecord.created_at,
                SelfConfidenceRecord.id,
            )
            .all()
        )
        if not rows:
            return {
                "record_count": 0,
                "average_self_confidence": None,
                "actual_performance": None,
                "state": "INSUFFICIENT_EVIDENCE",
                "message": "至少完成两道带自信判断的题目后再形成校准结论",
                "knowledge_points": [],
            }
        grouped: dict[int | None, list[SelfConfidenceRecord]] = defaultdict(list)
        for row in rows:
            grouped[row.knowledge_point_id].append(row)
        over_count = sum(
            1 for row in rows if row.calibration_signal == "overconfidence"
        )
        under_count = sum(
            1 for row in rows if row.calibration_signal == "underconfidence"
        )
        if len(rows) < 2:
            state = "INSUFFICIENT_EVIDENCE"
        elif over_count >= 2 and over_count / len(rows) >= 0.5:
            state = "OVERCONFIDENT"
        elif under_count >= 2 and under_count / len(rows) >= 0.5:
            state = "UNDERCONFIDENT"
        else:
            state = "CALIBRATED"
        point_rows = []
        for point_id, items in grouped.items():
            point_rows.append({
                "knowledge_point_id": point_id,
                "knowledge_point": (
                    items[0].knowledge_point.name
                    if items[0].knowledge_point
                    else ""
                ),
                "record_count": len(items),
                "average_self_confidence": round(
                    sum(item.self_confidence for item in items) / len(items),
                    2,
                ),
                "actual_performance": round(
                    sum(item.actual_score for item in items)
                    / len(items)
                    * 100,
                    2,
                ),
                "overconfidence_count": sum(
                    1
                    for item in items
                    if item.calibration_signal == "overconfidence"
                ),
                "underconfidence_count": sum(
                    1
                    for item in items
                    if item.calibration_signal == "underconfidence"
                ),
            })
        point_rows.sort(
            key=lambda item: (
                -abs(
                    item["average_self_confidence"]
                    - item["actual_performance"]
                ),
                item["knowledge_point_id"] or 0,
            )
        )
        return {
            "record_count": len(rows),
            "average_self_confidence": round(
                sum(row.self_confidence for row in rows) / len(rows),
                2,
            ),
            "actual_performance": round(
                sum(row.actual_score for row in rows) / len(rows) * 100,
                2,
            ),
            "state": state,
            "message": {
                "INSUFFICIENT_EVIDENCE": "当前证据不足，不形成高估或低估结论",
                "OVERCONFIDENT": "连续证据显示自我判断偏高，建议增加解释题和迁移题",
                "UNDERCONFIDENT": "连续证据显示自我判断偏低，可增加成功回顾",
                "CALIBRATED": "当前自我判断与实际表现基本一致",
            }[state],
            "knowledge_points": point_rows,
        }
