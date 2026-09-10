from __future__ import annotations

import concurrent.futures
import json
import os
import random
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from flask import Blueprint, Response, current_app, jsonify, request, send_from_directory, stream_with_context
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import (
    AdaptiveExam,
    AgentRun,
    ChatConversation,
    CognitiveDiagnosis,
    CodingCaseRecord,
    KnowledgeDocument,
    KnowledgePoint,
    LearningEvent,
    LearningPath,
    LearningPathNode,
    LearningPathVersion,
    Profile,
    ProfileEvidence,
    ProfileVersion,
    PptRecord,
    QuizResult,
    Resource,
    ResourceInnovationAnalysis,
    TaskActionLog,
    UserKnowledgeMastery,
)
from ..services.ai_client import QwenClient
from ..services.adaptive_assessment_service import AdaptiveAssessmentService
from ..services.agent_trace_service import AgentTraceService
from ..services.db_channel import DbChannel, enqueue_db_task, get_channel_metrics, reset_channel_metrics
from ..services.guardrails import ContentGuard
from ..services.decision_explanation_service import DecisionExplanationService
from ..services.diagnosis_service import DiagnosisService
from ..services.growth_service import GrowthService
from ..services.intervention_service import LearningInterventionService
from ..services.local_generator import RESOURCE_LABELS, LocalStudyGenerator
from ..services.learning_event_service import LearningEventService
from ..services.mastery_service import MasteryService
from ..services.misconception_service import MisconceptionService
from ..services.mindmap_sanitizer import normalize_mindmap_content, validate_mindmap_content, mermaid_to_tree_json
from ..services.path_service import ReplanningService, StructuredPathService
from ..services.profile_evolver import evolve_profile_from_behavior
from ..services.profile_service import (
    confirm_profile_draft,
    extract_profile_draft,
    record_behavior_profile_change,
    record_profile_version,
)
from ..services.quiz_judge import judge_open_answers
from ..services.question_mapping import (
    allowed_knowledge_points,
    knowledge_point_candidates,
    map_quiz_questions,
)
from ..services.remediation_service import RemediationService
from ..services.teaching_strategy_service import TeachingStrategyEngine
from ..services.transfer_service import (
    CapabilityGateService,
    MasteryDimensionService,
    MetacognitiveCalibrationService,
)
from ..services.rag_store import format_source_citation, hybrid_query_chunks
from ..services.agents.multimodal_tutor_agent import MultimodalTutorAgent
from ..services.study_agent import StudyResourceAgent
from ..services.search_bili import search_bili_video as search_bili_video_api

learning_bp = Blueprint("learning", __name__)
guard = ContentGuard()


def current_profile() -> Profile:
    profile = Profile.query.filter_by(user_id=int(get_jwt_identity())).first()
    if not profile:
        profile = Profile(user_id=int(get_jwt_identity()))
        db.session.add(profile)
        db.session.flush()
        record_profile_version(
            profile,
            previous={},
            changes=[],
            evidence_type="migration_snapshot",
            evidence_source_id="profile-create",
            evidence_description="创建用户默认画像快照",
            confidence=1.0,
            change_summary="创建初始画像",
        )
        db.session.commit()
    return profile


def _generate_path_resources_in_background(app, user_id: int, profile_snapshot: dict) -> None:
    """并发生成学习路径配套的 5 类个性化资源（后台线程执行，不阻塞 HTTP 响应）。"""
    auto_types = ["course_document", "mind_map", "exercise_bank", "extension_reading", "coding_case"]
    from app.services.rag_config import ENABLE_PARALLEL_RESOURCE_GEN

    def _generate_one(rtype: str) -> str:
        """生成单一资源，返回类型标识（成功时）或空字符串（失败时）。"""
        with app.app_context():
            try:
                profile = Profile.query.filter_by(user_id=user_id).first()
                profile_data = profile.to_dict() if profile else profile_snapshot
                agent = StudyResourceAgent(profile_data, user_id=user_id)
                generator = LocalStudyGenerator(profile_data)
                local_fn = lambda rt=rtype: generator.generate_resource(rt, "")
                content, meta = agent.generate_resource(rtype, local_fn, "")
                if rtype == "mind_map":
                    content = normalize_mindmap_content(content, profile_data.get("topic", ""))
                content, _ = ContentGuard().apply_output_guard(content)
                resource = Resource(
                    user_id=user_id,
                    resource_type=rtype,
                    title=RESOURCE_LABELS.get(rtype, rtype),
                    content=content,
                )
                db.session.add(resource)
                db.session.commit()
                return rtype
            except Exception as exc:
                db.session.rollback()
                app.logger.warning("path auto resource generation failed type=%s user=%s: %s", rtype, user_id, exc)
                return ""
            finally:
                db.session.remove()

    if ENABLE_PARALLEL_RESOURCE_GEN:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(auto_types), thread_name_prefix="path_res_") as pool:
            results = list(pool.map(_generate_one, auto_types))
        succeeded = [r for r in results if r]
        app.logger.info("path auto resource generation finished user=%s success=%d total=%d", user_id, len(succeeded), len(auto_types))
    else:
        generated_count = 0
        for rtype in auto_types:
            result = _generate_one(rtype)
            if result:
                generated_count += 1
        app.logger.info("path auto resource generation finished user=%s count=%s", user_id, generated_count)


def _generate_single_resource_in_background(
    app, user_id: int, profile_snapshot: dict,
    resource_type: str, extra_input: str,
) -> None:
    """在后台线程中生成单个资源并保存到数据库（不阻塞 HTTP 响应）。"""
    with app.app_context():
        try:
            profile = Profile.query.filter_by(user_id=user_id).first()
            profile_data = profile.to_dict() if profile else profile_snapshot
            agent = StudyResourceAgent(profile_data, user_id=user_id)
            generator = LocalStudyGenerator(profile_data)
            local_fn = lambda: generator.generate_resource(resource_type, extra_input)
            content, meta = agent.generate_resource(resource_type, local_fn, extra_input)
            if resource_type == "mind_map":
                content = normalize_mindmap_content(content, profile_data.get("topic", ""))
            content, _ = ContentGuard().apply_output_guard(content)
            resource = Resource(
                user_id=user_id,
                resource_type=resource_type,
                title=RESOURCE_LABELS.get(resource_type, resource_type),
                content=content,
            )
            db.session.add(resource)
            db.session.commit()
            app.logger.info("async resource generation succeeded type=%s user=%s", resource_type, user_id)
        except Exception as exc:
            db.session.rollback()
            app.logger.warning("async resource generation failed type=%s user=%s: %s", resource_type, user_id, exc)
        finally:
            db.session.remove()


# ── DB Channel 操作处理器 ──────────────────────────────
# 这些 handler 作为 enqueue_db_task 的回调，每个 handler 只做一件事

def _handler_save_resource(user_id: int, resource_type: str, title: str, content: str) -> Resource:
    """保存资源记录 → async_channel"""
    resource = Resource(user_id=user_id, resource_type=resource_type, title=title, content=content)
    db.session.add(resource)
    db.session.commit()
    return resource


def _handler_update_profile(profile_id: int, action: str, **data) -> None:
    """更新学习画像 → async_channel / background_channel"""
    profile = db.session.get(Profile, profile_id)
    if profile is None:
        return
    auto_update_profile(profile, action, **data)
    db.session.commit()


def _handler_update_conversation(conversation_id: int, messages: list) -> None:
    """保存对话消息 → async_channel"""
    conv = db.session.get(ChatConversation, conversation_id)
    if conv is None:
        return
    conv.messages = messages
    db.session.commit()


def _handler_save_quiz(handler_data: dict) -> None:
    """保存测评结果 → background_channel"""
    record = QuizResult(**handler_data)
    db.session.add(record)
    db.session.commit()


def _handler_log_action(user_id: int, action: str) -> None:
    """记录任务操作 → background_channel"""
    log = TaskActionLog(user_id=user_id, action=action)
    db.session.add(log)
    db.session.commit()


# ────────────────────────────────────────────────────────


def profile_dict() -> dict:
    return current_profile().to_dict()


def auto_update_profile(profile: Profile, action: str, **data):
    previous = profile.to_dict()
    evolve_profile_from_behavior(profile, action, data)
    record_behavior_profile_change(
        profile,
        previous=previous,
        action=action,
        evidence_payload=data,
    )
    return
    """用户执行关键操作后自动更新画像（不覆盖手动设置的值）"""
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    if action == "generate_resource":
        types = data.get("types") or []
        type_str = "、".join(types) if isinstance(types, list) else str(types)
        line = f"[{now}] 生成学习资源：{type_str}"
        profile.raw_dialogue = ((profile.raw_dialogue or "") + "\n" + line).strip()
        profile.engagement_pattern = f"主动生成 {len(types) if isinstance(types, list) else 1} 类资源 + 测评复盘"

    elif action == "submit_quiz":
        score = data.get("score", 0) or 0
        line = f"[{now}] 完成答题测评，得分：{score}"
        profile.raw_dialogue = ((profile.raw_dialogue or "") + "\n" + line).strip()
        # 根据得分自动调整知识水平
        if score >= 85 and profile.knowledge_level in ("beginner", ""):
            profile.knowledge_level = "intermediate"
        elif score >= 90 and profile.knowledge_level == "intermediate":
            profile.knowledge_level = "advanced"

    elif action == "generate_case":
        line = f"[{now}] 完成编程案例练习"
        profile.raw_dialogue = ((profile.raw_dialogue or "") + "\n" + line).strip()
        profile.engagement_pattern = f"编程实操 + 测评复盘"

    elif action == "tutor_ask":
        question = data.get("question", "")
        if question:
            line = f"[{now}] 辅导提问：{question[:120]}{'…' if len(question) > 120 else ''}"
            profile.raw_dialogue = ((profile.raw_dialogue or "") + "\n" + line).strip()

    elif action == "generate_ppt":
        topic = data.get("topic", "")
        line = f"[{now}] 生成 PPT：{topic[:80]}{'…' if len(topic) > 80 else ''}"
        profile.raw_dialogue = ((profile.raw_dialogue or "") + "\n" + line).strip()
        profile.engagement_pattern = f"PPT 制作 + 资源整合"


def visible_resources_for_user(user_id: int, limit: int | None = None) -> list[Resource]:
    query = Resource.query.filter_by(user_id=user_id).filter(Resource.resource_type != "ppt_deck").order_by(Resource.created_at.desc(), Resource.id.desc())
    if limit:
        query = query.limit(limit)
    return query.all()


def safety_rejection(text: str):
    safety = guard.scan_request(text)
    if safety.allowed:
        return None
    return jsonify({"message": "请求未通过后端内容安全约束", "safety": safety.to_dict()}), 400


def retrieve_knowledge_context(user_id: int, question: str, mode: str = "standard",
                                timeout_ms: int = 3000) -> tuple[str, list[dict]]:
    """检索知识库内容

    Args:
        user_id: 用户 ID
        question: 查询问题
        mode: RAG 模式 (light/standard/deep)
        timeout_ms: 超时时间（毫秒）

    Returns:
        (上下文文本, 来源列表)
    """
    documents = KnowledgeDocument.query.filter_by(user_id=user_id).all()
    document_payloads = [document.to_dict() for document in documents]
    sources = hybrid_query_chunks(question, document_payloads, user_id, mode=mode, timeout_ms=timeout_ms)
    if not sources:
        return "", []
    context = "\n\n".join(
        f"[{format_source_citation(item)}，相关度：{item['score']}]\n{item['content']}"
        for item in sources
    )
    return context, sources


def _build_quiz_history_summary(user_id: int) -> str:
    """构建历史测评摘要（用于评估时作为参照，防止幻觉）

    汇总最近测评的分数趋势和薄弱点，数据不存在时返回空字符串。
    """
    from app.services.rag_config import ENABLE_EVAL_HISTORY_REF
    if not ENABLE_EVAL_HISTORY_REF:
        return ""
    results = QuizResult.query.filter_by(user_id=user_id)\
        .order_by(QuizResult.created_at.desc()).limit(10).all()
    if not results:
        return ""
    scores = [r.score for r in results if r.score is not None]
    weak_points: set[str] = set()
    for r in results:
        if r.wrong_questions:
            for p in re.split(r"[;；,，\n]", r.wrong_questions):
                p = p.strip()
                if p and len(p) < 50:
                    weak_points.add(p)
    parts = []
    if scores:
        parts.append(f"最近{len(scores)}次测评分数趋势：{' → '.join(str(int(round(s))) for s in scores[:5])}")
    if weak_points:
        parts.append(f"历史薄弱点汇总：{'、'.join(list(weak_points)[:8])}")
    return "；".join(parts) if parts else ""


def _build_learning_record_summary(user_id: int) -> str:
    """构建学习记录摘要（用于辅导时参考）

    汇总已生成资源类型、测评成绩趋势、实操完成情况。
    数据不存在时返回空字符串。
    """
    from app.services.rag_config import  ENABLE_TUTOR_LEARNING_RECORD
    if not ENABLE_TUTOR_LEARNING_RECORD:
        return ""
    parts: list[str] = []
    # 已生成资源
    resources = Resource.query.filter_by(user_id=user_id)\
        .order_by(Resource.created_at.desc()).limit(20).all()
    if resources:
        type_labels = sorted({r.resource_type for r in resources})
        parts.append(f"已生成资源类型：{'、'.join(type_labels)}")
    # 测评记录
    results = QuizResult.query.filter_by(user_id=user_id)\
        .order_by(QuizResult.created_at.desc()).limit(5).all()
    if results:
        scores = [r.score for r in results if r.score is not None]
        if scores:
            parts.append(f"最近测评分数：{'→'.join(str(int(round(s))) for s in scores)}")
    # 实操案例
    cases = CodingCaseRecord.query.filter_by(user_id=user_id)\
        .order_by(CodingCaseRecord.created_at.desc()).limit(5).all()
    if cases:
        passed = sum(1 for c in cases if c.is_passed)
        parts.append(f"实操案例：完成{len(cases)}次，通过{passed}次")
    return "；".join(parts) if parts else ""


def _build_mastery_summary(user_id: int) -> str:
    mastery = MasteryService.list_user_mastery(user_id)
    assessed = [item for item in mastery if item["mastery_score"] is not None]
    if not assessed:
        return ""
    weakest = sorted(
        assessed,
        key=lambda item: (item["mastery_score"], item["confidence"]),
    )[:5]
    lines = [
        (
            f"{item['knowledge_point']}：Mastery {round(item['mastery_score'])}%"
            f"，Confidence {round(item['confidence'], 2)}"
            f"，作答 {item['attempt_count']} 次"
        )
        for item in weakest
    ]
    unassessed = len(mastery) - len(assessed)
    if unassessed:
        lines.append(f"另有 {unassessed} 个知识点尚未评估")
    return "；".join(lines)


def _build_weak_points_summary(user_id: int) -> str:
    """构建错题/薄弱点摘要（用于出题时优先考察）

    从最近测评记录中提取错题知识点，用于指导出题方向。
    数据不存在时返回空字符串。
    """
    from app.services.rag_config import ENABLE_QUIZ_WEAK_POINTS_PRIORITY
    if not ENABLE_QUIZ_WEAK_POINTS_PRIORITY:
        return ""
    results = QuizResult.query.filter_by(user_id=user_id)\
        .order_by(QuizResult.created_at.desc()).limit(10).all()
    if not results:
        return ""
    wrong_points: set[str] = set()
    for r in results:
        if r.wrong_questions:
            for p in re.split(r"[;；,，\n]", r.wrong_questions):
                p = p.strip()
                if p and len(p) < 50:
                    wrong_points.add(p)
        # 从 answers 的 weak_points 中提取
        if r.answers and isinstance(r.answers, dict):
            wp = r.answers.get("weak_points") or []
            if isinstance(wp, list):
                for p in wp:
                    if isinstance(p, str) and p.strip() and len(p) < 50:
                        wrong_points.add(p.strip())
    if not wrong_points:
        return ""
    return f"历史错题知识点（建议优先考察）：{'、'.join(list(wrong_points)[:10])}"


