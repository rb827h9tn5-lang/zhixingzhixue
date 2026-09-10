from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable
from urllib.parse import quote

from .base_agent import BaseAgent
from ..mindmap_sanitizer import normalize_mindmap_content, validate_mindmap_content
from ..local_generator import RESOURCE_LABELS


def mark_section(index: int, section: dict, content: str) -> str:
    title = str(section.get("title") or section.get("chapterTitle") or f"第 {index + 1} 章").strip()
    section_no = index + 1
    return (
        f"<!-- MA_SECTION_START index={section_no} title={quote(title, safe='')} -->\n\n"
        f"{(content or '').strip()}\n\n"
        f"<!-- MA_SECTION_END index={section_no} -->"
    )


def invalid_section_content(content: str) -> bool:
    text = (content or "").strip()
    if len(text) < 80:
        return True
    return any(
        phrase in text
        for phrase in ("未通过后端安全约束", "已停止输出", "触发后端安全约束", "请改为合规")
    )


def fallback_section_content(section: dict, is_reading: bool) -> str:
    description = str(section.get("description") or "围绕本章核心知识进行合规学习整理。").strip()
    topics = section.get("key_topics") if is_reading else section.get("sub_topics")
    topics = [str(item).strip() for item in (topics or []) if str(item).strip()]
    questions = section.get("reflection_questions") or section.get("common_mistakes") or []
    questions = [str(item).strip() for item in questions if str(item).strip()]
    topic_lines = "\n".join(f"- {topic}" for topic in topics[:5]) or "- 梳理核心概念\n- 对照示例理解\n- 完成自测巩固"
    question_label = "反思问题" if is_reading else "常见误区与自测"
    question_lines = "\n".join(f"- {item}" for item in questions[:3]) or "- 用自己的话解释本章核心概念\n- 找出一个实际场景并说明如何应用"
    return (
        f"### 本节学习目标\n\n{description}\n\n"
        f"### 核心知识点\n\n{topic_lines}\n\n"
        f"### 学习建议\n\n"
        "先理解概念边界，再结合例子或练习验证。若遇到不确定内容，优先回到知识库材料和课堂笔记进行核对。\n\n"
        f"### {question_label}\n\n{question_lines}"
    )


