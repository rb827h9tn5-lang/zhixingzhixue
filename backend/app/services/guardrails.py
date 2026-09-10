from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class GuardrailResult:
    allowed: bool
    warnings: list[str]
    suggestions: list[str]

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
        }


class ContentGuard:
    def __init__(self) -> None:
        self.blocked_patterns = [
            (r"(作弊|代考|替考|论文代写|绕过检测)", "疑似学术不端请求"),
            (r"(木马|钓鱼|盗号|撞库|勒索)", "疑似网络安全违规请求"),
            (r"(制毒|爆炸物|武器制造)", "疑似危险内容请求"),
        ]
        self.uncertain_markers = ["最新", "最权威", "唯一", "绝对", "100%"]

    def agent_constraints(self) -> str:
        return (
            "内容安全与防幻觉约束："
            "1. 拒绝学术不端、危险操作、违法攻击、隐私窃取等请求；"
            "2. 学术内容优先依据课程知识库、学生画像和已给上下；"
            "3. 禁止编造来源、页码、论文、实验数据、API 返回结果或不存在的引用；"
            "4. 涉及事实性判断时给出依据或限定条件，避免“唯一、绝对、100%”等强断言；"
            "5. 输出应服务于学习辅导、知识解释、练习反馈和合规实践。"
        )

    def scan_request(self, text: str) -> GuardrailResult:
        warnings = []
        suggestions = []
        safe_text = str(text) if text is not None else ""
        for pattern, message in self.blocked_patterns:
            if re.search(pattern, safe_text, flags=re.IGNORECASE):
                warnings.append(message)
                suggestions.append("请改为合规的学习辅导、概念解释或防御性实践请求。")
        return GuardrailResult(not warnings, warnings, suggestions)

    def review_content(self, content: str, source_context: str = "") -> GuardrailResult:
        warnings = []
        suggestions = []
        for pattern, message in self.blocked_patterns:
            if re.search(pattern, content or "", flags=re.IGNORECASE):
                warnings.append(f"生成内容命中安全风险：{message}")
                suggestions.append("应拒绝或改写为合规学习辅导内容。")
        for marker in self.uncertain_markers:
            if marker in (content or ""):
                warnings.append(f"发现强断言词：{marker}")
                suggestions.append("建议补充来源、限定条件或不确定性说明。")
        if source_context and not any(token in (content or "") for token in ["来源", "参考", "依据", "引用"]):
            warnings.append("内容可能缺少来源说明")
            suggestions.append("在关键知识点后补充课程资料来源或 RAG 引用。")
        return GuardrailResult(
            not any(warning.startswith("生成内容命中安全风险") for warning in warnings),
            warnings,
            suggestions,
        )

    def apply_output_guard(self, content: str, source_context: str = "") -> tuple[str, GuardrailResult]:
        result = self.review_content(content, source_context)
        if not result.allowed:
            return (
                "该内容未通过后端安全约束，已停止输出。请改为合规的学习辅导、概念解释或防御性实践请求。",
                result,
            )
        return content, result