def _build_learned_knowledge_summary(user_id: int) -> dict:
    """构建已学/未学知识点概览（用于学习路径规划）

    根据已生成资源类型、知识库文档和测评记录，
    判断学生已经覆盖的知识领域和尚未涉及的领域。
    数据不存在时返回空字典。
    """
    from app.services.rag_config import  ENABLE_PATH_LEARNED_TRACKING
    if not ENABLE_PATH_LEARNED_TRACKING:
        return {}
    # 已生成资源类型 → 已学的知识领域
    resources = Resource.query.filter_by(user_id=user_id)\
        .order_by(Resource.created_at.desc()).limit(30).all()
    learned_types = sorted({r.resource_type for r in resources}) if resources else []
    # 已上传的知识库文档标题 → 已接触的内容
    docs = KnowledgeDocument.query.filter_by(user_id=user_id)\
        .order_by(KnowledgeDocument.created_at.desc()).limit(10).all()
    doc_titles = [d.title for d in docs if d.title] if docs else []
    # 已测评的知识点
    results = QuizResult.query.filter_by(user_id=user_id)\
        .order_by(QuizResult.created_at.desc()).limit(10).all()
    quiz_concepts: set[str] = set()
    for r in results:
        if r.answers and isinstance(r.answers, dict):
            details = r.answers.get("details") or []
            for d in details:
                c = d.get("concept") or ""
                if c:
                    quiz_concepts.add(c)
    summary = {}
    if learned_types:
        summary["已学知识领域"] = "、".join(learned_types)
    if doc_titles:
        summary["已接触资料"] = "；".join(doc_titles[:5])
    if quiz_concepts:
        summary["已测评知识点"] = "、".join(list(quiz_concepts)[:8])
    # 计算未学领域（基于平台所有资源类型）
    all_types = {"course_document", "mind_map", "exercise_bank",
                 "extension_reading", "coding_case", "multimedia_video"}
    unlearned = all_types - set(learned_types)
    if unlearned:
        summary["建议拓展领域"] = "、".join(sorted(unlearned))
    return summary



def sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def mark_resource_section(index: int, section: dict, content: str) -> str:
    title = str(section.get("title") or section.get("chapterTitle") or f"第 {index + 1} 章").strip()
    section_no = index + 1
    return (
        f"<!-- MA_SECTION_START index={section_no} title={quote(title, safe='')} -->\n\n"
        f"{(content or '').strip()}\n\n"
        f"<!-- MA_SECTION_END index={section_no} -->"
    )


def is_invalid_resource_section(content: str) -> bool:
    text = (content or "").strip()
    if len(text) < 80:
        return True
    rejection_phrases = (
        "未通过后端安全约束",
        "已停止输出",
        "触发后端安全约束",
        "请改为合规",
    )
    return any(phrase in text for phrase in rejection_phrases)


def fallback_resource_section_content(section: dict, is_reading: bool) -> str:
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


def generate_resource_section_with_retry(agent: StudyResourceAgent, section: dict, extra_input: str, is_reading: bool) -> str:
    retry_note = ""
    last_content = ""
    for attempt in range(3):
        retry_input = extra_input
        if retry_note:
            retry_input = f"{extra_input}\n\n{retry_note}".strip()
        if is_reading:
            content = agent._generate_reading_section(section, retry_input)
        else:
            content = agent._generate_chapter_content(section, retry_input)
        last_content = (content or "").strip()
        if not is_invalid_resource_section(last_content):
            return last_content
        retry_note = (
            "上一版章节内容为空、过短或被安全约束拦截。请重新生成本章："
            "只讲合规的课程知识、概念解释、公式/案例/防御性实践；"
            "不要输出拒绝说明；使用标准 Markdown，二级/三级标题必须顶格书写。"
        )
    return fallback_resource_section_content(section, is_reading)


def parse_image_marker(marker: str) -> tuple[str, str]:
    """解析配图标记，返回 (prompt, size)，size 格式如 \"1024*1024\""""
    prompt = marker.strip()
    size = "1024*1024"
    if "|" in prompt:
        parts = prompt.split("|", 1)
        prompt = parts[0].strip()
        size_str = parts[1].strip()
        m = re.match(r'(\d+)\s*[xX×]\s*(\d+)', size_str)
        if m:
            size = f"{m.group(1)}*{m.group(2)}"
    # 校验 size 是否为 Wanx API 支持的尺寸，否则回退到默认值
    _valid_sizes = {"1024*1024", "720*1280", "1280*720", "768*1152", "1152*768"}
    if size not in _valid_sizes:
        print("[DEBUG parse_image_marker] unsupported size %s, falling back to 1024*1024" % size, file=sys.stderr, flush=True)
        size = "1024*1024"
    return prompt, size


def visible_thinking_steps(profile: dict, question: str, sources: list[dict]) -> list[str]:
    return [
        f"识别问题：围绕“{question[:60]}”进行学习辅导。",
        f"读取画像：当前主题为“{profile.get('topic', '')}”，知识水平为“{profile.get('knowledge_level', '')}”，学习风格为“{profile.get('learning_style', '')}”。",
        f"检索知识库：命中 {len(sources)} 个相关片段。",
        "回答计划：先解释核心概念，再给例子和练习建议。",
    ]


def is_tutor_identity_query(question: str) -> bool:
    text = re.sub(r"\s+", "", question or "").lower()
    if not text:
        return False
    greetings = {"你好", "您好", "hi", "hello", "嗨", "在吗", "你是谁", "介绍一下你自己", "你能做什么"}
    return text in greetings or text.strip("，。！？!?") in greetings


def tutor_identity_answer() -> str:
    return (
        "你好，我是「循证学习教练」，也是这个平台里的智能辅导 Agent。\n\n"
        "我会结合你的学生画像、课程知识库、上传的图片或文件来帮你定位困惑、解释概念、梳理步骤，"
        "并给出可执行的练习建议。你可以直接问我某个知识点、发题目截图，或者让我根据你的学习记录帮你复盘薄弱点。"
    )


def stream_text(text: str, chunk_size: int = 18):
    for index in range(0, len(text), chunk_size):
        yield sse_event("answer", {"content": text[index:index + chunk_size]})
        time.sleep(0.03)


# ──────────────────────────────────────────
# 媒体文件管理工具
# ──────────────────────────────────────────


def save_remote_file(url: str, subdir: str = "generated") -> str:
    """下载远程文件到 uploads/{subdir}/，返回本地服务 URL

    已在本地的文件（URL 包含 /api/uploads/）直接原样返回。
    """
    if not url or "/api/uploads/" in url:
        return url
    try:
        backend_dir = Path(__file__).resolve().parents[2]
        target_dir = backend_dir / "uploads" / subdir
        target_dir.mkdir(parents=True, exist_ok=True)

        resp = requests.get(url, timeout=120, stream=True)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "image" in content_type:
            ext = ".png"
        elif "video" in content_type:
            ext = ".mp4"
        else:
            path_part = url.split("?")[0]
            ext = os.path.splitext(path_part)[1] or ".bin"

        filename = f"{uuid.uuid4().hex}{ext}"
        local_path = target_dir / filename

        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        if local_path.exists() and local_path.stat().st_size > 0:
            return f"/api/uploads/{subdir}/{filename}"
    except Exception:
        pass
    return url  # 下载失败时回退到原 URL


# ──────────────────────────────────────────
# 流式 JSON 答案提取工具（智能辅导结构化输出）
# ──────────────────────────────────────────


def _extract_answer_from_json(text: str) -> tuple[str | None, bool]:
    """从（可能不完整的）JSON 文本中提取 answer 字段值。
    返回 (answer文本, 是否找到完整字段结束)。
    """
    match = re.search(r'"answer"\s*:\s*"', text)
    if not match:
        return None, False
    start = match.end()
    buf = text[start:]
    chars: list[str] = []
    i = 0
    while i < len(buf):
        c = buf[i]
        if c == '\\' and i + 1 < len(buf):
            chars.append(buf[i:i+2])
            i += 2
        elif c == '"':
            rest = buf[i + 1:]
            if not rest:
                return "".join(chars), False
            stripped = rest.lstrip()
            if stripped.startswith(",") or stripped.startswith("}"):
                return "".join(chars), True
            chars.append(c)
            i += 1
        else:
            chars.append(c)
            i += 1
    return "".join(chars), False


def _stream_json_answer(stream_gen, guard, rag_context, refusal_keywords):
    """包装流式 JSON 生成器，实时提取 answer 字段输出。
    完成后产出 ('image_prompt_raw', prompt_str)。
    """
    buffer = ""
    prev_answer = ""

    for chunk in stream_gen:
        buffer += chunk
        answer_text, is_complete = _extract_answer_from_json(buffer)
        if answer_text is None:
            continue

        if answer_text:
            if any(kw in answer_text for kw in refusal_keywords):
                yield "answer", {"content": "\n\n"}
                prev_answer = answer_text
                break
            safety = guard.review_content(answer_text, rag_context)
            if not safety.allowed:
                yield "answer", {"content": "\n\n该回答触发后端安全约束，已停止继续输出。"}
                prev_answer = answer_text
                break

        if len(answer_text) > len(prev_answer):
            new_part = answer_text[len(prev_answer):]
            yield "answer", {"content": new_part}
            prev_answer = answer_text

    # 从完整缓冲中解析 image_prompt
    image_prompt = ""
    try:
        data = json.loads(buffer)
        image_prompt = data.get("image_prompt", "") or ""
    except json.JSONDecodeError:
        pass
    yield "image_prompt_raw", image_prompt


def find_media_paths(data) -> set[str]:
    """在 JSON 数据中递归查找所有 /api/uploads/ 路径"""
    paths: set[str] = set()
    if isinstance(data, str):
        for m in re.finditer(r"/api/uploads/[^\s\"'<>]+", data):
            paths.add(m.group())
    elif isinstance(data, dict):
        for v in data.values():
            paths.update(find_media_paths(v))
    elif isinstance(data, list):
        for item in data:
            paths.update(find_media_paths(item))
    return paths


def delete_media_files(data):
    """删除 JSON 数据中引用的所有本地媒体文件"""
    if not data:
        return []
    backend_dir = Path(__file__).resolve().parents[2]
    upload_dir = backend_dir / "uploads"
    paths = find_media_paths(data)
    deleted = []
    for url_path in paths:
        relative = url_path.replace("/api/uploads/", "").lstrip("/")
        full_path = upload_dir / relative
        if full_path.exists() and full_path.is_file():
            try:
                os.remove(full_path)
                deleted.append(str(full_path))
            except Exception:
                pass
    return deleted


def weak_points_with_sources(user_id: int, limit: int = 8) -> list[dict]:
    results = (
        QuizResult.query
        .filter_by(user_id=user_id, category="evaluation")
        .order_by(QuizResult.created_at.desc())
        .limit(20)
        .all()
    )
    items: list[dict] = []
    seen: set[str] = set()
    for result in results:
        answers = result.answers if isinstance(result.answers, dict) else {}
        candidates: list[tuple[str, str]] = []
        if isinstance(answers.get("weak_points"), list):
            candidates.extend((str(point), "AI评价识别") for point in answers.get("weak_points") or [])
        for detail in answers.get("details") or []:
            if isinstance(detail, dict) and not detail.get("is_correct"):
                point = detail.get("concept") or detail.get("knowledge_point") or detail.get("id") or ""
                candidates.append((str(point), f"第{detail.get('id', '')}题答错"))
        candidates.extend((point, "历史错题记录") for point in re.split(r"[;；、,，\n]", result.wrong_questions or ""))

        for raw_point, reason in candidates:
            point = re.sub(r"^第?\d+题[:：、.\s-]*", "", raw_point).strip()
            point = re.sub(r"^(错题|知识点|概念)[:：\s]*", "", point).strip()
            if not point or point in seen:
                continue
            seen.add(point)
            items.append({
                "name": point,
                "source": reason,
                "record_id": result.id,
                "record_title": result.quiz_content or "测评记录",
                "score": result.score,
                "created_at": result.created_at.isoformat() if result.created_at else "",
            })
            if len(items) >= limit:
                return items

    if not items:
        profile = Profile.query.filter_by(user_id=user_id).first()
        for point in re.split(r"[;；、,，\n]", (profile.weak_points if profile else "") or ""):
            name = point.strip()
            if name and name not in seen:
                seen.add(name)
                items.append({
                    "name": name,
                    "source": "画像对话或旧记录提取",
                    "record_id": None,
                    "record_title": "学生画像",
                    "score": None,
                    "created_at": "",
                })
                if len(items) >= limit:
                    break
    return items


@learning_bp.get("/profile")
@jwt_required()
def get_profile():
    profile = current_profile()
    summary = LocalStudyGenerator(profile.to_dict()).build_profile_summary(profile.to_dict())
    return jsonify({
        "profile": profile.to_dict(),
        "summary": summary,
        "weak_points_sources": weak_points_with_sources(profile.user_id),
        "current_version": profile.current_version.to_dict() if profile.current_version else None,
    })


@learning_bp.post("/profile/intake/draft")
@jwt_required()
def draft_profile_intake():
    profile = current_profile()
    data = request.get_json(silent=True) or {}
    dialogue = str(data.get("dialogue") or "").strip()
    if not dialogue and not any(data.get(field) for field in ("major", "learning_goal", "time_availability")):
        return jsonify({"message": "请先填写一段学习情况或画像信息"}), 400
    result = extract_profile_draft(profile, data)
    result["current_version"] = profile.current_version.version if profile.current_version else 0
    return jsonify(result)


@learning_bp.post("/profile/intake/confirm")
@jwt_required()
def confirm_profile_intake():
    profile = current_profile()
    data = request.get_json(silent=True) or {}
    draft = data.get("draft")
    if not isinstance(draft, dict):
        return jsonify({"message": "待确认画像格式不正确"}), 400
    try:
        version, evidence, idempotent = confirm_profile_draft(
            profile,
            draft=draft,
            dialogue=str(data.get("dialogue") or ""),
            confidence=float(data.get("confidence") or 1.0),
            expected_version=(
                int(data["expected_version"])
                if data.get("expected_version") is not None
                else None
            ),
        )
        db.session.commit()
    except (TypeError, ValueError) as exc:
        db.session.rollback()
        return jsonify({"message": str(exc)}), 409
    summary = LocalStudyGenerator(profile.to_dict()).build_profile_summary(profile.to_dict())
    return jsonify({
        "profile": profile.to_dict(),
        "version": version.to_dict(),
        "evidence": [item.to_dict() for item in evidence],
        "idempotent": idempotent,
        "summary": summary,
        "weak_points_sources": weak_points_with_sources(profile.user_id),
    })


@learning_bp.get("/profile/versions")
@jwt_required()
def list_profile_versions():
    current_profile()
    versions = ProfileVersion.query.filter_by(
        user_id=int(get_jwt_identity()),
    ).order_by(ProfileVersion.version.desc()).all()
    return jsonify({"versions": [version.to_dict(include_evidence=True) for version in versions]})


@learning_bp.get("/profile/evidence")
@jwt_required()
def list_profile_evidence():
    current_profile()
    query = ProfileEvidence.query.filter_by(user_id=int(get_jwt_identity()))
    dimension = str(request.args.get("dimension") or "").strip()
    if dimension:
        query = query.filter_by(dimension=dimension)
    evidence = query.order_by(ProfileEvidence.created_at.desc(), ProfileEvidence.id.desc()).all()
    return jsonify({"evidence": [item.to_dict() for item in evidence]})


@learning_bp.get("/learning-events")
@jwt_required()
def list_learning_events():
    user_id = int(get_jwt_identity())
    knowledge_point_id = request.args.get("knowledge_point_id", type=int)
    limit = request.args.get("limit", default=100, type=int)
    if knowledge_point_id:
        rows = LearningEventService.list_kp_events(user_id, knowledge_point_id, limit)
    else:
        rows = LearningEventService.list_user_events(user_id, limit)
    return jsonify({"events": [row.to_dict() for row in rows]})


@learning_bp.post("/learning-events")
@jwt_required()
def create_learning_event():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    event_type = str(data.get("event_type") or "").strip()
    allowed_client_events = {"hint_request", "resource_open", "resource_complete", "tutor_help"}
    if event_type not in allowed_client_events:
        return jsonify({"message": "该学习事件只能由后端正式学习流程记录"}), 400

    knowledge_point_id = data.get("knowledge_point_id")
    if knowledge_point_id is not None:
        point = db.session.get(KnowledgePoint, int(knowledge_point_id))
        if not point:
            return jsonify({"message": "知识点不存在"}), 404
        knowledge_point_id = point.id

    resource_id = data.get("resource_id")
    if resource_id is not None:
        resource = Resource.query.filter_by(id=int(resource_id), user_id=user_id).first()
        if not resource:
            return jsonify({"message": "学习资源不存在"}), 404
        resource_id = resource.id

    event, created = LearningEventService.record_event(
        user_id=user_id,
        event_type=event_type,
        event_key=str(data.get("event_key") or "") or None,
        knowledge_point_id=knowledge_point_id,
        resource_id=resource_id,
        source_type="client_learning_action",
        source_id=str(data.get("source_id") or ""),
        value=data.get("value") if isinstance(data.get("value"), dict) else {},
    )
    mastery_change = MasteryService.apply_event(event) if created else None
    db.session.commit()
    return jsonify({
        "event": event.to_dict(),
        "created": created,
        "mastery_change": mastery_change,
    }), 201 if created else 200


@learning_bp.get("/mastery")
@jwt_required()
def list_mastery():
    user_id = int(get_jwt_identity())
    include_evidence = request.args.get("include_evidence", "false").lower() == "true"
    mastery = MasteryService.list_user_mastery(user_id, include_evidence=include_evidence)
    assessed = sum(1 for item in mastery if item["state"] != "unassessed")
    return jsonify({
        "mastery": mastery,
        "summary": {
            "total_knowledge_points": len(mastery),
            "assessed": assessed,
            "unassessed": len(mastery) - assessed,
            "coverage": round(assessed / len(mastery), 4) if mastery else 0.0,
        },
    })


