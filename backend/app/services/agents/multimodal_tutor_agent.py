from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import tempfile
import time
import traceback
import urllib.request
from collections.abc import Generator
from pathlib import Path
from typing import Any

from ..ai_client import QwenClient
from ..guardrails import ContentGuard
from .context_window import ContextWindowManager


class MultimodalInput:
    """多模态输入：封装用户发送的文本+图片+文件"""

    def __init__(self, text: str = "", images: list[str] = None, files: list[dict] = None):
        self.text = text or ""
        self.images = images or []
        self.files = files or []

    @property
    def has_images(self) -> bool:
        return len(self.images) > 0

    @property
    def has_files(self) -> bool:
        return len(self.files) > 0

    @property
    def is_multimodal(self) -> bool:
        return self.has_images or self.has_files

    def summary(self) -> str:
        parts = [f"文本指令：{self.text[:100]}"]
        if self.has_images:
            parts.append(f"图片：{len(self.images)} 张")
        if self.has_files:
            parts.append(f"文件：{len(self.files)} 个")
        return " | ".join(parts)


class MultimodalTutorAgent:
    """多模态智能辅导 Agent

    实现完整的多模态处理流程：
    1. 输入层拆解与预处理（文本/图片/文件分离）
    2. 多模态内容单独理解（OCR/文件解析/意图识别）
    3. 多模态融合思考（关联融合为统一上下文）
    4. 任务执行与结构化回复生成
    """

    # 用户意图分类
    INTENT_QA = "qa"                 # 问答提问
    INTENT_SUMMARIZE = "summarize"   # 总结概括
    INTENT_ANALYZE = "analyze"       # 解读分析
    INTENT_REWRITE = "rewrite"       # 改写润色翻译
    INTENT_SOLVE = "solve"           # 做题解题
    INTENT_EXTRACT = "extract"       # 提取信息
    INTENT_CREATE = "create"         # 创作文案
    INTENT_GENERATE_IMAGE = "generate_image"  # 文生图
    INTENT_GENERATE_VIDEO = "generate_video"  # 文生视频

    def __init__(self, profile: dict):
        self.profile = profile
        self.qwen = QwenClient()
        self.guard = ContentGuard()
        self.context_manager = ContextWindowManager(qwen_client=self.qwen)
        self._file_text_cache: dict[str, str] = {}

    @property
    def enabled(self) -> bool:
        return self.qwen.enabled

    # ═══════════════════════════════════════════
    # 第一步：输入层拆解与预处理
    # ═══════════════════════════════════════════

    def parse_input(self, text: str, images: list[str] = None, files: list[dict] = None) -> MultimodalInput:
        """拆解用户输入为三类独立流：文本指令 / 图像流 / 文件流"""
        return MultimodalInput(
            text=self._clean_text(text),
            images=images or [],
            files=files or [],
        )

    def _clean_text(self, text: str) -> str:
        """清洗文本：去除冗余空白，保留核心指令"""
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def should_ignore_multimodal(self, text: str) -> bool:
        """意图识别优先：检测用户是否明确要求忽略图片/文件，只处理文本

        当用户消息中包含以下指令时，直接丢弃图片/文件数据，
        不做任何视觉解析，只将文本内容传给 LLM。
        """
        if not text:
            return False
        ignore_phrases = [
            "不要看图", "不要看图片", "忽略图片", "不看图片",
            "不要读文件", "忽略文件", "不看文件",
            "只看文本", "只看文字", "根据文字",
            "别管图片", "不用看图片", "不用管图片",
            "ignore the image", "ignore image", "ignore images",
            "don't look at the image", "don't look at images",
            "只看文字内容",
        ]
        return any(phrase in text for phrase in ignore_phrases)

    # ═══════════════════════════════════════════
    # 第二步：多模态内容单独理解
    # ═══════════════════════════════════════════

    def extract_image_info(self, images: list[str]) -> list[dict]:
        """解析图片：为主体识别 + OCR 文本提取"""
        image_infos = []
        for idx, img_data in enumerate(images):
            image_infos.append({
                "index": idx,
                "type": self._identify_image_type(img_data),
                "data": img_data,
            })
        return image_infos

    def _identify_image_type(self, img_data: str) -> str:
        """识别图片类型（由 LLM 视觉能力在融合阶段完成）"""
        if img_data.startswith("data:"):
            mime = img_data.split(";")[0].split(":")[1] if ";" in img_data else "image/unknown"
            return mime
        return "image/url"

    def extract_file_text(self, files: list[dict]) -> list[dict]:
        """解析文件：根据文件类型提取文本内容

        支持的文件类型：
        - PDF：全文文本提取
        - Word (docx)：段落文本提取
        - Excel (xlsx)：表格数据提取
        - TXT/代码文件：直接读取
        """
        file_infos = []
        for file_item in files:
            file_name = file_item.get("name", "") or file_item.get("filename", "")
            file_content = file_item.get("content", "")  # base64 编码的文件内容
            file_type = file_item.get("type", "") or self._guess_file_type(file_name)

            text = ""
            ext = os.path.splitext(file_name)[1].lower()

            if file_content:
                text = self._extract_text_from_content(file_content, ext)

            file_infos.append({
                "name": file_name,
                "type": file_type,
                "ext": ext,
                "text": text,
                "text_length": len(text),
            })
        return file_infos

    def _guess_file_type(self, filename: str) -> str:
        ext = os.path.splitext(filename)[1].lower()
        type_map = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".csv": "text/csv",
            ".json": "application/json",
            ".py": "text/x-python",
            ".js": "text/javascript",
            ".java": "text/x-java",
            ".cpp": "text/x-c++",
            ".c": "text/x-c",
            ".html": "text/html",
            ".css": "text/css",
            ".sql": "text/x-sql",
        }
        return type_map.get(ext, "application/octet-stream")

    def _extract_text_from_content(self, base64_content: str, ext: str) -> str:
        """从 base64 编码的文件内容中提取文本"""
        try:
            raw_bytes = base64.b64decode(base64_content)
            # 对于纯文本格式直接解码
            text_exts = {".txt", ".md", ".csv", ".json", ".py", ".js", ".java",
                         ".cpp", ".c", ".html", ".css", ".sql", ".xml", ".yaml", ".yml"}
            if ext in text_exts:
                return raw_bytes.decode("utf-8", errors="replace")

            # 对于 PDF，使用 pypdf 提取
            if ext == ".pdf":
                return self._extract_pdf_text(raw_bytes)

            # 对于 DOCX，使用 python-docx 提取
            if ext == ".docx":
                return self._extract_docx_text(raw_bytes)

            # Excel 等结构化格式返回基本信息
            if ext in (".xlsx", ".xls"):
                return self._extract_excel_text(raw_bytes, ext)

            return f"[文件 {ext} 格式暂不支持完整文本提取，请在提问中说明文件内容]"
        except Exception as exc:
            return f"[文件解析失败：{exc}]"

    def _extract_pdf_text(self, raw_bytes: bytes) -> str:
        try:
            from io import BytesIO
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(raw_bytes))
            texts = []
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    texts.append(t)
            return "\n".join(texts) if texts else "[PDF 未能提取到文本内容]"
        except ImportError:
            return "[PDF 解析依赖未安装，请执行 pip install pypdf]"
        except Exception as exc:
            return f"[PDF 解析失败：{exc}]"

    def _extract_docx_text(self, raw_bytes: bytes) -> str:
        try:
            from io import BytesIO
            from docx import Document
            doc = Document(BytesIO(raw_bytes))
            texts = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(texts) if texts else "[DOCX 未能提取到文本内容]"
        except ImportError:
            return "[DOCX 解析依赖未安装，请执行 pip install python-docx]"
        except Exception as exc:
            return f"[DOCX 解析失败：{exc}]"

    def _extract_excel_text(self, raw_bytes: bytes, ext: str) -> str:
        try:
            from io import BytesIO
            import openpyxl
            wb = openpyxl.load_workbook(BytesIO(raw_bytes), read_only=True, data_only=True)
            texts = [f"工作表：{sheet.title}" for sheet in wb.worksheets]
            for sheet in wb.worksheets:
                rows = []
                for i, row in enumerate(sheet.iter_rows(values_only=True)):
                    if i < 50:  # 限制行数
                        rows.append(" | ".join(str(c) if c is not None else "" for c in row))
                if rows:
                    texts.append(f"--- {sheet.title} 数据前 {len(rows)} 行 ---")
                    texts.extend(rows)
            return "\n".join(texts)
        except ImportError:
            return "[Excel 解析依赖未安装，请执行 pip install openpyxl]"
        except Exception as exc:
            return f"[Excel 解析失败：{exc}]"

    def extract_image_descriptions(self, images: list[str]) -> str:
        """使用专用多模态理解模型提取图片内容描述

        仅在有图片时调用，将图片提交给视觉模型生成文本描述。
        使用 DASHSCOPE_MULTIMODAL_UNDERSTAND_MODEL 配置的专用视觉模型，
        提取图片中的文字、图表、公式、题目、笔记等关键信息。

        返回的描述文本将作为 Prompt 上下文提供给主模型，
        主模型不再需要接收原始图片数据，仅基于文本描述即可完成回答。
        """
        if not images or not self.enabled:
            return ""
        try:
            return self.qwen.describe_images(images)
        except Exception:
            return "[图片描述提取失败]"

    def classify_intent(self, text: str, has_multimodal: bool = False) -> str:
        """识别用户意图分类，优先处理多模态内容

        当用户上传了图片/文件且文本指令不明确时，优先触发解读分析流程。
        """
        if has_multimodal and not any(kw in text for kw in [
            "解题", "做题", "计算", "求", "解", "怎么算", "如何做",
            "总结", "概括", "摘要", "提炼", "归纳",
            "改写", "润色", "翻译", "重写", "修改",
            "写", "创作", "生成", "制作", "设计",
        ]):
            return self.INTENT_ANALYZE

        text_lower = text.lower()
        # 做题解题
        if any(kw in text for kw in ["解题", "做题", "计算", "求", "解", "怎么算", "如何做"]):
            return self.INTENT_SOLVE
        # 总结概括
        if any(kw in text for kw in ["总结", "概括", "摘要", "提炼", "归纳"]):
            return self.INTENT_SUMMARIZE
        # 解读分析
        if any(kw in text for kw in ["分析", "解读", "解释", "为什么", "说明", "阐述"]):
            return self.INTENT_ANALYZE
        # 改写润色翻译
        if any(kw in text for kw in ["改写", "润色", "翻译", "重写", "修改"]):
            return self.INTENT_REWRITE
        # 提取信息
        if any(kw in text for kw in ["提取", "找出", "列出", "有哪些", "包含什么"]):
            return self.INTENT_EXTRACT
        # 文生视频（优先匹配）
        if any(kw in text for kw in ["生成视频", "生成影片", "视频", "动画", "生成动画", "制作视频", "教学视频", "演示视频", "科普视频", "短片", "视频讲解"]):
            return self.INTENT_GENERATE_VIDEO
        # 文生图（放在"创作文案"之前优先匹配）
        if any(kw in text for kw in ["画图", "画一张", "画个", "生成图片", "生成图像", "绘制", "配图", "示意图", "画出", "画个图", "画一幅"]):
            return self.INTENT_GENERATE_IMAGE
        # 创作文案
        if any(kw in text for kw in ["写", "创作", "生成", "制作", "设计"]):
            return self.INTENT_CREATE
        # 默认为问答
        return self.INTENT_QA

    def intent_label(self, intent: str) -> str:
        labels = {
            self.INTENT_QA: "问答提问",
            self.INTENT_SUMMARIZE: "总结概括",
            self.INTENT_ANALYZE: "解读分析",
            self.INTENT_REWRITE: "改写润色/翻译",
            self.INTENT_SOLVE: "做题解题",
            self.INTENT_EXTRACT: "提取信息",
            self.INTENT_CREATE: "创作文案",
            self.INTENT_GENERATE_IMAGE: "文生图",
            self.INTENT_GENERATE_VIDEO: "文生视频",
        }
        return labels.get(intent, "综合处理")

    # ═══════════════════════════════════════════
    # 第三步：多模态融合思考（核心）
    # ═══════════════════════════════════════════

    def fusion_think(self, mm_input: MultimodalInput, file_infos: list[dict], rag_context: str,
                     image_description: str = "") -> list[str]:
        """生成多模态融合思考过程（不调用 LLM，纯逻辑推理）

        采用标准的 7 步多模态思考流程：
        定意图→拆素材→单模态解析→跨模态关联融合→对齐需求→校验修正→规整输出

        返回思考步骤列表，供前端 SSE 展示
        """
        steps = []
        intent = self.classify_intent(mm_input.text, has_multimodal=mm_input.is_multimodal)

        # ─── 第一步：锁定用户核心意图 ───
        priority = "图文文件内容优先（有多模态素材）" if mm_input.is_multimodal else "通用知识库优先（无多模态素材）"
        steps.append(
            f"**第一步：锁定用户核心意图**\n"
            f"已剥离冗余话术，锁定核心行为指令为「{self.intent_label(intent)}」。\n"
            f"用户原始指令：{mm_input.text[:120]}{'...' if len(mm_input.text) > 120 else ''}\n"
            f"判定优先级：{priority}"
        )

        # ─── 第二步：拆分所有输入模态 ───
        modal_parts = ["已拆分输入源："]
        modal_parts.append("  - [指令层] 用户明文要求，作为唯一行动标准")
        if mm_input.has_images:
            modal_parts.append(f"  - [视觉层] 检测到 {len(mm_input.images)} 张图片/截图/图表")
        else:
            modal_parts.append("  - [视觉层] 无图片素材，跳过视觉分析")
        if file_infos:
            modal_parts.append(f"  - [资料层] 检测到 {len(file_infos)} 个文件素材")
        else:
            modal_parts.append("  - [资料层] 无文件素材，跳过文件分析")
        if rag_context:
            modal_parts.append("  - [知识库] 已检索到相关知识库参考材料")
        steps.append("**第二步：拆分输入模态分类**\n" + "\n".join(modal_parts))

        # ─── 第三步：各模态独立解析 ───
        step3_parts = ["**第三步：各模态独立解析**\n"]
        step3_parts.append("【文本指令吃透】")
        step3_parts.append(
            f"解读用户指令中的约束、格式、侧重点、输出要求。\n"
            f"指令核心：「{mm_input.text[:100]}」"
        )

        if mm_input.has_images:
            step3_parts.append("\n【图片解析】")
            step3_parts.append(f"检测到 {len(mm_input.images)} 张图片，调用专用视觉模型进行内容提取：")
            step3_parts.append("  - 视觉识别：画面场景、结构、图形、框架、布局")
            step3_parts.append("  - OCR 提取：图内文字、标题、公式、题干、标注")
            step3_parts.append("  - 逻辑梳理：题干条件、数据关系、流程顺序、知识点")
            # 如果已有图片描述结果，直接展示
            if image_description:
                desc_short = image_description[:300]
                if len(image_description) > 300:
                    desc_short += "..."
                step3_parts.append(f"\n【视觉模型提取结果】\n{desc_short}")

        if file_infos:
            step3_parts.append("\n【文件解析】")
            for fi in file_infos:
                fi_desc = f"  - 「{fi['name']}」"
                if fi.get("text") and not fi["text"].startswith("[文件"):
                    fi_desc += f"（{len(fi['text'])} 字内容已提取）"
                else:
                    fi_desc += f"（{fi.get('text', '待解析')}）"
                step3_parts.append(fi_desc)
            step3_parts.append("将从文件中提取：核心段落、主旨、论据、知识点、结构化章节")

        steps.append("\n".join(step3_parts))

        # ─── 第四步：多模态联动融合思考（核心） ───
        step4_parts = ["**第四步：多模态联动融合思考**\n"]
        step4_parts.append("建立三类信息的对应关系，合并全局上下文：")
        step4_parts.append("  用户指令 → 视觉素材 → 文件资料 → 知识库参考\n")
        step4_parts.append("【融合三问】")
        step4_parts.append("Q1：用户指令需要用到视觉素材/文件资料中的哪些内容？")
        if mm_input.is_multimodal:
            step4_parts.append("Q2：文件资料能否佐证或补充图片中的信息？")
        if rag_context:
            step4_parts.append("Q3：知识库参考材料与图文内容如何互相印证？")
        step4_parts.append("")
        step4_parts.append("融合决策：将文本指令 + 图片描述 + 文件内容 + 知识库合并为统一全局上下文。")
        step4_parts.append("严格禁止脱离图文素材输出通用课程、通用大纲、无关知识点。")
        if image_description:
            step4_parts.append(f"\n【已使用专用视觉模型（{self.qwen._vision_model or '主模型'}）提取图片内容，主模型不再接收原始图片】")
        steps.append("\n".join(step4_parts))

        # ─── 第五步：匹配任务模式，确定作答框架 ───
        step5_parts = [f"**第五步：匹配任务模式（{self.intent_label(intent)}）**\n"]
        if intent == self.INTENT_SOLVE:
            step5_parts.append("解题类框架：图文题干梳理 → 条件罗列 → 分步推导 → 得出结论")
        elif intent == self.INTENT_ANALYZE:
            step5_parts.append("分析解读类框架：核心内容概括 → 细节拆解 → 逻辑梳理 → 观点总结")
        elif intent == self.INTENT_SUMMARIZE:
            step5_parts.append("总结提炼类框架：合并图文文件要点 → 去重整合 → 分层精简输出")
        elif intent == self.INTENT_QA:
            step5_parts.append("问答类框架：依托图文资料直接作答，不凭空拓展无关内容")
        elif intent in (self.INTENT_REWRITE, self.INTENT_CREATE):
            step5_parts.append("创作改写类框架：以图文文件为素材基底，严格按指令要求调整输出")
        elif intent == self.INTENT_EXTRACT:
            step5_parts.append("提取信息类框架：定位关键信息位置 → 筛选整合 → 按需输出")
        else:
            step5_parts.append("综合处理框架：依据图文融合内容进行灵活回应")
        steps.append("\n".join(step5_parts))

        # ─── 第六步：校验修正 ───
        step6_parts = ["**第六步：校验修正**\n"]
        step6_parts.append("完成输出前自查：")
        if mm_input.is_multimodal:
            step6_parts.append("  - 是否引用图片关键内容、文件核心内容")
        step6_parts.append("  - 是否偏离用户原始文本指令")
        step6_parts.append("  - 是否混入模板化套话、通用学习方案、无关拓展知识")
        step6_parts.append("  - 逻辑是否连贯，前后信息是否自洽")
        steps.append("\n".join(step6_parts))

        # ─── 第七步：结构化输出 ───
        steps.append(
            "**第七步：结构化有序输出**\n"
            "先承接用户需求，再整合图文融合后的核心内容，\n"
            "按条理分点/分段输出，重点内容对标原图原文件位置。"
        )

        # ─── 精简版流程日志 ───
        modal_summary = "文本+图片+文件" if mm_input.is_multimodal else "文本"
        steps.append(
            "---\n"
            "**整体思考链路（精简）**\n"
            f"识别意图「{self.intent_label(intent)}」"
            f" → 分离{modal_summary}三类输入"
            f" → 各模态独立解析"
            f" → 打通融合构建全局上下文"
            f" → 确定{self.intent_label(intent)}作答框架"
            f" → 校验修正"
            " → 结构化输出"
        )

        return steps

    def build_fusion_prompt(self, mm_input: MultimodalInput, file_infos: list[dict], rag_context: str,
                            image_description: str = "",
                            conversation_history: list[dict] | None = None) -> tuple[str, str]:
        """构建融合后的 System Prompt 和 User Prompt（融合上下文）

        使用严格的固定输出模板，强制模型先描述图片/文件内容，
        再基于确认的内容执行用户指令，避免模型生成与多模态内容无关的通用回答。

        当有图片时，image_description 由专用视觉模型预先生成，
        主模型不再接收原始图片数据，仅基于文本描述完成回答。

        如果提供了 conversation_history，则通过 ContextWindowManager
        自动管理短期记忆上下文窗口（保留近期对话 + 摘要较早对话）。
        """
        intent = self.classify_intent(mm_input.text, has_multimodal=mm_input.is_multimodal)

        system_prompt = (
            "你是「循证学习教练」，一个面向学生的多模态 AI 智能辅导员，具备文本理解、图像识别和文件解析能力。\n"
            "你的核心身份不是泛泛聊天助手，而是能够融合文字、图片、文件、课程知识库和学生画像的学习诊断与辅导教练。\n"
            "回答时要保持耐心、清晰、鼓励，但必须以证据和课程内容为依据，先定位学生困惑，再分层讲解，最后给出可执行练习或下一步建议。\n"
            "\n"
            "### 身份职责\n"
            "- 诊断：识别学生当前问题、薄弱知识点、概念误区或操作卡点。\n"
            "- 讲解：用适合学生水平的语言解释概念，必要时给类比、步骤和例子。\n"
            "- 追溯：优先引用用户上传材料、知识库片段或题目中的明确依据，不编造来源。\n"
            "- 训练：在回答末尾给出 1-3 个简短练习、检查点或下一步学习建议。\n"
            "\n"
            "### 【必须严格遵守的输出流程】\n"
            "1. **第一步：先确认多模态内容**\n"
            "   - 如果用户上传了图片，必须先写「1. 图片内容概述」，用清晰的列表描述每张图片里的所有关键信息"
            "（文字、图表、公式、题目、笔记等），让用户确认你已正确理解图片内容。\n"
            "   - 如果用户上传了文件，必须先写「文件内容摘要」，提取核心内容。\n"
            "2. **第二步：再执行用户指令**\n"
            "   - 必须基于第一步确认的内容，再回答用户的问题、提供建议、解题、分析等。\n"
            "   - 回答中必须明确引用第一步里的关键信息，不能脱离图片/文件凭空回答。\n"
            "\n"
            "### 多模态融合规则\n"
            "- 先融合再回答：把文本指令、图片内容、文件内容合并成一个完整上下文后再推理。\n"
            "- 全面引用：回答必须引用图片中的关键视觉信息（图表数据、公式、文字等）和文件中的核心内容。\n"
            "- 不遗漏细节：仔细检查图片中的每一个文字、图表坐标、数据点；文件中的每一段重要内容。\n"
            "- 结构化输出：根据用户意图选择合适的输出格式。\n"
            "   - 做题解题：分步骤展示推理过程\n"
            "   - 总结概括：先总述再分点\n"
            "   - 解读分析：指出关键发现并解释原因\n"
            "   - 改写润色：说明修改点\n"
            "\n"
            "### 禁止行为\n"
            "- 不得说\"无法查看图片\"或\"无法读取文件\"。你有能力处理图片和文件。\n"
            "- 不得编造图片或文件中不存在的内容。\n"
            "- 不得拒绝回答学科知识问题。\n"
            "- 严禁编造不存在的来源或引用。\n"
            "- **禁止脱离用户上传的图片/文件，生成和内容无关的通用学习计划、课程大纲等。**\n"
            "  例如：用户上传了一张笔记图片，你不能直接讲\"系统掌握人工智能课程\"，"
            "必须先描述笔记内容，再基于笔记给建议。\n"
        )

        # 构建融合上下文：把图片描述、文件内容、知识库全部整合到 user prompt 中
        context_parts = []
        context_parts.append(f"## 学生画像\n{json.dumps(self.profile, ensure_ascii=False, indent=2)}")
        context_parts.append(f"## 学生原始指令\n{mm_input.text}")

        if mm_input.has_images and image_description:
            context_parts.append(
                f"## 用户上传的图片内容（已由专用视觉模型提取）\n"
                f"【图片描述】以下是对用户上传的 {len(mm_input.images)} 张图片的详细内容描述：\n\n"
                f"{image_description}\n\n"
                "【要求】请基于以上图片描述内容回答用户的问题。"
                "第一步先概述图片内容让用户确认，第二步再执行用户指令。"
            )

        if file_infos:
            file_section = []
            file_section.append(f"## 上传的文件（共 {len(file_infos)} 个）")
            for fi in file_infos:
                file_section.append(f"\n### 文件：{fi['name']}")
                file_text = fi.get("text", "")
                if file_text and not file_text.startswith("[文件"):
                    truncated = file_text[:3000]
                    if len(file_text) > 3000:
                        truncated += "\n...（文件过长，以上为前 3000 字符）"
                    file_section.append(truncated)
                else:
                    file_section.append(file_text)
            context_parts.append("\n".join(file_section))

        if rag_context:
            context_parts.append(f"## 知识库参考片段\n{rag_context[:2000]}")

        if conversation_history:
            history_prompt = self.context_manager.build_history_prompt(conversation_history)
            if history_prompt:
                context_parts.append(history_prompt)

        user_prompt = "\n\n".join(context_parts)
        return system_prompt, user_prompt

    # ═══════════════════════════════════════════
    # 第四步：任务执行与结构化回复生成
    # ═══════════════════════════════════════════

    def generate_answer(self, mm_input: MultimodalInput, file_infos: list[dict], rag_context: str,
                        image_description: str = "",
                        conversation_history: list[dict] | None = None) -> str:
        """非流式：生成融合后的回答

        当有图片时，image_description 由专用视觉模型预先生成，
        主模型仅基于文本描述回答，不再接收原始图片数据。
        """
        if not self.enabled:
            return self._local_fallback(mm_input, file_infos)

        system_prompt, user_prompt = self.build_fusion_prompt(
            mm_input, file_infos, rag_context, image_description,
            conversation_history=conversation_history
        )
        try:
            answer = self.qwen.chat(system_prompt, user_prompt)
            answer, _ = self.guard.apply_output_guard(answer)
            return answer
        except Exception as exc:
            return self._local_fallback(mm_input, file_infos)

    def detect_and_generate_image(self, question: str, rag_context: str = "") -> dict[str, Any]:
        """LLM 判断用户意图是否需要文生图，若需要则优化提示词并调用 API

        流程：
        1. LLM 根据用户问题判断是否需要生成教学配图
        2. 若需要，LLM 生成优化后的图片描述 prompt
        3. 调用 DashScope 文生图 API

        返回:
            {"image_url": "...", "prompt": "..."} 或空字典（无需生成或 API 不可用时）
        """
        if not self.qwen.text2image_enabled:
            return {}

        import logging
        logger = logging.getLogger(__name__)

        try:
            topic = self.profile.get("topic", "学习内容")
            detection_prompt = (
                f"学生的问题：{question}\n"
                f"课程主题：{topic}\n"
                f"{'知识库上下文：' + rag_context[:500] if rag_context else ''}\n\n"
                "请判断学生是否在要求「生成一张图片/画图/配图/示意图」。\n"
                "如果是，用 JSON 输出：{\"need_image\": true, \"prompt\": \"优化后的图片描述（50-150字，含画面内容、风格、构图）\"}\n"
                "如果不是，输出：{\"need_image\": false}\n"
                "只输出 JSON，不要其他内容。"
            )
            response = self.qwen.chat(
                "你是一个教学配图意图判断助手。",
                detection_prompt
            ).strip()

            if not response:
                logger.warning("detect_and_generate_image: LLM returned empty response")
                return {}

            # 尝试解析 JSON
            import json as json_lib
            json_start = response.find("{")
            json_end = response.rfind("}")
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end + 1]
                try:
                    parsed = json_lib.loads(json_str)
                    if not parsed.get("need_image", False):
                        logger.info("detect_and_generate_image: LLM decided no image needed")
                        return {}
                    image_prompt = parsed.get("prompt", "").strip()
                    if not image_prompt:
                        logger.warning("detect_and_generate_image: LLM returned need_image=true but no prompt")
                        return {}
                except json_lib.JSONDecodeError:
                    logger.warning("detect_and_generate_image: failed to parse JSON from LLM response: %s", response[:200])
                    return {}
            else:
                logger.warning("detect_and_generate_image: no JSON found in LLM response: %s", response[:200])
                return {}

            logger.info("detect_and_generate_image: generating image with prompt: %s", image_prompt[:100])
            result = self.qwen.generate_text2image(image_prompt)
            task_id = result.get("task_id", "")
            results = result.get("results")

            # 同步返回了结果
            if results and len(results) > 0:
                image_url = results[0].get("url", "")
                if image_url:
                    logger.info("detect_and_generate_image: image generated (sync): %s", image_url[:80])
                    return {"image_url": image_url, "prompt": image_prompt}

            # 异步任务：轮询等待最多 60 秒
            if task_id:
                waited = 0
                while waited < 60:
                    time.sleep(3)
                    waited += 3
                    try:
                        status_result = self.qwen.query_task(task_id)
                        status = status_result.get("task_status", "UNKNOWN")
                        if status == "SUCCEEDED":
                            imgs = status_result.get("results", [])
                            if imgs and len(imgs) > 0:
                                url = imgs[0].get("url", "")
                                if url:
                                    logger.info("detect_and_generate_image: image generated (async): %s", url[:80])
                                    return {"image_url": url, "prompt": image_prompt}
                            break
                        if status == "FAILED":
                            msg = status_result.get("message", "unknown error")
                            logger.warning("detect_and_generate_image: task failed: %s", msg)
                            break
                    except Exception as e:
                        logger.warning("detect_and_generate_image: poll error: %s", e)
                        continue
                logger.warning("detect_and_generate_image: task timed out or no result")
            else:
                logger.warning("detect_and_generate_image: no task_id and no results")
            return {}
        except Exception as e:
            logger.error("detect_and_generate_image: unexpected error: %s", e, exc_info=True)
            return {}

    def _generate_single_video_segment(self, prompt: str) -> str:
        """生成单段视频并返回 URL

        调用 DashScope 文生视频 API，支持同步返回和异步任务轮询。
        每次最多生成 15 秒（wan2.6-t2v 模型限制）。

        返回:
            str: 视频 URL，失败时返回空字符串
        """
        result = self.qwen.generate_text2video(prompt, duration=15)
        if not result.get("enabled", True):
            return ""

        task_id = result.get("task_id", "")
        task_status = result.get("task_status", "UNKNOWN")
        results = result.get("results")

        # 同步返回了结果
        if results and len(results) > 0:
            url = results[0].get("url", "")
            if url:
                return url

        # 异步任务：轮询等待最多 180 秒
        if task_id:
            waited = 0
            while waited < 300:
                time.sleep(5)
                waited += 5
                try:
                    status_result = self.qwen.query_task(task_id)
                    task_output = status_result.get("output", {})
                    status = task_output.get("task_status", "UNKNOWN")
                    if status == "SUCCEEDED":
                        videos = task_output.get("results", [])
                        if videos and len(videos) > 0:
                            return videos[0].get("url", "")
                        video_url = task_output.get("video_url", "")
                        if video_url:
                            return video_url
                        break
                    if status == "FAILED":
                        break
                except Exception:
                    continue
        return ""

    def _try_concat_videos(self, video_urls: list[str]) -> str | None:
        """尝试用 ffmpeg 拼接多段视频

        将下载的视频片段通过 ffmpeg 无损拼接（copy 模式），
        保存到 uploads/generated_videos/ 目录下供 Flask 静态服务。

        返回:
            str: 拼接后视频的可访问 URL，失败时返回 None
        """
        ffmpeg_path: str | None = None
        try:
            result = subprocess.run(["where", "ffmpeg"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                lines = [ln.strip() for ln in result.stdout.strip().split("\n") if ln.strip()]
                if lines:
                    ffmpeg_path = lines[0]
        except Exception:
            pass

        if not ffmpeg_path:
            common_paths = [
                "C:\\ffmpeg\\bin\\ffmpeg.exe",
                "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
                os.path.expanduser("~\\ffmpeg\\bin\\ffmpeg.exe"),
            ]
            for path in common_paths:
                if os.path.exists(path):
                    ffmpeg_path = path
                    break

        if not ffmpeg_path:
            return None

        try:
            backend_dir = Path(__file__).resolve().parents[2]
            video_dir = backend_dir / "uploads" / "generated_videos"
            video_dir.mkdir(parents=True, exist_ok=True)

            # 下载各段视频
            local_paths = []
            for i, url in enumerate(video_urls):
                local_path = video_dir / f"segment_{i}.mp4"
                urllib.request.urlretrieve(url, local_path)
                local_paths.append(local_path)

            # 创建 ffmpeg concat 列表文件
            concat_file = video_dir / "concat_list.txt"
            with open(concat_file, "w", encoding="utf-8") as f:
                for p in local_paths:
                    f.write(f"file '{p.name}'\n")

            # 拼接输出
            timestamp = int(time.time())
            output_file = video_dir / f"combined_{timestamp}.mp4"

            cmd = [
                ffmpeg_path,
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",
                str(output_file),
            ]
            subprocess.run(cmd, capture_output=True, timeout=300)

            if output_file.exists() and output_file.stat().st_size > 0:
                # 清理临时片段
                for p in local_paths:
                    try:
                        os.remove(p)
                    except Exception:
                        pass
                try:
                    os.remove(concat_file)
                except Exception:
                    pass
                return f"/api/uploads/generated_videos/combined_{timestamp}.mp4"

            # 拼接失败，清理输出文件
            try:
                os.remove(output_file)
            except Exception:
                pass
        except Exception:
            pass
        return None

    def generate_video(self, mm_input: MultimodalInput, rag_context: str = "") -> dict[str, Any]:
        """若用户意图涉及文生视频，则调用文生视频 API 生成教学视频

        先通过 LLM 根据对话上下文构造完整的视频描述 prompt，
        再拆分为 2 个连续场景，各生成 15 秒视频片段。
        如果系统安装了 ffmpeg，则自动拼接为 30 秒完整视频；
        否则返回第一段 15 秒视频。

        返回:
            {"video_url": "...", "prompt": "...", "segments": 1|2}
            或空字典（无视频需求或 API 不可用时）
        """
        if not self.qwen.text2video_enabled:
            return {}
        try:
            topic = self.profile.get("topic", "学习内容")
            prompt_builder = (
                "你是一个专业的教学视频 prompt 工程师。请根据以下信息，生成一段适合输入文生视频模型的视频描述。\n"
                f"课程主题：{topic}\n"
                f"学生问题/指令：{mm_input.text}\n"
                f"{'知识库上下文：' + rag_context[:500] if rag_context else ''}\n"
                "要求：\n"
                "1. 描述视频画面内容、场景切换、镜头运动、色调风格\n"
                "2. 总时长 25-30 秒，包含 2 个连续镜头场景\n"
                "3. 适合教学场景，画面清晰流畅\n"
                "4. 包含关键知识点的可视化展示\n"
                "5. 仅返回视频描述文本，不要多余内容"
            )
            full_video_prompt = self.qwen.chat(self.role_prompt(), prompt_builder).strip()
            if not full_video_prompt:
                return {}

            # 拆分为 2 个场景描述（每个场景对应一段 15 秒视频）
            split_builder = (
                "你是一个视频分镜设计师。请将以下视频描述拆分为 2 个连续的、分别独立的镜头场景描述。\n"
                "要求：\n"
                "1. 每个场景描述控制在 50-80 字，适合输入文生视频模型\n"
                "2. 场景1 和 场景2 在内容上连续，逻辑衔接\n"
                "3. 每个场景单独成段，分别用【场景1】和【场景2】标记开头\n"
                "4. 仅返回场景描述，不要多余内容\n\n"
                f"完整视频描述：\n{full_video_prompt}"
            )
            scene_text = self.qwen.chat(self.role_prompt(), split_builder).strip()

            # 解析场景描述
            scenes: list[str] = []
            for match in re.finditer(
                r'【场景\d】[：:]\s*(.+?)(?=(【场景\d】[：:]|$))',
                scene_text,
                re.DOTALL,
            ):
                content = match.group(1).strip()
                if content:
                    scenes.append(content)

            # 如果解析失败，将完整描述按长度均分
            if len(scenes) < 2:
                mid = len(full_video_prompt) // 2
                scenes = [
                    full_video_prompt[:mid].strip(),
                    full_video_prompt[mid:].strip(),
                ]

            # 依次生成各段视频（限制最多 2 段）
            video_urls: list[str] = []
            for scene in scenes[:2]:
                if not scene:
                    continue
                url = self._generate_single_video_segment(scene)
                if url:
                    video_urls.append(url)

            if not video_urls:
                return {}

            # 如果有 2 段视频，尝试拼接
            if len(video_urls) >= 2:
                combined_url = self._try_concat_videos(video_urls)
                if combined_url:
                    return {
                        "video_url": combined_url,
                        "prompt": full_video_prompt,
                        "segments": 2,
                    }

            # 回退：返回第一段视频
            return {
                "video_url": video_urls[0],
                "prompt": full_video_prompt,
                "segments": 1,
            }
        except Exception:
            return {}

    def stream_generate_answer(
        self, mm_input: MultimodalInput, file_infos: list[dict], rag_context: str,
        image_description: str = "",
        conversation_history: list[dict] | None = None
    ) -> Generator[str, None, None]:
        """流式：生成融合后的回答

        当有图片时，image_description 由专用视觉模型预先生成，
        主模型仅基于文本描述回答，不再接收原始图片数据。
        """
        if not self.enabled:
            for chunk in self._stream_local_fallback(mm_input, file_infos):
                yield chunk
            return

        system_prompt, user_prompt = self.build_fusion_prompt(
            mm_input, file_infos, rag_context, image_description,
            conversation_history=conversation_history
        )
        try:
            stream_gen = self.qwen.stream_chat(system_prompt, user_prompt)
            for chunk in stream_gen:
                safe_chunk, _ = self.guard.apply_output_guard(chunk)
                yield safe_chunk
        except Exception:
            for chunk in self._stream_local_fallback(mm_input, file_infos):
                yield chunk

    def _local_fallback(self, mm_input: MultimodalInput, file_infos: list[dict]) -> str:
        """本地回退模板"""
        parts = [f"## 回答\n"]
        parts.append(f"针对你的问题「{mm_input.text}」，以下是本地模式的基础回答：\n")

        if mm_input.has_images:
            parts.append(f"> 你上传了 {len(mm_input.images)} 张图片。由于当前未配置远程 LLM，无法进行视觉分析。")
            parts.append("建议配置 DASHSCOPE_API_KEY 以启用图片理解能力。\n")

        if file_infos:
            file_names = [fi["name"] for fi in file_infos if fi.get("name")]
            parts.append(f"> 你上传了 {len(file_infos)} 个文件：{', '.join(file_names)}")
            parts.append("以下是从文件中提取的文本内容概要：\n")
            for fi in file_infos:
                if fi.get("text") and not fi["text"].startswith("[文件"):
                    parts.append(f"**{fi['name']}**（{fi['text_length']} 字）：")
                    parts.append(fi["text"][:500])
                    parts.append("")

        parts.append("---")
        parts.append("*当前使用本地模板模式，配置 API Key 后可获得更精准的多模态回答。*")
        return "\n".join(parts)

    def _stream_local_fallback(self, mm_input: MultimodalInput, file_infos: list[dict]) -> Generator[str, None, None]:
        """流式本地回退"""
        text = self._local_fallback(mm_input, file_infos)
        chunk_size = 20
        for i in range(0, len(text), chunk_size):
            yield text[i:i + chunk_size]

    # ═══════════════════════════════════════════
    # 完整处理流程（一站式调用）
    # ═══════════════════════════════════════════

    def process(
        self, text: str, images: list[str] = None, files: list[dict] = None, rag_context: str = "",
        conversation_history: list[dict] | None = None
    ) -> dict[str, Any]:
        """完整的多模态处理流程（非流式）"""
        # 第一步：拆解
        mm_input = self.parse_input(text, images, files)

        # 意图识别优先：检测用户是否明确要求忽略图片/文件
        # 如果命中，直接丢弃图片/文件数据，不做任何视觉解析
        if self.should_ignore_multimodal(mm_input.text):
            mm_input.images = []
            mm_input.files = []

        # 第二步：单独理解
        file_infos = self.extract_file_text(mm_input.files) if mm_input.has_files else []
        intent = self.classify_intent(mm_input.text, has_multimodal=mm_input.is_multimodal)

        # 提取图片描述（使用专用视觉模型）
        image_description = ""
        if mm_input.has_images:
            image_description = self.extract_image_descriptions(mm_input.images)

        # 第三步：融合思考（逻辑推理）
        thinking_steps = self.fusion_think(mm_input, file_infos, rag_context, image_description)

        # 第四步：生成回答
        answer = self.generate_answer(
            mm_input, file_infos, rag_context, image_description,
            conversation_history=conversation_history
        )

        # 第五步：若意图是文生图或文生视频，同步生成多媒体内容
        image_info: dict[str, Any] = {}
        video_info: dict[str, Any] = {}
        if intent == self.INTENT_GENERATE_IMAGE:
            image_info = self.generate_image(mm_input, rag_context)
        elif intent == self.INTENT_GENERATE_VIDEO:
            video_info = self.generate_video(mm_input, rag_context)

        return {
            "input_summary": mm_input.summary(),
            "intent": intent,
            "intent_label": self.intent_label(intent),
            "thinking_steps": thinking_steps,
            "answer": answer,
            "image_info": image_info,
            "video_info": video_info,
            "file_infos": [
                {"name": fi["name"], "type": fi["type"], "text_length": fi["text_length"]}
                for fi in file_infos
            ],
            "image_description": image_description[:200] if image_description else "",
        }

    def stream_process(
        self, text: str, images: list[str] = None, files: list[dict] = None, rag_context: str = "",
        conversation_history: list[dict] | None = None
    ) -> Generator[str, None, None]:
        """完整的多模态处理流程（流式，SSE 事件）"""
        mm_input = self.parse_input(text, images, files)

        # 意图识别优先：检测用户是否明确要求忽略图片/文件
        if self.should_ignore_multimodal(mm_input.text):
            mm_input.images = []
            mm_input.files = []

        file_infos = self.extract_file_text(mm_input.files) if mm_input.has_files else []
        intent = self.classify_intent(mm_input.text, has_multimodal=mm_input.is_multimodal)

        # 提取图片描述（使用专用视觉模型）
        image_description = ""
        if mm_input.has_images:
            image_description = self.extract_image_descriptions(mm_input.images)

        # 发送意图识别和拆解信息
        intent_info = {
            "intent": intent,
            "intent_label": self.intent_label(intent),
            "has_images": mm_input.has_images,
            "image_count": len(mm_input.images),
            "has_files": mm_input.has_files,
            "has_image_description": bool(image_description),
            "file_infos": [
                {"name": fi["name"], "type": fi["type"], "text_length": fi["text_length"]}
                for fi in file_infos
            ],
        }
        yield f"event: multimodal_info\ndata: {json.dumps(intent_info, ensure_ascii=False)}\n\n"

        # 发送融合思考步骤
        thinking_steps = self.fusion_think(mm_input, file_infos, rag_context, image_description)
        for step in thinking_steps:
            step_content = step + "\n"
            yield f"event: thinking\ndata: {json.dumps({'content': step_content}, ensure_ascii=False)}\n\n"

        yield "event: answer_start\ndata: {\"content\": \"\"}\n\n"

        # 生成回答
        for chunk in self.stream_generate_answer(
            mm_input, file_infos, rag_context, image_description,
            conversation_history=conversation_history
        ):
            yield f"event: answer\ndata: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"

        yield "event: done\ndata: {\"content\": \"[DONE]\"}\n\n"