class CourseDocumentAgent(BaseAgent):
    """课程讲解文档 Agent：先大纲 → 并行章节 → 合并"""

    def __init__(self, profile: dict):
        super().__init__(profile, "课程讲解文档 Agent")

    def role_prompt(self) -> str:
        return (
            "你是多智能体学习系统中的【课程讲解文档 Agent】，身份是高校课程助教和教学设计专家。"
            "你负责为学生生成结构完整、内容详实的专业课程讲解文档。"
            "输出必须结合学生画像动态生成，不允许复用固定模板。"
            f"{self.guard.agent_constraints()}"
        )

    def generate(self, extra_input: str, fallback: Callable[[], str]) -> tuple[str, dict[str, Any]]:
        if not self.enabled:
            return fallback(), self.fallback_meta("未配置 API Key，已使用本地模板生成。")
        try:
            outline = self._generate_outline(extra_input)
            chapters = outline.get("chapters", [])
            if not chapters:
                raise RuntimeError("大纲未包含章节列表")

            # 预检索一次知识库上下文，各章节共享，避免重复 RAG 调用
            rag_context = self._retrieve_context("course_document", extra_input or self.profile.get("topic", ""))
            chapter_contents = [None] * len(chapters)
            with ThreadPoolExecutor(max_workers=min(len(chapters), 8)) as executor:
                future_map = {}
                for index, chapter in enumerate(chapters):
                    future = executor.submit(self._generate_chapter_with_retry, chapter, extra_input, rag_context)
                    future_map[future] = index
                for future in as_completed(future_map):
                    index = future_map[future]
                    chapter_contents[index] = future.result()

            parts = [f"# {outline.get('title', '课程讲解文档')}\n\n"]
            if outline.get("overview"):
                parts.append(f"> **概述**：{outline['overview']}\n\n---\n\n")
            for index, content in enumerate(chapter_contents):
                if content:
                    parts.append(mark_section(index, chapters[index], content))

            full_doc = "\n\n".join(parts)
            full_doc, _ = self.apply_safety(full_doc)
            return full_doc, self.agent_meta("分步并行生成讲解文档（先大纲，再并行生成各章内容）")
        except Exception as exc:
            return fallback(), self.fallback_meta(f"分步生成讲解文档失败：{exc}")

    def _generate_outline(self, extra_input: str) -> dict:
        extra_note = f"\n用户额外要求：{extra_input}" if extra_input else ""
        rag_context = self._retrieve_context("course_document", extra_input or self.profile.get("topic", ""))
        rag_section = f"\n知识库参考材料：\n{rag_context}" if rag_context else ""
        user_prompt = (
            "请作为课程设计 Agent，为学生设计一份专业课程讲解文档的详细大纲。\n"
            f"学生画像：{json.dumps(self.profile, ensure_ascii=False)}\n{extra_note}\n"
            "必须只返回 JSON，不要 Markdown，不要添加```代码块标记。\n"
            "JSON Schema：\n"
            "{\n"
            "  \"title\": \"文档标题\",\n"
            "  \"overview\": \"课程概述（2-3句话）\",\n"
            "  \"chapters\": [\n"
            "    {\n"
            "      \"title\": \"第一章标题（用中文数字编排，如 一、基础知识）\",\n"
            "      \"description\": \"本章内容简介\",\n"
            "      \"sub_topics\": [\"子主题1\", \"子主题2\"],\n"
            "      \"examples\": [\"可讲解的例子1\", \"可讲解的例子2\"],\n"
            "      \"common_mistakes\": [\"常见误区1\", \"常见误区2\"]\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "要求：\n"
            "1. 章节数量为 6-10 章，覆盖该课程的核心知识点\n"
            "2. 标题要具体、有信息量，不能是泛泛的\"引言\"\"总结\"\n"
            "3. 结合学生画像中的主题、基础水平和学习目标编排章节深度\n"
            "4. sub_topics 列出该章需要讲解的具体知识点（3-5个）\n"
            "5. examples 列出适合该章的具体行业案例或问题场景（2-3个）\n"
            "6. common_mistakes 列出学生容易出现的理解错误（2-3个）"
            f"{rag_section}"
        )
        content = self.chat(self.role_prompt(), user_prompt)
        outline = self.extract_json(content)
        if not outline.get("chapters"):
            raise ValueError("大纲 JSON 缺少 chapters 字段")
        return outline

    def _generate_chapter(self, chapter: dict, extra_input: str, rag_context: str = "") -> str:
        extra_note = f"\n用户额外要求：{extra_input}" if extra_input else ""
        if not rag_context:
            rag_context = self._retrieve_context("course_document", chapter.get("title", "") or extra_input)
        rag_section = f"\n知识库相关参考材料：\n{rag_context}" if rag_context else ""
        user_prompt = (
            "请作为课程讲师 Agent，根据给定的章节大纲，生成详细的讲解内容。\n"
            f"学生画像：{json.dumps(self.profile, ensure_ascii=False)}\n{extra_note}\n"
            f"章节标题：{chapter.get('title', '')}\n"
            f"章节简介：{chapter.get('description', '')}\n"
            f"子主题：{', '.join(chapter.get('sub_topics', []))}\n"
            f"建议讲解的例子：{', '.join(chapter.get('examples', []))}\n"
            f"常见误区：{', '.join(chapter.get('common_mistakes', []))}\n\n"
            "输出要求：\n"
            "1. 使用 Markdown 格式；不要重复输出与“章节标题”相同或高度相似的二级标题，正文可直接从导语或 ### 小节开始\n"
            "2. 直接输出文档正文，不要问候、寒暄、自称课程助教，不要写“好的，同学”“你好”“今天我们”“让我们开始”等与文档无关的课堂开场白\n"
            "3. 内容详实，每个子主题至少写 3-5 段详细讲解，总字数不少于 800 字\n"
            "4. 结合学生的基础水平，从简单到深入逐步展开\n"
            "5. 每个概念务必给出具体的代码示例或公式或案例，不能只有理论描述\n"
            "6. 指出该章节内容与前面章节的联系\n"
            "7. 最后列出常见误区及正确理解\n"
            "8. 提供 2-3 道本章节的练习题（带答案）作为自测\n"
            "9. 内容必须是与学生主题相关的专业领域知识，不能是模板化的泛泛之谈"
            f"{rag_section}"
        )
        content = self.chat(self.role_prompt(), user_prompt).strip()
        content, _ = self.apply_safety(content)
        return content

    def _generate_chapter_with_retry(self, chapter: dict, extra_input: str, rag_context: str = "") -> str:
        retry_note = ""
        last_content = ""
        for _attempt in range(3):
            retry_input = f"{extra_input}\n\n{retry_note}".strip() if retry_note else extra_input
            content = self._generate_chapter(chapter, retry_input, rag_context)
            last_content = (content or "").strip()
            if not invalid_section_content(last_content):
                return last_content
            retry_note = (
                "上一版章节内容为空、过短或被安全约束拦截。请重新生成本章："
                "只讲合规的课程知识、概念解释、公式/案例/防御性实践；不要输出拒绝说明；"
                "使用标准 Markdown，二级/三级标题必须顶格书写。"
            )
        return fallback_section_content(chapter, False)


