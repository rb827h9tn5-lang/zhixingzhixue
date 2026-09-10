from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.code_analyzer import (
    CodeAnalysisError,
    MimoCodeAnalyzer,
    validate_analysis_request,
)
from ..services.code_runner import (
    CodeRunnerError,
    CodeValidationError,
    PistonCodeRunner,
    validate_execution_request,
)
from ..services.mimo_chat_client import MimoChatClient, MimoChatError


code_execution_bp = Blueprint("code_execution", __name__)
execution_slots = threading.BoundedSemaphore(4)
analysis_slots = threading.BoundedSemaphore(3)
rate_limit_lock = threading.Lock()
execution_history: dict[str, deque[float]] = defaultdict(deque)
analysis_history: dict[str, deque[float]] = defaultdict(deque)


def create_runner() -> PistonCodeRunner:
    return PistonCodeRunner(
        current_app.config["PISTON_API_URL"],
        compile_timeout_ms=current_app.config["CODE_COMPILE_TIMEOUT_MS"],
        compile_memory_bytes=current_app.config["CODE_COMPILE_MEMORY_BYTES"],
        run_memory_bytes=current_app.config["CODE_RUN_MEMORY_BYTES"],
        output_max_chars=current_app.config["CODE_OUTPUT_MAX_CHARS"],
    )


def _check_rate_limit(
    history_by_user: dict[str, deque[float]],
    user_id: str,
    limit: int,
) -> tuple[bool, int]:
    cutoff = time.monotonic() - 60
    now = time.monotonic()
    with rate_limit_lock:
        history = history_by_user[user_id]
        while history and history[0] < cutoff:
            history.popleft()
        if len(history) >= limit:
            retry_after = max(1, math.ceil(history[0] + 60 - now))
            return False, retry_after
        history.append(now)
        return True, 0


def _rate_limited_response(message: str, retry_after: int):
    response = jsonify({
        "message": f"{message}，请在 {retry_after} 秒后重试",
        "retry_after_seconds": retry_after,
    })
    response.headers["Retry-After"] = str(retry_after)
    return response, 429


@code_execution_bp.get("/runtimes")
@jwt_required()
def runtimes():
    try:
        return jsonify(create_runner().list_runtimes())
    except CodeRunnerError as exc:
        return jsonify(
            {
                "status": "unavailable",
                "languages": [],
                "message": str(exc),
            }
        ), exc.status_code


@code_execution_bp.post("/execute")
@jwt_required()
def execute():
    max_request_bytes = (
        current_app.config["CODE_MAX_CHARS"]
        + current_app.config["CODE_STDIN_MAX_CHARS"]
    ) * 4 + 4096
    if request.content_length and request.content_length > max_request_bytes:
        return jsonify({"message": "代码或标准输入过长"}), 413

    try:
        prepared = validate_execution_request(
            request.get_json(silent=True),
            max_code_chars=current_app.config["CODE_MAX_CHARS"],
            max_stdin_chars=current_app.config["CODE_STDIN_MAX_CHARS"],
            max_run_timeout_ms=current_app.config["CODE_RUN_TIMEOUT_MS"],
        )
        user_id = str(get_jwt_identity())
        allowed, retry_after = _check_rate_limit(
            execution_history,
            user_id,
            current_app.config["CODE_RATE_LIMIT_PER_MINUTE"],
        )
        if not allowed:
            return _rate_limited_response("运行次数过多", retry_after)

        if not execution_slots.acquire(blocking=False):
            return jsonify({"message": "当前运行任务较多，请稍后重试"}), 429

        started_at = time.perf_counter()
        try:
            result = create_runner().execute(prepared)
        finally:
            execution_slots.release()

        current_app.logger.info(
            "code execution finished user=%s language=%s status=%s duration_ms=%s",
            user_id,
            prepared["spec"].language,
            result["status"],
            round((time.perf_counter() - started_at) * 1000),
        )
        return jsonify(result)
    except CodeValidationError as exc:
        return jsonify({"message": str(exc)}), 400
    except CodeRunnerError as exc:
        return jsonify({"message": str(exc)}), exc.status_code


@code_execution_bp.post("/analyze-error")
@jwt_required()
def analyze_error():
    max_request_bytes = current_app.config["CODE_MAX_CHARS"] * 4 + 64 * 1024
    if request.content_length and request.content_length > max_request_bytes:
        return jsonify({"message": "待分析代码或错误信息过长"}), 413

    try:
        prepared = validate_analysis_request(
            request.get_json(silent=True),
            max_code_chars=current_app.config["CODE_MAX_CHARS"],
        )
        user_id = str(get_jwt_identity())
        allowed, retry_after = _check_rate_limit(
            analysis_history,
            user_id,
            current_app.config["CODE_AI_RATE_LIMIT_PER_MINUTE"],
        )
        if not allowed:
            return _rate_limited_response("AI 分析次数过多", retry_after)

        if not analysis_slots.acquire(blocking=False):
            return jsonify({"message": "当前 AI 分析任务较多，请稍后重试"}), 429

        client = MimoChatClient(
            model=current_app.config["MIMO_CODE_MODEL"],
            timeout=current_app.config["MIMO_CODE_TIMEOUT"],
        )
        if not client.enabled:
            analysis_slots.release()
            return jsonify({"message": "未配置 MiMo 代码分析服务"}), 503

        started_at = time.perf_counter()
        try:
            result = MimoCodeAnalyzer(client).analyze(prepared)
        finally:
            analysis_slots.release()

        current_app.logger.info(
            "code analysis finished user=%s language=%s status=%s model=%s duration_ms=%s",
            user_id,
            prepared["language"],
            prepared["status"],
            result["model"],
            round((time.perf_counter() - started_at) * 1000),
        )
        return jsonify(result)
    except CodeValidationError as exc:
        return jsonify({"message": str(exc)}), 400
    except CodeAnalysisError as exc:
        return jsonify({"message": str(exc)}), 502
    except MimoChatError as exc:
        current_app.logger.warning("MiMo 代码错误分析失败: %s", exc)
        return jsonify({"message": "MiMo 分析服务暂时不可用，请稍后重试"}), 502
