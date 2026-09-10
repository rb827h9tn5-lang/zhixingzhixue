from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import func

from ..extensions import db
from ..models import Profile, ProfileEvidence, ProfileVersion
from .local_generator import LocalStudyGenerator
from .mimo_chat_client import MimoChatClient, MimoChatError


PROFILE_FIELDS = (
    "topic",
    "major",
    "knowledge_level",
    "learning_goal",
    "learning_style",
    "cognitive_preference",
    "prior_experience",
    "time_availability",
    "motivation_driver",
    "engagement_pattern",
    "weak_points",
    "preferred_resource_types",
    "weekly_time_minutes",
    "practice_level",
)
KNOWLEDGE_LEVELS = {"beginner", "intermediate", "advanced"}
LEARNING_STYLES = {"mixed", "visual", "auditory", "kinesthetic", "reading_writing"}
PRACTICE_LEVELS = {"beginner", "intermediate", "advanced"}
FIELD_LIMITS = {
    "topic": 180,
    "major": 120,
    "knowledge_level": 80,
    "learning_style": 80,
    "cognitive_preference": 120,
    "time_availability": 120,
    "motivation_driver": 120,
    "engagement_pattern": 120,
    "practice_level": 40,
}


def extract_profile_draft(profile: Profile, payload: dict[str, Any]) -> dict[str, Any]:
    dialogue = str(payload.get("dialogue") or "").strip()
    previous = profile.to_dict()
    candidate: dict[str, Any] = {}
    provider = "local"
    confidence = 0.65

    client = MimoChatClient()
    if dialogue and client.enabled:
        try:
            candidate = _extract_with_mimo(client, dialogue, previous)
            provider = "mimo"
            confidence = 0.85
        except (MimoChatError, ValueError, json.JSONDecodeError):
            candidate = {}

    if not candidate:
        candidate = LocalStudyGenerator(previous).extract_profile(payload, previous)
        candidate.update({key: value for key, value in payload.items() if key in PROFILE_FIELDS})

    draft = sanitize_profile_values(candidate, previous)
    changes = diff_profile(previous, draft)
    return {
        "draft": draft,
        "changes": changes,
        "extraction": {
            "provider": provider,
            "model": client.model if provider == "mimo" else "deterministic-local",
            "confidence": confidence,
        },
    }


def confirm_profile_draft(
    profile: Profile,
    *,
    draft: dict[str, Any],
    dialogue: str = "",
    confidence: float = 1.0,
    expected_version: int | None = None,
) -> tuple[ProfileVersion, list[ProfileEvidence], bool]:
    previous = profile.to_dict()
    current_version = profile.current_version.version if profile.current_version else 0
    if expected_version is not None and expected_version != current_version:
        raise ValueError("画像已在其他操作中更新，请刷新后重新确认")

    cleaned = sanitize_profile_values(draft, previous)
    changes = diff_profile(previous, cleaned)
    if not changes and profile.current_version:
        evidence_rows = []
        clean_dialogue = dialogue.strip()
        updated_dialogue = _append_dialogue(profile.raw_dialogue, clean_dialogue) if clean_dialogue else (profile.raw_dialogue or "")
        if updated_dialogue != (profile.raw_dialogue or ""):
            profile.raw_dialogue = updated_dialogue
            row = ProfileEvidence(
                user_id=profile.user_id,
                profile_version_id=profile.current_version.id,
                dimension="dialogue_context",
                old_value_json=None,
                new_value_json=clean_dialogue,
                evidence_type="dialogue",
                evidence_source_id=f"profile-intake-v{current_version}",
                evidence_description=clean_dialogue,
                confidence=max(0.0, min(1.0, float(confidence))),
            )
            db.session.add(row)
            evidence_rows.append(row)
        return profile.current_version, evidence_rows, True

    for field in PROFILE_FIELDS:
        if field in cleaned:
            setattr(profile, field, cleaned[field])
    if dialogue.strip():
        profile.raw_dialogue = _append_dialogue(profile.raw_dialogue, dialogue.strip())

    version, evidence = record_profile_version(
        profile,
        previous=previous,
        changes=changes,
        evidence_type="dialogue",
        evidence_source_id=f"profile-intake-v{current_version + 1}",
        evidence_description=dialogue.strip() or "用户确认了画像字段",
        confidence=confidence,
        change_summary=_change_summary(changes, "用户确认画像"),
    )
    return version, evidence, False


def record_behavior_profile_change(
    profile: Profile,
    *,
    previous: dict[str, Any],
    action: str,
    evidence_payload: dict[str, Any],
) -> tuple[ProfileVersion | None, list[ProfileEvidence]]:
    current = profile.to_dict()
    changes = diff_profile(previous, current)
    if not changes:
        return None, []
    evidence_type = {
        "submit_quiz": "assessment",
        "evaluate_quiz": "assessment",
        "submit_case": "assessment",
        "tutor_ask": "tutor_session",
        "generate_resource": "resource_feedback",
    }.get(action, "learning_behavior")
    source_id = str(
        evidence_payload.get("record_id")
        or evidence_payload.get("resource_id")
        or evidence_payload.get("conversation_id")
        or action
    )
    description = json.dumps(evidence_payload, ensure_ascii=False, default=str)[:2000]
    return record_profile_version(
        profile,
        previous=previous,
        changes=changes,
        evidence_type=evidence_type,
        evidence_source_id=source_id,
        evidence_description=description,
        confidence=0.75,
        change_summary=_change_summary(changes, f"学习行为：{action}"),
    )