@learning_bp.get("/mastery/<int:knowledge_point_id>")
@jwt_required()
def mastery_detail(knowledge_point_id: int):
    user_id = int(get_jwt_identity())
    point = db.session.get(KnowledgePoint, knowledge_point_id)
    if not point:
        return jsonify({"message": "知识点不存在"}), 404
    mastery = UserKnowledgeMastery.query.filter_by(
        user_id=user_id,
        knowledge_point_id=knowledge_point_id,
    ).first()
    events = LearningEventService.list_kp_events(user_id, knowledge_point_id, 100)
    if not mastery:
        return jsonify({
            "mastery": {
                "knowledge_point_id": point.id,
                "knowledge_point": point.name,
                "knowledge_point_code": point.code,
                "mastery_score": None,
                "confidence": 0.0,
                "state": "unassessed",
                "evidence": [],
            },
            "events": [event.to_dict() for event in events],
        })
    return jsonify({
        "mastery": mastery.to_dict(include_evidence=True),
        "events": [event.to_dict() for event in events],
    })


@learning_bp.post("/mastery/replay")
@jwt_required()
def replay_mastery():
    user_id = int(get_jwt_identity())
    backfill = LearningEventService.backfill_quiz_history(user_id)
    changes = MasteryService.replay_user(user_id)
    db.session.commit()
    return jsonify({
        "backfill": backfill,
        "replayed_event_count": len(changes),
        "mastery": MasteryService.list_user_mastery(user_id, include_evidence=True),
    })


@learning_bp.get("/diagnosis")
@jwt_required()
def learning_diagnosis():
    profile = current_profile()
    return jsonify({
        "diagnosis": DiagnosisService.build(
            user_id=profile.user_id,
            profile=profile,
        )
    })


@learning_bp.get("/diagnosis/<int:knowledge_point_id>")
@jwt_required()
def learning_diagnosis_detail(knowledge_point_id: int):
    profile = current_profile()
    try:
        detail = DiagnosisService.detail(
            user_id=profile.user_id,
            profile=profile,
            knowledge_point_id=knowledge_point_id,
        )
    except LookupError as exc:
        return jsonify({"message": str(exc)}), 404
    return jsonify({"detail": detail})


@learning_bp.get("/growth-report")
@jwt_required()
def growth_report():
    user_id = int(get_jwt_identity())
    raw_days = request.args.get("days", "30")
    if str(raw_days).lower() == "all":
        period_days = None
    else:
        try:
            period_days = max(1, min(int(raw_days), 3650))
        except (TypeError, ValueError):
            return jsonify({"message": "days 必须是正整数或 all"}), 400
    return jsonify({
        "growth": GrowthService.build(
            user_id=user_id,
            period_days=period_days,
        )
    })


@learning_bp.post("/remediation-plans")
@jwt_required()
def create_remediation_plan():
    profile = current_profile()
    data = request.get_json(silent=True) or {}
    knowledge_point_id = data.get("knowledge_point_id")
    try:
        payload = RemediationService.create(
            user_id=profile.user_id,
            profile=profile,
            knowledge_point_id=(
                int(knowledge_point_id)
                if knowledge_point_id is not None
                else None
            ),
        )
    except LookupError as exc:
        return jsonify({"message": str(exc)}), 404
    except (TypeError, ValueError) as exc:
        return jsonify({"message": str(exc)}), 400
    return jsonify(payload), 200 if payload.get("reused") else 201


@learning_bp.get("/remediation-plans")
@jwt_required()
def list_remediation_plans():
    return jsonify({
        "plans": RemediationService.list_user(int(get_jwt_identity()))
    })


