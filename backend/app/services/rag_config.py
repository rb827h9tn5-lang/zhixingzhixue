# -*- coding: utf-8 -*-
from __future__ import annotations
"""
RAG 策略配置模块：资源类型识别、RAG 模式分级、策略配置、缓存、开关

集中管理所有 RAG 相关配置，新功能默认关闭（ENABLE_RAG_OPTIMIZATION=false）。
"""

import hashlib
import json
import os
import re
import threading
import time
from typing import Any

# ============================================================
# 一、全局开关（默认关闭）
# ============================================================
ENABLE_RAG_OPTIMIZATION = os.getenv("ENABLE_RAG_OPTIMIZATION", "false").lower() == "true"
ENABLE_RAG_CACHE = os.getenv("ENABLE_RAG_CACHE", "true").lower() == "true"
ENABLE_RAG_TIMING_LOG = os.getenv("ENABLE_RAG_TIMING_LOG", "false").lower() == "true"
ENABLE_PARALLEL_RESOURCE_GEN = os.getenv("ENABLE_PARALLEL_RESOURCE_GEN", "true").lower() == "true"
ENABLE_AUTO_PATH_RESOURCES = os.getenv("ENABLE_AUTO_PATH_RESOURCES", "true").lower() == "true"

# ============================================================
# 新增：数据流增强功能开关（默认关闭）
# ============================================================
# 测评评估时传入历史测评摘要作为参照
ENABLE_EVAL_HISTORY_REF = os.getenv("ENABLE_EVAL_HISTORY_REF", "false").lower() == "true"
# 学习路径中标记已学/未学知识点
ENABLE_PATH_LEARNED_TRACKING = os.getenv("ENABLE_PATH_LEARNED_TRACKING", "false").lower() == "true"
# 题库生成时优先考察历史错题和薄弱点
ENABLE_QUIZ_WEAK_POINTS_PRIORITY = os.getenv("ENABLE_QUIZ_WEAK_POINTS_PRIORITY", "false").lower() == "true"
# 智能辅导时传入完整学习记录摘要
ENABLE_TUTOR_LEARNING_RECORD = os.getenv("ENABLE_TUTOR_LEARNING_RECORD", "false").lower() == "true"


# ============================================================
# 二、资源类型枚举与识别
# ============================================================
RESOURCE_TYPES = {
    "normal_chat": "普通聊天",
    "explanation_doc": "讲解文档",
    "mindmap": "思维导图",
    "question_bank": "练习题库",
    "extended_reading": "拓展阅读",
    "practical_case": "实操案例",
    "teaching_video": "教学视频",
    "ppt_generation": "PPT 生成",
    "assessment": "测评评估",
    "tutoring": "智能辅导",
}