class MindMapAgent(BaseAgent):
    """思维导图 Agent：生成 Mermaid mindmap 代码"""

    def __init__(self, profile: dict):
        super().__init__(profile, "思维导图 Agent")

    def generate(self, extra_input: str, fallback: Callable[[], str]) -> tuple[str, dict[str, Any]]:
        if not self.enabled:
            return normalize_mindmap_content(fallback(), self.profile.get("topic") or "学习主题"), self.fallback_meta("未配置 API Key，已使用本地模板生成。")
        extra_note = f"\n用户额外要求：{extra_input}" if extra_input else ""
        user_prompt = (
            "请为学生的课程主题生成可直接被 Mermaid 11 mindmap 渲染的思维导图。\n"
            f"学生画像：{json.dumps(self.profile, ensure_ascii=False)}\n{extra_note}\n"
            "硬性格式要求：\n"
            "1. 只输出一个 ```mermaid 代码块，不要输出代码块外的解释、标题或学习建议。\n"
            "2. 第一行必须是 mindmap，第二行必须是两个空格缩进的 root((主题))。\n"
            "3. 只使用两个空格表示层级缩进，不要使用 Tab。\n"
            "4. 节点文本使用中文短语，每个节点不超过 18 个汉字；禁止 Markdown 标记、编号列表、HTML、<br/>、公式、反引号和英文括号。\n"
            "5. 节点文本如需冒号、括号、分号，使用中文全角符号。\n"
            "6. 结构控制在 4-6 个一级分支、每个分支 2-4 个子节点，最多 3 层，避免节点过密或互相重叠。"
        )
        try:
            last_errors: list[str] = []
            content = ""
            for attempt in range(2):
                raw_content = self.chat(self.role_prompt(), user_prompt).strip()
                if not raw_content:
                    raise RuntimeError("empty agent response")
                content = normalize_mindmap_content(raw_content, self.profile.get("topic") or "学习主题")
                validation = validate_mindmap_content(content)
                if validation.valid:
                    content, _ = self.apply_safety(content)
                    message = "生成并校验 Mermaid 思维导图"
                    if attempt > 0:
                        message += "（已自动修复重试）"
                    return content, self.agent_meta(message)
                last_errors = validation.errors
                user_prompt = (
                    "上一版 Mermaid mindmap 未通过结构检查，请修复后重新输出。\n"
                    f"检查问题：{'；'.join(last_errors)}\n"
                    "仍然只输出一个 ```mermaid 代码块，必须以 mindmap 开头并包含 root 根节点。\n"
                    f"上一版内容：\n{raw_content}"
                )
            raise RuntimeError("；".join(last_errors) or "思维导图结构校验失败")
        except Exception as exc:
            content = normalize_mindmap_content(fallback(), self.profile.get("topic") or "学习主题")
            return content, self.fallback_meta(f"生成思维导图失败，已使用本地安全结构：{exc}")