@learning_bp.post("/remediation-plans/<int:plan_id>/start")
@jwt_required()
def start_remediation_plan(plan_id: int):
    try:
        payload = RemediationService.start(
            user_id=int(get_jwt_identity()),
            plan_id=plan_id,
        )
    except LookupError as exc:
        return jsonify({"message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 409
    return jsonify(payload)


@learning_bp.post("/adaptive-exams")
@jwt_required()
def create_adaptive_exam():
    profile = current_profile()
    data = request.get_json(silent=True) or {}
    try:
        payload = AdaptiveAssessmentService.create(
            user_id=profile.user_id,
            profile=profile,
            duration_minutes=int(data.get("duration_minutes") or 30),
            goal=str(data.get("goal") or "diagnosis"),
            difficulty=str(data.get("difficulty") or "intermediate"),
            course_id=(
                int(data["course_id"])
                if data.get("course_id") is not None
                else None
            ),
            knowledge_point_id=(
                int(data["knowledge_point_id"])
                if data.get("knowledge_point_id") is not None
                else None
            ),
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"message": str(exc)}), 400
    return jsonify(payload), 201


@learning_bp.get("/adaptive-exams")
@jwt_required()
def list_adaptive_exams():
    return jsonify({
        "exams": AdaptiveAssessmentService.list_user(int(get_jwt_identity()))
    })


@learning_bp.get("/adaptive-exams/<int:exam_id>")
@jwt_required()
def get_adaptive_exam(exam_id: int):
    exam = AdaptiveExam.query.filter_by(
        id=exam_id,
        user_id=int(get_jwt_identity()),
    ).first()
    if not exam:
        return jsonify({"message": "自适应测评不存在"}), 404
    return jsonify({
        "exam": exam.to_dict(include_quiz=True),
        "agent_run": (
            exam.agent_run.to_dict(include_steps=True)
            if exam.agent_run
            else None
        ),
    })


@learning_bp.post("/adaptive-exams/<int:exam_id>/submit")
@jwt_required()
def submit_adaptive_exam(exam_id: int):
    profile = current_profile()
    data = request.get_json(silent=True) or {}
    answers = data.get("answers") or {}
    if not isinstance(answers, dict):
        return jsonify({"message": "answers 必须是对象"}), 400
    reasoning_steps = data.get("reasoning_steps") or {}
    self_confidence = data.get("self_confidence") or {}
    if not isinstance(reasoning_steps, dict):
        return jsonify({"message": "reasoning_steps 必须是对象"}), 400
    if not isinstance(self_confidence, dict):
        return jsonify({"message": "self_confidence 必须是对象"}), 400
    try:
        payload = AdaptiveAssessmentService.submit(
            user_id=profile.user_id,
            profile=profile,
            exam_id=exam_id,
            answers=answers,
            reasoning_steps=reasoning_steps,
            self_confidence=self_confidence,
        )
    except LookupError as exc:
        return jsonify({"message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 409
    return jsonify(payload)


def _owned_knowledge_point(
    user_id: int,
    profile: Profile,
    knowledge_point_id: int,
) -> KnowledgePoint | None:
    return next(
        (
            point
            for point in DiagnosisService._scoped_points(user_id, profile)
            if point.id == knowledge_point_id
        ),
        None,
    )


@learning_bp.get("/cognitive-diagnoses/<int:assessment_id>")
@jwt_required()
def cognitive_diagnosis(assessment_id: int):
    user_id = int(get_jwt_identity())
    assessment = QuizResult.query.filter_by(
        id=assessment_id,
        user_id=user_id,
    ).first()
    if not assessment:
        return jsonify({"message": "测评记录不存在"}), 404
    rows = (
        CognitiveDiagnosis.query.filter_by(
            user_id=user_id,
            assessment_id=assessment_id,
        )
        .order_by(CognitiveDiagnosis.question_id, CognitiveDiagnosis.id)
        .all()
    )
    return jsonify({
        "assessment_id": assessment_id,
        "diagnoses": [row.to_dict(include_steps=True) for row in rows],
    })


@learning_bp.get("/misconceptions")
@jwt_required()
def list_misconceptions():
    knowledge_point_id = request.args.get(
        "knowledge_point_id",
        default=None,
        type=int,
    )
    return jsonify({
        "misconceptions": MisconceptionService.list_user(
            int(get_jwt_identity()),
            knowledge_point_id=knowledge_point_id,
        )
    })


@learning_bp.get("/misconceptions/<int:knowledge_point_id>")
@jwt_required()
def list_knowledge_point_misconceptions(knowledge_point_id: int):
    profile = current_profile()
    if not _owned_knowledge_point(
        profile.user_id,
        profile,
        knowledge_point_id,
    ):
        return jsonify({"message": "知识点不存在"}), 404
    return jsonify({
        "misconceptions": MisconceptionService.list_user(
            profile.user_id,
            knowledge_point_id=knowledge_point_id,
        )
    })


@learning_bp.post("/teaching-strategies/select")
@jwt_required()
def select_teaching_strategy():
    profile = current_profile()
    data = request.get_json(silent=True) or {}
    knowledge_point_id = data.get("knowledge_point_id")
    if knowledge_point_id is not None:
        try:
            knowledge_point_id = int(knowledge_point_id)
        except (TypeError, ValueError):
            return jsonify({"message": "knowledge_point_id 必须是整数"}), 400
        if not _owned_knowledge_point(
            profile.user_id,
            profile,
            knowledge_point_id,
        ):
            return jsonify({"message": "知识点不存在"}), 404
    try:
        decision = TeachingStrategyEngine.select(
            user_id=profile.user_id,
            profile=profile,
            knowledge_point_id=knowledge_point_id,
        )
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    db.session.commit()
    return jsonify({
        "strategy": TeachingStrategyEngine.payload(decision),
    }), 201


@learning_bp.get("/teaching-strategies/current")
@jwt_required()
def current_teaching_strategy():
    decision = TeachingStrategyEngine.current(int(get_jwt_identity()))
    return jsonify({
        "strategy": TeachingStrategyEngine.payload(decision),
    })


@learning_bp.get("/teaching-strategies/history")
@jwt_required()
def teaching_strategy_history():
    limit = request.args.get("limit", default=30, type=int)
    return jsonify({
        "strategies": TeachingStrategyEngine.history(
            int(get_jwt_identity()),
            limit=limit or 30,
        )
    })


@learning_bp.get("/teaching-interventions")
@jwt_required()
def teaching_interventions():
    limit = request.args.get("limit", default=30, type=int)
    return jsonify({
        "interventions": LearningInterventionService.list_user(
            int(get_jwt_identity()),
            limit=limit or 30,
        )
    })


@learning_bp.post("/transfer-assessments")
@jwt_required()
def create_transfer_assessment():
    profile = current_profile()
    data = request.get_json(silent=True) or {}
    knowledge_point_id = data.get("knowledge_point_id")
    try:
        payload = AdaptiveAssessmentService.create(
            user_id=profile.user_id,
            profile=profile,
            duration_minutes=int(data.get("duration_minutes") or 15),
            goal="transfer",
            difficulty=str(data.get("difficulty") or "intermediate"),
            course_id=(
                int(data["course_id"])
                if data.get("course_id") is not None
                else None
            ),
            knowledge_point_id=(
                int(knowledge_point_id)
                if knowledge_point_id is not None
                else None
            ),
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"message": str(exc)}), 400
    return jsonify(payload), 201


@learning_bp.get("/mastery-dimensions/<int:knowledge_point_id>")
@jwt_required()
def mastery_dimensions(knowledge_point_id: int):
    profile = current_profile()
    if not _owned_knowledge_point(
        profile.user_id,
        profile,
        knowledge_point_id,
    ):
        return jsonify({"message": "知识点不存在"}), 404
    return jsonify({
        "knowledge_point_id": knowledge_point_id,
        "dimensions": MasteryDimensionService.get_dimensions(
            profile.user_id,
            knowledge_point_id,
        ),
    })


@learning_bp.get("/capability-gates/<int:knowledge_point_id>")
@jwt_required()
def capability_gate(knowledge_point_id: int):
    profile = current_profile()
    if not _owned_knowledge_point(
        profile.user_id,
        profile,
        knowledge_point_id,
    ):
        return jsonify({"message": "知识点不存在"}), 404
    return jsonify({
        "capability": CapabilityGateService.evaluate(
            user_id=profile.user_id,
            knowledge_point_id=knowledge_point_id,
        )
    })


@learning_bp.get("/metacognitive-calibration")
@jwt_required()
def metacognitive_calibration():
    return jsonify({
        "calibration": MetacognitiveCalibrationService.report(
            int(get_jwt_identity())
        )
    })


@learning_bp.post("/decision-explanations")
@jwt_required()
def decision_explanation():
    profile = current_profile()
    data = request.get_json(silent=True) or {}
    try:
        payload = DecisionExplanationService.explain(
            user_id=profile.user_id,
            profile=profile,
            decision_type=str(data.get("decision_type") or "next_learning"),
            knowledge_point_id=data.get("knowledge_point_id"),
            node_id=data.get("node_id"),
            path_version_id=data.get("path_version_id"),
            exam_id=data.get("exam_id"),
        )
    except LookupError as exc:
        return jsonify({"message": str(exc)}), 404
    except (TypeError, ValueError) as exc:
        return jsonify({"message": str(exc)}), 400
    return jsonify({"explanation": payload})


@learning_bp.get("/agent-runs")
@jwt_required()
def list_agent_runs():
    user_id = int(get_jwt_identity())
    task_type = str(request.args.get("task_type") or "")
    limit = request.args.get("limit", default=20, type=int)
    runs = AgentTraceService.list_user_runs(
        user_id,
        task_type=task_type,
        limit=limit,
    )
    return jsonify({
        "runs": [run.to_dict(include_steps=True) for run in runs]
    })


@learning_bp.get("/agent-runs/<int:run_id>")
@jwt_required()
def get_agent_run(run_id: int):
    run = AgentRun.query.filter_by(
        id=run_id,
        user_id=int(get_jwt_identity()),
    ).first()
    if not run:
        return jsonify({"message": "Agent 执行记录不存在"}), 404
    return jsonify({"run": run.to_dict(include_steps=True)})


@learning_bp.post("/profile/dialogue")
@jwt_required()
def update_profile_by_dialogue():
    profile = current_profile()
    data = request.get_json(silent=True) or {}
    extracted = extract_profile_draft(profile, data)
    version, evidence, idempotent = confirm_profile_draft(
        profile,
        draft=extracted["draft"],
        dialogue=str(data.get("dialogue") or ""),
        confidence=extracted["extraction"]["confidence"],
    )
    db.session.commit()
    summary = LocalStudyGenerator(profile.to_dict()).build_profile_summary(profile.to_dict())
    return jsonify({
        "profile": profile.to_dict(),
        "version": version.to_dict(),
        "evidence": [item.to_dict() for item in evidence],
        "idempotent": idempotent,
        "summary": summary,
        "weak_points_sources": weak_points_with_sources(profile.user_id),
    })


@learning_bp.post("/path/plan")
@jwt_required()
def plan_path():
    _start = time.time()
    profile = current_profile()

    # 只查询必要字段，避免加载 quiz_content/answers 等大字段
    quiz_cols = (QuizResult.score, QuizResult.wrong_questions, QuizResult.created_at)
    quiz_results = [
        {"score": r.score, "wrong_questions": r.wrong_questions, "created_at": r.created_at.isoformat()}
        for r in QuizResult.query.with_entities(*quiz_cols)
        .filter_by(user_id=profile.user_id).order_by(QuizResult.created_at.desc()).limit(5).all()
    ]

    documents = KnowledgeDocument.query.filter_by(user_id=profile.user_id).order_by(KnowledgeDocument.created_at.desc()).limit(8).all()
    knowledge_documents = [
        {"title": document.title, "excerpt": (document.content or "")[:240], "created_at": document.created_at.isoformat()}
        for document in documents
    ]

    # 只查询资源类型，避免加载 content 大字段
    resource_types = {
        r.resource_type for r in
        Resource.query.with_entities(Resource.resource_type)
        .filter(Resource.user_id == profile.user_id, Resource.resource_type != "ppt_deck")
        .order_by(Resource.created_at.desc()).limit(12).all()
    }
    resources = [{"resource_type": t} for t in resource_types]

    context = {
        "quiz_results": quiz_results,
        "knowledge_documents": knowledge_documents,
        "resources": resources,
    }
    # Gap 2 改进：构建已学/未学知识点概览，数据不存在时跳过
    learned_summary = _build_learned_knowledge_summary(profile.user_id)
    if learned_summary:
        context["learned_knowledge"] = learned_summary
    agent = StudyResourceAgent(profile.to_dict(), user_id=profile.user_id)
    content = agent.plan_path(context)
    content, output_safety = guard.apply_output_guard(content, " ".join(item["title"] for item in knowledge_documents))
    path, version = StructuredPathService.create_version(
        profile=profile,
        legacy_content=content,
    )
    auto_update_profile(
        profile,
        "generate_path",
        quiz_results=context["quiz_results"],
        resource_count=len(resources),
        document_count=len(documents),
    )
    db.session.commit()

    app = current_app._get_current_object()
    from app.services.rag_config import ENABLE_AUTO_PATH_RESOURCES
    if ENABLE_AUTO_PATH_RESOURCES:
        threading.Thread(
            target=_generate_path_resources_in_background,
            args=(app, profile.user_id, profile.to_dict()),
            daemon=True,
            name=f"path-auto-resources-{profile.user_id}",
        ).start()
        auto_status = "background"
    else:
        auto_status = "disabled"

    return jsonify({
        "path": path.to_dict(include_version=True),
        "version": version.to_dict(include_nodes=True),
        "resources": [],
        "auto_resource_status": auto_status,
        "context": context,
        "duration_seconds": round(time.time() - _start, 1),
        "safety": output_safety.to_dict(),
    })


@learning_bp.get("/path/latest")
@jwt_required()
def latest_path():
    path, version = StructuredPathService.latest_user_path(int(get_jwt_identity()))
    return jsonify({
        "path": path.to_dict(include_version=True) if path else None,
        "version": version.to_dict(include_nodes=True) if version else None,
    })


@learning_bp.get("/path/versions")
@jwt_required()
def list_path_versions():
    user_id = int(get_jwt_identity())
    path, _ = StructuredPathService.latest_user_path(user_id)
    if not path:
        return jsonify({"path": None, "versions": []})
    versions = (
        LearningPathVersion.query.filter_by(path_id=path.id)
        .order_by(LearningPathVersion.version_number.desc())
        .all()
    )
    return jsonify({
        "path": path.to_dict(),
        "versions": [version.to_dict(include_nodes=True) for version in versions],
    })


@learning_bp.get("/path/versions/<int:from_version_id>/diff/<int:to_version_id>")
@jwt_required()
def path_version_diff(from_version_id: int, to_version_id: int):
    try:
        diff = StructuredPathService.diff_versions(
            user_id=int(get_jwt_identity()),
            from_version_id=from_version_id,
            to_version_id=to_version_id,
        )
    except LookupError as exc:
        return jsonify({"message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    return jsonify({"diff": diff})


@learning_bp.get("/path/latest-diff")
@jwt_required()
def latest_path_diff():
    user_id = int(get_jwt_identity())
    path, latest = StructuredPathService.latest_user_path(user_id)
    if not path or not latest or not latest.parent_version_id:
        return jsonify({"diff": None})
    diff = StructuredPathService.diff_versions(
        user_id=user_id,
        from_version_id=latest.parent_version_id,
        to_version_id=latest.id,
    )
    return jsonify({"diff": diff})


@learning_bp.post("/path/nodes/<int:node_id>/open")
@jwt_required()
def open_path_node(node_id: int):
    try:
        node, event, created = StructuredPathService.open_node(
            user_id=int(get_jwt_identity()),
            node_id=node_id,
        )
    except LookupError as exc:
        return jsonify({"message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 409
    db.session.commit()
    return jsonify({
        "node": node.to_dict(include_resources=True),
        "event": event.to_dict(),
        "created": created,
    })


@learning_bp.post("/path/nodes/<int:node_id>/complete")
@jwt_required()
def complete_path_node(node_id: int):
    try:
        node, events, mastery_changes = StructuredPathService.complete_node(
            user_id=int(get_jwt_identity()),
            node_id=node_id,
        )
    except LookupError as exc:
        return jsonify({"message": str(exc)}), 404
    db.session.commit()
    return jsonify({
        "node": node.to_dict(include_resources=True),
        "events": [event.to_dict() for event in events],
        "mastery_changes": MasteryService.grouped_changes(mastery_changes),
    })


@learning_bp.post("/resources/generate")
@jwt_required()
def generate_resources():
    profile = current_profile()
    data = request.get_json(silent=True) or {}
    extra_input = data.get("extra_input") or ""
    rejected = safety_rejection(f"{profile.topic} {profile.learning_goal} {data.get('type') or ''} {' '.join(data.get('types') or [])} {extra_input}")
    if rejected:
        return rejected
    selected_type = data.get("type")
    selected_types = [selected_type] if selected_type else data.get("types") or list(RESOURCE_LABELS.keys())
    if not selected_type and len(selected_types) < 5:
        return jsonify({"message": "赛题要求至少生成 5 类个性化资源"}), 400

    generator = LocalStudyGenerator(profile.to_dict())
    agent = StudyResourceAgent(profile.to_dict(), user_id=profile.user_id)
    resources: list[Resource] = []
    agent_meta = None

    # 并行生成各类资源：使用线程池加速 LLM 调用
    app = current_app._get_current_object()
    profile_data = profile.to_dict()
    user_id = profile.user_id

    def _generate_one(rtype: str) -> tuple[Resource | None, dict | None]:
        """在独立 app 上下文中生成一种资源，避免线程安全问题"""
        with app.app_context():
            try:
                p = Profile.query.filter_by(user_id=user_id).first()
                pd = p.to_dict() if p else profile_data
                ag = StudyResourceAgent(pd, user_id=user_id)
                gen = LocalStudyGenerator(pd)
                content, meta = ag.generate_resource(
                    rtype,
                    lambda rt=rtype: gen.generate_resource(rt, extra_input),
                    extra_input,
                )
                if rtype == "mind_map":
                    content = normalize_mindmap_content(content, pd.get("topic", ""))
                content, _ = ContentGuard().apply_output_guard(content)
                resource = Resource(
                    user_id=user_id,
                    resource_type=rtype,
                    title=RESOURCE_LABELS.get(rtype, rtype),
                    content=content,
                )
                db.session.add(resource)
                db.session.commit()
                return resource, meta
            except Exception as exc:
                db.session.rollback()
                current_app.logger.warning("并行资源生成失败 type=%s user=%s: %s", rtype, user_id, exc)
                return None, None
            finally:
                db.session.remove()

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(selected_types), 5)) as pool:
        futures = {pool.submit(_generate_one, rt): rt for rt in selected_types}
        results: list[tuple[Resource | None, dict | None]] = []
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    # 按原始 selected_types 顺序排列结果
    type_to_result: dict[str, tuple[Resource, dict]] = {}
    for rt in selected_types:
        for res, meta in results:
            if res and res.resource_type == rt:
                type_to_result[rt] = (res, meta)
                break
    resources = [type_to_result[rt][0] for rt in selected_types if rt in type_to_result]
    agent_meta = next((meta for rt in selected_types if rt in type_to_result and (meta := type_to_result[rt][1]) is not None), None)
    payload = [resource.to_dict() for resource in resources]
    artifact = None
    if selected_type == "mind_map":
        validation = validate_mindmap_content(payload[0]["content"])
        artifact = {
            "enabled": True,
            "renderer": "local",
            "message": "思维导图已转换为结构化 JSON，由前端本地图库渲染。",
            "validation": {"valid": validation.valid, "errors": validation.errors},
        }
        try:
            tree = mermaid_to_tree_json(payload[0]["content"], profile.topic)
            artifact["mindmap"] = {"root": tree}
            artifact["layout_json"] = {"root": tree}
        except Exception as exc:
            artifact["mindmap"] = None
            artifact["layout_json"] = None
            artifact["message"] = f"结构化导图解析失败：{exc}"
    elif agent_meta:
        artifact = agent_meta.copy()  # 创建副本以避免循环引用
    if artifact and agent_meta and artifact is not agent_meta:
        artifact.setdefault("agent", agent_meta)
    auto_update_profile(
        profile,
        "generate_resource",
        types=selected_types or [selected_type or "all"],
        extra_input=extra_input,
        generated_titles=[item.get("title") for item in payload],
        content_excerpt="\n".join((item.get("content") or "")[:300] for item in payload[:3]),
    )
    db.session.commit()
    return jsonify({"resources": payload, "resource": payload[0] if selected_type else None, "artifact": artifact, "agent": agent_meta})


@learning_bp.post("/resources/generate-stream")
@jwt_required()
def generate_resource_stream():
    """SSE 流式生成资源（边生成边输出章节内容）"""
    profile = current_profile()
    data = request.get_json(silent=True) or {}
    resource_type = data.get("type")
    extra_input = data.get("extra_input") or ""

    def generate():
        _start = time.time()
        agent = StudyResourceAgent(profile.to_dict(), user_id=profile.user_id)
        generator = LocalStudyGenerator(profile.to_dict())
        local_fallback = lambda rt=resource_type: generator.generate_resource(rt, extra_input)

        try:
            # ── 讲解文档 / 拓展阅读：分步流式输出 ──
            if resource_type in ("course_document", "extension_reading"):
                is_reading = resource_type == "extension_reading"
                yield sse_event("status", {"message": "正在生成大纲..."})

                # 生成大纲
                try:
                    if is_reading:
                        outline = agent._generate_reading_outline(extra_input)
                        sections = outline.get("sections", [])
                    else:
                        outline = agent._generate_document_outline(extra_input)
                        sections = outline.get("chapters", [])
                    total = len(sections)
                    if total == 0:
                        raise RuntimeError("大纲未包含章节")
                except Exception:
                    fallback_content = local_fallback()
                    fallback_content, _ = guard.apply_output_guard(fallback_content)
                    resource = Resource(
                        user_id=profile.user_id,
                        resource_type=resource_type,
                        title=RESOURCE_LABELS.get(resource_type, resource_type),
                        content=fallback_content,
                    )
                    db.session.add(resource)
                    db.session.commit()
                    auto_update_profile(
                        profile,
                        "generate_resource",
                        types=[resource_type or "all"],
                        extra_input=extra_input,
                        generated_titles=[resource.title],
                        content_excerpt=(fallback_content or "")[:500],
                    )
                    db.session.commit()
                    yield sse_event("done", {"resource": resource.to_dict(), "fallback": True})
                    return

                yield sse_event("outline", {
                    "title": outline.get("title", ""),
                    "overview": outline.get("overview", ""),
                    "total": total,
                })

                # 并行生成各章节
                yield sse_event("status", {"message": f"正在生成 {total} 个章节内容..."})
                contents: dict[int, str] = {}

                with concurrent.futures.ThreadPoolExecutor(max_workers=min(total, 8)) as executor:
                    future_map = {}
                    for index, section in enumerate(sections):
                        future = executor.submit(generate_resource_section_with_retry, agent, section, extra_input, is_reading)
                        future_map[future] = index

                    for future in concurrent.futures.as_completed(future_map):
                        index = future_map[future]
                        try:
                            content = future.result()
                        except Exception:
                            content = ""
                        contents[index] = content
                        marked_content = mark_resource_section(index, sections[index], content) if content else ""
                        yield sse_event("section", {
                            "index": index,
                            "title": sections[index].get("title", ""),
                            "content": marked_content,
                            "completed": len(contents),
                            "total": total,
                        })

                # 合并完整文档
                full_parts = []
                full_parts.append(f"# {outline.get('title', '')}\n\n")
                if outline.get("overview"):
                    label = "阅读指引" if is_reading else "概述"
                    full_parts.append(f"> **{label}**：{outline['overview']}\n\n---\n\n")
                for i in range(total):
                    if contents.get(i):
                        full_parts.append(mark_resource_section(i, sections[i], contents[i]))

                full_doc = "\n\n".join(full_parts)
                full_doc, _ = guard.apply_output_guard(full_doc)

                resource = Resource(
                    user_id=profile.user_id,
                    resource_type=resource_type,
                    title=RESOURCE_LABELS.get(resource_type, resource_type),
                    content=full_doc,
                )
                db.session.add(resource)
                db.session.commit()
                auto_update_profile(
                    profile,
                    "generate_resource",
                    types=[resource_type],
                    extra_input=extra_input,
                    generated_titles=[resource.title],
                    content_excerpt=(full_doc or "")[:500],
                )
                db.session.commit()
                yield sse_event("done", {"resource": resource.to_dict()})

            # ── 练习题库 ──
            elif resource_type == "exercise_bank":
                yield sse_event("status", {"message": "正在生成练习题..."})
                local_gen = lambda: generator.generate_resource("exercise_bank", extra_input)
                content, meta = agent.generate_resource("exercise_bank", local_gen, extra_input)
                content, _ = guard.apply_output_guard(content)
                resource = Resource(
                    user_id=profile.user_id,
                    resource_type=resource_type,
                    title=RESOURCE_LABELS.get(resource_type, resource_type),
                    content=content,
                )
                db.session.add(resource)
                db.session.commit()
                auto_update_profile(
                    profile,
                    "generate_resource",
                    types=[resource_type],
                    extra_input=extra_input,
                    generated_titles=[resource.title],
                    content_excerpt=(content or "")[:500],
                )
                db.session.commit()
                yield sse_event("done", {"resource": resource.to_dict()})

            # ── 实操案例 ──
            elif resource_type == "coding_case":
                yield sse_event("status", {"message": "正在生成实操题..."})
                question, meta = agent.generate_coding_case_question(
                    lambda: generator.generate_resource("coding_case", extra_input), extra_input
                )
                case_content = json.dumps(question, ensure_ascii=False)
                case_content, _ = guard.apply_output_guard(case_content)
                resource = Resource(
                    user_id=profile.user_id,
                    resource_type=resource_type,
                    title=RESOURCE_LABELS.get(resource_type, resource_type),
                    content=case_content,
                )
                db.session.add(resource)
                db.session.commit()
                auto_update_profile(
                    profile,
                    "generate_resource",
                    types=[resource_type],
                    extra_input=extra_input,
                    generated_titles=[resource.title],
                    content_excerpt=(case_content or "")[:500],
                )
                db.session.commit()
                yield sse_event("done", {"resource": resource.to_dict()})

            else:
                yield sse_event("error", {"message": f"不支持的资源类型: {resource_type}"})

        except Exception as exc:
            if resource_type in RESOURCE_LABELS:
                try:
                    fallback_content = local_fallback()
                    if resource_type == "mind_map":
                        fallback_content = normalize_mindmap_content(fallback_content, profile.topic)
                    fallback_content, _ = guard.apply_output_guard(fallback_content)
                    resource = Resource(
                        user_id=profile.user_id,
                        resource_type=resource_type,
                        title=RESOURCE_LABELS.get(resource_type, resource_type),
                        content=fallback_content,
                    )
                    db.session.add(resource)
                    db.session.commit()
                    auto_update_profile(
                        profile,
                        "generate_resource",
                        types=[resource_type or "all"],
                        extra_input=extra_input,
                        generated_titles=[resource.title],
                        content_excerpt=(fallback_content or "")[:500],
                    )
                    db.session.commit()
                    yield sse_event("fallback", {
                        "resource": resource.to_dict(),
                        "message": f"远程生成失败，已使用本地模板兜底：{str(exc)[:120]}",
                    })
                    return
                except Exception:
                    pass
            yield sse_event("error", {"message": str(exc)})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@learning_bp.get("/resources/auto-status")
@jwt_required()
def auto_resource_generation_status():
    """查询学习路径后台自动生成的 5 类资源的状态（供 PathView 轮询）"""
    user_id = int(get_jwt_identity())
    since_str = request.args.get("since")
    since = datetime.fromisoformat(since_str) if since_str else None
    auto_types = ["course_document", "mind_map", "exercise_bank", "extension_reading", "coding_case"]

    status = {}
    for rtype in auto_types:
        query = Resource.query.filter_by(user_id=user_id, resource_type=rtype)
        if since:
            query = query.filter(Resource.created_at >= since)
        exists = query.order_by(Resource.created_at.desc()).first() is not None
        status[rtype] = "completed" if exists else "generating"

    all_completed = all(v == "completed" for v in status.values())
    return jsonify({"status": status, "all_completed": all_completed})


@learning_bp.post("/resources/generate-async")
@jwt_required()
def generate_resource_async():
    """异步生成单个资源：立即返回，后台线程执行实际生成。"""
    profile = current_profile()
    data = request.get_json(silent=True) or {}
    resource_type = data.get("type")
    extra_input = data.get("extra_input") or ""
    if not resource_type:
        return jsonify({"message": "缺少资源类型 type"}), 400
    rejected = safety_rejection(f"{profile.topic} {profile.learning_goal} {resource_type} {extra_input}")
    if rejected:
        return rejected

    start_time = datetime.utcnow()
    app = current_app._get_current_object()
    threading.Thread(
        target=_generate_single_resource_in_background,
        args=(app, profile.user_id, profile.to_dict(), resource_type, extra_input),
        daemon=True,
        name=f"async-resource-{profile.user_id}-{resource_type}",
    ).start()

    return jsonify({
        "status": "started",
        "resource_type": resource_type,
        "started_at": start_time.isoformat(),
    })


@learning_bp.get("/resources/generate-async-status")
@jwt_required()
def generate_async_status():
    """查询异步生成的单个资源的状态。"""
    user_id = int(get_jwt_identity())
    resource_type = request.args.get("type")
    started_at_str = request.args.get("started_at")
    if not resource_type:
        return jsonify({"message": "缺少资源类型 type"}), 400

    query = Resource.query.filter_by(user_id=user_id, resource_type=resource_type)
    if started_at_str:
        try:
            started_at = datetime.fromisoformat(started_at_str)
            query = query.filter(Resource.created_at >= started_at)
        except ValueError:
            pass
    resource = query.order_by(Resource.created_at.desc()).first()

    if resource:
        response_data = {"status": "completed", "resource": resource.to_dict()}
        # 对思维导图额外返回布局优化的 JSON 节点数组
        if resource_type == "mind_map":
            try:
                from ..services.mindmap_sanitizer import mermaid_to_tree_json
                resource_obj = Resource.query.filter_by(id=resource.id).first()
                topic = resource_obj.title if resource_obj else "思维导图"
                tree = mermaid_to_tree_json(resource.content, topic)
                response_data["artifact"] = {
                    "enabled": True,
                    "renderer": "local",
                    "mindmap": {"root": tree},
                    "layout_json": {"root": tree},
                }
            except Exception as exc:
                response_data["artifact"] = {
                    "enabled": False,
                    "renderer": "local",
                    "layout_json": None,
                    "message": f"结构化导图解析失败：{exc}",
                }
        return jsonify(response_data)
    return jsonify({"status": "generating"})


@learning_bp.get("/resources")
@jwt_required()
def list_resources():
    resources = visible_resources_for_user(int(get_jwt_identity()))
    return jsonify({"resources": [resource.to_dict() for resource in resources]})


@learning_bp.get("/resources/<int:resource_id>/innovation-analysis")
@jwt_required()
def resource_innovation_analysis(resource_id: int):
    user_id = int(get_jwt_identity())
    Resource.query.filter_by(id=resource_id, user_id=user_id).first_or_404()
    return jsonify({
        "evaluation": None,
        "basis": None,
        "status": "unavailable",
        "cached": False,
        "message": "真实证据验证工作流尚未启用",
    })


@learning_bp.patch("/resources/<int:resource_id>")
@jwt_required()
def rename_resource(resource_id: int):
    resource = Resource.query.filter_by(id=resource_id, user_id=int(get_jwt_identity())).first_or_404()
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"message": "资源名称不能为空"}), 400
    resource.title = title
    db.session.commit()
    return jsonify({"resource": resource.to_dict()})


@learning_bp.delete("/resources/<int:resource_id>")
@jwt_required()
def delete_resource(resource_id: int):
    user_id = int(get_jwt_identity())
    resource = Resource.query.filter_by(id=resource_id, user_id=user_id).first_or_404()
    content = resource.content
    ResourceInnovationAnalysis.query.filter_by(resource_id=resource_id, user_id=user_id).delete()
    CodingCaseRecord.query.filter_by(resource_id=resource_id, user_id=user_id).delete()
    db.session.delete(resource)
    db.session.commit()
    delete_media_files(content)
    return jsonify({"message": "资源已删除"})


@learning_bp.route("/resources/evaluate", methods=["POST"])
@jwt_required()
def evaluate_resource():
    return jsonify({
        "evaluation": None,
        "status": "unavailable",
        "message": "真实证据验证工作流尚未启用",
    })


@learning_bp.post("/resources/search-bili")
@jwt_required()
def search_bili_video():
    """搜索B站视频，返回视频列表供前端选择播放"""
    data = request.get_json(silent=True) or {}
    keyword = (data.get("keyword") or "").strip()
    if not keyword:
        return jsonify({"videos": [], "message": "请输入搜索关键词"})
    try:
        limit = int(data.get("limit", 5))
    except (ValueError, TypeError):
        limit = 5
    cookie = (data.get("cookie") or "").strip()
    result = search_bili_video_api(keyword, limit, cookie)
    return jsonify({
        "videos": result.get("videos", []),
        "need_cookie": result.get("need_cookie", False),
        "message": result.get("message", ""),
    })


@learning_bp.post("/quiz/generate")
@jwt_required()
def generate_quiz():
    data = request.get_json(silent=True) or {}
    rejected = safety_rejection(data.get("focus") or "")
    if rejected:
        return rejected
    profile = current_profile()
    if data.get("structured"):
        generator = LocalStudyGenerator(profile.to_dict())
        difficulty = data.get("difficulty") or "intermediate"
        focus = data.get("focus") or ""
        count = int(data.get("count") or 5)
        # Gap 3 改进：构建错题摘要用于优先出题，数据不存在时跳过
        weak_points_summary = _build_weak_points_summary(profile.user_id)
        point_candidates = knowledge_point_candidates(profile.topic)
        quiz, agent_meta = StudyResourceAgent(profile.to_dict(), user_id=profile.user_id).generate_structured_quiz(
            difficulty,
            focus,
            count,
            lambda: generator.structured_quiz(difficulty, focus, count),
            weak_points_summary=weak_points_summary,
            allowed_knowledge_points=allowed_knowledge_points(point_candidates),
        )
        quiz, mapping_coverage = map_quiz_questions(quiz, point_candidates)
        return jsonify({
            "quiz": quiz,
            "agent": agent_meta,
            "duration_seconds": agent_meta.get("duration_seconds"),
            "question_knowledge_point_coverage": mapping_coverage,
        })
    content = LocalStudyGenerator(profile.to_dict()).generate_quiz(
        data.get("difficulty") or "intermediate",
        data.get("focus") or "",
        int(data.get("count") or 8),
    )
    return jsonify({"quiz": content})


@learning_bp.post("/quiz/save-draft")
@jwt_required()
def save_quiz_draft():
    """保存生成的题目草稿到后端，切换到其他页面再切回来时仍可看到"""
    profile = current_profile()
    data = request.get_json(silent=True) or {}
    quiz = data.get("quiz") or {}
    category = data.get("category") or "exercise"
    record = QuizResult(
        user_id=profile.user_id,
        quiz_content=quiz.get("title") or f"{profile.topic} - 练习草稿",
        answers={"quiz": quiz, "submitted": {}, "details": [], "completed": False},
        score=0,
        wrong_questions="",
        analysis="",
        category=category,
    )
    db.session.add(record)
    db.session.commit()
    return jsonify({"record": record.to_dict()})


@learning_bp.patch("/quiz/<int:result_id>/draft")
@jwt_required()
def update_quiz_draft(result_id: int):
    """保存练习中的答案，不触发判题，也不把草稿标记为已完成。"""
    user_id = int(get_jwt_identity())
    record = QuizResult.query.filter_by(id=result_id, user_id=user_id).first_or_404()
    payload = dict(record.answers or {})
    if payload.get("completed") or payload.get("details"):
        return jsonify({"message": "该练习已经提交，不能再修改答案"}), 409

    quiz = payload.get("quiz") or {}
    if not (quiz.get("questions") or []):
        return jsonify({"message": "草稿中没有可保存的题目"}), 400

    data = request.get_json(silent=True) or {}
    raw_answers = data.get("answers") or {}
    if not isinstance(raw_answers, dict):
        return jsonify({"message": "答案格式不正确"}), 400
    payload["submitted"] = _normalize_draft_answers(quiz, raw_answers)
    payload["completed"] = False
    record.answers = payload
    db.session.commit()
    return jsonify({
        "record": record.to_dict(),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    })


@learning_bp.post("/quiz/submit-structured")
@jwt_required()
def submit_structured_quiz():
    data = request.get_json(silent=True) or {}
    rejected = safety_rejection(" ".join(str(value) for value in (data.get("answers") or {}).values()))
    if rejected:
        return rejected
    profile = current_profile()
    record_id = data.get("record_id")
    quiz = data.get("quiz") or {}
    quiz, mapping_coverage = map_quiz_questions(
        quiz,
        knowledge_point_candidates(profile.topic),
    )
    category = data.get("category") if data.get("category") in ("exercise", "evaluation") else "exercise"
    submitted_answers = data.get("answers") or {}
    # 开放题并行交给 MiMo，限制等待时间；失败的题目立即使用本地规则兜底。
    open_answer_scores = {}
    try:
        open_answer_scores = judge_open_answers(
            quiz,
            submitted_answers,
            model=current_app.config["MIMO_CHAT_MODEL"],
            timeout=current_app.config["QUIZ_OPEN_ANSWER_TIMEOUT"],
        )
    except Exception:
        pass
    llm_judge = lambda _answer, question: open_answer_scores.get(str(question.get("id")))
    result = LocalStudyGenerator(profile.to_dict()).grade_structured_quiz(quiz, submitted_answers, llm_judge)

    if record_id:
        record = QuizResult.query.filter_by(id=record_id, user_id=profile.user_id).first_or_404()
        record.category = category or record.category
        record.created_at = datetime.utcnow()  # 更新为提交时间，确保按做卷顺序排列
    else:
        record = QuizResult(user_id=profile.user_id, category=category)
        db.session.add(record)

    record.quiz_content = quiz.get("title") or f"{profile.topic} 练习记录"
    record.answers = {
        "submitted": submitted_answers,
        "quiz": quiz,
        "details": result["details"],
        "weak_points": [
            item.get("concept") or str(item["id"])
            for item in result["details"]
            if not item["is_correct"]
        ],
        "completed": True,
    }
    record.score = result["score"]
    record.wrong_questions = "; ".join(
        item.get("concept") or str(item["id"])
        for item in result["details"]
        if not item["is_correct"]
    )
    record.analysis = result["summary"]
    db.session.flush()

    learning_events, mapping_coverage = LearningEventService.record_assessment_events(
        user_id=profile.user_id,
        record=record,
        quiz=quiz,
        details=result["details"],
    )
    mastery_changes = MasteryService.grouped_changes(
        MasteryService.apply_events(learning_events),
    )
    record.answers = {
        **dict(record.answers or {}),
        "quiz": quiz,
        "details": result["details"],
        "question_knowledge_point_coverage": mapping_coverage,
    }
    wrong_points = record.wrong_questions.strip()
    if wrong_points:
        profile.weak_points = wrong_points
    auto_update_profile(
        profile,
        "submit_quiz",
        score=result.get("score", 0),
        weak_points=record.answers.get("weak_points", []),
        details=result.get("details", []),
        quiz_title=record.quiz_content,
        mastery_changes=mastery_changes,
    )
    replanning = ReplanningService.maybe_replan(
        profile=profile,
        mastery_changes=mastery_changes,
        assessment_id=record.id,
    )
    replan_version = replanning.get("version") or {}
    replan_diff = replanning.get("diff") or {}
    record.answers = {
        **dict(record.answers or {}),
        "mastery_changes": mastery_changes,
        "replanning": {
            "triggered": bool(replanning.get("triggered")),
            "reason": replanning.get("reason") or "",
            "version_number": replan_version.get("version_number"),
            "added_nodes": [
                {
                    "knowledge_point": item.get("knowledge_point") or "",
                    "node_type": item.get("node_type") or "",
                    "node_order": item.get("node_order"),
                }
                for item in replan_diff.get("added_nodes") or []
            ],
        },
    }
    db.session.commit()
    return jsonify({
        "result": result,
        "record": record.to_dict(),
        "mastery_changes": mastery_changes,
        "question_knowledge_point_coverage": mapping_coverage,
        "replanning": replanning,
    })


def _normalize_draft_answers(quiz: dict, raw_answers: dict) -> dict:
    normalized = {}
    for question in quiz.get("questions") or []:
        question_id = question.get("id")
        key = str(question_id)
        value = raw_answers.get(key, raw_answers.get(question_id, ""))
        if question.get("type") == "multiple_choice":
            values = value if isinstance(value, list) else [value]
            normalized[key] = [str(item)[:200] for item in values[:20] if str(item).strip()]
        else:
            normalized[key] = str(value or "")[:5000]
    return normalized


@learning_bp.get("/quiz/history")
@jwt_required()
def quiz_history():
    user_id = int(get_jwt_identity())
    category = request.args.get("category", "").strip()
    query = QuizResult.query.filter_by(user_id=user_id)
    if category in ("exercise", "evaluation"):
        query = query.filter_by(category=category)
    results = query.order_by(QuizResult.created_at.desc()).limit(20).all()
    return jsonify({"history": [result.to_dict() for result in results]})


@learning_bp.post("/quiz/evaluate")
@jwt_required()
def evaluate_quiz():
    data = request.get_json(silent=True) or {}
    profile = current_profile()
    quiz = data.get("quiz") or {}
    answers = data.get("answers") or {}
    details = data.get("details") or []
    score = data.get("score", 0)
    agent = StudyResourceAgent(profile.to_dict(), user_id=profile.user_id)
    # Gap 1 改进：构建历史测评摘要作为评估参照，数据不存在时跳过
    history_summary = _build_quiz_history_summary(profile.user_id)
    evaluation = agent.generate_quiz_evaluation(quiz, answers, details, score, history_summary=history_summary)
    weak_points = [
        (item.get("concept") or str(item.get("id") or "")).strip()
        for item in details
        if item and not item.get("is_correct") and (item.get("concept") or item.get("id"))
    ]
    # 如果传入了 record_id，将 evaluation 保存到记录的 answers 中
    record_id = data.get("record_id")
    if record_id:
        record = QuizResult.query.filter_by(id=record_id, user_id=profile.user_id).first()
        if record:
            answers_dict = dict(record.answers or {})
            answers_dict["evaluation"] = evaluation
            answers_dict["weak_points"] = weak_points
            record.answers = answers_dict
            record.wrong_questions = "；".join(weak_points)
            profile.weak_points = record.wrong_questions
            db.session.commit()
    auto_update_profile(
        profile,
        "evaluate_quiz",
        score=score,
        weak_points=weak_points,
        details=details,
        evaluation=evaluation,
    )
    db.session.commit()
    return jsonify({"evaluation": evaluation, "weak_points": weak_points})


@learning_bp.patch("/quiz/history/<int:result_id>")
@jwt_required()
def rename_quiz_history(result_id: int):
    result = QuizResult.query.filter_by(id=result_id, user_id=int(get_jwt_identity())).first_or_404()
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"message": "记录名称不能为空"}), 400
    result.quiz_content = title
    db.session.commit()
    return jsonify({"record": result.to_dict()})


