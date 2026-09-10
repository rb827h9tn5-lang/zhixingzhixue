from __future__ import annotations

import json
from typing import Any, Callable

from .base_agent import BaseAgent


class CodingCaseAgent(BaseAgent):
    """实操案例 Agent：生成可提交给 AI 判题的实操题"""

    def __init__(self, profile: dict):
        super().__init__(profile, "实操案例 Agent")

    def generate(self, fallback: Callable[[], dict], extra_input: str = "") -> tuple[dict, dict[str, Any]]:
        if not self.enabled:
            return fallback(), self.fallback_meta("未配置 API Key，已使用本地实操题生成。")

        extra_note = f"\n用户额外要求：{extra_input}" if extra_input else ""
        user_prompt = (
            "请作为实操案例 Agent，生成一个适合学生画像的中文实操题。\n"
            f"学生画像：{json.dumps(self.profile, ensure_ascii=False)}\n{extra_note}"
            "必须只返回 JSON，不要 Markdown。JSON Schema："
            "{\"title\":\"...\",\"prompt\":\"...\",\"requirements\":[\"...\"],\"reference_answer\":\"...\"}"
            "题目要能让学生输入答案后被 AI 判题，不能只是阅读材料。"
        )
        try:
            content = self.chat(self.role_prompt(), user_prompt)
            question = self.extract_json(content)
            if not question.get("title") or not question.get("prompt"):
                raise ValueError("实操题缺少 title 或 prompt")
            question["requirements"] = question.get("requirements") or []
            question["reference_answer"] = question.get("reference_answer") or ""
            return question, self.agent_meta("生成实操案例题目")
        except Exception as exc:
            return fallback(), self.fallback_meta(f"实操题生成失败：{exc}")