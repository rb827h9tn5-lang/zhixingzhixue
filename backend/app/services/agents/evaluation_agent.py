from __future__ import annotations

import json
from typing import Any

from .base_agent import BaseAgent


class EvaluationAgent(BaseAgent):
    """学习评估 Agent：根据答题情况生成评价和建议"""

    def __init__(self, profile: dict):
        super().__init__(profile, "学习评估 Agent")

    def evaluate(self, quiz: dict, answers: dict, details: list, score: float) -> str:
        if not self.enabled:
            return self._local_evaluation(quiz, details, score)

        wrong_items = [d for d in details if not d.get("is_correct")]
        correct_count = sum(1 for d in details if d.get("is_correct"))
        total = len(details)
        user_prompt = (
            "请作为学习评估 Agent，根据学生的答题情况给出详细的评价和建议。\n"
            f"学生画像：{json.dumps(self.profile, ensure_ascii=False)}\n"
            f"题目：{json.dumps(quiz, ensure_ascii=False)}\n"
            f"学生答案：{json.dumps(answers, ensure_ascii=False)}\n"
            f"答题详情：{json.dumps(details, ensure_ascii=False)}\n"
            f"得分：{score}/100，共 {total} 题，答对 {correct_count} 题。\n"
            f"错题概念：{[w.get('concept') for w in wrong_items]}\n"
            "请输出 Markdown 格式的评价和建议，包括：\n"
            "1. 总体表现评价\n"
            "2. 各题型的掌握情况分析\n"
            "3. 薄弱知识点及改进建议\n"
            "4. 推荐的学习资源和后续学习方向\n"
            "输出要具体、有针对性，结合学生画像给出个性化建议。"
        )
        try:
            content = self.chat(self.role_prompt(), user_prompt).strip()
            if not content:
                raise RuntimeError("empty agent response")
            content, _ = self.apply_safety(content)
            return content
        except Exception as exc:
            return self._local_evaluation(quiz, details, score)

    def _local_evaluation(self, quiz: dict, details: list, score: float) -> str:
        correct_count = sum(1 for d in details if d.get("is_correct"))
        total = len(details)
        wrong_concepts = [d.get("concept") for d in details if not d.get("is_correct") and d.get("concept")]
        parts = [
            "## 答题评价与建议\n",
            f"### 总体表现\n",
            f"本次答题得分 **{score}/100**，共 {total} 题，答对 {correct_count} 题。",
        ]
        if wrong_concepts:
            parts.append("\n### 薄弱知识点\n")
            for c in wrong_concepts:
                parts.append(f"- {c}")
            parts.append("\n建议优先复习以上知识点，回到知识学习页面查看相关讲解文档。")
        else:
            parts.append("\n### 评价\n全部答对，请继续保持学习节奏，尝试更高难度的题目。")
        parts.append("\n### 建议\n")
        parts.append("1. 将错题中的知识点添加到学习画像的易错点中，便于后续资源推荐。")
        parts.append("2. 针对薄弱知识点，建议生成对应主题的讲解文档和思维导图。")
        parts.append("3. 完成本轮学习后，可以重新进行一次测评评估，检验进步情况。")
        return "\n".join(parts)