@learning_bp.delete("/quiz/history/<int:result_id>")
@jwt_required()
def delete_quiz_history(result_id: int):
    result = QuizResult.query.filter_by(id=result_id, user_id=int(get_jwt_identity())).first_or_404()
    db.session.delete(result)
    db.session.commit()
    return jsonify({"message": "答题记录已删除"})


@learning_bp.post("/case/generate")
@jwt_required()
def generate_case():
    profile = current_profile()
    data = request.get_json(silent=True) or {}
    extra_input = data.get("extra_input") or ""
    rejected = safety_rejection(f"{profile.topic} {profile.learning_goal} {extra_input}")
    if rejected:
        return rejected
    generator = LocalStudyGenerator(profile.to_dict())
    question, agent_meta = StudyResourceAgent(profile.to_dict(), user_id=profile.user_id).generate_coding_case_question(
        lambda: generator.coding_case_question(extra_input), extra_input
    )
    resource = Resource(
        user_id=profile.user_id,
        resource_type="coding_case",
        title=question.get("title") or RESOURCE_LABELS["coding_case"],
        content=json.dumps(question, ensure_ascii=False),
    )
    db.session.add(resource)
    db.session.commit()
    auto_update_profile(
        profile,
        "generate_case",
        extra_input=extra_input,
        case_title=question.get("title") or "",
        requirements=question.get("requirements") or [],
    )
    db.session.commit()
    return jsonify({"case": question, "resource": resource.to_dict(), "agent": agent_meta})


@learning_bp.post("/case/submit")
@jwt_required()
def submit_case():
    data = request.get_json(silent=True) or {}
    rejected = safety_rejection(data.get("answer") or "")
    if rejected:
        return rejected
    profile = current_profile()
    case_data = data.get("case") or {}
    answer = data.get("answer") or ""
    result = StudyResourceAgent(profile.to_dict(), user_id=profile.user_id).grade_coding_case(case_data, answer)

    # 保存答题记录到数据库
    resource_id = data.get("resource_id")
    if resource_id:
        try:
            record = CodingCaseRecord(
                user_id=profile.user_id,
                resource_id=resource_id,
                case_content=json.dumps(case_data, ensure_ascii=False),
                answer=answer,
                score=result.get("score", 0),
                is_passed=result.get("is_passed", False),
                analysis=result.get("analysis", ""),
                reference_answer=result.get("reference_answer", ""),
            )
            db.session.add(record)
            db.session.commit()
            result["record_id"] = record.id
        except Exception as exc:
            db.session.rollback()
            current_app.logger.warning("实操判题记录保存失败（不影响判题结果）：%s", exc)

    # 提交案例后自动更新画像
    auto_update_profile(
        profile,
        "submit_case",
        score=result.get("score", 0),
        is_passed=result.get("is_passed", False),
        analysis=result.get("analysis", ""),
        answer_length=len(answer),
        case_title=case_data.get("title") or "",
        requirements=case_data.get("requirements") or [],
    )
    if result.get("wrong_questions"):
        existing = set()
        if isinstance(profile.weak_points, str):
            existing = set(p.strip() for p in profile.weak_points.split(",") if p.strip())
        elif isinstance(profile.weak_points, list):
            existing = set(profile.weak_points)
        if existing:
            existing.update(result["wrong_questions"])
            profile.weak_points = ",".join(existing)
    db.session.commit()

    return jsonify({"result": result})


