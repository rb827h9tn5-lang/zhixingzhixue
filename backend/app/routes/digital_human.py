from __future__ import annotations

import math
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import QuizResult
from ..services.digital_human import (
    DigitalHumanScriptService,
    MimoTTSProvider,
    TTSProviderError,
)
from ..services.digital_human.mimo_tts import SUPPORTED_VOICES
from ..services.digital_human.script_service import SCRIPT_VERSION
from ..services.mimo_chat_client import MimoChatClient


digital_human_bp = Blueprint("digital_human", __name__)
script_slots = threading.BoundedSemaphore(3)
tts_slots = threading.BoundedSemaphore(3)
rate_lock = threading.Lock()
request_history: dict[str, deque[float]] = defaultdict(deque)


def _quiz_result_for_current_user(result_id: int) -> QuizResult:
    return QuizResult.query.filter_by(
        id=result_id,
        user_id=int(get_jwt_identity()),
    ).first_or_404()


def _rate_limit(user_id: str) -> tuple[bool, int]:
    limit = current_app.config["DIGITAL_HUMAN_RATE_LIMIT_PER_MINUTE"]
    key = f"{user_id}:{request.endpoint}"
    cutoff = time.monotonic() - 60
    now = time.monotonic()
    with rate_lock:
        history = request_history[key]
        while history and history[0] < cutoff:
            history.popleft()
        if len(history) >= limit:
            return False, max(1, math.ceil(history[0] + 60 - now))
        history.append(now)
        return True, 0


def _limited(retry_after: int):
    response = jsonify({
        "message": f"数字人请求过于频繁，请在 {retry_after} 秒后重试",
        "retry_after_seconds": retry_after,
    })
    response.headers["Retry-After"] = str(retry_after)
    return response, 429


@digital_human_bp.get("/digital-human/status")
@jwt_required()
def status():
    enabled = current_app.config["DIGITAL_HUMAN_ENABLED"]
    tts_configured = enabled and bool(current_app.config["MIMO_API_KEY"])
    return jsonify({
        "enabled": enabled,
        "script_model": current_app.config["MIMO_DIGITAL_HUMAN_MODEL"],
        "tts_configured": tts_configured,
        "tts_model": current_app.config["MIMO_TTS_MODEL"],
        "default_voice": current_app.config["MIMO_TTS_DEFAULT_VOICE"],
        "voices": [
            {"id": voice_id, **metadata}
            for voice_id, metadata in SUPPORTED_VOICES.items()
        ],
    })


