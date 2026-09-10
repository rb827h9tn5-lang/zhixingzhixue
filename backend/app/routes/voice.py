import re

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required

from ..services.ai_client import QwenClient
from ..services.guardrails import ContentGuard
from ..services.mimo_chat_client import MimoChatClient, MimoChatError
from ..services.mimo_voice_client import MimoVoiceClient, MimoVoiceError

voice_bp = Blueprint("voice", __name__)

# 单次上传音频上限。前端一句话最长约 5 秒，16k/mono/16bit 约 160KB，
# 留出余量防止异常大包打满内存。
MAX_AUDIO_BYTES = 2 * 1024 * 1024
MAX_QUESTION_CHARS = 500
MAX_HISTORY_ITEMS = 6
MAX_HISTORY_TEXT_CHARS = 300
MAX_ANSWER_CHARS = 220

_DIALOGUE_SYSTEM_PROMPT = """你是“知行智学”中的语音学习助手“小智同学”。
请直接、友好、准确地回答用户，适合用中文语音朗读。
要求：
1. 普通知识问题用 2 到 4 句大白话回答，先给结论，通常不超过 150 个汉字；
2. 可以结合最近对话理解追问，但不要复述对话记录；
3. 不使用 Markdown、列表、标题、公式排版或网址；
4. 不知道或信息不足时坦诚说明，并用一句话询问必要信息；
5. 不编造事实、来源或个人经历。"""

# 静音或环境噪音时 MiMo 不会返回空串，而是返回「呃。」这类语气词。
# 这些结果必须丢弃，否则待机监听会把噪音当成指令。
_NOISE_TEXTS = {
    "呃", "嗯", "啊", "哦", "唔", "额", "喔", "诶", "欸", "哎",
    "嗯嗯", "呃呃", "啊啊", "嗯哼", "谢谢观看", "谢谢大家",
    "字幕由amara.org社区提供", "请不吝点赞", "订阅",
}


def _is_noise(text: str) -> bool:
    """判断识别结果是否为无效噪音。

    去掉标点后落在噪音词表里、或长度过短的结果都视为没说话。
    """
    cleaned = re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)
    if not cleaned:
        return True
    if cleaned in _NOISE_TEXTS:
        return True
    # 单字结果基本都是噪音，唤醒词和指令都不止一个字
    if len(cleaned) <= 1:
        return True
    return False


def _dialogue_history(raw_history) -> str:
    """把有限的最近对话整理成纯文本，控制提示词大小。"""
    if not isinstance(raw_history, list):
        return ""

    lines = []
    for item in raw_history[-MAX_HISTORY_ITEMS:]:
        if not isinstance(item, dict):
            continue
        user_text = str(item.get("user") or "").strip()[:MAX_HISTORY_TEXT_CHARS]
        assistant_text = str(item.get("assistant") or "").strip()[:MAX_HISTORY_TEXT_CHARS]
        if user_text:
            lines.append(f"用户：{user_text}")
        if assistant_text:
            lines.append(f"小智：{assistant_text}")
    return "\n".join(lines)


def _speech_friendly_answer(answer: str) -> str:
    """去掉不适合朗读的 Markdown，并兜底限制回答长度。"""
    text = str(answer or "").strip()
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"[#*_>`~]+", "", text)
    text = re.sub(r"\[(.*?)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= MAX_ANSWER_CHARS:
        return text

    shortened = text[:MAX_ANSWER_CHARS]
    sentence_end = max(shortened.rfind(mark) for mark in "。！？；")
    if sentence_end >= 80:
        return shortened[:sentence_end + 1]
    return shortened.rstrip("，、；：") + "。"


@voice_bp.post("/chat")
@jwt_required()
def chat():
    """回答适合语音播报的简短问题，并支持有限的多轮上下文。"""
    data = request.get_json(silent=True) or {}
    question = str(data.get("question") or "").strip()
    if not question:
        return jsonify({"message": "请输入想问的问题"}), 400
    if len(question) > MAX_QUESTION_CHARS:
        return jsonify({"message": f"问题过长，请控制在 {MAX_QUESTION_CHARS} 字以内"}), 400

    guard = ContentGuard()
    safety = guard.scan_request(question)
    if not safety.allowed:
        return jsonify({
            "answer": "这个问题我不能直接帮助完成。可以换成合规的知识讲解或学习辅导问题。",
            "safety": safety.to_dict(),
        })

    mimo_client = MimoChatClient()
    qwen_client = QwenClient()
    if not mimo_client.enabled and not qwen_client.enabled:
        return jsonify({"message": "对话服务未配置，请联系管理员配置大模型服务"}), 503

    history_text = _dialogue_history(data.get("history"))
    user_prompt = (
        f"最近对话：\n{history_text}\n\n当前问题：{question}"
        if history_text
        else f"当前问题：{question}"
    )

    answer = ""
    if mimo_client.enabled:
        try:
            answer = mimo_client.chat(_DIALOGUE_SYSTEM_PROMPT, user_prompt)
        except MimoChatError as exc:
            current_app.logger.warning("MiMo 语音助手对话生成失败，尝试备用服务: %s", exc)

    if not answer and qwen_client.enabled:
        try:
            answer = qwen_client.chat(_DIALOGUE_SYSTEM_PROMPT, user_prompt)
        except Exception:
            current_app.logger.exception("备用语音助手对话生成失败")

    if not answer:
        return jsonify({"message": "对话服务暂时不可用，请稍后再试"}), 502

    answer, _ = guard.apply_output_guard(answer)
    answer = _speech_friendly_answer(answer)
    if not answer:
        return jsonify({"message": "暂时没有生成有效回答，请换个问法再试"}), 502
    return jsonify({"answer": answer})


@voice_bp.post("/transcribe")
@jwt_required()
def transcribe():
    """识别一段音频分片。

    前端持续采集并在一句话结束后上传 WAV，由前端做唤醒词匹配和指令解析。
    MiMo API Key 只存在于后端，不下发给浏览器。
    """
    client = MimoVoiceClient()
    if not client.enabled:
        return jsonify({"message": "语音服务未配置", "code": "not_configured"}), 503

    uploaded = request.files.get("audio")
    if uploaded is None:
        return jsonify({"message": "缺少音频数据"}), 400

    audio_bytes = uploaded.read()
    if not audio_bytes:
        return jsonify({"message": "音频数据为空"}), 400
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        return jsonify({"message": "音频分片过大"}), 413

    try:
        text = client.transcribe(audio_bytes, "wav")
    except MimoVoiceError as exc:
        current_app.logger.warning("语音识别失败: %s", exc)
        return jsonify({"message": str(exc), "code": "asr_failed"}), 502

    noise = _is_noise(text)
    return jsonify({
        "text": "" if noise else text,
        "raw_text": text,
        "is_noise": noise,
    })


@voice_bp.get("/status")
@jwt_required()
def status():
    """前端开启语音助手前先查这里，避免没配置时白白申请麦克风权限。"""
    client = MimoVoiceClient()
    chat_client = MimoChatClient()
    return jsonify({
        "enabled": client.enabled,
        "model": client.model if client.enabled else "",
        "dialogue_enabled": chat_client.enabled or QwenClient().enabled,
        "dialogue_model": chat_client.model if chat_client.enabled else "",
        # 当前表示单句话允许的最长时长
        "chunk_ms": int(current_app.config.get("VOICE_CHUNK_MS", 2000)),
        "sample_rate": 16000,
    })
