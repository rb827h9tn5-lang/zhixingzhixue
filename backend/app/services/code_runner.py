from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class LanguageSpec:
    language: str
    label: str
    version: str
    filename: str


SUPPORTED_LANGUAGES = {
    "python": LanguageSpec(
        language="python",
        label="Python",
        version="3.12.0",
        filename="main.py",
    ),
    "c": LanguageSpec(
        language="c",
        label="C",
        version="10.2.0",
        filename="main.c",
    ),
}


class CodeRunnerError(Exception):
    status_code = 502


class CodeValidationError(CodeRunnerError):
    status_code = 400


class CodeRunnerUnavailableError(CodeRunnerError):
    status_code = 503


def validate_execution_request(
    data: Any,
    *,
    max_code_chars: int,
    max_stdin_chars: int,
    max_run_timeout_ms: int,
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise CodeValidationError("请求内容必须是 JSON 对象")

    language = str(data.get("language") or "").strip().lower()
    spec = SUPPORTED_LANGUAGES.get(language)
    if spec is None:
        raise CodeValidationError("目前仅支持 Python 和 C")

    code = data.get("code")
    if not isinstance(code, str) or not code.strip():
        raise CodeValidationError("代码不能为空")
    if len(code) > max_code_chars:
        raise CodeValidationError(f"代码不能超过 {max_code_chars} 个字符")

    stdin = data.get("stdin", "")
    if not isinstance(stdin, str):
        raise CodeValidationError("标准输入必须是文本")
    if len(stdin) > max_stdin_chars:
        raise CodeValidationError(f"标准输入不能超过 {max_stdin_chars} 个字符")

    timeout_ms = data.get("timeout_ms", min(3000, max_run_timeout_ms))
    if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, (int, float)):
        raise CodeValidationError("运行超时必须是数字")

    timeout_ms = int(timeout_ms)
    if timeout_ms < 100 or timeout_ms > max_run_timeout_ms:
        raise CodeValidationError(
            f"运行超时必须在 100 到 {max_run_timeout_ms} 毫秒之间"
        )

    return {
        "spec": spec,
        "code": code,
        "stdin": stdin,
        "timeout_ms": timeout_ms,
    }


class PistonCodeRunner:
    def __init__(
        self,
        api_url: str,
        *,
        compile_timeout_ms: int,
        compile_memory_bytes: int,
        run_memory_bytes: int,
        output_max_chars: int,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.compile_timeout_ms = compile_timeout_ms
        self.compile_memory_bytes = compile_memory_bytes
        self.run_memory_bytes = run_memory_bytes
        self.output_max_chars = output_max_chars

    def list_runtimes(self) -> dict[str, Any]:
        try:
            response = requests.get(
                f"{self.api_url}/api/v2/runtimes",
                timeout=(2, 5),
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise CodeRunnerUnavailableError(
                "代码沙箱暂时不可用，请确认 Piston 服务已启动"
            ) from exc

        if not isinstance(payload, list):
            raise CodeRunnerUnavailableError("代码沙箱返回了无法识别的运行环境列表")

        installed = {
            (
                str(item.get("language", "")).lower(),
                str(item.get("version", "")),
            )
            for item in payload
            if isinstance(item, dict)
        }

        languages = []
        for language_id, spec in SUPPORTED_LANGUAGES.items():
            languages.append(
                {
                    "id": language_id,
                    "label": spec.label,
                    "version": spec.version,
                    "available": (spec.language, spec.version) in installed,
                }
            )

        available_count = sum(1 for item in languages if item["available"])
        if available_count == len(languages):
            status = "ready"
        elif available_count:
            status = "partial"
        else:
            status = "unavailable"
        return {"status": status, "languages": languages}

    def execute(self, prepared: dict[str, Any]) -> dict[str, Any]:
        spec: LanguageSpec = prepared["spec"]
        payload = {
            "language": spec.language,
            "version": spec.version,
            "files": [{"name": spec.filename, "content": prepared["code"]}],
            "stdin": prepared["stdin"],
            "args": [],
            "compile_timeout": self.compile_timeout_ms,
            "run_timeout": prepared["timeout_ms"],
            "compile_memory_limit": self.compile_memory_bytes,
            "run_memory_limit": self.run_memory_bytes,
        }

        request_timeout = (
            self.compile_timeout_ms + prepared["timeout_ms"]
        ) / 1000 + 5
        started_at = time.perf_counter()
        try:
            response = requests.post(
                f"{self.api_url}/api/v2/execute",
                json=payload,
                timeout=(2, request_timeout),
            )
        except requests.Timeout as exc:
            raise CodeRunnerUnavailableError("代码沙箱响应超时，请稍后重试") from exc
        except requests.RequestException as exc:
            raise CodeRunnerUnavailableError(
                "无法连接代码沙箱，请确认 Piston 服务已启动"
            ) from exc

        duration_ms = round((time.perf_counter() - started_at) * 1000)
        try:
            result = response.json()
        except ValueError as exc:
            raise CodeRunnerUnavailableError(
                "代码沙箱返回了无法识别的响应"
            ) from exc

        if not isinstance(result, dict):
            raise CodeRunnerUnavailableError("代码沙箱返回了无法识别的响应")
        if not response.ok:
            raise CodeRunnerUnavailableError(
                str(result.get("message") or "代码沙箱执行失败")
            )

        compile_result = result.get("compile") or {}
        run_result = result.get("run") or {}
        if not isinstance(compile_result, dict) or not isinstance(run_result, dict):
            raise CodeRunnerUnavailableError("代码沙箱执行结果格式异常")

        compile_output, compile_truncated = self._truncate(
            str(compile_result.get("output") or "")
        )
        stdout, stdout_truncated = self._truncate(
            str(run_result.get("stdout") or "")
        )
        stderr, stderr_truncated = self._truncate(
            str(run_result.get("stderr") or "")
        )

        compile_failed = bool(compile_result) and (
            compile_result.get("code") not in (None, 0)
            or compile_result.get("signal") is not None
        )
        run_code = run_result.get("code")
        run_signal = run_result.get("signal")
        combined_output = str(run_result.get("output") or "")
        timed_out = (
            bool(run_signal) and "timed out" in combined_output.lower()
        ) or run_signal in {"SIGKILL", "SIGXCPU"}

        if compile_failed:
            status = "compile_error"
        elif timed_out:
            status = "timeout"
        elif run_code not in (None, 0) or run_signal is not None:
            status = "runtime_error"
        else:
            status = "success"

        return {
            "status": status,
            "language": spec.language,
            "version": str(result.get("version") or spec.version),
            "stdout": stdout,
            "stderr": stderr,
            "compile_output": compile_output,
            "exit_code": run_code,
            "signal": run_signal,
            "duration_ms": duration_ms,
            "truncated": compile_truncated or stdout_truncated or stderr_truncated,
        }

    def _truncate(self, value: str) -> tuple[str, bool]:
        if len(value) <= self.output_max_chars:
            return value, False
        suffix = "\n\n[输出过长，已截断]"
        remaining = max(0, self.output_max_chars - len(suffix))
        return value[:remaining] + suffix, True