@digital_human_bp.post("/quiz/<int:result_id>/digital-human/prepare")
@jwt_required()
def prepare(result_id: int):
    if not current_app.config["DIGITAL_HUMAN_ENABLED"]:
        return jsonify({"message": "数字人功能未启用"}), 503

    record = _quiz_result_for_current_user(result_id)
    if not (record.answers or {}).get("details"):
        return jsonify({"message": "当前测评记录没有可讲解的答题详情"}), 400

    allowed, retry_after = _rate_limit(str(get_jwt_identity()))
    if not allowed:
        return _limited(retry_after)

    data = request.get_json(silent=True) or {}
    regenerate = bool(data.get("regenerate"))
    existing = (record.answers or {}).get("digital_human") or {}
    expected_model = current_app.config["MIMO_DIGITAL_HUMAN_MODEL"]
    if (
        not regenerate
        and existing.get("version") == SCRIPT_VERSION
        and existing.get("lessons")
        and existing.get("script_model") == expected_model
    ):
        return jsonify({
            "status": "ready",
            "result_id": record.id,
            "lessons": existing["lessons"],
            "script_provider": existing.get("script_provider", "cache"),
            "cached": True,
            "warning": existing.get("warning", ""),
        })

    if not script_slots.acquire(blocking=False):
        return jsonify({"message": "当前数字人讲解生成任务较多，请稍后重试"}), 429
    try:
        client = MimoChatClient(
            model=expected_model,
            timeout=current_app.config["MIMO_DIGITAL_HUMAN_TIMEOUT"],
        )
        lessons, provider, warning = DigitalHumanScriptService(
            client,
            max_script_chars=current_app.config[
                "DIGITAL_HUMAN_SCRIPT_MAX_CHARS"
            ],
        ).prepare(record)
    finally:
        script_slots.release()

    answers = dict(record.answers or {})
    answers["digital_human"] = {
        "version": SCRIPT_VERSION,
        "script_model": expected_model,
        "script_provider": provider,
        "warning": warning,
        "lessons": lessons,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    record.answers = answers
    db.session.commit()
    current_app.logger.info(
        "digital human script ready user=%s result=%s lessons=%s provider=%s",
        get_jwt_identity(),
        result_id,
        len(lessons),
        provider,
    )
    return jsonify({
        "status": "ready",
        "result_id": record.id,
        "lessons": lessons,
        "script_provider": provider,
        "cached": False,
        "warning": warning,
    })


@digital_human_bp.post(
    "/quiz/<int:result_id>/digital-human/questions/<string:question_id>/speech"
)
@jwt_required()
def synthesize_speech(result_id: int, question_id: str):
    if not current_app.config["DIGITAL_HUMAN_ENABLED"]:
        return jsonify({"message": "数字人功能未启用"}), 503

    record = _quiz_result_for_current_user(result_id)
    lessons = (
        ((record.answers or {}).get("digital_human") or {}).get("lessons")
        or []
    )
    lesson = next(
        (
            item
            for item in lessons
            if str(item.get("question_id")) == question_id
        ),
        None,
    )
    if not lesson:
        return jsonify({"message": "请先生成该测评的数字人讲解"}), 404

    data = request.get_json(silent=True) or {}
    voice = str(
        data.get("voice") or current_app.config["MIMO_TTS_DEFAULT_VOICE"]
    ).strip()
    if voice not in SUPPORTED_VOICES:
        return jsonify({"message": "不支持所选音色"}), 400

    allowed, retry_after = _rate_limit(str(get_jwt_identity()))
    if not allowed:
        return _limited(retry_after)
    if not tts_slots.acquire(blocking=False):
        return jsonify({"message": "当前语音合成任务较多，请稍后重试"}), 429

    upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
    if not upload_folder.is_absolute():
        upload_folder = Path(current_app.root_path).parent / upload_folder
    try:
        result = MimoTTSProvider(
            api_key=current_app.config["MIMO_API_KEY"],
            base_url=current_app.config["MIMO_BASE_URL"],
            model=current_app.config["MIMO_TTS_MODEL"],
            timeout=current_app.config["MIMO_TTS_TIMEOUT"],
            cache_dir=upload_folder / "digital_human" / "audio",
        ).synthesize(lesson.get("speech_text") or "", voice)
    except TTSProviderError as exc:
        current_app.logger.warning(
            "MiMo TTS failed user=%s result=%s question=%s error=%s",
            get_jwt_identity(),
            result_id,
            question_id,
            exc,
        )
        return jsonify({
            "message": f"{exc}，已可降级使用浏览器语音",
            "fallback": "browser",
        }), 502
    finally:
        tts_slots.release()

    result["subtitles"] = _subtitle_timeline(
        lesson.get("speech_text") or "",
        result["duration_ms"],
    )
    result["voice"] = voice
    return jsonify(result)


def _subtitle_timeline(text: str, duration_ms: int) -> list[dict]:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[。！？；])", str(text or ""))
        if sentence.strip()
    ]
    if not sentences:
        return []
    total_chars = sum(len(sentence) for sentence in sentences)
    total_duration = duration_ms or max(2000, total_chars * 180)
    cursor = 0
    timeline = []
    for index, sentence in enumerate(sentences):
        if index == len(sentences) - 1:
            end = total_duration
        else:
            end = cursor + round(total_duration * len(sentence) / total_chars)
        timeline.append({"start": cursor, "end": end, "text": sentence})
        cursor = end
    return timeline
