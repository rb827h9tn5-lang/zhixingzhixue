from __future__ import annotations

from typing import Any

from ..extensions import db
from ..models import LearningEvent, QuizResult
from .question_mapping import knowledge_point_candidates, map_quiz_questions


QUESTION_EVENT_TYPES = {
    "correct": "question_correct",
    "wrong": "question_wrong",
    "partial": "question_partial",
}


class LearningEventService:
    @staticmethod
    def record_event(
        *,
        user_id: int,
        event_type: str,
        event_key: str | None = None,
        knowledge_point_id: int | None = None,
        path_id: int | None = None,
        path_version_id: int | None = None,
        node_id: int | None = None,
        resource_id: int | None = None,
        question_id: str = "",
        assessment_id: int | None = None,
        source_type: str = "",
        source_id: str = "",
        value: dict[str, Any] | None = None,
    ) -> tuple[LearningEvent, bool]:
        if event_key:
            existing = LearningEvent.query.filter_by(user_id=user_id, event_key=event_key).first()
            if existing:
                return existing, False

        event = LearningEvent(
            user_id=user_id,
            event_key=event_key[:220] if event_key else None,
            event_type=event_type,
            knowledge_point_id=knowledge_point_id,
            path_id=path_id,
            path_version_id=path_version_id,
            node_id=node_id,
            resource_id=resource_id,
            question_id=str(question_id or "")[:120],
            assessment_id=assessment_id,
            source_type=str(source_type or "")[:60],
            source_id=str(source_id or "")[:120],
            value_json=value or {},
        )
        db.session.add(event)
        db.session.flush()
        return event, True

    @staticmethod
    def list_user_events(user_id: int, limit: int = 100) -> list[LearningEvent]:
        return (
            LearningEvent.query.filter_by(user_id=user_id)
            .order_by(LearningEvent.created_at.desc(), LearningEvent.id.desc())
            .limit(max(1, min(limit, 500)))
            .all()
        )

    @staticmethod
    def list_kp_events(user_id: int, knowledge_point_id: int, limit: int = 100) -> list[LearningEvent]:
        return (
            LearningEvent.query.filter_by(
                user_id=user_id,
                knowledge_point_id=knowledge_point_id,
            )
            .order_by(LearningEvent.created_at.desc(), LearningEvent.id.desc())
            .limit(max(1, min(limit, 500)))
            .all()
        )

    @classmethod
    def record_assessment_events(
        cls,
        *,
        user_id: int,
        record: QuizResult,
        quiz: dict,
        details: list[dict],
    ) -> tuple[list[LearningEvent], dict]:
        points = knowledge_point_candidates()
        mapped_quiz, coverage = map_quiz_questions(quiz, points)
        questions = {
            str(question.get("id")): question
            for question in mapped_quiz.get("questions") or []
            if isinstance(question, dict)
        }
        events = []

        for detail in details:
            question_id = str(detail.get("id") or "")
            question = questions.get(question_id, {})
            knowledge_point_id = question.get("primary_knowledge_point_id")
            detail["primary_knowledge_point_id"] = knowledge_point_id
            detail["knowledge_point_mapping_status"] = question.get(
                "knowledge_point_mapping_status",
                "unmapped",
            )
            if not knowledge_point_id:
                continue

            status = str(detail.get("status") or ("correct" if detail.get("is_correct") else "wrong"))
            event_type = QUESTION_EVENT_TYPES.get(status, "question_wrong")
            event, _ = cls.record_event(
                user_id=user_id,
                event_type=event_type,
                event_key=f"quiz:{record.id}:question:{question_id}",
                knowledge_point_id=int(knowledge_point_id),
                question_id=question_id,
                assessment_id=record.id,
                source_type="quiz_result",
                source_id=str(record.id),
                value={
                    "concept": detail.get("concept") or question.get("concept") or "",
                    "status": status,
                    "user_answer": detail.get("user_answer") or "",
                    "reference_answer": detail.get("reference_answer") or "",
                    "quiz_title": record.quiz_content,
                    "category": record.category,
                },
            )
            events.append(event)

        complete_event, _ = cls.record_event(
            user_id=user_id,
            event_type="assessment_complete",
            event_key=f"quiz:{record.id}:complete",
            assessment_id=record.id,
            source_type="quiz_result",
            source_id=str(record.id),
            value={
                "score": record.score,
                "category": record.category,
                "question_count": len(details),
                "mapped_question_count": coverage["mapped"],
            },
        )
        events.append(complete_event)
        return events, coverage

    @classmethod
    def backfill_quiz_history(cls, user_id: int) -> dict:
        records = (
            QuizResult.query.filter_by(user_id=user_id)
            .order_by(QuizResult.created_at, QuizResult.id)
            .all()
        )
        created_before = LearningEvent.query.filter_by(user_id=user_id).count()
        processed = 0
        for record in records:
            payload = dict(record.answers or {})
            quiz = payload.get("quiz") or {}
            details = payload.get("details") or []
            if not payload.get("completed") or not quiz or not details:
                continue
            mapped_quiz, _ = map_quiz_questions(quiz, knowledge_point_candidates())
            payload["quiz"] = mapped_quiz
            record.answers = payload
            cls.record_assessment_events(
                user_id=user_id,
                record=record,
                quiz=mapped_quiz,
                details=details,
            )
            processed += 1
        db.session.flush()
        created_after = LearningEvent.query.filter_by(user_id=user_id).count()
        return {
            "processed_assessments": processed,
            "created_events": max(0, created_after - created_before),
        }
