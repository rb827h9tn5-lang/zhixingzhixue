from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable
from urllib.parse import quote

from .agents.orchestrator import AgentOrchestrator
from .ai_client import QwenClient
from .guardrails import ContentGuard
from .local_generator import RESOURCE_LABELS
from .mindmap_sanitizer import normalize_mindmap_content


class StudyResourceAgent:
    def __init__(self, profile: dict, user_id: int | None = None):
        self.profile = profile
        self.user_id = user_id
        self.guard = ContentGuard()
        self.qwen = QwenClient()
        self.use_remote = os.getenv("USE_REMOTE_LLM", "auto").lower() != "never"

    @property
    def enabled(self) -> bool:
        return self.use_remote and self.qwen.enabled

    def _retrieve_context(self, resource_type: str, query_hint: str = "") -> str:
        """根据资源类型从知识库检索相关上下文，用于注入生成 prompt

        Args:
            resource_type: 资源类型（如 course_document, mind_map 等）
            query_hint: 检索提示词（如用户额外输入或主题）

        Returns:
            知识库上下文文本，无结果时返回空字符串
        """
        if not self.user_id:
            return ""
        from app.services.rag_config import  ENABLE_RAG_OPTIMIZATION, getRagMode, getRagPolicy, shouldUseRAG, detectResourceType
        if not ENABLE_RAG_OPTIMIZATION:
            return ""

        # 映射后端资源类型到 rag_config 中的资源类型
        type_map = {
            "course_document": "explanation_doc",
            "mind_map": "mindmap",
            "exercise_bank": "question_bank",
            "extension_reading": "extended_reading",
            "coding_case": "practical_case",
            "multimedia_video": "teaching_video",
            "ppt_deck": "ppt_generation",
        }
        rag_resource_type = type_map.get(resource_type, "normal_chat")
        if not shouldUseRAG(query_hint or self.profile.get("topic", ""), [], rag_resource_type):
            return ""

        rag_mode = getRagMode(rag_resource_type, query_hint)
        if rag_mode == "none":
            return ""
        policy = getRagPolicy(rag_resource_type)
        if not policy.get("useRag", False):
            return ""

        try:
            from ..routes.learning import retrieve_knowledge_context
            context, sources = retrieve_knowledge_context(
                self.user_id,
                query_hint or self.profile.get("topic", "") or "课程核心知识",
                mode=rag_mode,
                timeout_ms=policy.get("timeoutMs", 3000),
            )
            return context
        except Exception as exc:
            import sys
            print(f"[study_agent] _retrieve_context error: {exc}", file=sys.stderr, flush=True)
            return ""

    @staticmethod
    def _mark_section(index: int, section: dict, content: str) -> str:
        title = str(section.get("title") or section.get("chapterTitle") or f"第 {index + 1} 章").strip()
        section_no = index + 1
        return (
            f"<!-- MA_SECTION_START index={section_no} title={quote(title, safe='')} -->\n\n"
            f"{(content or '').strip()}\n\n"
            f"<!-- MA_SECTION_END index={section_no} -->"
        )

    @staticmethod
    def _invalid_section_content(content: str) -> bool:
        text = (content or "").strip()
        if len(text) < 80:
            return True
        return any(
            phrase in text
            for phrase in ("未通过后端安全约束", "已停止输出", "触发后端安全约束", "请改为合规")
        )

    @staticmethod
    def _fallback_section_content(section: dict, is_reading: bool) -> str:
        title = str(section.get("title") or "本章学习内容").strip()
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

    def _generate_section_with_retry(self, section: dict, extra_input: str, is_reading: bool, rag_context: str = "") -> str:
        retry_note = ""
        last_content = ""
        for _attempt in range(3):
            retry_input = f"{extra_input}\n\n{retry_note}".strip() if retry_note else extra_input
            content = (
                self._generate_reading_section(section, retry_input, rag_context)
                if is_reading
                else self._generate_chapter_content(section, retry_input, rag_context)
            )
            last_content = (content or "").strip()
            if not self._invalid_section_content(last_content):
                return last_content
            retry_note = (
                "上一版章节内容为空、过短或被安全约束拦截。请重新生成本章："
                "只讲合规的课程知识、概念解释、公式/案例/防御性实践；不要输出拒绝说明；"
                "使用标准 Markdown，二级/三级标题必须顶格书写。"
            )
        return self._fallback_section_content(section, is_reading)

    @property
    def orchestrator(self) -> AgentOrchestrator:
        """获取多智能体编排器实例（组合模式，保持向后兼容）"""
        return AgentOrchestrator(self.profile)

    def generate_resource(self, resource_type: str, fallback: Callable[[], str], extra_input: str = "") -> tuple[str, dict[str, Any]]:
        _start = time.time()
        if not self.enabled:
            return fallback(), self._fallback_meta("未配置 DASHSCOPE_API_KEY 或 USE_REMOTE_LLM=never，已使用本地模板生成。")

        # 优先使用多智能体编排器（支持 course_document、mind_map、extension_reading）
        orchestrator_supported = {"course_document", "mind_map", "extension_reading"}
        if resource_type in orchestrator_supported:
            content, meta = self.orchestrator.dispatch_resource(resource_type, fallback, extra_input)
            meta["duration_seconds"] = round(time.time() - _start, 1)
            return content, meta

        # 教学视频 → 路由到 MultimediaAgent（调用文生视频 API）
        if resource_type == "multimedia_video":
            content, meta = self.orchestrator.dispatch_multimedia_video(extra_input, fallback)
            meta["duration_seconds"] = round(time.time() - _start, 1)
            return content, meta

        label = RESOURCE_LABELS.get(resource_type, resource_type)
        extra_note = f"\n用户额外要求：{extra_input}" if extra_input else ""
        system_prompt = self._system_prompt()
        user_prompt = (
            f"请作为学习资源生成，为学生生成\u201c{label}\u201d。\n"
            f"学生画像：{json.dumps(self.profile, ensure_ascii=False)}\n"
            f"资源类型：{resource_type}\n"
            f"输出要求：{self._resource_instruction(resource_type)}\n{extra_note}"
            "必须生成具体内容，避免空泛模板；需要结合学生目标、基础、风格和短板。"
        )
        try:
            content = self._chat(system_prompt, user_prompt).strip()
            if not content:
                raise RuntimeError("empty agent response")
            if resource_type == "mind_map":
                content = normalize_mindmap_content(content, self.profile.get("topic") or "学习主题")
            content, _ = self.guard.apply_output_guard(content)
            meta = self._agent_meta()
            meta["duration_seconds"] = round(time.time() - _start, 1)
            return content, meta
        except Exception as exc:
            meta = self._fallback_meta(f"Agent 生成失败，已回退本地模板：{exc}")
            meta["duration_seconds"] = round(time.time() - _start, 1)
            return fallback(), meta

    def plan_path(self, context: dict | None = None) -> str:
        """基于学生画像和上下文，让 LLM 动态生成个性化学习路径

        当 LLM 不可用或生成失败时，回退到 LocalStudyGenerator 的静态模板。
        """
        if not self.enabled:
            from .local_generator import LocalStudyGenerator
            return LocalStudyGenerator(self.profile).plan_path(context)

        context = context or {}
        quizzes = context.get("quiz_results") or []
        documents = context.get("knowledge_documents") or []
        resources = context.get("resources") or []

        wrong_points_list = []
        for q in quizzes:
            wrong = q.get("wrong_points") or q.get("weak_points") or ""
            if wrong:
                wrong_points_list.append(wrong)
        wrong_points = "；".join(wrong_points_list[:5]) or self.profile.get("weak_points") or "暂无明确短板"
        recent_scores = [float(q.get("score") or 0) for q in quizzes[:3]]
        avg_score = round(sum(recent_scores) / len(recent_scores), 1) if recent_scores else None
        doc_titles = [d.get("title", "未命名") for d in documents[:8]]
        knowledge_hint = "；".join(doc_titles) if doc_titles else "暂无知识库材料"
        resource_types = {r.get("resource_type") for r in resources}
        available_labels = [RESOURCE_LABELS.get(t, t) for t in sorted(resource_types)]
        available_resources = "、".join(available_labels) if available_labels else "暂无已生成资源"

        system_prompt = (
            "你是多智能体学习系统中的学习路径规划 Agent，身份是高校课程助教和学习设计师。"
            "你需要根据学生画像和上下文信息，为每个学生生成独一无二的个性化学习路径。"
            "不允许输出固定模板或套话，必须根据学生实际情况动态编排。"
            f"{self.guard.agent_constraints()}"
        )

        user_prompt = (
            f"请为以下学生生成一份完整的动态学习路径。\n\n"
            f"## 学生画像\n"
            f"- 课程主题：{self.profile.get('topic', '未知')}\n"
            f"- 专业：{self.profile.get('major', '未知')}\n"
            f"- 知识水平：{self.profile.get('knowledge_level', '未知')}\n"
            f"- 学习目标：{self.profile.get('learning_goal', '未设定')}\n"
            f"- 学习风格：{self.profile.get('learning_style', '混合型')}\n"
            f"- 认知偏好：{self.profile.get('cognitive_preference', '未设定')}\n"
            f"- 可用时间：{self.profile.get('time_availability', '未设定')}\n"
            f"- 已识别短板：{wrong_points}\n"
            f"- 学习驱动力：{self.profile.get('motivation_driver', '未设定')}\n\n"
            f"## 学习上下文\n"
            f"- 最近测评均分：{avg_score if avg_score is not None else '暂无测评记录'}\n"
            f"- 知识库材料：{knowledge_hint}\n"
            f"- 已生成资源类型：{available_resources}\n"
            # Gap 2 改进：注入已学/未学知识点概览
            f"{self._format_learned_knowledge(context)}\n\n"
            f"## 输出要求\n"
            f"请严格按照以下格式输出 Markdown 学习路径，确保格式完全匹配：\n\n"
            f"## [学习路径标题]\n\n"
            f"- 课程主题：{self.profile.get('topic', '未知')}\n"
            f"- 学习目标：{self.profile.get('learning_goal', '未设定')}\n"
            f"- 当前基础：{self.profile.get('knowledge_level', '未知')}\n"
            f"- 学习风格：{self.profile.get('learning_style', '混合型')}\n"
            f"- 可用时间：{self.profile.get('time_availability', '未设定')}\n"
            f"- 最近测评均分：{avg_score if avg_score is not None else '暂无测评记录'}\n"
            f"- 已识别短板：{wrong_points}\n"
            f"- 动态策略：[根据测评成绩说明本次路径的侧重点]\n\n"
            f"然后输出 5-7 个步骤，每个步骤格式如下：\n\n"
            f"### 第N步：[步骤标题]\n"
            f"- 时间：[预估时间]\n"
            f"- 学习目标：[该步骤要达成的具体目标]\n"
            f"- 学习任务：[具体做什么]\n"
            f"- 操作入口：[引导到平台哪个功能]\n"
            f"- 使用资源：[利用已生成的 {available_resources} 或建议生成新资源]\n"
            f"- 产出物：[完成该步骤后有什么产出]\n"
            f"- 完成标准：[如何判断这一步完成]\n\n"
            f"严格要求：\n"
            f"1. 步骤的先后顺序和内容必须根据该学生的知识水平、短板和测评成绩动态决定\n"
            f"2. 不能输出固定模板，每个学生的路径必须不同\n"
            f"3. 操作入口必须是平台真实功能：知识学习、测评评估、智能辅导、知识库管理\n"
            f"4. 每步的完成标准应可量化或可明确判断\n"
            f"5. 第1步最好从诊断或基础开始，最后一步最好以复测收尾\n"
            f"6. 步骤数量控制在 5-7 步\n"
            f"7. 步骤标题不要用编号（第N步已包含编号），直接写标题内容\n"
            f'8. 不需要输出”下一轮更新规则”或类似章节\n'
            f'9. 使用资源中资源类别名使用中文，禁止使用英文类别名\n'
            f'10. 平台只有以下6种资源类型：讲解文档、思维导图、练习题库、拓展阅读、实操案例、教学视频，且都是知识学习里的功能页。不允许出现这6种之外的任何资源类型（如multimedia_script、动画、视频脚本等都不存在）'
        )

        try:
            content = self._chat(system_prompt, user_prompt).strip()
            if not content:
                raise RuntimeError("empty agent response")
            content, _ = self.guard.apply_output_guard(content)
            if len(content) < 100:
                raise RuntimeError("generated path too short")
            return content
        except Exception:
            from .local_generator import LocalStudyGenerator
            return LocalStudyGenerator(self.profile).plan_path(context)

    def _generate_document(self, extra_input: str, fallback: Callable[[], str]) -> tuple[str, dict[str, Any]]:
        """分步生成讲解文档：先获取大纲，再并行生成各章详细内容，最后合并"""
        try:
            # Step 1: 生成文档大纲
            outline = self._generate_document_outline(extra_input)
            chapters = outline.get("chapters", [])
            if not chapters:
                raise RuntimeError("大纲未包含章节列表")

            # Step 2: 预检索一次知识库上下文，各章节共享，避免重复 RAG 调用
            rag_context = self._retrieve_context("course_document", extra_input or self.profile.get("topic", ""))
            # 并行生成各章详细内容
            chapter_contents = [None] * len(chapters)
            with ThreadPoolExecutor(max_workers=min(len(chapters), 8)) as executor:
                future_map = {}
                for index, chapter in enumerate(chapters):
                    future = executor.submit(self._generate_section_with_retry, chapter, extra_input, False, rag_context)
                    future_map[future] = index
                for future in as_completed(future_map):
                    index = future_map[future]
                    chapter_contents[index] = future.result()

            full_doc_parts = []
            full_doc_parts.append(f"# {outline.get('title', '课程讲解文档')}\n\n")
            if outline.get("overview"):
                full_doc_parts.append(f"> **概述**：{outline['overview']}\n\n---\n\n")
            for index, content in enumerate(chapter_contents):
                if content:
                    full_doc_parts.append(self._mark_section(index, chapters[index], content))

            full_doc = "\n\n".join(full_doc_parts)
            full_doc, _ = self.guard.apply_output_guard(full_doc)
            return full_doc, self._agent_meta()
        except Exception as exc:
            return fallback(), self._fallback_meta(f"Agent 分步生成讲解文档失败，已回退本地模板：{exc}")

    def _generate_document_outline(self, extra_input: str) -> dict:
        """第一轮：生成讲解文档的章节大纲（JSON 格式）"""
        extra_note = f"\n用户额外要求：{extra_input}" if extra_input else ""
        rag_context = self._retrieve_context("course_document", extra_input or self.profile.get("topic", ""))
        rag_section = f"\n知识库参考材料：\n{rag_context}" if rag_context else ""
        system_prompt = self._system_prompt()
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
        content = self._chat(system_prompt, user_prompt)
        outline = self._extract_json(content)
        if not outline.get("chapters"):
            raise ValueError("大纲 JSON 缺少 chapters 字段")
        return outline

    def _generate_chapter_content(self, chapter: dict, extra_input: str, rag_context: str = "") -> str:
        """第二轮：根据大纲中的一个章节，生成详细的 Markdown 讲解内容"""
        extra_note = f"\n用户额外要求：{extra_input}" if extra_input else ""
        if not rag_context:
            rag_context = self._retrieve_context("course_document", chapter.get("title", "") or extra_input)
        rag_section = f"\n知识库相关参考材料：\n{rag_context}" if rag_context else ""
        system_prompt = self._system_prompt()
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
            "3. 每个章节的总字数控制在 800-1200 字之间，内容精炼，突出重点\n"
            "4. 结合学生的基础水平，从简单到深入逐步展开\n"
            "5. 每个概念务必给出具体的代码示例或公式或案例，不能只有理论描述\n"
            "6. 指出该章节内容与前面章节的联系\n"
            "7. 最后列出常见误区及正确理解\n"
            "8. 提供 2-3 道本章节的练习题（带答案）作为自测\n"
            "9. 内容必须是与学生主题相关的专业领域知识，不能是模板化的泛泛之谈"
            f"{rag_section}"
        )
        content = self._chat(system_prompt, user_prompt).strip()
        content, _ = self.guard.apply_output_guard(content)
        return content

    def _generate_reading(self, extra_input: str, fallback: Callable[[], str]) -> tuple[str, dict[str, Any]]:
        """分步生成拓展阅读：先获取大纲，再并行生成各节详细内容，最后合并"""
        try:
            # Step 1: 生成阅读大纲
            outline = self._generate_reading_outline(extra_input)
            sections = outline.get("sections", [])
            if not sections:
                raise RuntimeError("大纲未包含阅读章节列表")

            # Step 2: 预检索一次知识库上下文，各章节共享，避免重复 RAG 调用
            rag_context = self._retrieve_context("extension_reading", extra_input or self.profile.get("topic", ""))
            # 并行生成各节详细内容
            section_contents = [None] * len(sections)
            with ThreadPoolExecutor(max_workers=min(len(sections), 8)) as executor:
                future_map = {}
                for index, section in enumerate(sections):
                    future = executor.submit(self._generate_section_with_retry, section, extra_input, True, rag_context)
                    future_map[future] = index
                for future in as_completed(future_map):
                    index = future_map[future]
                    section_contents[index] = future.result()

            full_doc_parts = []
            full_doc_parts.append(f"# {outline.get('title', '拓展阅读')}\n\n")
            if outline.get("overview"):
                full_doc_parts.append(f"> **阅读指引**：{outline['overview']}\n\n---\n\n")
            for index, content in enumerate(section_contents):
                if content:
                    full_doc_parts.append(self._mark_section(index, sections[index], content))

            full_doc = "\n\n".join(full_doc_parts)
            full_doc, _ = self.guard.apply_output_guard(full_doc)
            return full_doc, self._agent_meta()
        except Exception as exc:
            return fallback(), self._fallback_meta(f"Agent 分步生成拓展阅读失败，已回退本地模板：{exc}")

    def _generate_reading_outline(self, extra_input: str) -> dict:
        """第一轮：生成拓展阅读的章节大纲（JSON 格式）"""
        extra_note = f"\n用户额外要求：{extra_input}" if extra_input else ""
        rag_context = self._retrieve_context("extension_reading", extra_input or self.profile.get("topic", ""))
        rag_section = f"\n知识库参考材料：\n{rag_context}" if rag_context else ""
        system_prompt = self._system_prompt()
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
            "        { \"title\": \"推荐阅读材料标题\", \"type\": \"论文/书籍章节/技术文档/博客文章\", \"reason\": \"推荐理由（说明该材料对理解主题的帮助）\" }\n"
            "      ],\n"
            "      \"reflection_questions\": [\"引导反思的问题1\", \"引导反思的问题2\", \"引导反思的问题3\"]\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "要求：\n"
            "1. 阅读章节数量为 4-6 节，覆盖该课程的核心拓展方向\n"
            "2. 每个章节的标题要具体、有信息量，不能是泛泛的\"阅读材料\"\n"
            "3. 结合学生画像中的主题、基础水平和学习目标编排阅读深度\n"
            "4. key_topics 列出该节阅读需要关注的核心知识点（3-4个）\n"
            "5. reading_materials 每节推荐 2-4 篇具体材料（论文/书籍/文档等），给出具体标题和推荐理由\n"
            "6. reflection_questions 设计 2-3 个能引导学生深入思考的问题\n"
            "7. 阅读材料应包含经典文献和前沿资料，兼顾理论深度和实践指导"
            f"{rag_section}"
        )
        content = self._chat(system_prompt, user_prompt)
        outline = self._extract_json(content)
        if not outline.get("sections"):
            raise ValueError("大纲 JSON 缺少 sections 字段")
        return outline

    def _generate_reading_section(self, section: dict, extra_input: str, rag_context: str = "") -> str:
        """第二轮：根据大纲中的一个阅读章节，生成详细的 Markdown 拓展阅读内容"""
        extra_note = f"\n用户额外要求：{extra_input}" if extra_input else ""
        if not rag_context:
            rag_context = self._retrieve_context("extension_reading", section.get("title", "") or extra_input)
        rag_section = f"\n知识库相关参考材料：\n{rag_context}" if rag_context else ""
        system_prompt = self._system_prompt()
        materials_text = "\n".join(
            f"- 《{m.get('title', '')}》（{m.get('type', '')}）：{m.get('reason', '')}"
            for m in (section.get("reading_materials") or [])
        )
        user_prompt = (
            "请作为课程阅读导师 Agent，根据给定的阅读章节大纲，生成详细的拓展阅读指南。\n"
            f"学生画像：{json.dumps(self.profile, ensure_ascii=False)}\n{extra_note}\n"
            f"章节标题：{section.get('title', '')}\n"
            f"章节简介：{section.get('description', '')}\n"
            f"核心知识点：{', '.join(section.get('key_topics', []))}\n"
            f"推荐材料：\n{materials_text}\n"
            f"反思问题：{', '.join(section.get('reflection_questions', []))}\n\n"
            "输出要求：\n"
            "1. 使用 Markdown 格式；不要重复输出与“章节标题”相同或高度相似的二级标题，正文可直接从导语或 ### 小节开始\n"
            "2. 直接输出阅读材料正文，不要问候、寒暄、自称阅读导师，不要写“好的，同学”“你好”“今天我们”“让我们开始”等与文档无关的课堂开场白\n"
            "3. 内容详实，每个核心知识点至少写 2-3 段讲解，总字数不少于 600 字\n"
            "4. 对每篇推荐材料进行简要介绍，说明阅读重点、需要关注的关键内容和学习方法\n"
            "5. 结合学生的基础水平，从入门到深入逐步组织阅读顺序\n"
            "6. 指出该主题与课程核心内容的关联\n"
            "7. 最后列出 2-3 个反思问题，并给出思考方向提示\n"
            "8. 内容必须是与学生主题相关的专业领域知识，不能是模板化的泛泛之谈"
            f"{rag_section}"
        )
        content = self._chat(system_prompt, user_prompt).strip()
        content, _ = self.guard.apply_output_guard(content)
        return content

    def generate_structured_quiz(
        self,
        difficulty: str,
        focus: str,
        count: int,
        fallback: Callable[[], dict],
        weak_points_summary: str = "",
        allowed_knowledge_points: list[dict] | None = None,
    ) -> tuple[dict, dict[str, Any]]:
        _start = time.time()
        if not self.enabled:
            return fallback(), self._fallback_meta("未配置 DASHSCOPE_API_KEY 或 USE_REMOTE_LLM=never，已使用本地题库生成。")

        try:
            # Phase 1: 先出题纲 —— 快速 LLM 调用，只确定每道题的题型和知识点
            plan = self._generate_question_plan(
                difficulty,
                focus,
                count,
                weak_points_summary=weak_points_summary,
                allowed_knowledge_points=allowed_knowledge_points,
            )
            if not plan:
                raise ValueError("题目规划为空")
        except Exception as exc:
            return fallback(), self._fallback_meta(f"题目规划失败，已回退本地题库：{exc}")

        # Phase 2: 并行生成各题（同讲解文档的分步并行模式）
        questions: dict[int, dict] = {}
        with ThreadPoolExecutor(max_workers=min(len(plan), 8)) as executor:
            future_map = {
                executor.submit(self._generate_single_question, item, index, difficulty, focus,
                                weak_points_summary): index
                for index, item in enumerate(plan, 1)
            }
            for future in as_completed(future_map):
                index = future_map[future]
                try:
                    questions[index] = future.result()
                except Exception:
                    questions[index] = None  # 单题失败不影响其他题

        # Phase 3: 合并校验
        valid_questions = [q for i in range(1, len(plan) + 1) if (q := questions.get(i)) is not None]
        if not valid_questions:
            return fallback(), self._fallback_meta("所有题目生成失败，已回退本地题库")

        quiz = {
            "title": f"{focus or '课程核心知识'} - {difficulty}练习题",
            "questions": valid_questions,
        }
        self._validate_quiz(quiz)
        meta = self._agent_meta()
        meta["duration_seconds"] = round(time.time() - _start, 1)
        return quiz, meta

    def _generate_question_plan(self, difficulty: str, focus: str, count: int,
                                  weak_points_summary: str = "",
                                  allowed_knowledge_points: list[dict] | None = None) -> list[dict]:
        """快速生成题目规划：每道题的题型和考察知识点"""
        system_prompt = self._system_prompt()
        weak_note = f"\n历史薄弱点（出题时请优先覆盖）：{weak_points_summary}" if weak_points_summary else ""
        allowed_note = ""
        if allowed_knowledge_points:
            allowed_note = (
                "\n允许使用的真实知识点（只能从此列表选择 id 和 name）："
                f"{json.dumps(allowed_knowledge_points, ensure_ascii=False)}\n"
            )
        user_prompt = (
            "请作为测评出题 Agent，为学生规划一份结构化练习题的题目清单。\n"
            f"学生画像：{json.dumps(self.profile, ensure_ascii=False)}\n"
            f"难度：{difficulty}\n聚焦知识点：{focus or '课程核心知识'}\n题目数量：{count}\n"
            f"{weak_note}{allowed_note}"
            "必须只返回 JSON 数组，不要 Markdown，不要```代码块标记。\n"
            "格式如下：\n"
            '[\n'
            '  {"type": "single_choice", "concept": "知识点名称", "primary_knowledge_point_id": 1},\n'
            '  {"type": "multiple_choice", "concept": "知识点名称", "primary_knowledge_point_id": 2},\n'
            '  {"type": "true_false", "concept": "知识点名称", "primary_knowledge_point_id": 3},\n'
            '  {"type": "fill_blank", "concept": "知识点名称", "primary_knowledge_point_id": 4},\n'
            '  {"type": "short_answer", "concept": "知识点名称", "primary_knowledge_point_id": 5}\n'
            "]\n"
            "重要规则：\n"
            f"1. 生成恰好 {count} 道题\n"
            "2. 题型从以下5种中选取：single_choice（单选）、multiple_choice（多选）、true_false（判断）、fill_blank（填空）、short_answer（简答）\n"
            "3. 当数量 >= 5 时覆盖全部5种；数量 < 5 时尽可能多样化\n"
            "4. concept 必须是具体的知识点名称，不能为空\n"
            "5. 概念应该多样化，覆盖不同的知识点\n"
            "6. 如果提供了允许知识点列表，primary_knowledge_point_id 和 concept 必须来自同一条记录；"
            "不得创建列表之外的知识点\n"
        )
        content = self._chat(system_prompt, user_prompt)
        plan = self._extract_json(content)
        if not isinstance(plan, list) or not plan:
            raise ValueError("题目规划格式无效")
        return plan[:count]

    def _generate_single_question(self, plan_item: dict, index: int, difficulty: str, focus: str,
                                    weak_points_summary: str = "") -> dict:
        """根据题目规划生成一道具体的题目"""
        qtype = plan_item.get("type", "single_choice")
        concept = plan_item.get("concept", focus or "课程核心知识")
        rag_context = self._retrieve_context("exercise_bank", concept)
        rag_section = f"\n知识库参考材料（题目必须基于以下内容）：\n{rag_context}" if rag_context else ""

        type_schemas = {
            "single_choice": (
                '{"type":"single_choice","concept":"知识点","prompt":"题面","options":["A","B","C","D"],'
                '"answer":"正确选项","hint":"针对性提示","explanation":"解析"}'
            ),
            "multiple_choice": (
                '{"type":"multiple_choice","concept":"知识点","prompt":"题面","options":["A","B","C","D"],'
                '"answer":["A","B"],"hint":"针对性提示","explanation":"解析"}'
            ),
            "true_false": (
                '{"type":"true_false","concept":"知识点","prompt":"判断题面",'
                '"options":["正确","错误"],"answer":"正确","hint":"针对性提示","explanation":"解析"}'
            ),
            "fill_blank": (
                '{"type":"fill_blank","concept":"知识点","prompt":"填空题面___",'
                '"options":[],"answer":"正确答案","hint":"针对性提示","explanation":"解析"}'
            ),
            "short_answer": (
                '{"type":"short_answer","concept":"知识点","prompt":"简答题面",'
                '"options":[],"answer":"参考答案","hint":"针对性提示","explanation":"解析"}'
            ),
        }

        system_prompt = self._system_prompt()
        weak_note = f"\n历史薄弱点参考（若本题考察的知识点在以下列表中，应设计为重点考察题）：{weak_points_summary}" if weak_points_summary else ""
        user_prompt = (
            "请作为测评出题 Agent，生成一道结构化中文练习题。\n"
            f"学生画像：{json.dumps(self.profile, ensure_ascii=False)}\n"
            f"难度：{difficulty}\n聚焦知识点：{focus or '课程核心知识'}\n"
            f"题目类型：{qtype}\n考察概念：{concept}\n"
            f"{weak_note}"
            "必须只返回 JSON，不要 Markdown，不要添加```代码块标记。\n"
            f"JSON Schema 如下：\n{type_schemas.get(qtype, type_schemas['single_choice'])}\n"
            "重要规则：\n"
            "1. prompt 必须是一个完整的题目描述\n"
            "2. 选择题型必须提供 options 数组，且至少包含 2 个选项\n"
            "3. true_false 的 options 必须是 [\"正确\", \"错误\"]\n"
            "4. fill_blank 和 short_answer 的 options 为空数组 []\n"
            "5. multiple_choice 的 answer 是字符串数组\n"
            "6. hint 必须结合本题具体内容给出针对性提示，不能是通用模板\n"
            "7. explanation 要详细说明为什么对/错\n"
            "8. 返回前请检查 options 是否满足要求\n"
            f"{rag_section}"
        )
        content = self._chat(system_prompt, user_prompt)
        question = self._extract_json(content)
        question["primary_knowledge_point_id"] = plan_item.get("primary_knowledge_point_id")
        question["id"] = index
        return question

    def generate_coding_case_question(self, fallback: Callable[[], dict], extra_input: str = "") -> tuple[dict, dict[str, Any]]:
        _start = time.time()
        if not self.enabled:
            return fallback(), self._fallback_meta("未配置 DASHSCOPE_API_KEY 或 USE_REMOTE_LLM=never，已使用本地实操题生成。")

        extra_note = f"\n用户额外要求：{extra_input}" if extra_input else ""
        rag_context = self._retrieve_context("coding_case", extra_input or self.profile.get("topic", ""))
        rag_section = f"\n知识库参考材料：\n{rag_context}" if rag_context else ""
        system_prompt = self._system_prompt()
        user_prompt = (
            "请作为实操案例 Agent，生成一个适合学生画像的中文实操题。\n"
            f"学生画像：{json.dumps(self.profile, ensure_ascii=False)}\n{extra_note}{rag_section}"
            "必须只返回 JSON，不要 Markdown。JSON Schema："
            "{\"title\":\"...\",\"prompt\":\"...\",\"requirements\":[\"...\"],\"reference_answer\":\"...\"}"
            "题目要能让学生输入答案后被 AI 判题，不能只是阅读材料。"
        )
        try:
            content = self._chat(system_prompt, user_prompt)
            question = self._extract_json(content)
            if not question.get("title") or not question.get("prompt"):
                raise ValueError("实操题缺少 title 或 prompt")
            question["requirements"] = question.get("requirements") or []
            question["reference_answer"] = question.get("reference_answer") or ""
            meta = self._agent_meta()
            meta["duration_seconds"] = round(time.time() - _start, 1)
            return question, meta
        except Exception as exc:
            meta = self._fallback_meta(f"Agent 实操题生成失败，已回退本地题目：{exc}")
            meta["duration_seconds"] = round(time.time() - _start, 1)
            return fallback(), meta

    def grade_coding_case(self, question: dict, answer: str) -> dict:
        """用 AI 对实操案例答案进行判题评分"""
        if not self.enabled:
            return self._local_grade_coding_case(question, answer)
        system_prompt = (
            "你是一个专业的编程实操题判题助手。请根据题目要求和参考答案，对学生的答案进行评分。\n"
            f"{self.guard.agent_constraints()}"
        )
        user_prompt = (
            f"## 题目\n{json.dumps(question, ensure_ascii=False)}\n\n"
            f"## 学生答案\n{answer}\n\n"
            "请从以下维度评分（每题满分100分，60分及格）：\n"
            "1. 代码正确性（是否能正确运行并得到预期结果）\n"
            "2. 思路合理性（解题思路是否清晰，算法选择是否恰当）\n"
            "3. 代码质量（是否符合编码规范，是否有良好的注释和结构）\n"
            "4. 完整性（是否覆盖了题目要求的所有要点）\n\n"
            "必须只返回 JSON，不要 Markdown。JSON Schema：\n"
            '{"score": 0-100, "is_passed": true/false, "analysis": "评分分析（中文，可使用 Markdown 格式）", "reference_answer": "参考答案文本，使用 Markdown 代码块格式，便于前端渲染"}'
        )
        try:
            content = self._chat(system_prompt, user_prompt)
            result = self._extract_json(content)
            result.setdefault("score", 0)
            result.setdefault("is_passed", result.get("score", 0) >= 60)
            result.setdefault("analysis", "")
            # 优先使用题目自带的参考答案（包含完整结构化代码），
            # AI 返回的分析中可能摘录不完整的代码片段。
            q_ra = question.get("reference_answer", "")
            ai_ra = result.get("reference_answer", "")
            source_ra = q_ra if q_ra else ai_ra
            result["reference_answer"] = self._format_reference_answer(source_ra)
            return result
        except Exception:
            return self._local_grade_coding_case(question, answer)

    @staticmethod
    def _format_reference_answer(ra: str) -> str:
        """将参考答案格式化为 readable Markdown"""
        if not ra:
            return ""
        # 尝试 JSON 解析 → 转为代码块＋说明
        try:
            parsed = json.loads(ra)
            if isinstance(parsed, dict):
                lines = []
                for k, v in parsed.items():
                    label = k.replace("_", " ").replace("-", " ").title()
                    lines.append(f"**{label}**\n```python\n{v}\n```")
                return "\n\n".join(lines)
            return f"```python\n{ra}\n```"
        except (json.JSONDecodeError, TypeError):
            # 已经在 Markdown 中或纯文本
            return ra

    @staticmethod
    def _local_grade_coding_case(question: dict, answer: str) -> dict:
        """本地关键词匹配判题（AI 不可用时的兜底）"""
        from .local_generator import LocalStudyGenerator
        return LocalStudyGenerator({}).grade_coding_case(question, answer)

    def judge_open_answer(self, question: dict, user_answer: str) -> float | None:
        """用 LLM 判断填空题/简答题答案的语义正确性

        返回:
            1.0 — 完全正确
            0.5 — 部分正确
            0.0 — 错误
            None — LLM 不可用或调用失败，由调用方走本地回退
        """
        if not self.enabled:
            return None
        expected = question.get("answer", "")
        if not user_answer or not expected:
            return None
        title = question.get("concept", "")
        explanation = question.get("explanation", "")
        system_prompt = (
            "你是一个严谨的判题助手。你的任务是根据题目和参考答案，判断学生答案在语义上是否正确。\n"
            f"{self.guard.agent_constraints()}"
        )
        user_prompt = (
            f"## 题目\n{title}\n\n"
            f"## 参考答案\n{expected}\n\n"
            f"## 学生答案\n{user_answer}\n\n"
            f"## 题目解析\n{explanation}\n\n"
            "判断学生答案在语义上是否与参考答案一致（意思对即可，不要求完全相同的表述）。\n"
            "必须只返回 JSON，不要 Markdown。JSON Schema：\n"
            '{"score": 1.0, "reason": "理由"}\n'
            "其中 score 取值：1.0 = 完全正确，0.5 = 部分正确/表述不完整，0.0 = 错误/无关。"
        )
        try:
            content = self._chat(system_prompt, user_prompt)
            result = self._extract_json(content)
            score = float(result.get("score", 0))
            score = max(0.0, min(1.0, score))
            return score
        except Exception:
            return None

    def _chat(self, system_prompt: str, user_prompt: str) -> str:
        """直接调用 DashScope API，跳过 LangChain 避免导入和超时开销"""
        return self.qwen.chat(system_prompt, user_prompt)

    def _system_prompt(self) -> str:
        return (
            "你是多智能体学习系统中的资源生成，身份是高校课程助教和学习设计师。"
            "你要生成课程学习、测评练习、知识讲解、学习资源和实践任务相关内容。"
            "输出必须结合学生画像动态生成，不允许复用固定模板。"
            f"{self.guard.agent_constraints()}"
        )

    def _resource_instruction(self, resource_type: str) -> str:
        instructions = {
            "course_document": "分步生成：先设计章节大纲（6-10章），再逐章撰写详细内容。每章包含核心概念讲解、代码/案例演示、常见误区分析和章节练习题。",
            "mind_map": "只输出一个可被 Mermaid 11 渲染的 ```mermaid mindmap 代码块：第一行 mindmap，第二行 root((主题))；只用两个空格缩进；节点用中文短语，每个节点不超过18个汉字；不要 Markdown 列表、编号、HTML、<br/>、公式、反引号、英文括号或代码块外解释；控制在4-6个一级分支、每个分支2-4个子节点、最多3层，避免节点过密重叠。",
            "exercise_bank": "输出分层练习题库，包含基础题、应用题、综合题，但不要泄露答案。",
            "extension_reading": "分步生成：先设计阅读大纲（4-6节），再逐节生成详细的拓展阅读指南。每节包含核心知识点讲解、推荐材料导读、阅读方法和反思问题。",
            "coding_case": "输出实操案例说明，包含题目、输入输出、要求、评分点和参考思路。",
            "multimedia_video": "生成教学视频：先根据学生画像构造视频描述 prompt，调用文生视频 API 生成实际教学视频。",
        }
        return instructions.get(resource_type, instructions["course_document"])

    def _extract_json(self, content: str) -> dict:
        text = (content or "").strip()
        # \u5148\u76f4\u63a5\u89e3\u6790\uff08\u6a21\u578b\u8fd4\u56de\u7684\u662f\u6807\u51c6 JSON\uff0c\u4e2d\u6587\u5f15\u53f7\u5728\u5b57\u7b26\u4e32\u5185\u662f\u5408\u6cd5\u5185\u5bb9\uff09
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # \u53bb\u6389 markdown \u4ee3\u7801\u5757\u6807\u8bb0\u540e\u91cd\u8bd5
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        # \u6b63\u5219\u63d0\u53d6 JSON \u5bf9\u8c61
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        # \u6700\u540e\u515c\u5e95\uff1a\u66ff\u6362\u4e2d\u6587\u5f15\u53f7\u4e3a ASCII\uff08\u6a21\u578b\u53ef\u80fd\u628a\u4e2d\u6587\u5f15\u53f7\u7528\u4f5c JSON \u5b9a\u754c\u7b26\uff09
        text = (content or "").strip()
        text = text.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.S)
            if not match:
                raise
            return json.loads(match.group(0))

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
                    print(f"[Quiz Auto-Fix] 选择题 #{index} 缺少 options，已自动补全")
            elif not question.get("options"):
                question["options"] = []

    def _agent_meta(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "mode": "langchain_agent_or_qwen_agent",
            "message": "已调用学习资源 Agent 动态生成内容；",
        }

    def _fallback_meta(self, message: str) -> dict[str, Any]:
        return {"enabled": False, "mode": "local_fallback", "message": message}

    # Gap 2 改进：格式化已学/未学知识点概览
    @staticmethod
    def _format_learned_knowledge(context: dict) -> str:
        learned = context.get("learned_knowledge") or {}
        if not learned:
            return ""
        parts = ["## 已学/未学知识点概览"]
        for key, value in learned.items():
            if value:
                parts.append(f"- {key}：{value}")
        return "\n".join(parts)

    def generate_quiz_evaluation(self, quiz: dict, answers: dict, details: list, score: float,
                                   history_summary: str = "") -> str:
        if not self.enabled:
            return self._local_quiz_evaluation(quiz, details, score)

        try:
            # Phase 1: 构建评估规划 —— 列出需要逐题评估的题目
            plan = self._build_evaluation_plan(quiz, details)

            # Phase 2: 并行评估各题
            eval_parts: list[str] = []
            if plan:
                with ThreadPoolExecutor(max_workers=min(len(plan), 8)) as executor:
                    future_map = {}
                    for index, item in enumerate(plan):
                        future = executor.submit(self._evaluate_single_question, quiz, answers, item)
                        future_map[future] = index
                    results: dict[int, str] = {}
                    for future in as_completed(future_map):
                        idx = future_map[future]
                        try:
                            results[idx] = future.result()
                        except Exception:
                            results[idx] = ""
                eval_parts = [results[i] for i in range(len(plan)) if results.get(i)]

            # Phase 3: 合并为最终评估报告
            return self._merge_evaluation(quiz, details, score, eval_parts, history_summary=history_summary)
        except Exception as exc:
            return self._local_quiz_evaluation(quiz, details, score)

    def _build_evaluation_plan(self, quiz: dict, details: list) -> list[dict]:
        """构建评估规划：错题逐题评估，正确题选代表性题巩固分析"""
        questions = {}
        if isinstance(quiz.get("questions"), list):
            for q in quiz["questions"]:
                questions[q.get("id")] = q

        plan = []
        seen_concepts: set[str] = set()
        # 错题：每道错题都单独评估
        for item in details:
            if not item.get("is_correct"):
                qid = item.get("id", 0)
                qdata = questions.get(qid, {})
                plan.append({
                    "question_id": qid,
                    "concept": item.get("concept", qdata.get("concept", "")),
                    "type": qdata.get("type", ""),
                    "prompt": qdata.get("prompt", ""),
                    "user_answer": item.get("user_answer", ""),
                    "reference_answer": item.get("reference_answer", ""),
                    "is_correct": False,
                    "focus": "错题诊断",
                })
        # 正确题：每种概念选一道
        for item in details:
            if item.get("is_correct"):
                concept = item.get("concept", "")
                if concept and concept not in seen_concepts:
                    seen_concepts.add(concept)
                    qid = item.get("id", 0)
                    qdata = questions.get(qid, {})
                    plan.append({
                        "question_id": qid,
                        "concept": concept,
                        "type": qdata.get("type", ""),
                        "prompt": qdata.get("prompt", ""),
                        "user_answer": item.get("user_answer", ""),
                        "reference_answer": item.get("reference_answer", ""),
                        "is_correct": True,
                        "focus": "掌握确认",
                    })
        return plan

    def _evaluate_single_question(self, quiz: dict, answers: dict, plan_item: dict) -> str:
        """对单道题目进行逐题评估"""
        system_prompt = (
            "你是多智能体学习系统中的【学习评估 Agent】，身份是高校课程助教和教学评测专家。"
            "你负责对学生的单道答题情况进行详细诊断和个性化反馈。"
            f"{self.guard.agent_constraints()}"
        )
        label = "【掌握确认】" if plan_item.get("is_correct") else "【错题诊断】"
        user_prompt = (
            f"请对学生的一道答题情况进行评估。\n"
            f"学生画像：{json.dumps(self.profile, ensure_ascii=False)}\n"
            f"{label}\n"
            f"题目：{plan_item.get('prompt', '')}\n"
            f"题型：{plan_item.get('type', '')}\n"
            f"知识点：{plan_item.get('concept', '')}\n"
            f"学生答案：{plan_item.get('user_answer', '')}\n"
            f"参考答案：{plan_item.get('reference_answer', '')}\n"
            "请输出 2-4 句话的个性化反馈，包括：\n"
            "1. 判断该题学生的掌握程度\n"
            "2. 如果是错题，分析错误原因（概念不清、审题失误、计算错误等）\n"
            "3. 给出针对性的改进建议或巩固方法\n"
            "输出简洁直接，不要问候语。"
        )
        try:
            content = self._chat(system_prompt, user_prompt).strip()
            if content:
                content, _ = self.apply_safety(content)
            return content or ""
        except Exception:
            return ""

    def _merge_evaluation(self, quiz: dict, details: list, score: float, eval_parts: list[str],
                            history_summary: str = "") -> str:
        """将逐题评估合并为完整的测评报告"""
        wrong_items = [d for d in details if not d.get("is_correct")]
        correct_count = sum(1 for d in details if d.get("is_correct"))
        total = len(details)
        wrong_concepts = list({
            d.get("concept") for d in wrong_items if d.get("concept")
        })

        parts = [
            f"## 测评评估报告\n",
            f"### 总体表现\n",
            f"得分 **{score}/100** | 共 {total} 题 | 答对 {correct_count} 题 | 答错 {len(wrong_items)} 题",
        ]
        if wrong_concepts:
            parts.append(f"\n薄弱知识点：{'、'.join(wrong_concepts[:5])}")
        if wrong_items:
            parts.append(
                "\n\n> 建议重点复习以上薄弱知识点，结合讲解文档和思维导图巩固理解，"
                "然后重新进行练习检验进步情况。"
            )

        if eval_parts:
            parts.append("\n\n### 逐题评估\n")
            for ep in eval_parts:
                if ep.strip():
                    parts.append(f"- {ep.strip()}")

        # Gap 1 改进：若有历史测评摘要，添加到报告中作为参照
        if history_summary:
            parts.append(f"\n\n### 历史对比（参照）\n\n{history_summary}")

        # 用 LLM 生成总体建议（单次调用，小上下文）
        if self.enabled:
            try:
                system_prompt = self._system_prompt()
                weak_text = "、".join(wrong_concepts[:5]) if wrong_concepts else "无明显短板"
                history_note = f"\n历史测评参照：{history_summary}" if history_summary else ""
                user_prompt = (
                    "请根据以下测评统计，为学生生成 3-5 条个性化的学习建议。\n"
                    f"学生画像：{json.dumps(self.profile, ensure_ascii=False)}\n"
                    f"得分：{score}/100，共 {total} 题，答对 {correct_count} 题\n"
                    f"薄弱知识点：{weak_text}\n"
                    f"{history_note}"
                    "输出 Markdown 格式的改进建议，具体到每个薄弱知识点该做什么。"
                )
                advices = self._chat(system_prompt, user_prompt).strip()
                if advices:
                    parts.append(f"\n\n### 改进建议\n\n{advices}")
            except Exception:
                pass

        return "\n".join(parts)

    def _local_quiz_evaluation(self, quiz: dict, details: list, score: float) -> str:
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
            parts.append("\n建议优先复习以上知识点，可以回到知识学习页面查看相关讲解文档。")
        else:
            parts.append("\n### 评价\n全部答对，请继续保持学习节奏，尝试更高难度的题目。")
        parts.append("\n### 建议\n")
        parts.append("1. 将错题中的知识点添加到学习画像的易错点中，便于后续资源推荐。")
        parts.append("2. 针对薄弱知识点，建议生成对应主题的讲解文档和思维导图。")
        parts.append("3. 完成本轮学习后，可以重新进行一次测评评估，检验进步情况。")
        return "\n".join(parts)
