from __future__ import annotations

import re
from typing import Any

from ..extensions import db
from ..models import (
    CognitiveDiagnosis,
    CognitiveStep,
    KnowledgeChunk,
    KnowledgeDocument,
    QuizResult,
)


class ErrorPropagationService:
    @staticmethod
    def classify(steps: list[dict[str, Any]]) -> dict[str, Any]:
        first_error_index = next(
            (
                index
                for index, step in enumerate(steps)
                if step["status"] == "incorrect"
            ),
            None,
        )
        if first_error_index is None:
            for step in steps:
                step["error_role"] = (
                    "uncertain" if step["status"] == "uncertain" else "none"
                )
            return {
                "root_error": None,
                "propagation_chain": [],
                "message": "没有观察到可定位的错误传播起点",
            }

        chain = []
        for index, step in enumerate(steps):
            if step["status"] == "uncertain":
                step["error_role"] = "uncertain"
            elif index == first_error_index:
                step["error_role"] = "root_error"
                chain.append(ErrorPropagationService._chain_item(step))
            elif step["status"] == "incorrect":
                previous = steps[index - 1] if index > 0 else None
                depends_on = step.get("depends_on", index)
                propagated = (
                    previous is not None
                    and previous.get("error_role") in {
                        "root_error",
                        "derived_error",
                    }
                    and depends_on in {index, index - 1, step["step_index"] - 1}
                )
                step["error_role"] = (
                    "derived_error" if propagated else "independent_error"
                )
                if propagated:
                    chain.append(ErrorPropagationService._chain_item(step))
            else:
                step["error_role"] = "none"

        root = steps[first_error_index]
        return {
            "root_error": ErrorPropagationService._chain_item(root),
            "propagation_chain": chain,
            "derived_error_count": sum(
                1 for step in steps if step["error_role"] == "derived_error"
            ),
            "independent_error_count": sum(
                1
                for step in steps
                if step["error_role"] == "independent_error"
            ),
            "message": (
                f"第一处可定位错误出现在 Step {root['step_index']}；"
                f"其后识别到 {sum(1 for step in steps if step['error_role'] == 'derived_error')} "
                "个可能受前一步影响的错误"
            ),
        }

    @staticmethod
    def _chain_item(step: dict) -> dict:
        return {
            "step_index": step["step_index"],
            "concept": step.get("concept") or "",
            "knowledge_point_id": step.get("knowledge_point_id"),
            "error_role": step.get("error_role") or "",
            "error_type": step.get("error_type") or "",
        }