def detectResourceType(userMessage: str, chatHistory: list | None = None, agentConfig: dict | None = None) -> str:
    """根据用户消息和对话历史识别资源类型

    优先级规则：按匹配强度从高到低依次检查

    Args:
        userMessage: 用户当前输入
        chatHistory: 对话历史列表（可选）
        agentConfig: Agent 配置（可选）

    Returns:
        资源类型字符串，取值来自 RESOURCE_TYPES 的 key
    """
    text = (userMessage or "").strip()
    if not text:
        return "normal_chat"

    # 规则 1：讲解文档
    if re.search(r"生成\s*(讲解文档|学习资料|教案|章节讲义|教学讲义|课程讲义)", text):
        return "explanation_doc"

    # 规则 2：思维导图
    if re.search(r"生成\s*(思维导图|知识图谱|脑图|mindmap|mind map|知识结构图|概念图)", text, re.IGNORECASE):
        return "mindmap"

    # 规则 3：练习题库
    if re.search(r"(出题|练习题|题库|选择题|判断题|填空题|简答题|试卷|考试题|测试题|自测|练习)", text):
        return "question_bank"

    # 规则 4：拓展阅读
    if re.search(r"(拓展阅读|推荐阅读|延伸资料|参考资料|扩展阅读|延伸阅读|课外阅读)", text):
        return "extended_reading"

    # 规则 5：实操案例
    if re.search(r"(案例|实操|项目实战|上机实验|操作步骤|实战案例|动手实践|实验)", text):
        return "practical_case"

    # 规则 6：教学视频
    if re.search(r"(教学视频|视频脚本|分镜|旁白|镜头脚本|视频制作|录课|微课)", text):
        return "teaching_video"

    # 规则 7：PPT 生成
    if re.search(r"(PPT|课件|幻灯片|slide|presentation|演示文稿|演示文档)", text, re.IGNORECASE):
        return "ppt_generation"

    # 规则 8：测评评估
    if re.search(r"(测评|评估|学习诊断|水平测试|评分|能力分析|摸底|测试水平|诊断)", text):
        return "assessment"

    # 规则 9：智能辅导（连续问答、答疑、纠错、追问、辅导）
    # 如果消息以疑问词开头或包含问号，且其他类型都不匹配，视为辅导
    if re.search(r"^(为什么|怎么|如何|什么是|能不能|是否|怎样|哪个|哪些|有没有|是不是|会不会)", text):
        return "tutoring"

    # 如果有对话历史且上一轮是辅导或聊天，视为连续辅导
    if chatHistory and len(chatHistory) > 0:
        last_role = chatHistory[-1].get("role", "") if isinstance(chatHistory[-1], dict) else ""
        if last_role == "assistant":
            return "tutoring"

    # 规则 10：默认
    return "normal_chat"


# ============================================================
# 三、RAG 模式分级
# ============================================================
RAG_MODES = ["none", "light", "standard", "deep"]


def getRagMode(resourceType: str, userMessage: str = "", knowledgeBaseMode: str = "auto") -> str:
    """根据资源类型和用户设置确定 RAG 模式

    Args:
        resourceType: 资源类型
        userMessage: 用户消息（用于 tutoring 模式下的智能判断）
        knowledgeBaseMode: 用户设置 auto/on/off

    Returns:
        rag 模式: none/light/standard/deep
    """
    # knowledgeBaseMode 优先级最高
    if knowledgeBaseMode == "off":
        return "none"
    if knowledgeBaseMode == "on":
        # 强制开启知识库时，tutoring 走 light，其他走对应默认
        if resourceType == "tutoring":
            # 判断是否涉及新知识点或复杂问题
            if knowledgeBaseMode == "on":
                if re.search(r"(是什么|概念|定义|原理|公式|分类|区别|比较|为什么)", userMessage):
                    return "standard"
                return "light"
        return _get_default_mode(resourceType)

    # knowledgeBaseMode == "auto"
    if resourceType == "tutoring":
        # 连续追问、解释上一轮、简单答疑优先使用对话上下文
        if re.search(r"(刚才|上一|刚才那|为什么这样|什么意思|能不能解释)", userMessage):
            return "light"
        # 新知识点、课程内容、明确说根据资料
        if re.search(r"(根据资料|根据课件|根据文档|根据知识库|按课程|按教材|什么是|概念|定义|原理)", userMessage):
            return "standard"
        return "light"
    elif resourceType == "normal_chat":
        # 判断是否需要知识库
        if re.search(r"(根据资料|根据课件|根据文档|根据知识库|按课程|课程内容|知识库|教材|章节)", userMessage):
            return "light"
        return "none"

    # 其他资源类型按默认策略
    return _get_default_mode(resourceType)


def _get_default_mode(resourceType: str) -> str:
    """获取资源类型的默认 RAG 模式"""
    mode_map = {
        "explanation_doc": "deep",
        "question_bank": "deep",
        "ppt_generation": "deep",
        "assessment": "deep",
        "mindmap": "standard",
        "extended_reading": "standard",
        "practical_case": "standard",
        "teaching_video": "standard",
        "tutoring": "light",
        "normal_chat": "none",
    }
    return mode_map.get(resourceType, "none")


