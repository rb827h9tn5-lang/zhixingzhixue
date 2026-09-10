from __future__ import annotations

import json
from typing import Any


# 上下文窗口默认配置
DEFAULT_TOKEN_BUDGET = 3000        # 历史消息 token 预算上限
TOKENS_PER_CHAR = 0.5              # 中英文混合的近似 token/字符比
MIN_RECENT_EXCHANGES = 2           # 至少保留的最近完整对话轮数
SUMMARY_MAX_LENGTH = 200           # 摘要的最大字符数


class ContextWindowManager:
    """短期记忆上下文窗口管理器

    功能：
    1. 在 token 预算内保留最近的对话历史
    2. 超出预算的较早对话使用 LLM 自动摘要
    3. 提供降级方案（无 LLM 时使用简单截断）
    """

    def __init__(self, qwen_client=None, token_budget: int = DEFAULT_TOKEN_BUDGET):
        self.qwen = qwen_client
        self.token_budget = token_budget

    def count_tokens(self, text: str) -> int:
        """估算文本的 token 数量

        使用近似算法：中英文混合文本平均约 0.5 token/字符
        """
        if not text:
            return 0
        return max(1, int(len(text) * TOKENS_PER_CHAR))

    def build_history_prompt(self, history: list[dict]) -> str:
        """构建历史对话上下文文本

        从后往前分配 token 预算，优先保留最近的对话。
        超出预算的较早对话将被 LLM 摘要压缩。

        Args:
            history: 对话历史列表，格式为 [{role, content}, ...]
                     role 取值为 "user" 或 "assistant"

        Returns:
            格式化的历史上下文文本，空列表时返回空字符串
        """
        if not history:
            return ""

        scored = []
        for msg in history:
            tokens = self.count_tokens(msg.get("content", ""))
            scored.append({**msg, "_tokens": tokens})

        recent = []
        summary_list = []
        budget_remaining = self.token_budget

        min_pairs = MIN_RECENT_EXCHANGES * 2

        for i in range(len(scored) - 1, -1, -1):
            msg = scored[i]
            msg_tokens = msg["_tokens"]

            if len(recent) < min_pairs:
                if msg_tokens <= budget_remaining:
                    budget_remaining -= msg_tokens
                    recent.insert(0, msg)
                else:
                    summary_list.insert(0, msg)
            else:
                if msg_tokens > budget_remaining:
                    summary_list.insert(0, msg)
                else:
                    budget_remaining -= msg_tokens
                    recent.insert(0, msg)

        parts = []

        if summary_list:
            summary = self._summarize_history(summary_list)
            parts.append(f"## 历史对话摘要（较早的对话）\n{summary}\n")

        if recent:
            history_lines = ["## 近期对话历史"]
            for msg in recent:
                role_label = "用户" if msg["role"] == "user" else "助手"
                history_lines.append(f"{role_label}：{msg['content']}")
            parts.append("\n".join(history_lines))

        return "\n\n".join(parts)

    def _summarize_history(self, exchanges: list[dict]) -> str:
        """使用 LLM 对历史对话进行摘要

        Args:
            exchanges: 需要摘要的历史对话列表

        Returns:
            摘要文本
        """
        if not exchanges:
            return ""

        if not self.qwen:
            return self._simple_summarize(exchanges)

        dialogue_lines = []
        for msg in exchanges:
            role_label = "用户" if msg["role"] == "user" else "助手"
            dialogue_lines.append(f"{role_label}：{msg['content']}")
        dialogue_text = "\n".join(dialogue_lines)

        system_prompt = (
            "你是一个对话摘要助手。请将以下对话内容压缩为一段简洁的摘要"
            f"（{SUMMARY_MAX_LENGTH}字以内），"
            "保留关键问题、核心答案和重要结论。只输出摘要文本，不要多余内容。"
        )

        try:
            summary = self.qwen.chat(system_prompt, dialogue_text)
            summary = summary.strip().strip('"').strip("'")
            if len(summary) > SUMMARY_MAX_LENGTH * 2:
                summary = summary[:SUMMARY_MAX_LENGTH] + "..."
            return summary
        except Exception:
            return self._simple_summarize(exchanges)

    def _simple_summarize(self, exchanges: list[dict]) -> str:
        """无 LLM 时的降级摘要：取每轮前 100 字拼接

        Args:
            exchanges: 需要摘要的历史对话列表

        Returns:
            摘要文本
        """
        summary_parts = []
        for msg in exchanges:
            role = "用户" if msg["role"] == "user" else "助手"
            content = msg.get("content", "")
            truncated = content[:100] + "..." if len(content) > 100 else content
            summary_parts.append(f"{role}：{truncated}")
        return "\n".join(summary_parts)