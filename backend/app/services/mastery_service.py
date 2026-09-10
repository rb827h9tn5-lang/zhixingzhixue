from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func

from ..extensions import db
from ..models import (
    KnowledgePoint,
    LearningEvent,
    MasteryEvidence,
    UserKnowledgeMastery,
)


EVENT_DELTAS: dict[str, tuple[float, float, float]] = {
    "question_correct": (1.0, 0.0, 1.0),
    "question_wrong": (0.0, 1.0, 1.0),
    "question_partial": (0.5, 0.5, 1.0),
    "hint_request": (0.0, 0.25, 0.25),
    "resource_complete": (0.10, 0.0, 0.10),
    "code_run": (1.20, 0.0, 1.20),
    "code_error": (0.0, 0.80, 0.80),
}


class MasteryService:
    @classmethod
    def apply_event(cls, event: LearningEvent) -> dict[str, Any] | None:
        if not event.knowledge_point_id or event.event_type not in EVENT_DELTAS:
            return None
        existing_evidence = MasteryEvidence.query.filter_by(event_id=event.id).first()
        if existing_evidence:
            mastery = db.session.get(
                UserKnowledgeMastery,
                existing_evidence.mastery_id,
            )
            return cls._change_payload(mastery, existing_evidence) if mastery else None

        mastery = UserKnowledgeMastery.query.filter_by(
            user_id=event.user_id,
            knowledge_point_id=event.knowledge_point_id,
        ).first()
        if not mastery:
            mastery = UserKnowledgeMastery(
                user_id=event.user_id,
                knowledge_point_id=event.knowledge_point_id,
                mastery_score=50.0,
                confidence=0.0,
                alpha=1.0,
                beta=1.0,
                evidence_weight=0.0,
            )
            db.session.add(mastery)
            db.session.flush()

        old_score = float(mastery.mastery_score)
        alpha_delta, beta_delta, evidence_weight = EVENT_DELTAS[event.event_type]
        if event.event_type == "code_run" and not (event.value_json or {}).get("tests_passed"):
            return None

        mastery.alpha = float(mastery.alpha) + alpha_delta
        mastery.beta = float(mastery.beta) + beta_delta
        mastery.evidence_weight = float(mastery.evidence_weight) + evidence_weight
        mastery.mastery_score = round(mastery.alpha / (mastery.alpha + mastery.beta) * 100, 4)
        mastery.confidence = round(
            mastery.evidence_weight / (mastery.evidence_weight + 3.0),
            4,
        )
        mastery.last_event_id = event.id

        if event.event_type.startswith("question_"):
            mastery.attempt_count += 1
        if event.event_type == "question_correct":
            mastery.correct_count += 1
        elif event.event_type == "question_wrong":
            mastery.wrong_count += 1
        elif event.event_type == "question_partial":
            mastery.partial_count += 1
        elif event.event_type == "hint_request":
            mastery.hint_count += 1

        if event.assessment_id:
            assessment_count = (
                db.session.query(func.count(func.distinct(LearningEvent.assessment_id)))
                .filter(
                    LearningEvent.user_id == event.user_id,
                    LearningEvent.knowledge_point_id == event.knowledge_point_id,
                    LearningEvent.assessment_id.isnot(None),
                    LearningEvent.id <= event.id,
                )
                .scalar()
                or 0
            )
            mastery.assessment_count = int(assessment_count)

        evidence = MasteryEvidence(
            mastery_id=mastery.id,
            event_id=event.id,
            old_score=old_score,
            new_score=mastery.mastery_score,
            delta=mastery.mastery_score - old_score,
            evidence_type=event.event_type,
            weight=evidence_weight,
            description=cls._description(event),
        )
        db.session.add(evidence)
        db.session.flush()
        return cls._change_payload(mastery, evidence)

    @classmethod
    def apply_events(cls, events: list[LearningEvent]) -> list[dict]:
        changes = []
        for event in sorted(events, key=lambda item: item.id):
            change = cls.apply_event(event)
            if change and change["event_id"] == event.id:
                changes.append(change)
        return changes

    @classmethod
    def replay_user(cls, user_id: int) -> list[dict]:
        masteries = UserKnowledgeMastery.query.filter_by(user_id=user_id).all()
        for mastery in masteries:
            db.session.delete(mastery)
        db.session.flush()
        events = (
            LearningEvent.query.filter_by(user_id=user_id)
            .order_by(LearningEvent.created_at, LearningEvent.id)
            .all()
        )
        return cls.apply_events(events)

    @staticmethod
    def list_user_mastery(user_id: int, include_evidence: bool = False) -> list[dict]:
        rows = {
            row.knowledge_point_id: row
            for row in UserKnowledgeMastery.query.filter_by(user_id=user_id).all()
        }
        points = KnowledgePoint.query.order_by(
            KnowledgePoint.course_id,
            KnowledgePoint.code,
            KnowledgePoint.id,
        ).all()
        payload = []
        for point in points:
            row = rows.get(point.id)
            if row:
                payload.append(row.to_dict(include_evidence=include_evidence))
            else:
                payload.append({
                    "id": None,
                    "knowledge_point_id": point.id,
                    "knowledge_point": point.name,
                    "knowledge_point_code": point.code,
                    "chapter_id": point.chapter_id,
                    "mastery_score": None,
                    "confidence": 0.0,
                    "state": "unassessed",
                    "attempt_count": 0,
                    "correct_count": 0,
                    "wrong_count": 0,
                    "partial_count": 0,
                    "hint_count": 0,
                    "assessment_count": 0,
                    "last_event_id": None,
                    "updated_at": None,
                    "evidence": [] if include_evidence else None,
                })
        return payload

    @staticmethod
    def grouped_changes(changes: list[dict]) -> list[dict]:
        grouped: dict[int, list[dict]] = defaultdict(list)
        for change in changes:
            grouped[int(change["knowledge_point_id"])].append(change)
        result = []
        for knowledge_point_id, rows in grouped.items():
            first = rows[0]
            last = rows[-1]
            result.append({
                "knowledge_point_id": knowledge_point_id,
                "knowledge_point": last["knowledge_point"],
                "old": first["old"],
                "new": last["new"],
                "delta": round(last["new"] - first["old"], 2),
                "confidence": last["confidence"],
                "reason": MasteryService._group_reason(rows),
                "event_ids": [row["event_id"] for row in rows],
            })
        return sorted(result, key=lambda item: item["knowledge_point_id"])

    @staticmethod
    def _change_payload(mastery: UserKnowledgeMastery, evidence: MasteryEvidence) -> dict:
        return {
            "event_id": evidence.event_id,
            "knowledge_point_id": mastery.knowledge_point_id,
            "knowledge_point": mastery.knowledge_point.name if mastery.knowledge_point else "",
            "old": round(float(evidence.old_score), 2),
            "new": round(float(evidence.new_score), 2),
            "delta": round(float(evidence.delta), 2),
            "confidence": round(float(mastery.confidence), 4),
            "reason": evidence.description or evidence.evidence_type,
        }

    @staticmethod
    def _description(event: LearningEvent) -> str:
        labels = {
            "question_correct": "题目回答正确",
            "question_wrong": "题目回答错误",
            "question_partial": "题目部分正确",
            "hint_request": "请求学习提示",
            "resource_complete": "完成学习资源",
            "code_run": "代码测试通过",
            "code_error": "出现关键代码错误",
        }
        value = event.value_json or {}
        concept = value.get("concept") or ""
        suffix = f"：{concept}" if concept else ""
        return f"{labels.get(event.event_type, event.event_type)}{suffix}"

    @staticmethod
    def _group_reason(rows: list[dict]) -> str:
        counts: dict[str, int] = defaultdict(int)
        for row in rows:
            reason = row.get("reason") or "学习证据"
            counts[reason] += 1
        return "；".join(
            f"{reason} ×{count}" if count > 1 else reason
            for reason, count in counts.items()
        )
