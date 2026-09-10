from __future__ import annotations

import json
import re
from typing import Any, Callable

from .base_agent import BaseAgent


class QuizAgent(BaseAgent):
    """测评出题 Agent：生成结构化练习题库"""

    def __init__(self, profile: dict):
        super().__init__(profile, "测评出题 Agent")

    def generate(
        self, difficulty: str, focus: str, count: int, fallback: Callable[[], dict]
    ) -> tuple[dict, dict[str, Any]]:
        if not self.enabled:
            return fallback(), self.fallback_meta("未配置 API Key，已使用本地题库生成。")

        user_prompt = (
            "请作为测评出题 Agent，生成一套结构化中文练习题。\n"
            f"学生画像：{json.dumps(self.profile, ensure_ascii=False)}\n"
            f"难度：{difficulty}\n聚焦知识点：{focus or '课程核心知识'}\n题目数量：{count}\n"
            "必须只返回 JSON，不要 Markdown，不要添加```代码块标记。\n"
            "JSON Schema 如下：\n"
            "{\n"
            "  \"title\": \"练习题标题\",\n"
            "  \"questions\": [\n"
            "    {\n"
            "      \"id\": 1,\n"
            "      \"type\": \"single_choice\",\n"
            "      \"concept\": \"知识点名称\",\n"
            "      \"prompt\": \"题面描述\",\n"
            "      \"options\": [\"选项A\", \"选项B\", \"选项C\", \"选项D\"],\n"
            "      \"answer\": \"正确选项\",\n"
            "      \"hint\": \"针对性提示（不能使用固定套话）\",\n"
            "      \"explanation\": \"解析说明\"\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "重要规则：\n"
            "1. 题型必须覆盖：single_choice（单选）、multiple_choice（多选）、true_false（判断）、fill_blank（填空）、short_answer（简答）\n"
            "2. 选择题必须提供 options 数组\n"
            "3. true_false 类型的 options 必须是 [\"正确\", \"错误\"]\n"
            "4. fill_blank 的 answer 是字符串，short_answer 的 answer 是字符串\n"
            "5. multiple_choice 的 answer 是字符串数组\n"
            "6. 每道题的 hint 必须结合本题具体内容给出提示\n"
            "7. 返回前请检查：每个选择类的题目是否都有 options 数组"
        )
        try:
            content = self.chat(self.role_prompt(), user_prompt)
            quiz = self.extract_json(content)
            self._validate_quiz(quiz)
            return quiz, self.agent_meta("生成结构化题库（含 5 种题型）")
        except Exception as exc:
            return fallback(), self.fallback_meta(f"出题失败：{exc}")

    def _validate_quiz(self, quiz: dict) -> None:
        questions = quiz.get("questions") or []
        if not quiz.get("title") or not questions:
            raise ValueError("题库缺少 title 或 questions")
        for index, question in enumerate(questions, 1):
            question.setdefault("id", index)
            question.setdefault("concept", "课程核心知识")
            question.setdefault("hint", "结合本题的关键词、适用条件和常见误区思考。")
            question.setdefault("explanation", "提交后对照参考答案复盘知识点。")
            qtype = question.get("type", "")
            if qtype in {"single_choice", "multiple_choice", "true_false"} and not question.get("options"):
                if qtype == "true_false":
                    question["options"] = ["正确", "错误"]
                else:
                    prompt_text = question.get("prompt", "")
                    possible = re.findall(r'[A-D][.、．)]?\s*([^A-D\s][^，,。]*?)(?=[，,。]|\s*[A-D][.、．)]|\s*$)', prompt_text)
                    if len(possible) >= 2:
                        question["options"] = [opt.strip() for opt in possible[:4]]
                    else:
                        question["options"] = [f"选项{i}" for i in ["A", "B", "C", "D"]]
                    question["hint"] = f"{question.get('hint', '')} 注意：请从给定选项中选择正确答案。"