# ============================================================
# 四、RAG 策略配置
# ============================================================
RAG_POLICIES = {
    "none": {
        "useRag": False,
        "description": "不使用 RAG",
    },
    "light": {
        "useRag": True,
        "topK": 3,
        "candidateK": 10,
        "rerank": False,
        "timeoutMs": 600,
        "useCache": True,
        "description": "轻量 RAG：仅关键词检索，适用于辅导、简单问答",
    },
    "standard": {
        "useRag": True,
        "topK": 6,
        "candidateK": 20,
        "rerank": True,
        "timeoutMs": 1200,
        "useCache": True,
        "description": "标准 RAG：FAISS + 关键词检索，适用于一般资源生成",
    },
    "deep": {
        "useRag": True,
        "topK": 10,
        "candidateK": 40,
        "rerank": True,
        "timeoutMs": 2500,
        "useCache": True,
        "description": "深度 RAG：高覆盖率检索 + 重排序，适用于文档、题库、PPT、测评",
    },
}


def getRagPolicy(resourceType: str) -> dict:
    """获取指定资源类型的完整 RAG 策略配置"""
    rag_mode = _get_default_mode(resourceType)
    return dict(RAG_POLICIES.get(rag_mode, RAG_POLICIES["none"]))


# ============================================================
# 五、RAG 决策逻辑
# ============================================================
def shouldUseRAG(
    userMessage: str,
    chatHistory: list | None = None,
    resourceType: str = "normal_chat",
    agentConfig: dict | None = None,
    knowledgeBaseMode: str = "auto",
) -> bool:
    """判断当前请求是否应该使用 RAG

    优先级：knowledgeBaseMode > resourceType 规则 > 消息内容分析

    Args:
        userMessage: 用户消息
        chatHistory: 对话历史
        resourceType: 已识别的资源类型
        agentConfig: Agent 配置
        knowledgeBaseMode: 用户设置 auto/on/off

    Returns:
        是否使用 RAG
    """
    # 如果没有启用 RAG 优化，回退到原有逻辑
    if not ENABLE_RAG_OPTIMIZATION:
        # 保留原有判断（仅在 tutoring 中基于消息内容判断）
        if resourceType in ("tutoring", "normal_chat"):
            text = (userMessage or "").strip()
            if not text or re.search(r"^(你好|hi|hello|谢谢|再见|bye|早上好|下午好|晚上好|嗯|好的|ok)", text, re.IGNORECASE):
                return False
            if re.search(r"翻译|润色|改写", text):
                return False
            return True
        return True

    # 规则 1：knowledgeBaseMode 优先级最高
    if knowledgeBaseMode == "off":
        return False
    if knowledgeBaseMode == "on":
        return True

    # knowledgeBaseMode == "auto"
    # 规则 2：资源生成类必须优先使用 RAG
    resource_must_rag = {
        "explanation_doc", "mindmap", "question_bank", "extended_reading",
        "practical_case", "teaching_video", "ppt_generation", "assessment",
    }
    if resourceType in resource_must_rag:
        return True

    # 规则 3：tutoring 自动判断
    if resourceType == "tutoring":
        text = (userMessage or "").strip()
        # 跳过：闲聊、打招呼、翻译、润色、改写
        if re.search(r"^(你好|hi|hello|谢谢|再见|bye|早上好|下午好|晚上好|嗯|好的|ok|哈哈|呵呵|好的谢谢)", text, re.IGNORECASE):
            return False
        if re.search(r"^(翻译|润色|改写|总结一下|格式化)", text):
            return False
        # 需要使用 RAG：课程相关、资料相关
        if re.search(r"(根据资料|根据课件|根据文档|根据知识库|按课程|课程内容|知识库|教材|章节|是什么|概念|定义|原理|公式)", text):
            return True
        # 简单答疑、追问可以不使用 RAG
        if re.search(r"^(为什么|怎么|如何|能不能|是否|怎样|哪个|哪些|有没有)", text):
            return False
        return False

    # 规则 4：normal_chat
    if resourceType == "normal_chat":
        text = (userMessage or "").strip()
        # 跳过
        if not text or re.search(r"^(你好|hi|hello|谢谢|再见|bye|早上好|下午好|晚上好)", text, re.IGNORECASE):
            return False
        if re.search(r"翻译|润色|改写|格式调整", text):
            return False
        # 需要知识库
        if re.search(r"(课程|知识库|资料|文档|课件|教材|章节|根据)", text):
            return True
        return False

    return False