def record_profile_version(
    profile: Profile,
    *,
    previous: dict[str, Any],
    changes: list[dict[str, Any]],
    evidence_type: str,
    evidence_source_id: str,
    evidence_description: str,
    confidence: float,
    change_summary: str,
) -> tuple[ProfileVersion, list[ProfileEvidence]]:
    latest = (
        db.session.query(func.max(ProfileVersion.version))
        .filter(ProfileVersion.user_id == profile.user_id)
        .scalar()
        or 0
    )
    version = ProfileVersion(
        user_id=profile.user_id,
        version=latest + 1,
        snapshot_json=_snapshot(profile),
        change_summary=change_summary,
    )
    db.session.add(version)
    db.session.flush()

    evidence_rows = []
    if not changes:
        changes = [{
            "dimension": "profile_snapshot",
            "old_value": None,
            "new_value": _snapshot(profile),
        }]
    for change in changes:
        row = ProfileEvidence(
            user_id=profile.user_id,
            profile_version_id=version.id,
            dimension=change["dimension"],
            old_value_json=change["old_value"],
            new_value_json=change["new_value"],
            evidence_type=evidence_type,
            evidence_source_id=evidence_source_id[:120],
            evidence_description=evidence_description,
            confidence=max(0.0, min(1.0, float(confidence))),
        )
        db.session.add(row)
        evidence_rows.append(row)
    profile.current_version_id = version.id
    db.session.flush()
    version.snapshot_json = _snapshot(profile)
    return version, evidence_rows


def sanitize_profile_values(
    values: dict[str, Any],
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    previous = previous or {}
    aliases = {
        "current_level": "knowledge_level",
        "weekly_time": "time_availability",
        "weaknesses": "weak_points",
    }
    normalized = dict(values or {})
    for source, target in aliases.items():
        if source in normalized and target not in normalized:
            normalized[target] = normalized[source]

    result: dict[str, Any] = {}
    for field in PROFILE_FIELDS:
        value = normalized.get(field, previous.get(field))
        if field == "preferred_resource_types":
            if isinstance(value, str):
                value = re.split(r"[、,，;；\s]+", value)
            result[field] = _dedupe_strings(value or [])[:8]
            continue
        if field == "weekly_time_minutes":
            result[field] = _positive_int(value)
            continue
        text = re.sub(r"\s+", " ", str(value or "").strip())
        if field == "knowledge_level" and text not in KNOWLEDGE_LEVELS:
            text = previous.get(field) or "beginner"
        elif field == "learning_style" and text not in LEARNING_STYLES:
            text = previous.get(field) or "mixed"
        elif field == "practice_level" and text not in PRACTICE_LEVELS:
            text = previous.get(field) or "beginner"
        limit = FIELD_LIMITS.get(field)
        result[field] = text[:limit] if limit else text
    return result


def diff_profile(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    changes = []
    for field in PROFILE_FIELDS:
        old_value = previous.get(field)
        new_value = current.get(field)
        if (old_value or None) != (new_value or None):
            changes.append({
                "dimension": field,
                "old_value": old_value,
                "new_value": new_value,
            })
    return changes


def _extract_with_mimo(
    client: MimoChatClient,
    dialogue: str,
    previous: dict[str, Any],
) -> dict[str, Any]:
    system_prompt = (
        "你是学习建档助手。仅从学生原话中提取有证据的画像字段。"
        "不要编造经历、薄弱点或时间。只输出 JSON，不要 Markdown。"
    )
    user_prompt = json.dumps(
        {
            "学生原话": dialogue,
            "当前画像": {field: previous.get(field) for field in PROFILE_FIELDS},
            "输出字段": {
                "major": "专业背景",
                "learning_goal": "学习目标",
                "knowledge_level": "beginner/intermediate/advanced",
                "time_availability": "原话中的可投入时间",
                "weekly_time_minutes": "可确定时才给整数分钟",
                "preferred_resource_types": "偏好的资源类型数组",
                "weak_points": "明确提及的知识短板，用顿号分隔",
                "learning_style": "mixed/visual/auditory/kinesthetic/reading_writing",
                "practice_level": "beginner/intermediate/advanced",
                "prior_experience": "明确提及的经历",
                "motivation_driver": "考试/竞赛/项目等动机",
            },
            "要求": "证据不足的字段省略，禁止用常见默认答案补齐。",
        },
        ensure_ascii=False,
    )
    raw = client.complete(
        system_prompt,
        user_prompt,
        max_completion_tokens=600,
        temperature=0.1,
    )
    payload = _extract_json(raw)
    if not isinstance(payload, dict):
        raise ValueError("画像抽取结果不是对象")
    return payload


def _extract_json(value: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (value or "").strip(), flags=re.I)
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        result = json.loads(match.group(0))
    return result if isinstance(result, dict) else {}


def _snapshot(profile: Profile) -> dict[str, Any]:
    return {field: getattr(profile, field) for field in PROFILE_FIELDS}


def _append_dialogue(existing: str | None, dialogue: str) -> str:
    lines = [line for line in (existing or "").splitlines() if line.strip()]
    if not lines or lines[-1] != dialogue:
        lines.append(dialogue)
    return "\n".join(lines)


def _change_summary(changes: list[dict[str, Any]], prefix: str) -> str:
    fields = "、".join(change["dimension"] for change in changes[:6])
    return f"{prefix}：{fields}" if fields else f"{prefix}：建立初始快照"


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _dedupe_strings(values: list[Any]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
