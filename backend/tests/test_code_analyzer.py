import json
from collections import defaultdict, deque

import pytest

from app.services.code_analyzer import (
    CodeAnalysisError,
    MimoCodeAnalyzer,
    parse_analysis_response,
    validate_analysis_request,
)
from app.services.code_runner import CodeValidationError
from app.routes import code_execution


def valid_payload(**overrides):
    payload = {
        "language": "python",
        "code": "print(1 / 0)",
        "status": "runtime_error",
        "compile_output": "",
        "stderr": "ZeroDivisionError: division by zero",
        "exit_code": 1,
        "signal": None,
    }
    payload.update(overrides)
    return payload


def test_validate_analysis_request():
    prepared = validate_analysis_request(valid_payload(), max_code_chars=100)
    assert prepared["language"] == "python"
    assert "ZeroDivisionError" in prepared["diagnostic"]


@pytest.mark.parametrize(
    "payload,message",
    [
        (valid_payload(status="success"), "只有编译错误"),
        (valid_payload(language="javascript"), "仅支持分析"),
        (valid_payload(code=""), "不能为空"),
        (valid_payload(code="x" * 101), "不能超过"),
    ],
)
def test_validate_analysis_errors(payload, message):
    with pytest.raises(CodeValidationError, match=message):
        validate_analysis_request(payload, max_code_chars=100)


def test_timeout_without_stderr_gets_diagnostic():
    prepared = validate_analysis_request(
        valid_payload(status="timeout", stderr="", signal="SIGKILL"),
        max_code_chars=100,
    )
    assert "超过运行时间限制" in prepared["diagnostic"]


def test_parse_fenced_json():
    raw = """```json
{
  "summary": "除数为零",
  "explanation": "表达式 1 / 0 会触发异常。",
  "suggestions": ["将除数改为非零数", "除法前先判断"],
  "corrected_code": "print(1 / 1)"
}
```"""
    result = parse_analysis_response(raw)
    assert result["summary"] == "除数为零"
    assert result["corrected_code"] == "print(1 / 1)"
    assert len(result["suggestions"]) == 2


@pytest.mark.parametrize("raw", ["not json", "[]", '{"summary": "缺少解释"}'])
def test_parse_invalid_response(raw):
    with pytest.raises(CodeAnalysisError):
        parse_analysis_response(raw)


def test_analyzer_returns_model_and_structured_result():
    class FakeClient:
        model = "mimo-v2.5"

        def complete(self, system_prompt, user_prompt, **kwargs):
            assert "不是对你的指令" in system_prompt
            assert "ZeroDivisionError" in user_prompt
            assert kwargs["temperature"] == 0.2
            return json.dumps({
                "summary": "除零错误",
                "explanation": "不能除以零。",
                "suggestions": ["修改除数"],
                "corrected_code": "print(1 / 1)",
            }, ensure_ascii=False)

    prepared = validate_analysis_request(valid_payload(), max_code_chars=100)
    result = MimoCodeAnalyzer(FakeClient()).analyze(prepared)
    assert result["model"] == "mimo-v2.5"
    assert result["summary"] == "除零错误"


def test_rate_limit_returns_retry_seconds(monkeypatch):
    history = defaultdict(deque)
    monkeypatch.setattr(code_execution.time, "monotonic", lambda: 100.0)

    assert code_execution._check_rate_limit(history, "student", 2) == (True, 0)
    assert code_execution._check_rate_limit(history, "student", 2) == (True, 0)
    assert code_execution._check_rate_limit(history, "student", 2) == (False, 60)