# ============================================================
# 六、简易 RAG 缓存
# ============================================================
_rag_cache: dict[str, dict] = {}
_rag_cache_lock = threading.Lock()
_RAG_CACHE_TTL = int(os.getenv("RAG_CACHE_TTL", "300"))  # 默认 5 分钟


def _rag_cache_key(user_id: int, query: str, resource_type: str, rag_mode: str, kb_mode: str) -> str:
    """生成缓存 key"""
    raw = f"{user_id}:{resource_type}:{rag_mode}:{kb_mode}:{query.lower().strip()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def ragCacheGet(user_id: int, query: str, resource_type: str, rag_mode: str, kb_mode: str = "auto") -> list[dict] | None:
    """从缓存中获取 RAG 结果"""
    if not ENABLE_RAG_CACHE:
        return None
    key = _rag_cache_key(user_id, query, resource_type, rag_mode, kb_mode)
    with _rag_cache_lock:
        entry = _rag_cache.get(key)
        if entry is not None:
            if time.time() - entry["ts"] < _RAG_CACHE_TTL:
                return entry["data"]
            del _rag_cache[key]
    return None


def ragCacheSet(user_id: int, query: str, resource_type: str, rag_mode: str, kb_mode: str, data: list[dict]) -> None:
    """将 RAG 结果写入缓存"""
    if not ENABLE_RAG_CACHE:
        return
    key = _rag_cache_key(user_id, query, resource_type, rag_mode, kb_mode)
    with _rag_cache_lock:
        _rag_cache[key] = {"data": data, "ts": time.time()}


def ragCacheClear(user_id: int | None = None) -> None:
    """清除 RAG 缓存（可指定用户）"""
    with _rag_cache_lock:
        if user_id is None:
            _rag_cache.clear()
        else:
            keys_to_delete = [k for k in _rag_cache if k.startswith(str(user_id) + ":")]
            for k in keys_to_delete:
                del _rag_cache[k]


# ============================================================
# 七、计时日志工具
# ============================================================
class RagTimingLogger:
    """RAG 计时日志记录器"""

    def __init__(self, request_id: str = ""):
        self.request_id = request_id
        self._logs: list[dict] = []

    def record(self, operation: str, elapsed_ms: float, **kwargs) -> None:
        """记录一条计时日志"""
        if not ENABLE_RAG_TIMING_LOG:
            return
        entry = {
            "operation": operation,
            "elapsed_ms": round(elapsed_ms, 1),
            "ts": time.time(),
        }
        entry.update(kwargs)
        self._logs.append(entry)

    def summary(self) -> dict:
        """汇总日志为结构化的报告字典"""
        if not self._logs:
            return {}
        total_ms = sum(e["elapsed_ms"] for e in self._logs)
        return {
            "request_id": self.request_id,
            "total_ms": round(total_ms, 1),
            "operation_count": len(self._logs),
            "operations": list(self._logs),
        }

    def print_log(self, **extra_fields) -> None:
        """打印结构化日志到 stderr"""
        if not ENABLE_RAG_TIMING_LOG:
            return
        import sys
        pieces = [f"[rag_timing] request_id={self.request_id}"]
        for k, v in extra_fields.items():
            pieces.append(f"{k}={v}")
        total_ms = sum(e["elapsed_ms"] for e in self._logs) if self._logs else 0
        pieces.append(f"total_ms={round(total_ms, 1)}")
        pieces.append(f"operations={len(self._logs)}")
        print(" | ".join(pieces), file=sys.stderr, flush=True)