from __future__ import annotations

import re
from typing import Iterable

from ..models import Course, KnowledgePoint


def knowledge_point_candidates(topic: str = "", course_id: int | None = None) -> list[KnowledgePoint]:
    query = KnowledgePoint.query
    if course_id:
        return query.filter_by(course_id=course_id).order_by(KnowledgePoint.code, KnowledgePoint.id).all()

    normalized_topic = _normalize(topic)
    if normalized_topic:
        course = Course.query.order_by(Course.id).all()
        matching_ids = [
            item.id
            for item in course
            if normalized_topic in _normalize(item.title) or _normalize(item.title) in normalized_topic
        ]
        if matching_ids:
            return (
                query.filter(KnowledgePoint.course_id.in_(matching_ids))
                .order_by(KnowledgePoint.code, KnowledgePoint.id)
                .all()
            )
    return query.order_by(KnowledgePoint.course_id, KnowledgePoint.code, KnowledgePoint.id).all()


def allowed_knowledge_points(points: Iterable[KnowledgePoint]) -> list[dict]:
    return [
        {
            "id": point.id,
            "code": point.code,
            "name": point.name,
            "chapter_id": point.chapter_id,
        }
        for point in points
    ]


def map_quiz_questions(
    quiz: dict,
    points: Iterable[KnowledgePoint],
) -> tuple[dict, dict]:
    questions = quiz.get("questions") if isinstance(quiz, dict) else None
    if not isinstance(questions, list):
        return quiz, {"total": 0, "mapped": 0, "unmapped": 0, "coverage": 0.0}

    point_list = list(points)
    points_by_id = {point.id: point for point in point_list}
    mapped = 0

    for question in questions:
        if not isinstance(question, dict):
            continue
        requested_id = _positive_int(question.get("primary_knowledge_point_id"))
        point = points_by_id.get(requested_id) if requested_id else None
        method = "provided_id" if point else ""

        if point is None:
            point, method = _match_point(
                str(question.get("concept") or question.get("prompt") or ""),
                point_list,
            )

        if point is None:
            question["primary_knowledge_point_id"] = None
            question["knowledge_point_mapping_status"] = "unmapped"
            question["knowledge_point_mapping_method"] = ""
            continue

        mapped += 1
        question["primary_knowledge_point_id"] = point.id
        question["knowledge_point_mapping_status"] = "mapped"
        question["knowledge_point_mapping_method"] = method
        question["knowledge_point"] = {
            "id": point.id,
            "code": point.code,
            "name": point.name,
            "chapter_id": point.chapter_id,
        }

    total = len([item for item in questions if isinstance(item, dict)])
    return quiz, {
        "total": total,
        "mapped": mapped,
        "unmapped": max(0, total - mapped),
        "coverage": round(mapped / total, 4) if total else 0.0,
    }


def _match_point(value: str, points: list[KnowledgePoint]) -> tuple[KnowledgePoint | None, str]:
    normalized_value = _normalize(value)
    if len(normalized_value) < 2:
        return None, ""

    exact_matches = []
    for point in points:
        labels = [point.name, point.code, *(point.aliases_json or [])]
        normalized_labels = [_normalize(label) for label in labels if _normalize(label)]
        if normalized_value in normalized_labels:
            exact_matches.append(point)
    if len(exact_matches) == 1:
        return exact_matches[0], "exact_name"

    containment = []
    for point in points:
        point_name = _normalize(point.name)
        if len(point_name) >= 3 and (point_name in normalized_value or normalized_value in point_name):
            containment.append((min(len(point_name), len(normalized_value)), point))
    if containment:
        containment.sort(key=lambda item: (-item[0], item[1].id))
        if len(containment) == 1 or containment[0][0] > containment[1][0]:
            return containment[0][1], "name_containment"

    value_grams = _bigrams(normalized_value)
    candidates = []
    for point in points:
        labels = [point.name, *(point.aliases_json or [])]
        best = 0.0
        for label in labels:
            label_grams = _bigrams(_normalize(label))
            union = value_grams | label_grams
            if union:
                best = max(best, len(value_grams & label_grams) / len(union))
        if best >= 0.55:
            candidates.append((best, point))
    candidates.sort(key=lambda item: (-item[0], item[1].id))
    if candidates and (len(candidates) == 1 or candidates[0][0] > candidates[1][0]):
        return candidates[0][1], "name_similarity"
    return None, ""


def _normalize(value: object) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").lower())


def _bigrams(value: str) -> set[str]:
    if len(value) < 2:
        return {value} if value else set()
    return {value[index:index + 2] for index in range(len(value) - 1)}


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
