from __future__ import annotations

import json
import os
import re
from typing import Any

from ..ai_client import QwenClient
from ..guardrails import ContentGuard


class BaseAgent:
    """所有 Agent 的基类，提供 LLM 通信、JSON 解析、安全审核等公共能力"""

    def __init__(self, profile: dict, agent_name: str = ""):
        self.profile = profile
        self.agent_name = agent_name or self.__class__.__name__
        self.guard = ContentGuard()
        self.qwen = QwenClient()
        self.use_remote = os.getenv("USE_REMOTE_LLM", "auto").lower() != "never"

    @property
    def enabled(self) -> bool:
        return self.use_remote and self.qwen.enabled

    def role_prompt(self) -> str:
        """每个 Agent 子类重写此方法，返回自己的角色定义"""
        return (
            f"你是多智能体学习系统中的【{self.agent_name}】，"
            "负责特定的学习辅助任务。"
            "输出必须结合学生画像动态生成，不允许复用固定模板。"
            f"{self.guard.agent_constraints()}"
        )

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM，支持 LangChain 和直接 API 两种方式"""
        langchain_answer = self._try_langchain(system_prompt, user_prompt)
        if langchain_answer:
            return langchain_answer
        return self.qwen.chat(system_prompt, user_prompt)

    def _try_langchain(self, system_prompt: str, user_prompt: str) -> str:
        if os.getenv("USE_LANGCHAIN_AGENT", "false").lower() != "true":
            return ""
        try:
            from langchain_community.chat_models.tongyi import ChatTongyi
            from langchain_core.messages import HumanMessage, SystemMessage
        except Exception:
            return ""
        model = ChatTongyi(
            model_name=os.getenv("DASHSCOPE_MODEL", "qwen-max"),
            dashscope_api_key=os.getenv("DASHSCOPE_API_KEY", ""),
            temperature=0.7,
            request_timeout=300,
            model_kwargs={
                "enable_thinking": os.getenv("DASHSCOPE_ENABLE_THINKING", "false").strip().lower()
                in ("true", "1", "yes", "on")
            },
        )
        retry_count = int(os.getenv("LLM_RETRY_COUNT", "2"))
        import time, random
        for attempt in range(retry_count + 1):
            try:
                response = model.invoke(
                    [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                )
                return getattr(response, "content", "") or ""
            except Exception:
                if attempt >= retry_count:
                    raise
                time.sleep((2 ** attempt) + random.uniform(0, 0.5))
        return ""

    def extract_json(self, content: str) -> dict:
        """从 LLM 返回文本中提取 JSON"""
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
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.S)
            if not match:
                raise
            return json.loads(match.group(0))

    def apply_safety(self, content: str, source_context: str = "") -> tuple[str, Any]:
        return self.guard.apply_output_guard(content, source_context)

    def _retrieve_context(self, resource_type: str, query_hint: str = "") -> str:
        """根据资源类型从知识库检索相关上下文，用于注入生成 prompt"""
        user_id = self.profile.get("user_id") or self.profile.get("id")
        if not user_id:
            return ""
        from ..rag_config import ENABLE_RAG_OPTIMIZATION, getRagMode, getRagPolicy, shouldUseRAG
        if not ENABLE_RAG_OPTIMIZATION:
            return ""
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
                user_id,
                query_hint or self.profile.get("topic", "") or "课程核心知识",
                mode=rag_mode,
                timeout_ms=policy.get("timeoutMs", 3000),
            )
            return context
        except Exception as exc:
            import sys
            print(f"[base_agent] _retrieve_context error: {exc}", file=sys.stderr, flush=True)
            return ""

    def agent_meta(self, message: str = "") -> dict[str, Any]:
        return {
            "enabled": True,
            "agent": self.agent_name,
            "mode": "langchain_agent_or_qwen_agent",
            "message": message or f"已调用【{self.agent_name}】动态生成内容",
        }

    def fallback_meta(self, message: str) -> dict[str, Any]:
        return {"enabled": False, "agent": self.agent_name, "mode": "local_fallback", "message": message}
