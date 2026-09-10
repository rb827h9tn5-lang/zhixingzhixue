from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .mimo_chat_client import MimoChatClient


OPEN_QUESTION_TYPES = {"fill_blank", "short_answer"}


def judge_open_answers(
    quiz: dict[str, Any],
    submitted_answers: dict[str, Any],
    *,
    model: str,
    timeout: int,
) -> dict[str, float]:
    """并行调用 MiMo 判开放题，失败的题目由本地判分逻辑兜底。"""
    client = MimoChatClient(model=model, timeout=timeout)
    if not client.enabled:
        return {}

    jobs: list[tuple[str, dict[str, Any], str]] = []
    for question in quiz.get("questions") or []:
        if question.get("type") not in OPEN_QUESTION_TYPES:
            continue
        question_id = str(question.get("id", ""))
        answer = submitted_answers.get(question_id, submitted_answers.get(question.get("id"), ""))
        answer_text = str(answer or "").strip()
        if question_id and answer_text:
            jobs.append((question_id, question, answer_text))

    if not jobs:
        return {}

    scores: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=min(3, len(jobs))) as pool:
        futures = {
            pool.submit(_judge_one, client, question, answer): question_id
            for question_id, question, answer in jobs
        }
        for future in as_completed(futures):
            try:
                score = future.result()
            except Exception:
                continue
            if score is not None:
                scores[futures[future]] = score
    return scores


def _judge_one(
    client: MimoChatClient,
    question: dict[str, Any],
    answer: str,
) -> float | None:
    system_prompt = (
        "你是严谨的课程判题助手。只根据题目、参考答案和学生答案判断语义正确性，"
        "不要补充题目中没有的事实。只返回 JSON。"
    )
    user_prompt = (
        f"题目：{question.get('prompt') or question.get('concept') or ''}\n"
        f"参考答案：{question.get('answer') or ''}\n"
        f"学生答案：{answer}\n"
        f"解析：{question.get('explanation') or ''}\n"
        '返回格式：{"score": 1.0}。score 只能为 1.0、0.5 或 0.0。'
    )
    content = client.complete(
        system_prompt,
        user_prompt,
        max_completion_tokens=80,
        temperature=0.1,
    )
    payload = _extract_json(content)
    try:
        raw_score = float(payload.get("score"))
    except (TypeError, ValueError):
        return None
    if raw_score >= 0.75:
        return 1.0
    if raw_score >= 0.25:
        return 0.5
    return 0.0


def _extract_json(content: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return {}
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return payload if isinstance(payload, dict) else {}
