from unittest.mock import Mock

import pytest
import requests

from app.services.code_runner import (
    CodeRunnerUnavailableError,
    CodeValidationError,
    PistonCodeRunner,
    validate_execution_request,
)


def prepare(language="python", code="print('ok')", stdin="", timeout_ms=3000):
    return validate_execution_request(
        {
            "language": language,
            "code": code,
            "stdin": stdin,
            "timeout_ms": timeout_ms,
        },
        max_code_chars=100,
        max_stdin_chars=20,
        max_run_timeout_ms=5000,
    )


def runner(output_max_chars=200):
    return PistonCodeRunner(
        "http://piston.test",
        compile_timeout_ms=10000,
        compile_memory_bytes=256 * 1024 * 1024,
        run_memory_bytes=128 * 1024 * 1024,
        output_max_chars=output_max_chars,
    )


@pytest.mark.parametrize(
    "payload,message",
    [
        ({"language": "python", "code": ""}, "代码不能为空"),
        ({"language": "javascript", "code": "1"}, "目前仅支持"),
        ({"language": "python", "code": "x" * 101}, "代码不能超过"),
        ({"language": "python", "code": "1", "stdin": 1}, "标准输入必须"),
        (
            {"language": "python", "code": "1", "timeout_ms": 6000},
            "运行超时必须",
        ),
    ],
)
def test_validation_errors(payload, message):
    with pytest.raises(CodeValidationError, match=message):
        validate_execution_request(
            payload,
            max_code_chars=100,
            max_stdin_chars=20,
            max_run_timeout_ms=5000,
        )


def mock_response(payload, ok=True):
    response = Mock()
    response.ok = ok
    response.json.return_value = payload
    return response


def test_python_success(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        Mock(return_value=mock_response({
            "language": "python",
            "version": "3.12.0",
            "run": {"stdout": "ok\n", "stderr": "", "code": 0, "signal": None},
        })),
    )
    result = runner().execute(prepare())
    assert result["status"] == "success"
    assert result["stdout"] == "ok\n"


def test_compile_error(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        Mock(return_value=mock_response({
            "language": "c",
            "version": "10.2.0",
            "compile": {
                "output": "main.c: error",
                "code": 1,
                "signal": None,
            },
            "run": {},
        })),
    )
    result = runner().execute(prepare(language="c", code="bad"))
    assert result["status"] == "compile_error"
    assert "main.c" in result["compile_output"]


@pytest.mark.parametrize(
    "run_result,expected",
    [
        ({"stderr": "boom", "code": 1, "signal": None}, "runtime_error"),
        ({"output": "Execution timed out", "code": None, "signal": "SIGKILL"}, "timeout"),
    ],
)
def test_run_errors(monkeypatch, run_result, expected):
    monkeypatch.setattr(
        requests,
        "post",
        Mock(return_value=mock_response({
            "language": "python",
            "version": "3.12.0",
            "run": run_result,
        })),
    )
    assert runner().execute(prepare())["status"] == expected


def test_output_is_truncated(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        Mock(return_value=mock_response({
            "run": {"stdout": "x" * 100, "code": 0, "signal": None},
        })),
    )
    result = runner(output_max_chars=40).execute(prepare())
    assert result["truncated"] is True
    assert result["stdout"].endswith("[输出过长，已截断]")
    assert len(result["stdout"]) == 40


def test_connection_failure(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        Mock(side_effect=requests.ConnectionError("offline")),
    )
    with pytest.raises(CodeRunnerUnavailableError):
        runner().list_runtimes()