class ExtensionReadingAgent(BaseAgent):
    """拓展阅读 Agent：先大纲 → 并行章节 → 合并"""

    def __init__(self, profile: dict):
        super().__init__(profile, "拓展阅读 Agent")

    def generate(self, extra_input: str, fallback: Callable[[], str]) -> tuple[str, dict[str, Any]]:
        if not self.enabled:
            return fallback(), self.fallback_meta("未配置 API Key，已使用本地模板生成。")
        try:
            outline = self._generate_outline(extra_input)
            sections = outline.get("sections", [])
            if not sections:
                raise RuntimeError("大纲未包含阅读章节列表")

            # 预检索一次知识库上下文，各章节共享，避免重复 RAG 调用
            rag_context = self._retrieve_context("extension_reading", extra_input or self.profile.get("topic", ""))
            section_contents = [None] * len(sections)
            with ThreadPoolExecutor(max_workers=min(len(sections), 8)) as executor:
                future_map = {}
                for index, section in enumerate(sections):
                    future = executor.submit(self._generate_section_with_retry, section, extra_input, rag_context)
                    future_map[future] = index
                for future in as_completed(future_map):
                    index = future_map[future]
                    section_contents[index] = future.result()

            parts = [f"# {outline.get('title', '拓展阅读')}\n\n"]
            if outline.get("overview"):
                parts.append(f"> **阅读指引**：{outline['overview']}\n\n---\n\n")
            for index, content in enumerate(section_contents):
                if content:
                    parts.append(mark_section(index, sections[index], content))

            full_doc = "\n\n".join(parts)
            full_doc, _ = self.apply_safety(full_doc)
            return full_doc, self.agent_meta("分步并行生成拓展阅读（先大纲，再并行生成各节内容）")
        except Exception as exc:
            return fallback(), self.fallback_meta(f"分步生成拓展阅读失败：{exc}")

    def _generate_outline(self, extra_input: str) -> dict:
        extra_note = f"\n用户额外要求：{extra_input}" if extra_input else ""
        rag_context = self._retrieve_context("extension_reading", extra_input or self.profile.get("topic", ""))
        rag_section = f"\n知识库参考材料：\n{rag_context}" if rag_context else ""
        user_prompt = (
            "请作为课程阅读导师 Agent，为学生设计一份专业课程拓展阅读材料的详细大纲。\n"
            f"学生画像：{json.dumps(self.profile, ensure_ascii=False)}\n{extra_note}\n"
            "必须只返回 JSON，不要 Markdown，不要添加```代码块标记。\n"
            "JSON Schema：\n"
            "{\n"
            "  \"title\": \"拓展阅读标题\",\n"
            "  \"overview\": \"整体阅读指引（2-3句话，说明阅读目标和预期收获）\",\n"
            "  \"sections\": [\n"
            "    {\n"
            "      \"title\": \"一、阅读主题名称（用中文数字编排）\",\n"
            "      \"description\": \"该主题简介和阅读目标\",\n"
            "      \"key_topics\": [\"核心知识点1\", \"核心知识点2\", \"核心知识点3\"],\n"
            "      \"reading_materials\": [\n"
            "        { \"title\": \"推荐阅读材料标题\", \"type\": \"论文/书籍章节/技术文档/博客文章\", \"reason\": \"推荐理由\" }\n"
            "      ],\n"
            "      \"reflection_questions\": [\"引导反思的问题1\", \"引导反思的问题2\"]\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "要求：4-6 节，覆盖核心拓展方向，标题具体有信息量。"
            f"{rag_section}"
        )
        content = self.chat(self.role_prompt(), user_prompt)
        outline = self.extract_json(content)
        if not outline.get("sections"):
            raise ValueError("大纲 JSON 缺少 sections 字段")
        return outline

    def _generate_section(self, section: dict, extra_input: str, rag_context: str = "") -> str:
        extra_note = f"\n用户额外要求：{extra_input}" if extra_input else ""
        if not rag_context:
            rag_context = self._retrieve_context("extension_reading", section.get("title", "") or extra_input)
        rag_section = f"\n知识库相关参考材料：\n{rag_context}" if rag_context else ""
        materials_text = "\n".join(
            f"- 《{m.get('title', '')}》（{m.get('type', '')}）：{m.get('reason', '')}"
            for m in (section.get("reading_materials") or [])
        )
        user_prompt = (
            "请作为课程阅读导师 Agent，根据给定的阅读章节大纲，生成详细的拓展阅读指南。\n"
            f"学生画像：{json.dumps(self.profile, ensure_ascii=False)}\n{extra_note}\n"
            f"章节标题：{section.get('title', '')}\n"
            f"核心知识点：{', '.join(section.get('key_topics', []))}\n"
            f"推荐材料：\n{materials_text}\n"
            f"反思问题：{', '.join(section.get('reflection_questions', []))}\n\n"
            "输出要求：\n"
            "1. 使用 Markdown 格式；不要重复输出与“章节标题”相同或高度相似的二级标题，正文可直接从导语或 ### 小节开始\n"
            "2. 直接输出阅读材料正文，不要问候、寒暄、自称阅读导师，不要写“好的，同学”“你好”“今天我们”“让我们开始”等与文档无关的课堂开场白\n"
            "3. 每个核心知识点至少写 2-3 段讲解，总字数不少于 600 字\n"
            "4. 对每篇推荐材料进行简要介绍\n"
            "5. 结合学生的基础水平，从入门到深入逐步组织\n"
            "6. 指出该主题与课程核心内容的关联\n"
            "7. 最后列出 2-3 个反思问题，并给出思考方向提示"
            f"{rag_section}"
        )
        content = self.chat(self.role_prompt(), user_prompt).strip()
        content, _ = self.apply_safety(content)
        return content

    def _generate_section_with_retry(self, section: dict, extra_input: str, rag_context: str = "") -> str:
        retry_note = ""
        last_content = ""
        for _attempt in range(3):
            retry_input = f"{extra_input}\n\n{retry_note}".strip() if retry_note else extra_input
            content = self._generate_section(section, retry_input, rag_context)
            last_content = (content or "").strip()
            if not invalid_section_content(last_content):
                return last_content
            retry_note = (
                "上一版章节内容为空、过短或被安全约束拦截。请重新生成本节："
                "只讲合规的拓展阅读、资料导读和反思问题；不要输出拒绝说明；"
                "使用标准 Markdown，二级/三级标题必须顶格书写。"
            )
        return fallback_section_content(section, True)
