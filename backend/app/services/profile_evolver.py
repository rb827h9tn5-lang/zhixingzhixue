from __future__ import annotations

import json
import re
import time
from typing import Any

from .ai_client import QwenClient


PROFILE_FIELDS = {
    "knowledge_level",
    "learning_style",
    "cognitive_preference",
    "prior_experience",
    "time_availability",
    "motivation_driver",
    "engagement_pattern",
    "weak_points",
}

LEARNING_STYLES = {"mixed", "visual", "auditory", "kinesthetic", "reading_writing"}
KNOWLEDGE_LEVELS = {"beginner", "intermediate", "advanced"}
PROFILE_FIELD_LIMITS = {
    "knowledge_level": 80,
    "learning_style": 80,
    "cognitive_preference": 120,
    "time_availability": 120,
    "motivation_driver": 120,
    "engagement_pattern": 120,
}


def evolve_profile_from_behavior(profile: Any, action: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    """Update profile from learning behavior.

    The primary path asks the LLM to infer a conservative profile delta from recent
    behavior. If the LLM is unavailable or returns invalid JSON, a deterministic
    local inference is applied so the profile still evolves during offline demos.
    """
    evidence = evidence or {}
    previous = profile.to_dict() if hasattr(profile, "to_dict") else {}
    updates = _local_profile_delta(previous, action, evidence)
    llm_updates = _llm_profile_delta(previous, action, evidence)
    if llm_updates:
        if updates.get("weak_points") and llm_updates.get("weak_points"):
            raw_points = llm_updates.get("weak_points")
            llm_points = [str(item) for item in raw_points] if isinstance(raw_points, list) else _split_points(str(raw_points or ""))
            llm_updates["weak_points"] = _merge_points(updates.get("weak_points"), llm_points)
        updates.update(llm_updates)
    cleaned = _clean_updates(updates)
    _apply_updates(profile, cleaned)
    return cleaned


def append_profile_event(profile: Any, action: str, summary: str) -> None:
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    label = {
        "generate_resource": "资源生成",
        "submit_quiz": "答题测评",
        "evaluate_quiz": "AI测评评价",
        "generate_case": "实操案例生成",
        "submit_case": "实操案例提交",
        "tutor_ask": "智能辅导提问",
        "generate_ppt": "PPT生成",
        "generate_path": "学习路径生成",
    }.get(action, action)
    line = f"[{now}] {label}：{summary}".strip()
    profile.raw_dialogue = ((profile.raw_dialogue or "") + "\n" + line).strip()


def _llm_profile_delta(previous: dict[str, Any], action: str, evidence: dict[str, Any]) -> dict[str, Any]:
    client = QwenClient()
    if not client.enabled:
        return {}
    system_prompt = (
        "你是学习平台的动态学生画像分析智能体。"
        "请根据学生最近一次学习行为，对画像做保守、可解释的增量更新。"
        "只能输出 JSON，不要输出 Markdown。"
    )
    user_prompt = json.dumps(
        {
            "当前画像": _compact_profile(previous),
            "学习行为": action,
            "行为证据": evidence,
            "允许更新字段": sorted(PROFILE_FIELDS),
            "枚举约束": {
                "knowledge_level": sorted(KNOWLEDGE_LEVELS),
                "learning_style": sorted(LEARNING_STYLES),
            },
            "要求": [
                "不要凭空生成具体经历，只能基于证据归纳。",
                "weak_points 使用中文知识点，多个用中文顿号分隔。",
                "engagement_pattern 描述最近学习习惯与行为模式。",
                "cognitive_preference 描述更适合的讲解/练习方式。",
                "如果证据不足，字段可以省略。",
            ],
        },
        ensure_ascii=False,
    )
    try:
        raw = client.chat(system_prompt, user_prompt)
        parsed = _extract_json(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _local_profile_delta(previous: dict[str, Any], action: str, evidence: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    score = _to_float(evidence.get("score"))
    weak_points = _extract_weak_points(evidence)

    if action in {"submit_quiz", "evaluate_quiz", "submit_case"}:
        if weak_points:
            updates["weak_points"] = _merge_points(previous.get("weak_points"), weak_points)
        if score is not None:
            current_level = previous.get("knowledge_level") or "beginner"
            if score >= 90:
                updates["knowledge_level"] = "advanced"
            elif score >= 75 and current_level == "beginner":
                updates["knowledge_level"] = "intermediate"
            elif score < 60 and current_level == "advanced":
                updates["knowledge_level"] = "intermediate"
            updates["engagement_pattern"] = "测评反馈驱动复盘" if action != "submit_case" else "编程实操 + 判题反馈复盘"
        if action == "submit_case":
            updates["learning_style"] = "kinesthetic"
            updates["cognitive_preference"] = "案例拆解、代码实践与即时反馈"

    elif action == "generate_resource":
        resource_types = evidence.get("types") or []
        type_text = "、".join(resource_types) if isinstance(resource_types, list) else str(resource_types)
        updates["engagement_pattern"] = f"主动生成学习资源并按{type_text or '多类型资源'}推进"
        if any(item in type_text for item in ("mind_map", "multimedia_video", "思维导图", "教学视频")):
            updates["learning_style"] = "visual"
            updates["cognitive_preference"] = "图示化结构梳理与多模态理解"
        elif any(item in type_text for item in ("coding_case", "实操")):
            updates["learning_style"] = "kinesthetic"
            updates["cognitive_preference"] = "动手实践、案例迁移和即时反馈"
        elif any(item in type_text for item in ("course_document", "extension_reading", "讲解", "阅读")):
            updates["learning_style"] = "reading_writing"
            updates["cognitive_preference"] = "结构化阅读、分层讲解和重点摘记"

    elif action == "generate_case":
        updates["learning_style"] = "kinesthetic"
        updates["engagement_pattern"] = "主动选择实操案例进行迁移练习"
        updates["cognitive_preference"] = "任务驱动、代码实践和错误修正"

    elif action == "tutor_ask":
        question = str(evidence.get("question") or "")
        if question:
            guessed = _keywords_from_text(question)
            if guessed:
                updates["weak_points"] = _merge_points(previous.get("weak_points"), guessed)
        updates["engagement_pattern"] = "遇到疑问后主动提问并结合反馈学习"
        updates["cognitive_preference"] = "问答式澄清、示例解释和分步推理"

    elif action == "generate_ppt":
        updates["engagement_pattern"] = "PPT制作 + 资源整合输出"
        updates["motivation_driver"] = "课程汇报、成果展示与知识结构化表达"

    elif action == "generate_path":
        updates["engagement_pattern"] = "按学习路径阶段推进并定期测评校准"

    return updates


def _apply_updates(profile: Any, updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        if key in PROFILE_FIELDS and value not in (None, "") and hasattr(profile, key):
            setattr(profile, key, _fit_field_value(key, value))


def _clean_updates(updates: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in updates.items():
        if key not in PROFILE_FIELDS or value in (None, ""):
            continue
        if key == "knowledge_level":
            value = str(value).strip()
            if value not in KNOWLEDGE_LEVELS:
                continue
        elif key == "learning_style":
            value = str(value).strip()
            if value not in LEARNING_STYLES:
                value = "mixed"
        elif key == "weak_points":
            value = "、".join(_split_points(str(value))[:8])
        else:
            value = _fit_field_value(key, value)
        cleaned[key] = value
    return cleaned


def _fit_field_value(key: str, value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    limit = PROFILE_FIELD_LIMITS.get(key)
    if not limit or len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip("、，,;； ") + "…"


def _compact_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {key: profile.get(key) for key in [
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
    ]}


def _extract_json(text: str) -> Any:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {}
        return json.loads(match.group(0))


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_weak_points(evidence: dict[str, Any]) -> list[str]:
    points: list[str] = []
    raw = evidence.get("weak_points")
    if isinstance(raw, list):
        points.extend(str(item) for item in raw)
    elif raw:
        points.extend(_split_points(str(raw)))
    for detail in evidence.get("details") or []:
        if isinstance(detail, dict) and not detail.get("is_correct"):
            points.append(str(detail.get("concept") or detail.get("id") or "").strip())
    if evidence.get("analysis"):
        points.extend(_keywords_from_text(str(evidence.get("analysis"))))
    return [item for item in _dedupe(points) if item]


def _merge_points(existing: Any, new_points: list[str]) -> str:
    merged = _split_points(str(existing or "")) + new_points
    return "、".join(_dedupe(merged)[:8])


def _split_points(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[;；、,，\n]", text or "") if item.strip()]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        clean = str(item).strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _keywords_from_text(text: str) -> list[str]:
    candidates = []
    for pattern in [
        r"(?:不懂|不会|薄弱|困难|错在|问题在|卡在|混淆)([^，。；;、\n]{2,20})",
        r"(?:关于|针对)([^，。；;、\n]{2,20})(?:的问题|不清楚|还不会)",
    ]:
        candidates.extend(match.strip(" ：:") for match in re.findall(pattern, text))
    return _dedupe(candidates)[:4]
