from __future__ import annotations

import re
from datetime import datetime

from ..extensions import db
from ..models import (
    CognitiveDiagnosis,
    CognitiveStep,
    KnowledgePoint,
    KnowledgeRelation,
    Misconception,
    MisconceptionEvidence,
    UserMisconception,
)


class MisconceptionService:
    @classmethod
    def apply_diagnoses(
        cls,
        *,
        user_id: int,
        diagnoses: list[CognitiveDiagnosis],
    ) -> list[UserMisconception]:
        changed = []
        for diagnosis in diagnoses:
            error_steps = [
                step
                for step in diagnosis.steps
                if step.error_role in {"root_error", "independent_error"}
            ]
            if not error_steps and diagnosis.overall_status == "no_error":
                cls._record_correct_response(user_id, diagnosis)
                continue
            for step in error_steps:
                point_id = (
                    step.knowledge_point_id
                    or diagnosis.root_cause_knowledge_point_id
                    or diagnosis.knowledge_point_id
                )
                if not point_id:
                    continue
                misconception = cls._catalog_for_step(point_id, step)
                user_item = cls._user_item(user_id, misconception)
                source_id = (
                    f"assessment:{diagnosis.assessment_id}:"
                    f"question:{diagnosis.question_id}:step:{step.step_index}"
                )
                evidence = MisconceptionEvidence.query.filter_by(
                    user_misconception_id=user_item.id,
                    source_type="reasoning_step",
                    source_id=source_id,
                ).first()
                if not evidence:
                    evidence = MisconceptionEvidence(
                        user_misconception_id=user_item.id,
                        cognitive_step_id=step.id,
                        assessment_id=diagnosis.assessment_id,
                        source_type="reasoning_step",
                        source_id=source_id,
                        description=(
                            f"Step {step.step_index}“{step.concept}”与课程证据不一致，"
                            f"被识别为 {step.error_role}"
                        ),
                        payload_json={
                            "status": step.status,
                            "error_role": step.error_role,
                            "error_type": step.error_type,
                            "student": step.student_text,
                            "expected": step.expected_text,
                            "course_sources": step.course_sources_json or [],
                        },
                        confidence=step.confidence,
                    )
                    db.session.add(evidence)
                    db.session.flush()
                    user_item.evidence_count += 1
                    user_item.last_detected_at = datetime.utcnow()
                    user_item.confidence = min(
                        0.95,
                        round(0.42 + user_item.evidence_count * 0.18, 4),
                    )
                    if user_item.evidence_count >= 2:
                        user_item.status = "confirmed"
                    elif user_item.status == "resolved":
                        user_item.status = "suspected"
                        user_item.resolved_at = None
                changed.append(user_item)
        db.session.flush()
        return list({item.id: item for item in changed}.values())

    @staticmethod
    def list_user(
        user_id: int,
        *,
        knowledge_point_id: int | None = None,
    ) -> list[dict]:
        query = UserMisconception.query.join(Misconception).filter(
            UserMisconception.user_id == user_id
        )
        if knowledge_point_id:
            query = query.filter(
                Misconception.knowledge_point_id == knowledge_point_id
            )
        rows = query.order_by(
            UserMisconception.last_detected_at.desc(),
            UserMisconception.id.desc(),
        ).all()
        result = []
        for row in rows:
            payload = row.to_dict(include_evidence=True)
            point_id = row.misconception.knowledge_point_id
            dependents = (
                KnowledgeRelation.query.filter_by(
                    source_knowledge_point_id=point_id,
                    relation_type="prerequisite",
                )
                .order_by(KnowledgeRelation.id)
                .all()
            )
            payload["affected_knowledge_points"] = [
                {
                    "knowledge_point_id": relation.target.id,
                    "name": relation.target.name,
                }
                for relation in dependents
                if relation.target
            ]
            payload["affected_assessment_ids"] = sorted({
                evidence.assessment_id
                for evidence in row.evidence
                if evidence.assessment_id
            })
            result.append(payload)
        return result

    @classmethod
    def resolve_after_transfer(
        cls,
        *,
        user_id: int,
        knowledge_point_id: int,
        assessment_id: int,
        passed: bool,
        confidence: float,
    ) -> list[UserMisconception]:
        rows = (
            UserMisconception.query.join(Misconception)
            .filter(
                UserMisconception.user_id == user_id,
                Misconception.knowledge_point_id == knowledge_point_id,
                UserMisconception.status != "resolved",
            )
            .all()
        )
        for row in rows:
            source_id = f"transfer:{assessment_id}:{knowledge_point_id}"
            existing = MisconceptionEvidence.query.filter_by(
                user_misconception_id=row.id,
                source_type="transfer_question",
                source_id=source_id,
            ).first()
            if not existing:
                db.session.add(MisconceptionEvidence(
                    user_misconception_id=row.id,
                    assessment_id=assessment_id,
                    source_type="transfer_question",
                    source_id=source_id,
                    description=(
                        "迁移题验证通过"
                        if passed
                        else "迁移题仍未通过，误区保持待处理"
                    ),
                    payload_json={"passed": passed},
                    confidence=confidence,
                ))
            if passed:
                row.status = "resolved"
                row.resolved_at = datetime.utcnow()
                row.confidence = max(row.confidence, confidence)
            elif row.status == "improving":
                row.status = "confirmed"
        db.session.flush()
        return rows

    @classmethod
    def _record_correct_response(
        cls,
        user_id: int,
        diagnosis: CognitiveDiagnosis,
    ) -> None:
        rows = (
            UserMisconception.query.join(Misconception)
            .filter(
                UserMisconception.user_id == user_id,
                Misconception.knowledge_point_id
                == diagnosis.knowledge_point_id,
                UserMisconception.status.in_(["suspected", "confirmed"]),
            )
            .all()
        )
        for row in rows:
            source_id = (
                f"assessment:{diagnosis.assessment_id}:"
                f"question:{diagnosis.question_id}:correct"
            )
            if not MisconceptionEvidence.query.filter_by(
                user_misconception_id=row.id,
                source_type="correct_response",
                source_id=source_id,
            ).first():
                db.session.add(MisconceptionEvidence(
                    user_misconception_id=row.id,
                    assessment_id=diagnosis.assessment_id,
                    source_type="correct_response",
                    source_id=source_id,
                    description="后续解题过程与课程证据一致",
                    payload_json={"overall_status": "no_error"},
                    confidence=diagnosis.confidence,
                ))
                row.status = "improving"
                row.last_detected_at = datetime.utcnow()

    @staticmethod
    def _catalog_for_step(
        point_id: int,
        step: CognitiveStep,
    ) -> Misconception:
        point = db.session.get(KnowledgePoint, point_id)
        if not point:
            raise LookupError("认知步骤关联的知识点不存在")
        error_code = re.sub(
            r"[^A-Z0-9]+",
            "_",
            str(step.error_type or "PROCESS_ERROR").upper(),
        ).strip("_")[:40]
        code = f"M_AUTO_{point.id}_{error_code}"
        misconception = Misconception.query.filter_by(
            course_id=point.course_id,
            code=code,
        ).first()
        if misconception:
            return misconception
        concept = step.concept or point.name
        misconception = Misconception(
            course_id=point.course_id,
            knowledge_point_id=point.id,
            code=code,
            name=f"“{concept}”理解或步骤不一致",
            description=(
                f"基于学生提交的解题步骤推断：对“{concept}”的理解或应用"
                "与课程证据存在不一致。该结论需由重复 Evidence 确认。"
            ),
            correction_strategy=(
                f"回到“{concept}”的定义与适用条件，使用正确/错误对比例子，"
                "再进行小步骤复测。"
            ),
        )
        db.session.add(misconception)
        db.session.flush()
        return misconception

    @staticmethod
    def _user_item(
        user_id: int,
        misconception: Misconception,
    ) -> UserMisconception:
        row = UserMisconception.query.filter_by(
            user_id=user_id,
            misconception_id=misconception.id,
        ).first()
        if row:
            return row
        row = UserMisconception(
            user_id=user_id,
            misconception_id=misconception.id,
            status="suspected",
            confidence=0.0,
            evidence_count=0,
        )
        db.session.add(row)
        db.session.flush()
        return row