@learning_bp.get("/case/record")
@jwt_required()
def get_case_record():
    resource_id = request.args.get("resource_id", type=int)
    if not resource_id:
        return jsonify({"error": "缺少 resource_id"}), 400
    profile = current_profile()
    record = CodingCaseRecord.query.filter_by(
        user_id=profile.user_id,
        resource_id=resource_id,
    ).order_by(CodingCaseRecord.id.desc()).first()
    return jsonify({"record": record.to_dict() if record else None})


# ──────────────────────────────────────────
# 多模态教学资源生成（视频脚本 / 动画分镜）
# ──────────────────────────────────────────


@learning_bp.post("/multimedia/video")
@jwt_required()
def generate_multimedia_video():
    """基于学生画像调用文生视频 API 生成教学视频"""
    data = request.get_json(silent=True) or {}
    profile = current_profile()
    extra_input = data.get("extra_input", "")
    local_gen = LocalStudyGenerator(profile.to_dict())

    def local_fallback():
        return local_gen.generate("multimedia_video")

    content, meta = StudyResourceAgent(profile.to_dict(), user_id=profile.user_id).generate_resource(
        "multimedia_video", local_fallback, extra_input
    )
    return jsonify({"content": content, "meta": meta})


@learning_bp.get("/multimedia/history")
@jwt_required()
def multimedia_history():
    """获取教学视频生成历史"""
    profile = current_profile()
    resources = Resource.query.filter_by(
        user_id=profile.user_id,
    ).filter(
        Resource.resource_type == "multimedia_video",
    ).order_by(Resource.created_at.desc()).all()
    return jsonify({
        "resources": [r.to_dict() for r in resources],
    })

@learning_bp.post("/quiz/submit")
@jwt_required()
def submit_quiz():
    data = request.get_json(silent=True) or {}
    rejected = safety_rejection(" ".join([
        data.get("practice_summary") or "",
        data.get("resource_feedback") or "",
        data.get("progress_notes") or "",
    ]))
    if rejected:
        return rejected
    profile = current_profile()
    evaluation = LocalStudyGenerator(profile.to_dict()).evaluate(
        data.get("practice_summary") or "",
        data.get("resource_feedback") or "",
        data.get("progress_notes") or "",
    )
    # 构建结构化的 answers 字段，确保包含 quiz 题目数据
    # 前端 selectQuizHistory 依赖 answers.quiz.questions 来加载题目
    raw_answers = data.get("answers") or {}
    if isinstance(raw_answers, dict) and "quiz" in raw_answers:
        answers = raw_answers
    else:
        answers = {
            "quiz": data.get("quiz") or raw_answers.get("quiz") or {},
            "submitted": raw_answers.get("submitted") or raw_answers,
            "details": evaluation.get("details") or raw_answers.get("details") or [],
        }
    result = QuizResult(
        user_id=profile.user_id,
        quiz_content=data.get("quiz_content") or "",
        answers=answers,
        score=evaluation["score"],
        wrong_questions=evaluation["wrong_questions"],
        analysis=evaluation["analysis"],
        category="evaluation",
    )
    db.session.add(result)
    profile.weak_points = evaluation["wrong_questions"]
    auto_update_profile(
        profile,
        "submit_quiz",
        score=evaluation.get("score", 0),
        weak_points=evaluation.get("wrong_questions", ""),
        analysis=evaluation.get("analysis", ""),
        practice_summary=data.get("practice_summary") or "",
        resource_feedback=data.get("resource_feedback") or "",
        progress_notes=data.get("progress_notes") or "",
    )
    db.session.commit()
    return jsonify({"result": result.to_dict(), "profile": profile.to_dict()})


@learning_bp.post("/evaluation")
@jwt_required()
def evaluate_learning():
    data = request.get_json(silent=True) or {}
    rejected = safety_rejection(" ".join([
        data.get("practice_summary") or "",
        data.get("resource_feedback") or "",
        data.get("progress_notes") or "",
    ]))
    if rejected:
        return rejected
    profile = current_profile()
    evaluation = LocalStudyGenerator(profile.to_dict()).evaluate(
        data.get("practice_summary") or "",
        data.get("resource_feedback") or "",
        data.get("progress_notes") or "",
    )
    profile.weak_points = evaluation["wrong_questions"]
    auto_update_profile(
        profile,
        "submit_quiz",
        score=evaluation.get("score", 0),
        weak_points=evaluation.get("wrong_questions", ""),
        analysis=evaluation.get("analysis", ""),
        practice_summary=data.get("practice_summary") or "",
        resource_feedback=data.get("resource_feedback") or "",
        progress_notes=data.get("progress_notes") or "",
    )
    db.session.commit()
    return jsonify({"evaluation": evaluation, "profile": profile.to_dict()})