class CognitiveProcessService:
    @classmethod
    def diagnose_assessment(
        cls,
        *,
        user_id: int,
        record: QuizResult,
        quiz: dict,
        details: list[dict],
        reasoning_steps: dict[str, Any] | None = None,
    ) -> list[CognitiveDiagnosis]:
        question_by_id = {
            str(question.get("id")): question
            for question in quiz.get("questions") or []
            if isinstance(question, dict)
        }
        detail_by_id = {
            str(detail.get("id")): detail
            for detail in details
            if isinstance(detail, dict)
        }
        submitted_steps = reasoning_steps or {}
        diagnoses = []
        for question_id, question in question_by_id.items():
            expected_steps = question.get("expected_steps") or []
            if not expected_steps:
                continue
            existing = CognitiveDiagnosis.query.filter_by(
                user_id=user_id,
                assessment_id=record.id,
                question_id=question_id,
            ).first()
            if existing:
                diagnoses.append(existing)
                continue
            detail = detail_by_id.get(question_id, {})
            student_steps = cls._normalize_student_steps(
                submitted_steps.get(
                    question_id,
                    submitted_steps.get(question.get("id"), []),
                )
            )
            analyzed = cls._analyze_steps(
                expected_steps=expected_steps,
                student_steps=student_steps,
                question=question,
                detail=detail,
                user_id=user_id,
            )
            propagation = ErrorPropagationService.classify(analyzed)
            root = next(
                (
                    step
                    for step in analyzed
                    if step["error_role"] == "root_error"
                ),
                None,
            )
            observed = [
                step
                for step in analyzed
                if step["status"] in {"correct", "incorrect"}
            ]
            if root:
                overall_status = "root_error"
                summary = (
                    f"基于已提交解题过程，第一处可定位错误在 Step "
                    f"{root['step_index']}：{root['concept']}"
                )
            elif observed and all(
                step["status"] == "correct" for step in observed
            ):
                overall_status = "no_error"
                summary = "已观察到的解题步骤与课程证据一致"
            else:
                overall_status = "insufficient_evidence"
                summary = "解题过程证据不足，未对未观察步骤作错误判断"

            diagnosis = CognitiveDiagnosis(
                user_id=user_id,
                assessment_id=record.id,
                question_id=question_id,
                knowledge_point_id=question.get(
                    "primary_knowledge_point_id"
                ),
                first_error_step=root["step_index"] if root else None,
                root_cause_knowledge_point_id=(
                    root.get("knowledge_point_id") if root else None
                ),
                overall_status=overall_status,
                confidence=(
                    root["confidence"]
                    if root
                    else cls._diagnosis_confidence(analyzed)
                ),
                summary=summary,
                propagation_json=propagation,
            )
            db.session.add(diagnosis)
            db.session.flush()
            for step in analyzed:
                db.session.add(CognitiveStep(
                    diagnosis_id=diagnosis.id,
                    step_index=step["step_index"],
                    knowledge_point_id=step.get("knowledge_point_id"),
                    concept=step.get("concept") or "",
                    expected_text=step.get("expected") or "",
                    student_text=step.get("student") or "",
                    status=step["status"],
                    error_role=step["error_role"],
                    error_type=step.get("error_type") or "",
                    confidence=step["confidence"],
                    evidence_json=step.get("evidence") or [],
                    course_sources_json=step.get("course_sources") or [],
                ))
            db.session.flush()
            diagnoses.append(diagnosis)
        return diagnoses

    @staticmethod
    def list_assessment(
        *,
        user_id: int,
        assessment_id: int,
    ) -> list[CognitiveDiagnosis]:
        return (
            CognitiveDiagnosis.query.filter_by(
                user_id=user_id,
                assessment_id=assessment_id,
            )
            .order_by(CognitiveDiagnosis.id)
            .all()
        )

    @classmethod
    def _analyze_steps(
        cls,
        *,
        expected_steps: list[dict],
        student_steps: list[str],
        question: dict,
        detail: dict,
        user_id: int,
    ) -> list[dict]:
        rows = []
        final_index = len(expected_steps) - 1
        for index, expected in enumerate(expected_steps):
            student = student_steps[index] if index < len(student_steps) else ""
            is_final = bool(expected.get("is_final_answer")) or index == final_index
            if not student and is_final and detail.get("user_answer"):
                student = f"选择答案 {detail.get('user_answer')}"
            status, confidence, error_type, evidence = cls._evaluate_step(
                expected=expected,
                student=student,
                is_final=is_final,
                question=question,
                detail=detail,
            )
            rows.append({
                "step_index": int(expected.get("step_id") or index + 1),
                "knowledge_point_id": (
                    expected.get("knowledge_point_id")
                    or question.get("primary_knowledge_point_id")
                ),
                "concept": (
                    expected.get("concept")
                    or question.get("concept")
                    or ""
                ),
                "expected": str(expected.get("expected") or ""),
                "student": student,
                "status": status,
                "error_role": "none",
                "error_type": error_type,
                "confidence": confidence,
                "depends_on": expected.get("depends_on", index),
                "evidence": evidence,
                "course_sources": cls._course_sources(
                    user_id=user_id,
                    source_chunk_id=question.get("source_chunk_id"),
                ),
            })
        return rows

    @classmethod
    def _evaluate_step(
        cls,
        *,
        expected: dict,
        student: str,
        is_final: bool,
        question: dict,
        detail: dict,
    ) -> tuple[str, float, str, list[dict]]:
        if not student:
            return (
                "not_observed",
                0.0,
                "",
                [{"type": "missing_step", "description": "学生未提交该步骤"}],
            )
        if is_final:
            correct = bool(detail.get("is_correct"))
            return (
                "correct" if correct else "incorrect",
                0.99,
                "" if correct else "answer_selection_error",
                [{
                    "type": "assessment_result",
                    "user_answer": detail.get("user_answer") or "",
                    "reference_answer": detail.get("reference_answer") or "",
                }],
            )

        keywords = [
            str(item)
            for item in expected.get("keywords") or []
            if str(item).strip()
        ]
        expected_text = str(expected.get("expected") or "")
        if not keywords:
            keywords = cls._keywords(expected_text)
        normalized_student = cls._normalize(student)
        hits = [
            keyword
            for keyword in keywords
            if cls._normalize(keyword) in normalized_student
        ]
        ratio = len(hits) / len(keywords) if keywords else 0.0
        evidence = [{
            "type": "keyword_alignment",
            "matched_keywords": hits,
            "expected_keywords": keywords,
            "ratio": round(ratio, 4),
        }]
        if ratio >= 0.6:
            return "correct", min(0.95, 0.65 + ratio * 0.3), "", evidence
        if ratio <= 0.15:
            return (
                "incorrect",
                0.82 if keywords else 0.55,
                "concept_or_process_mismatch",
                evidence,
            )
        return "uncertain", 0.55, "incomplete_reasoning", evidence

    @staticmethod
    def _normalize_student_steps(value: Any) -> list[str]:
        if isinstance(value, str):
            return [
                item.strip()
                for item in re.split(r"[\r\n；;]+", value)
                if item.strip()
            ]
        if not isinstance(value, list):
            return []
        result = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
            else:
                text = item
            result.append(str(text or "").strip())
        return result

    @staticmethod
    def _keywords(text: str) -> list[str]:
        tokens = re.findall(r"[A-Za-z0-9_()+*-]+|[\u4e00-\u9fff]{2,8}", text)
        return list(dict.fromkeys(tokens))[:6]

    @staticmethod
    def _normalize(value: object) -> str:
        return re.sub(
            r"[^0-9a-z\u4e00-\u9fff]+",
            "",
            str(value or "").lower(),
        )

    @staticmethod
    def _course_sources(
        *,
        user_id: int,
        source_chunk_id: int | None,
    ) -> list[dict]:
        if not source_chunk_id:
            return []
        chunk = (
            KnowledgeChunk.query.join(KnowledgeDocument)
            .filter(
                KnowledgeChunk.id == source_chunk_id,
                KnowledgeDocument.user_id == user_id,
            )
            .first()
        )
        if not chunk:
            return []
        return [{
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "document": chunk.document.title if chunk.document else "",
            "section": chunk.section or "",
            "page_start": chunk.page_start,
            "excerpt": (chunk.chunk_text or "")[:240],
        }]

    @staticmethod
    def _diagnosis_confidence(steps: list[dict]) -> float:
        observed = [
            step["confidence"]
            for step in steps
            if step["status"] != "not_observed"
        ]
        return round(sum(observed) / len(observed), 4) if observed else 0.0