@learning_bp.post("/tutor/ask")
@jwt_required()
def ask_tutor():
    """智能辅导：支持多模态输入（文本+图片+文件）的完整融合处理流程"""
    reset_channel_metrics()
    data = request.get_json(silent=True) or {}
    question = data.get("question") or ""
    context = data.get("context") or ""
    images = data.get("images") or []
    files = data.get("files") or []
    history = data.get("history") or []
    stream = bool(data.get("stream"))
    knowledge_base_mode = data.get("knowledge_base_mode", "auto")  # auto/on/off
    image_gen_enabled = data.get("image_gen_enabled", True)  # 是否允许生成配图

    # 使用 RAG 配置判断是否使用知识库
    from ..services.rag_config import ENABLE_RAG_OPTIMIZATION, detectResourceType, shouldUseRAG, getRagMode, RagTimingLogger
    _rag_timing = RagTimingLogger(request_id=str(uuid.uuid4())[:8])
    _rag_timing.record("ask_tutor_start", 0, resource_type="tutoring", knowledge_base_mode=knowledge_base_mode)

    resource_type = detectResourceType(question, history)
    _use_rag = shouldUseRAG(question, history, resource_type, None, knowledge_base_mode)
    _rag_mode = getRagMode(resource_type, question, knowledge_base_mode)
    rag_decision_reason = (
        f"knowledgeBaseMode={knowledge_base_mode}"
        f", resourceType={resource_type}"
        f", shouldUseRAG={_use_rag}"
        f", ragMode={_rag_mode}"
    )

    has_images = bool(images) and isinstance(images, list) and len(images) > 0
    has_files = bool(files) and isinstance(files, list) and len(files) > 0
    is_multimodal = has_images or has_files

    safety = guard.scan_request(question)
    if not safety.allowed:
        return jsonify({"message": "请求未通过后端内容安全约束", "safety": safety.to_dict()}), 400

    profile = current_profile()
    profile_dict = profile.to_dict()
    # Gap 4 改进：构建学习记录摘要并附加到上下文中，数据不存在时跳过
    learning_record = _build_learning_record_summary(profile.user_id)
    if learning_record:
        context = f"{context}\n\n【学习记录摘要】{learning_record}" if context else f"【学习记录摘要】{learning_record}"
        # 多模态路径的 build_fusion_prompt 不使用 context 变量，附加到 question 中
        question = f"{question}\n\n（学习记录：{learning_record}）" if question else f"学习记录：{learning_record}"
    mastery_summary = _build_mastery_summary(profile.user_id)
    if mastery_summary:
        mastery_context = f"【知识掌握状态】{mastery_summary}"
        context = f"{context}\n\n{mastery_context}" if context else mastery_context
        if is_multimodal:
            question = f"{question}\n\n（{mastery_context}）"
    current_strategy = TeachingStrategyEngine.current(profile.user_id)
    if current_strategy:
        strategy_payload = TeachingStrategyEngine.payload(current_strategy)
        profile_dict["teaching_strategy"] = strategy_payload
        strategy_context = (
            f"【当前教学策略】{strategy_payload['strategy_label']}；"
            f"依据：{'、'.join(strategy_payload['reason_codes'])}；"
            f"本轮优先动作：{'、'.join(strategy_payload['action_labels'])}。"
            "请把这些动作落实到回答方式中，但不要编造新的诊断证据。"
        )
        context = (
            f"{context}\n\n{strategy_context}"
            if context
            else strategy_context
        )
        if is_multimodal:
            question = f"{question}\n\n（{strategy_context}）"
    qwen = QwenClient()

    if stream:
        def generate_multimodal():
            """多模态流式生成"""
            try:
                yield sse_event("thinking", {"content": "- 已收到问题，正在准备多模态分析。\n"})
                mm_agent = MultimodalTutorAgent(profile_dict)

                # 多模态融合思考步骤
                mm_input = mm_agent.parse_input(question, images, files)

                # 意图识别优先：检测用户是否明确要求忽略图片/文件
                # 如果命中，直接丢弃图片/文件数据，不做任何视觉解析
                if mm_agent.should_ignore_multimodal(mm_input.text):
                    mm_input.images = []
                    mm_input.files = []

                if _use_rag and _rag_mode != "none":
                    yield sse_event("thinking", {"content": "- 正在读取知识库与上传材料。\n"})
                elif knowledge_base_mode == "off":
                    yield sse_event("thinking", {"content": "- 知识库已关闭，仅结合对话与上传材料分析。\n"})
                else:
                    yield sse_event("thinking", {"content": "- 当前问题未触发知识库检索，正在读取对话与上传材料。\n"})
                from ..services.rag_config import ENABLE_RAG_OPTIMIZATION
                if _use_rag and _rag_mode != "none":
                    rag_context, sources = retrieve_knowledge_context(
                        profile.user_id, question, mode=_rag_mode,
                        timeout_ms={"light": 600, "standard": 1200, "deep": 2500}.get(_rag_mode, 1200),
                    )
                else:
                    rag_context, sources = "", []
                _rag_timing.record("rag_retrieve", 0, mode=_rag_mode, used=bool(rag_context), reason=rag_decision_reason)
                fallback_answer = LocalStudyGenerator(profile_dict).tutor(question, context)
                file_infos = mm_agent.extract_file_text(mm_input.files) if mm_input.has_files else []

                # 使用专用视觉模型提取图片描述
                image_description = ""
                if mm_input.has_images:
                    image_description = mm_agent.extract_image_descriptions(mm_input.images)

                thinking_steps = mm_agent.fusion_think(mm_input, file_infos, rag_context, image_description)

                for step in thinking_steps:
                    yield sse_event("thinking", {"content": f"{step}\n"})

                yield sse_event("answer_start", {"content": ""})

                # 使用多模态Agent生成回答
                if mm_agent.enabled:
                    system_prompt, user_prompt = mm_agent.build_fusion_prompt(
                        mm_input, file_infos, rag_context, image_description,
                        conversation_history=history
                    )
                    # 根据配图开关构建 JSON 格式指令
                    if image_gen_enabled:
                        json_format = (
                            '\n\n你必须以 JSON 格式回复，格式如下：\n'
                            '{"answer": "你的完整回答（支持 Markdown 格式）", '
                            '"image_prompt": "图片描述（需要配图时填写，不需要则留空）"}\n'
                            "要求：\n"
                            "1. answer 字段包含给用户的完整回答，支持 Markdown 格式。\n"
                            "2. image_prompt 字段：当用户要求画图、生成图片、生成图像、画示意图，"
                            "或者回答适合配图时填写详细的图片描述（画面内容、风格、色调、构图 50-150字），"
                            "不需要配图时留空字符串。\n"
                            "3. 图片尺寸可在描述后添加“| 宽x高”，如“神经网络结构图 | 400x225”，默认 1024*1024。\n"
                            '4. 严禁在 answer 中显示任何与 JSON 结构或 image_prompt 相关的内容，answer 只包含用户可见文本。\n'
                        )
                    else:
                        json_format = (
                            '\n\n你必须以 JSON 格式回复，格式如下：\n'
                            '{"answer": "你的完整回答（支持 Markdown 格式）"}\n'
                            "要求：\n"
                            "1. answer 字段包含给用户的完整回答，支持 Markdown 格式。\n"
                            "2. 严禁在 answer 中显示任何与 JSON 结构相关的内容，answer 只包含用户可见文本。\n"
                        )
                    system_prompt += json_format
                    try:
                        REFUSAL_KEYWORDS = [
                            "只回答", "无法回答", "无法解答", "不能回答", "不回答",
                            "学习辅导Agent", "学习辅导", "与学习无关", "超出",
                        ]
                        stream_gen = qwen.stream_chat(system_prompt, user_prompt)
                        answer_text_accumulated = ""
                        for event_name, payload in _stream_json_answer(stream_gen, guard, rag_context, REFUSAL_KEYWORDS):
                            if event_name == "answer":
                                answer_text_accumulated += payload.get("content", "")
                                yield sse_event(event_name, payload)
                            elif event_name == "image_prompt_raw" and image_gen_enabled:
                                image_prompt_raw = payload
                                if answer_text_accumulated and image_prompt_raw and qwen.text2image_enabled:
                                    print("[DEBUG multim] JSON image_prompt:", image_prompt_raw[:80], file=sys.stderr, flush=True)
                                    image_prompt, image_size = parse_image_marker(image_prompt_raw)
                                    img_result = qwen.generate_text2image(image_prompt, size=image_size)
                                    task_id = img_result.get("task_id", "")
                                    results = img_result.get("results")
                                    print("[DEBUG multim] generate_text2image: task_id=%s has_results=%s" % (task_id, results is not None), file=sys.stderr, flush=True)
                                    if results and len(results) > 0:
                                        url = results[0].get("url", "")
                                        if url:
                                            local_url = save_remote_file(url, "generated")
                                            yield sse_event("image", {"image_url": local_url, "prompt": image_prompt})
                                    elif task_id:
                                        print("[DEBUG multim] starting async poll for task:", task_id, file=sys.stderr, flush=True)
                                        for _ in range(30):
                                            time.sleep(2)
                                            try:
                                                status = qwen.query_task(task_id)
                                                task_output = status.get("output", {})
                                                ts = task_output.get("task_status", "")
                                                print("[DEBUG multim] poll status:", ts, file=sys.stderr, flush=True)
                                                if ts == "SUCCEEDED":
                                                    status_results = task_output.get("results")
                                                    if status_results and len(status_results) > 0:
                                                        url = status_results[0].get("url", "")
                                                        if url:
                                                            local_url = save_remote_file(url, "generated")
                                                            yield sse_event("image", {"image_url": local_url, "prompt": image_prompt})
                                                    break
                                                elif ts in ("FAILED", "CANCELED"):
                                                    print("[DEBUG multim] task failed: %s" % ts, file=sys.stderr, flush=True)
                                                    break
                                            except Exception as poll_e:
                                                print("[DEBUG multim] poll error:", poll_e, file=sys.stderr, flush=True)
                                                break
                                elif not image_prompt_raw and qwen.text2image_enabled and answer_text_accumulated:
                                    # 由 LLM 判断是否需要生成图片（fallback）
                                    combined_text = question or ""
                                    if not combined_text.strip() and image_description:
                                        combined_text = image_description
                                    if combined_text.strip():
                                        print("[DEBUG multim] calling detect_and_generate_image fallback", file=sys.stderr, flush=True)
                                        try:
                                            mm_agent_fb = MultimodalTutorAgent(profile_dict)
                                            img_result = mm_agent_fb.detect_and_generate_image(combined_text, rag_context)
                                            if img_result.get("image_url"):
                                                local_url = save_remote_file(img_result["image_url"], "generated")
                                                yield sse_event("image", {"image_url": local_url, "prompt": img_result.get("prompt", "")})
                                        except Exception as fb_e:
                                            print("[DEBUG multim] fallback image error:", fb_e, file=sys.stderr, flush=True)
                    except Exception as e:
                        current_app.logger.error("Tutor multimodal streaming/image error: %s", e)
                        guarded_fallback, _ = guard.apply_output_guard(fallback_answer, rag_context)
                        yield from stream_text(guarded_fallback)
                else:
                    for chunk in mm_agent._stream_local_fallback(mm_input, file_infos):
                        yield sse_event("answer", {"content": chunk})
            except Exception as e:
                current_app.logger.error("Tutor generate_multimodal error: %s", e)
                yield sse_event("answer", {"content": f"\n\n回答生成过程中遇到错误，已自动使用本地模板。"})
            # 流式回答完成后，检测是否需要文生视频
            try:
                intent = mm_agent.classify_intent(question, has_multimodal=is_multimodal)
                if intent == mm_agent.INTENT_GENERATE_VIDEO and mm_agent.qwen.text2video_enabled:
                    video_result = mm_agent.generate_video(mm_input, rag_context)
                    if video_result.get("video_url"):
                        local_url = save_remote_file(video_result["video_url"], "generated")
                        yield sse_event("video", {"video_url": local_url, "prompt": video_result.get("prompt", "")})
            except Exception:
                pass
            yield sse_event("done", {"content": "[DONE]"})

        def generate_text_only():
            """纯文本流式生成（保留旧有逻辑）"""
            try:
                if is_tutor_identity_query(question):
                    yield sse_event("answer_start", {"content": ""})
                    yield from stream_text(tutor_identity_answer())
                    yield sse_event("done", {"content": "[DONE]"})
                    return

                if _use_rag and _rag_mode != "none":
                    yield sse_event("thinking", {"content": "- 已收到问题，正在检索知识库并读取你的学习画像。\n"})
                elif knowledge_base_mode == "off":
                    yield sse_event("thinking", {"content": "- 已收到问题，知识库已关闭，正在读取你的学习画像。\n"})
                else:
                    yield sse_event("thinking", {"content": "- 已收到问题，当前问题未触发知识库检索，正在读取你的学习画像。\n"})
                from ..services.rag_config import ENABLE_RAG_OPTIMIZATION
                if _use_rag and _rag_mode != "none":
                    rag_context, sources = retrieve_knowledge_context(
                        profile.user_id, question, mode=_rag_mode,
                        timeout_ms={"light": 600, "standard": 1200, "deep": 2500}.get(_rag_mode, 1200),
                    )
                else:
                    rag_context, sources = "", []
                _rag_timing.record("rag_retrieve", 0, mode=_rag_mode, used=bool(rag_context), reason=rag_decision_reason)
                fallback_answer = LocalStudyGenerator(profile_dict).tutor(question, context)
                for step in visible_thinking_steps(profile_dict, question, sources):
                    yield sse_event("thinking", {"content": f"- {step}\n"})

                yield sse_event("answer_start", {"content": ""})

                used_local = False
                if qwen.enabled:
                    try:
                        system_prompt = (
                            "你是「循证学习教练」，这个知行智学-学习平台里的智能辅导 Agent。\n"
                            "你的核心能力是结合学生画像、课程知识库和对话上下文进行学习诊断、概念讲解、题目辅导与练习建议。\n"
                            "\n"
                            "重要规则（必须遵守）：\n"
                            "1. 对于任何知识类问题，都必须直接给出认真、准确、清晰的回答。\n"
                            "2. 如果知识库提供了相关内容，优先使用知识库中的资料来回答。\n"
                            "3. 如果知识库没有相关内容，直接基于你自己的知识回答即可，不需要做任何额外说明。\n"
                            "4. 当用户只是问候或询问你的身份时，要先说明你是“循证学习教练/智能辅导 Agent”，再简短说明你能做什么，不要套用知识点讲解模板。\n"
                            "\n"
                        )
                        # 根据配图开关构建 JSON 格式指令
                        if image_gen_enabled:
                            json_format = (
                                "你必须以 JSON 格式回复，格式如下：\n"
                                '{"answer": "你的完整回答（支持 Markdown 格式）", '
                                '"image_prompt": "图片描述（需要配图时填写，不需要则留空）"}\n'
                                "要求：\n"
                                "1. answer 字段包含给用户的完整回答，支持 Markdown 格式。\n"
                                "2. image_prompt 字段：当用户要求画图、生成图片、生成图像、画示意图，"
                                "或者回答适合配图时填写详细的图片描述（画面内容、风格、色调、构图 50-150字），"
                                "不需要配图时留空字符串。\n"
                                "3. 图片尺寸可在描述后添加\"| 宽x高\"，如\"神经网络结构图 | 400x225\"，默认 1024*1024。\n"
                                '4. 严禁在 answer 中显示任何与 JSON 结构或 image_prompt 相关的内容，answer 只包含用户可见文本。\n'
                            )
                        else:
                            json_format = (
                                "你必须以 JSON 格式回复，格式如下：\n"
                                '{"answer": "你的完整回答（支持 Markdown 格式）"}\n'
                                "要求：\n"
                                "1. answer 字段包含给用户的完整回答，支持 Markdown 格式。\n"
                                "2. 严禁在 answer 中显示任何与 JSON 结构相关的内容，answer 只包含用户可见文本。\n"
                            )
                        system_prompt += json_format + (
                            "\n"
                            "禁止行为：\n"
                            "- 严禁拒绝回答任何学科概念问题。不得说出\"只回答\"或\"无法回答\"或类似的话。\n"
                            "- 严禁在知识库没有相关内容时拒绝作答。\n"
                            "- 严禁编造不存在的来源或引用。\n"
                        )
                        rag_section = f"\n知识库检索到的参考片段：\n{rag_context}" if rag_context else ""
                        user_prompt = (
                            f"学生画像：{profile_dict}\n"
                            f"学生问题：{question}\n"
                            f"学生补充上下文：{context or '无'}"
                            f"{rag_section}"
                        )
                        stream_gen = qwen.stream_chat(system_prompt, user_prompt)
                        REFUSAL_KEYWORDS = [
                            "只回答", "无法回答", "无法解答", "不能回答", "不回答",
                            "学习辅导Agent", "学习辅导", "与学习无关", "超出",
                        ]
                        answer_text_accumulated = ""
                        for event_name, payload in _stream_json_answer(stream_gen, guard, rag_context, REFUSAL_KEYWORDS):
                            if event_name == "answer":
                                answer_text_accumulated += payload.get("content", "")
                                yield sse_event(event_name, payload)
                            elif event_name == "image_prompt_raw" and image_gen_enabled:
                                image_prompt_raw = payload
                                if answer_text_accumulated and image_prompt_raw and qwen.text2image_enabled:
                                    print("[DEBUG text] JSON image_prompt:", image_prompt_raw[:80], file=sys.stderr, flush=True)
                                    image_prompt, image_size = parse_image_marker(image_prompt_raw)
                                    img_result = qwen.generate_text2image(image_prompt, size=image_size)
                                    task_id = img_result.get("task_id", "")
                                    results = img_result.get("results")
                                    if results and len(results) > 0:
                                        url = results[0].get("url", "")
                                        if url:
                                            local_url = save_remote_file(url, "generated")
                                            yield sse_event("image", {"image_url": local_url, "prompt": image_prompt})
                                    elif task_id:
                                        for _ in range(30):
                                            time.sleep(2)
                                            try:
                                                status = qwen.query_task(task_id)
                                                task_output = status.get("output", {})
                                                ts = task_output.get("task_status", "")
                                                if ts == "SUCCEEDED":
                                                    status_results = task_output.get("results")
                                                    if status_results and len(status_results) > 0:
                                                        url = status_results[0].get("url", "")
                                                        if url:
                                                            local_url = save_remote_file(url, "generated")
                                                            yield sse_event("image", {"image_url": local_url, "prompt": image_prompt})
                                                    break
                                                elif ts in ("FAILED", "CANCELED"):
                                                    break
                                            except Exception as poll_e:
                                                break
                                elif not image_prompt_raw and qwen.text2image_enabled and answer_text_accumulated:
                                    # LLM 未生成 image_prompt 时，由 fallback 检测是否需要配图
                                    if question.strip():
                                        print("[DEBUG text] calling detect_and_generate_image fallback", file=sys.stderr, flush=True)
                                        try:
                                            mm_agent_fb = MultimodalTutorAgent(profile_dict)
                                            img_result = mm_agent_fb.detect_and_generate_image(question, rag_context)
                                            if img_result.get("image_url"):
                                                local_url = save_remote_file(img_result["image_url"], "generated")
                                                yield sse_event("image", {"image_url": local_url, "prompt": img_result.get("prompt", "")})
                                        except Exception as fb_e:
                                            print("[DEBUG text] fallback image error:", fb_e, file=sys.stderr, flush=True)
                        if not answer_text_accumulated:
                            used_local = True
                    except Exception as e:
                        current_app.logger.error("Tutor text_only streaming/image error: %s", e)
                        used_local = True
                else:
                    used_local = True

                if used_local:
                    guarded_fallback, _ = guard.apply_output_guard(fallback_answer, rag_context)
                    yield from stream_text(guarded_fallback)
            except Exception as e:
                current_app.logger.error("Tutor generate_text_only error: %s", e)
                yield sse_event("answer", {"content": f"\n\n回答生成过程中遇到错误，已自动使用本地模板。"})
            # 纯文本流式完成后，检测是否需要文生视频
            try:
                video_keywords = ["生成视频", "生成影片", "视频", "动画", "生成动画", "制作视频", "教学视频", "演示视频", "科普视频", "短片", "视频讲解"]
                if not is_multimodal and qwen.text2video_enabled and any(kw in question for kw in video_keywords):
                    mm_agent = MultimodalTutorAgent(profile_dict)
                    mm_input = mm_agent.parse_input(question)
                    video_result = mm_agent.generate_video(mm_input, rag_context)
                    if video_result.get("video_url"):
                        local_url = save_remote_file(video_result["video_url"], "generated")
                        yield sse_event("video", {"video_url": local_url, "prompt": video_result.get("prompt", "")})
            except Exception:
                pass
            yield sse_event("done", {"content": "[DONE]"})

        generate_func = generate_multimodal if is_multimodal else generate_text_only

        # 学习画像更新走 async_channel，不阻塞首字响应
        _app = current_app._get_current_object()
        enqueue_db_task(
            DbChannel.ASYNC, "tutor_ask_update_profile",
            _handler_update_profile, app=_app,
            profile_id=profile.id, action="tutor_ask",
            question=question, source_count=0,
        )

        _chan_metrics = get_channel_metrics()
        _rag_timing.record("db_channels", 0,
                           dbCriticalMs=_chan_metrics["dbCriticalMs"],
                           dbAsyncQueuedMs=_chan_metrics["dbAsyncQueuedMs"],
                           dbBackgroundQueuedMs=_chan_metrics["dbBackgroundQueuedMs"],
                           dbAsyncTaskCount=_chan_metrics["dbAsyncTaskCount"],
                           dbBackgroundTaskCount=_chan_metrics["dbBackgroundTaskCount"],
                           dbChannelErrors=_chan_metrics["dbChannelErrors"])

        _rag_timing.print_log(
            resource_type=resource_type,
            rag_mode=_rag_mode,
            used_rag=str(_use_rag),
            knowledge_base_mode=knowledge_base_mode,
            rag_decision_reason=rag_decision_reason,
            streaming="true",
        )
        return Response(
            stream_with_context(generate_func()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # 非流式响应
    from ..services.rag_config import ENABLE_RAG_OPTIMIZATION
    if _use_rag and _rag_mode != "none":
        rag_context, sources = retrieve_knowledge_context(
            profile.user_id, question, mode=_rag_mode,
            timeout_ms={"light": 600, "standard": 1200, "deep": 2500}.get(_rag_mode, 1200),
        )
    else:
        rag_context, sources = "", []
    _rag_timing.record("rag_retrieve_nonstream", 0, mode=_rag_mode, used=bool(rag_context), reason=rag_decision_reason)
    fallback_answer = tutor_identity_answer() if is_tutor_identity_query(question) else LocalStudyGenerator(profile_dict).tutor(question, context)
    image_info: dict = {}
    video_info: dict = {}
    try:
        if is_tutor_identity_query(question) and not is_multimodal:
            answer = tutor_identity_answer()
        elif is_multimodal:
            mm_agent = MultimodalTutorAgent(profile.to_dict())
            result = mm_agent.process(question, images, files, rag_context)
            answer = result["answer"]
            image_info = result.get("image_info") or {}
            video_info = result.get("video_info") or {}
            if image_info.get("image_url"):
                image_info["image_url"] = save_remote_file(image_info["image_url"], "generated")
            if video_info.get("video_url"):
                video_info["video_url"] = save_remote_file(video_info["video_url"], "generated")
        else:
            if qwen.enabled:
                system_prompt = (
                    "你是一个知识渊博的通用AI问答助手。\n"
                    "你的核心能力是回答各类学科知识拓展、问题答疑、概念解释等各类学习问题。\n"
                    "\n"
                    "重要规则（必须遵守）：\n"
                    "1. 对于任何知识类问题，都必须直接给出认真、准确、清晰的回答。\n"
                    "2. 如果知识库提供了相关内容，优先使用知识库中的资料来回答。\n"
                    "3. 如果知识库没有相关内容，直接基于你自己的知识回答即可，不需要做任何额外说明。\n"
                    "4. 当被问到\"什么是XX\"这类概念解释问题时，直接给出一段清晰的定义和解释。\n"
                    "\n"
                    "禁止行为：\n"
                    "- 严禁拒绝回答任何学科概念问题。不得说出\"只回答\"或\"无法回答\"或类似的话。\n"
                    "- 严禁在知识库没有相关内容时拒绝作答。\n"
                    "- 严禁编造不存在的来源或引用。\n"
                )
                rag_section = f"\n知识库检索到的参考片段：\n{rag_context}" if rag_context else ""
                user_prompt = (
                    f"学生画像：{profile.to_dict()}\n"
                    f"学生问题：{question}\n"
                    f"学生补充上下文：{context or '无'}"
                    f"{rag_section}"
                )
                answer = qwen.chat(system_prompt, user_prompt)
            else:
                answer = fallback_answer
            # 非多模态非流式：检测是否需要文生图
            if not is_multimodal and qwen.text2image_enabled and image_gen_enabled:
                image_keywords = ["画图", "画一张", "画个", "生成图片", "生成图像", "绘制", "配图", "示意图", "画出", "画个图", "画一幅"]
                if any(kw in question for kw in image_keywords):
                    try:
                        mm_agent = MultimodalTutorAgent(profile.to_dict())
                        image_info = mm_agent.detect_and_generate_image(question, rag_context)
                        if image_info.get("image_url"):
                            image_info["image_url"] = save_remote_file(image_info["image_url"], "generated")
                    except Exception:
                        image_info = {}
            # 非多模态非流式：检测是否需要文生视频
            if not is_multimodal and qwen.text2video_enabled:
                video_keywords = ["生成视频", "生成影片", "视频", "动画", "生成动画", "制作视频", "教学视频", "演示视频", "科普视频", "短片", "视频讲解"]
                if any(kw in question for kw in video_keywords):
                    try:
                        mm_agent = MultimodalTutorAgent(profile.to_dict())
                        mm_input = mm_agent.parse_input(question)
                        video_info = mm_agent.generate_video(mm_input, rag_context)
                        if video_info.get("video_url"):
                            video_info["video_url"] = save_remote_file(video_info["video_url"], "generated")
                    except Exception:
                        video_info = {}
            REFUSAL_KEYWORDS = [
                "只回答", "无法回答", "无法解答", "不能回答", "不回答",
                "学习辅导Agent", "学习辅导", "与学习无关", "超出",
            ]
            if any(kw in answer for kw in REFUSAL_KEYWORDS):
                answer = fallback_answer
    except Exception:
        answer = fallback_answer
        image_info = {}
    answer, output_safety = guard.apply_output_guard(answer, rag_context)
    # 学习画像更新走 async_channel，不阻塞非流式响应
    _app = current_app._get_current_object()
    enqueue_db_task(
        DbChannel.ASYNC, "tutor_ask_update_profile",
        _handler_update_profile, app=_app,
        profile_id=profile.id, action="tutor_ask",
        question=question, answer_excerpt=(answer or "")[:400],
        source_count=len(sources),
    )

    _chan_metrics = get_channel_metrics()
    _rag_timing.record("db_channels", 0,
                       dbCriticalMs=_chan_metrics["dbCriticalMs"],
                       dbAsyncQueuedMs=_chan_metrics["dbAsyncQueuedMs"],
                       dbBackgroundQueuedMs=_chan_metrics["dbBackgroundQueuedMs"],
                       dbAsyncTaskCount=_chan_metrics["dbAsyncTaskCount"],
                       dbBackgroundTaskCount=_chan_metrics["dbBackgroundTaskCount"],
                       dbChannelErrors=_chan_metrics["dbChannelErrors"])
    _rag_timing.print_log(
        resource_type=resource_type,
        rag_mode=_rag_mode,
        used_rag=str(_use_rag),
        knowledge_base_mode=knowledge_base_mode,
        rag_decision_reason=rag_decision_reason,
        streaming="false",
    )
    return jsonify({
        "answer": answer,
        "image_info": image_info if image_info else None,
        "video_info": video_info if video_info else None,
        "safety": {"input": safety.to_dict(), "output": output_safety.to_dict()},
        "sources": sources,
    })


@learning_bp.get("/dashboard")
@jwt_required()
def dashboard():
    user_id = int(get_jwt_identity())
    visible_resources = visible_resources_for_user(user_id)
    covered_resource_types = {resource.resource_type for resource in visible_resources}
    # 只查询已提交的测评记录（过滤掉未答题的草稿记录）
    all_results = QuizResult.query.filter_by(user_id=user_id, category="evaluation").order_by(QuizResult.created_at.desc()).limit(20).all()
    quiz_results = [
        r for r in all_results
        if r.answers and isinstance(r.answers, dict) and r.answers.get("submitted")
    ]
    quiz_results = quiz_results[:10]
    latest_score = quiz_results[0].score if quiz_results else 0
    profile = current_profile()
    weak_point_sources = weak_points_with_sources(user_id)
    weak_points = [item["name"] for item in weak_point_sources]
    diagnosis = DiagnosisService.build(user_id=user_id, profile=profile)
    target = diagnosis.get("recommended_target")
    current_path = diagnosis.get("current_path") or {}
    current_node = current_path.get("current_node")
    current_strategy = TeachingStrategyEngine.current(user_id)
    current_intervention = LearningInterventionService.current(user_id)
    return jsonify(
        {
            "profile": profile.to_dict(),
            "metrics": {
                "knowledge_level": profile.knowledge_level,
                "resource_coverage": f"{len(covered_resource_types)}/{len(RESOURCE_LABELS)}",
                "quiz_count": len(quiz_results),
                "latest_score": latest_score,
            },
            "scores": [result.score for result in reversed(quiz_results)],
            "weak_points": weak_points[:8],
            "weak_points_sources": weak_point_sources,
            "learning_decision": {
                "summary": diagnosis["summary"],
                "recommended_target": target,
                "next_action": diagnosis["closed_loop"]["next_action"],
                "mastery_overview": diagnosis["overall"],
                "path_version": current_path.get("version_number"),
                "current_node": current_node,
                "latest_change": current_path.get("latest_diff"),
                "current_strategy": TeachingStrategyEngine.payload(
                    current_strategy
                ),
                "current_intervention": (
                    current_intervention.to_dict()
                    if current_intervention
                    else None
                ),
            },
        }
    )


@learning_bp.get("/chat-conversations")
@jwt_required()
def get_chat_conversations():
    user_id = int(get_jwt_identity())
    conversations = ChatConversation.query.filter_by(user_id=user_id).order_by(ChatConversation.updated_at.desc()).limit(50).all()
    return jsonify({"conversations": [conv.to_dict() for conv in conversations]})


@learning_bp.post("/chat-conversations")
@jwt_required()
def create_chat_conversation():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    title = data.get("title", "新学习辅导")
    messages = data.get("messages", [])
    conversation = ChatConversation(user_id=user_id, title=title, messages=messages)
    db.session.add(conversation)
    db.session.commit()
    return jsonify({"conversation": conversation.to_dict()})


@learning_bp.route("/chat-conversations/<int:conversation_id>", methods=["PATCH", "POST"])
@jwt_required()
def update_chat_conversation(conversation_id: int):
    user_id = int(get_jwt_identity())
    conversation = ChatConversation.query.filter_by(id=conversation_id, user_id=user_id).first_or_404()
    data = request.get_json(silent=True) or {}
    if "title" in data:
        conversation.title = data["title"]
    if "messages" in data:
        conversation.messages = data["messages"]
    db.session.commit()
    return jsonify({"conversation": conversation.to_dict()})


@learning_bp.delete("/chat-conversations/<int:conversation_id>")
@jwt_required()
def delete_chat_conversation(conversation_id: int):
    user_id = int(get_jwt_identity())
    conversation = ChatConversation.query.filter_by(id=conversation_id, user_id=user_id).first_or_404()
    delete_media_files(conversation.messages)
    db.session.delete(conversation)
    db.session.commit()
    return jsonify({"message": "对话已删除"})


@learning_bp.get("/uploads/<path:filename>")
def serve_upload(filename: str):
    from pathlib import Path
    backend_dir = Path(__file__).resolve().parents[2]
    upload_dir = backend_dir / "uploads"
    return send_from_directory(str(upload_dir.resolve()), filename)


@learning_bp.route("/tasks/log-action", methods=["POST"])
@jwt_required()
def log_task_action():
    """记录用户今日任务相关行为（页面访问等），用于判断任务完成状态"""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    action = data.get("action", "").strip()
    sub_type = data.get("sub_type", "").strip()

    # visit_resources 支持细化到子类型（如 visit_resources_course_document）
    if action == "visit_resources" and sub_type:
        action = f"visit_resources_{sub_type}"
    elif action not in {"visit_path", "visit_quiz", "visit_resources", "visit_tutor", "visit_knowledge", "visit_dashboard"}:
        return jsonify({"error": f"无效的 action"}), 400

    # 每个用户每种 action 只保留一条记录（跨天复用），更新 created_at 到当前时间
    existing = TaskActionLog.query.filter(
        TaskActionLog.user_id == user_id,
        TaskActionLog.action == action,
    ).first()
    if existing:
        existing.created_at = datetime.utcnow()
        db.session.commit()
        kept_id = existing.id
    else:
        log = TaskActionLog(user_id=user_id, action=action)
        db.session.add(log)
        db.session.commit()
        kept_id = log.id

    # 清理该用户该 action 的重复记录（确保只保留一条）
    TaskActionLog.query.filter(
        TaskActionLog.user_id == user_id,
        TaskActionLog.action == action,
        TaskActionLog.id != kept_id,
    ).delete(synchronize_session=False)
    db.session.commit()

    return jsonify({"message": "ok"})


@learning_bp.route("/tasks/reset", methods=["POST"])
@jwt_required()
def reset_tasks():
    """清空用户今日的任务完成记录（刷新任务时调用），使所有任务显示为未完成"""
    user_id = int(get_jwt_identity())
    from datetime import datetime, timedelta
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    TaskActionLog.query.filter(
        TaskActionLog.user_id == user_id,
        TaskActionLog.created_at >= today_start,
        TaskActionLog.created_at < today_end,
    ).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"message": "ok"})


@learning_bp.get("/tasks/recommended")
@jwt_required()
def recommended_tasks():
    """动态生成今日推荐任务，基于学生画像、成绩趋势、学习路径和资源覆盖情况。"""
    from ..services.local_generator import RESOURCE_LABELS

    user_id = int(get_jwt_identity())
    profile = current_profile()
    tasks: list[dict] = []

    # ── 加载上下文数据（用于任务个性化） ────────────────
    recent_results = (
        QuizResult.query.filter_by(user_id=user_id, category="evaluation")
        .order_by(QuizResult.created_at.desc())
        .limit(10)
        .all()
    )
    recent_results = [
        r for r in recent_results
        if r.answers and isinstance(r.answers, dict) and r.answers.get("submitted")
    ]
    recent_results = recent_results[:5]
    low_score_results = [r for r in recent_results if r.score is not None and r.score < 60]
    has_path = LearningPath.query.filter_by(user_id=user_id).first() is not None
    visible_resources = visible_resources_for_user(user_id)
    covered_types = {r.resource_type for r in visible_resources}

    # ── 每日轮转任务池（10 种核心学习类型） ────────────────
    DAILY_POOL: list[tuple[str, str, str, str]] = [
        ("daily_assessment",   "assessment", "quiz",                         "测评评估"),
        ("daily_path",         "path",       "path",                         "学习路径"),
        ("daily_course_doc",   "practice",   "resources_course_document",    "讲解文档"),
        ("daily_mind_map",     "practice",   "resources_mind_map",           "思维导图"),
        ("daily_exercise",     "practice",   "resources_exercise_bank",      "练习题库"),
        ("daily_reading",      "practice",   "resources_extension_reading",  "拓展阅读"),
        ("daily_coding",       "practice",   "resources_coding_case",        "实操案例"),
        ("daily_video",        "practice",   "resources_multimedia_video",   "教学视频"),
        ("daily_ppt",          "practice",   "resources_ppt_deck",           "PPT演示文稿"),
        ("daily_tutor",        "practice",   "tutor",                         "智能辅导"),
    ]

    # 提前查今天的行为记录，已完成的任务类型优先展示
    today = datetime.utcnow().date()
    today_actions = {
        row.action
        for row in TaskActionLog.query.filter(
            TaskActionLog.user_id == user_id,
            db.func.date(TaskActionLog.created_at) == today,
        ).all()
    }

    def _is_done(tid: str, action: str) -> bool:
        if action == "quiz":
            return "visit_quiz" in today_actions
        if action == "path":
            return "visit_path" in today_actions
        if action.startswith("resources_"):
            return f"visit_{action}" in today_actions
        if action == "tutor":
            return "visit_tutor" in today_actions
        return False

    # 默认同一天任务稳定；刷新/登录后的首次加载用新随机种子，重新抽 3-5 个不重复任务。
    force_refresh = str(request.args.get("refresh") or "").lower() in {"1", "true", "yes"}
    task_seed_prefix = "task_seed_"
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    today_end = today_start + timedelta(days=1)

    if force_refresh:
        TaskActionLog.query.filter(
            TaskActionLog.user_id == user_id,
            TaskActionLog.action.like(f"{task_seed_prefix}%"),
            TaskActionLog.created_at >= today_start,
            TaskActionLog.created_at < today_end,
        ).delete(synchronize_session=False)
        seed_value = uuid.uuid4().hex[:12]
        db.session.add(TaskActionLog(user_id=user_id, action=f"{task_seed_prefix}{seed_value}"))
        db.session.commit()
    else:
        seed_log = (
            TaskActionLog.query.filter(
                TaskActionLog.user_id == user_id,
                TaskActionLog.action.like(f"{task_seed_prefix}%"),
                TaskActionLog.created_at >= today_start,
                TaskActionLog.created_at < today_end,
            )
            .order_by(TaskActionLog.created_at.desc())
            .first()
        )
        seed_value = seed_log.action[len(task_seed_prefix):] if seed_log else str(today)

    seed = f"{today}:{user_id}:{seed_value}"
    rng = random.Random(seed)
    target = rng.randint(3, 5)
    unique_pool = list({item[0]: item for item in DAILY_POOL}.values())
    selected = rng.sample(unique_pool, min(target, len(unique_pool)))

    # ── 场景描述池（每次刷新随机选一条） ──
    DESC = {

        "gen_course_document": [
            "系统梳理核心概念，帮你构建完整的知识框架",
            "用通俗易懂的方式呈现复杂知识，降低理解门槛",
            "将零散知识点串联成体系，学习更高效",
            "定制专属学习材料，让知识点不再枯燥",
        ],
        "rev_course_document": [
            "温故知新，回顾核心知识，加深理解与记忆",
            "快速重温已学内容，巩固知识体系",
            "查漏补缺，看看之前的知识点还记得多少",
        ],
        "gen_mind_map": [
            "将复杂知识可视化，一张图理清所有关联",
            "用思维导图串联知识点，构建清晰的知识网络",
            "把厚厚的内容画成一张图，一目了然",
        ],
        "rev_mind_map": [
            "浏览知识结构图，强化对整体框架的认知",
            "快速复盘知识脉络，加深体系化理解",
        ],
        "gen_exercise_bank": [
            "学练结合，通过做题检验知识掌握程度",
            "用针对性练习巩固所学，快速定位薄弱环节",
            "边学边练，让知识记得更牢",
        ],
        "rev_exercise_bank": [
            "练几道题热热身，保持学习状态",
            "查漏补缺，通过实战检验真功夫",
        ],
        "gen_extension_reading": [
            "延伸学习边界，探索更多相关领域的有趣内容",
            "不止于课本，推荐高质量拓展材料开阔视野",
            "深入了解知识背后的故事与应用场景",
        ],
        "rev_extension_reading": [
            "重温拓展材料，发现之前忽略的精彩内容",
            "再读一遍，往往会有新的收获和启发",
        ],
        "gen_coding_case": [
            "动手实践真实编程案例，把知识变成技能",
            "边做边学，通过实战项目加深理解",
            "纸上得来终觉浅，亲手编码才是真功夫",
        ],
        "rev_coding_case": [
            "回顾经典案例，巩固实操技能",
            "再跑一遍代码，加深对实现细节的理解",
        ],
        "gen_multimedia_video": [
            "观看视频讲解，多感官辅助理解复杂概念",
            "视听结合，让抽象知识变得直观易懂",
            "跟着视频一步步学，轻松掌握难点",
        ],
        "rev_multimedia_video": [
            "快速回顾视频要点，巩固学习成果",
            "重看关键章节，加深对重难点的理解",
        ],
        "gen_ppt_deck": [
            "将学习成果转化为精美的演示文稿，便于复习与展示",
            "一键生成专业 PPT，让知识可视化呈现",
            "制作专属学习课件，适合自己的才是最好的",
        ],
        "rev_ppt_deck": [
            "翻阅已生成的 PPT，快速回顾知识要点",
            "打开演示文稿，过一遍核心知识点",
        ],
        "tutor": [
            "遇到难题？让 AI 导师为你随时解惑",
            "开启对话式学习，在问答中深化理解",
            "不懂就问，智能辅导 7×24 小时在线",
            "和 AI 导师聊一聊，学习也可以很有趣",
        ],
        "assess_retake": [
            "上次没考好？再来一次，见证你的进步",
            "重新挑战测评，看看这段时间进步了多少",
            "针对薄弱环节再测一次，攻克知识短板",
        ],
        "assess_first": [
            "做一次全面的知识体检，了解自己的真实水平",
            "首次测评摸底，为后续学习规划提供依据",
            "花几分钟测一测，看看从哪里入手最有效",
        ],
        "assess_daily": [
            "每日一练，保持学习手感和思维活跃",
            "花几分钟练几道题，积少成多见成效",
            "小练习大收获，每天进步一点点",
        ],
        "path_continue": [
            "按规划路线稳步前进，保持学习节奏不中断",
            "从上次中断的地方接上，学习最怕半途而废",
            "按照学习路线继续前行，一步一个脚印",
        ],
        "path_plan": [
            "量身定制专属学习路线图，明确前进方向",
            "科学规划学习路径，让努力用在刀刃上",
            "从目标出发，规划最高效的学习路线",
        ],
    }

    # ── 任务名称池（每次刷新随机选一条） ──
    NAME = {
        "rev":          ["快速回顾{label}", "重温{label}", "巩固{label}", "复盘{label}"],
        "gen":          ["生成{label}", "创建{label}", "制作{label}"],
        "assess_retake": ["重新测评（上次 {score} 分）", "再测一次（上次 {score} 分）", "重新挑战（上次 {score} 分）"],
        "assess_no_score": ["重新测评", "再测一次", "重新挑战"],
        "assess_first":  ["进行首次学习测评", "摸底测评", "初次知识评估"],
        "assess_daily":  ["每日一练", "今日练习", "每日挑战"],
        "path_continue": ["继续学习路径", "继续学习", "按路线前进"],
        "path_plan":     ["规划学习路径", "制定学习路线", "定制学习路线"],
        "tutor":         ["智能辅导问答", "AI 智能辅导", "问问 AI 导师"],
    }

    for tid, type_tag, action, label in selected:
        if tid == "daily_assessment":
            if low_score_results:
                score = low_score_results[0].score
                l = rng.choice(NAME["assess_retake"]).format(score=f"{score:.0f}")
                d = rng.choice(DESC["assess_retake"])
                s = f"最近测评得分偏低（{score:.0f} 分）"
            elif not recent_results:
                l = rng.choice(NAME["assess_first"])
                d = rng.choice(DESC["assess_first"])
                s = "暂无测评记录"
            else:
                l = rng.choice(NAME["assess_daily"])
                d = rng.choice(DESC["assess_daily"])
                s = "今日推荐"
        elif tid == "daily_path":
            if has_path:
                l = rng.choice(NAME["path_continue"])
                d = rng.choice(DESC["path_continue"])
                s = "基于最新学习路径"
            else:
                l = rng.choice(NAME["path_plan"])
                d = rng.choice(DESC["path_plan"])
                s = "基于学习目标与当前水平"
        elif tid == "daily_tutor":
            l = rng.choice(NAME["tutor"])
            d = rng.choice(DESC["tutor"])
            s = "今日推荐"
        else:
            resource_key = action.replace("resources_", "")
            if resource_key in covered_types:
                l = rng.choice(NAME["rev"]).format(label=label)
                d = rng.choice(DESC.get(f"rev_{resource_key}", ["回顾已生成内容，巩固知识"]))
                s = "已生成，建议回顾"
                type_tag = "review"
            else:
                l = rng.choice(NAME["gen"]).format(label=label)
                d = rng.choice(DESC.get(f"gen_{resource_key}", ["生成个性化学习材料"]))
                s = f"尚未生成{label}"

        tasks.append({
            "id": tid,
            "type": type_tag,
            "label": l,
            "desc": d,
            "status": "pending",
            "action": action,
            "source": s,
        })

    # 打乱展示顺序（而非按 pool 顺序排）
    rng.shuffle(tasks)

    # 动态计算完成条件：根据每个任务的 action 字段匹配今日行为
    # 资源类任务细化到具体子类型（course_document、mind_map、exercise_bank 等）
    completion: dict[str, bool] = {}
    for task in tasks:
        tid = task["id"]
        action = task.get("action", "")

        if action == "quiz":
            done = "visit_quiz" in today_actions
        elif action == "path":
            done = "visit_path" in today_actions
        elif action.startswith("resources_"):
            subtype = action[len("resources_"):]
            done = f"visit_resources_{subtype}" in today_actions
        elif action == "resources":
            # 通用资源跳转（fallback），任一子类型即可
            done = any(a.startswith("visit_resources_") for a in today_actions)
        elif action == "tutor":
            done = "visit_tutor" in today_actions
        elif action == "knowledge":
            done = "visit_knowledge" in today_actions
        else:
            done = False

        completion[tid] = done
        if done:
            task["status"] = "completed"

    return jsonify({"tasks": tasks, "completion": completion, "day_key": datetime.utcnow().strftime("%Y-%m-%d")})
