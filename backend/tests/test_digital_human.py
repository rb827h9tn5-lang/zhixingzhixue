import base64
import io
import json
import wave
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services.digital_human.mimo_tts import (
    MimoTTSProvider,
    TTSProviderError,
)
from app.services.digital_human.script_service import (
    DigitalHumanScriptService,
    build_source_lessons,
)
from app.services.mimo_chat_client import MimoChatError


def quiz_record(details=None, score=50):
    return SimpleNamespace(
        id=12,
        score=score,
        quiz_content="机器学习测评",
        answers={
            "quiz": {
                "title": "机器学习测评",
                "questions": [
                    {"id": 1, "prompt": "什么是过拟合？", "concept": "过拟合"},
                    {"id": 2, "prompt": "什么是正则化？", "concept": "正则化"},
                    {"id": 3, "prompt": "什么是验证集？", "concept": "验证集"},
                ],
            },
            "details": details or [
                {
                    "id": 1,
                    "status": "wrong",
                    "is_correct": False,
                    "concept": "过拟合",
                    "user_answer": "训练误差高",
                    "reference_answer": "训练好但泛化差",
                    "explanation": "训练表现好、验证表现差是典型过拟合。",
                },
                {
                    "id": 2,
                    "status": "partial",
                    "is_correct": False,
                    "concept": "正则化",
                    "user_answer": "限制参数",
                    "reference_answer": "在损失中加入惩罚项",
                    "explanation": "惩罚复杂度可以改善泛化。",
                },
                {
                    "id": 3,
                    "status": "correct",
                    "is_correct": True,
                    "concept": "验证集",
                    "user_answer": "评估泛化",
                    "reference_answer": "评估泛化",
                    "explanation": "回答正确。",
                },
            ],
        },
    )


def test_build_source_lessons_only_includes_wrong_and_partial():
    lessons = build_source_lessons(quiz_record())
    assert [item["question_id"] for item in lessons] == ["1", "2"]
    assert lessons[0]["question_summary"] == "什么是过拟合？"
    assert lessons[1]["status"] == "partial"


def test_all_correct_creates_summary():
    details = [{
        "id": 1,
        "status": "correct",
        "is_correct": True,
        "concept": "过拟合",
    }]
    lessons = build_source_lessons(quiz_record(details=details, score=100))
    assert lessons[0]["question_id"] == "summary"
    assert lessons[0]["score"] == 100


def test_script_service_merges_mimo_result():
    class FakeClient:
        enabled = True
        model = "mimo-v2.5"

        def complete(self, system_prompt, user_prompt, **kwargs):
            assert "不得修改判题结果" in system_prompt
            assert "训练好但泛化差" in user_prompt
            return json.dumps({
                "lessons": [
                    {
                        "question_id": "1",
                        "mistake_reason": "混淆了训练误差与泛化误差",
                        "reasoning_steps": ["比较训练集与验证集表现"],
                        "memory_tip": "训练好、验证差，就是过拟合",
                        "speech_text": "我们来看第一题，这道题需要比较训练集和验证集表现。",
                    }
                ]
            }, ensure_ascii=False)

    lessons, provider, warning = DigitalHumanScriptService(FakeClient()).prepare(
        quiz_record()
    )
    assert provider == "mimo-v2.5"
    assert warning == ""
    assert lessons[0]["mistake_reason"] == "混淆了训练误差与泛化误差"
    assert lessons[0]["reference_answer"] == "训练好但泛化差"
    assert lessons[1]["speech_text"]


def test_script_service_falls_back_when_mimo_fails():
    class BrokenClient:
        enabled = True
        model = "mimo-v2.5"

        def complete(self, *args, **kwargs):
            raise MimoChatError("offline")

    lessons, provider, warning = DigitalHumanScriptService(
        BrokenClient()
    ).prepare(quiz_record())
    assert provider == "local"
    assert "本地讲解模板" in warning
    assert "参考答案" in lessons[0]["speech_text"]


def wav_bytes(duration_ms=200):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(b"\x00\x00" * (24000 * duration_ms // 1000))
    return buffer.getvalue()


def test_mimo_tts_saves_and_reuses_cache(monkeypatch, tmp_path):
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [{
            "message": {
                "audio": {
                    "data": base64.b64encode(wav_bytes()).decode("ascii")
                }
            }
        }]
    }
    post = Mock(return_value=response)
    monkeypatch.setattr("requests.post", post)
    provider = MimoTTSProvider(
        api_key="test-key",
        base_url="https://mimo.test/v1",
        model="mimo-v2.5-tts",
        timeout=10,
        cache_dir=tmp_path,
    )

    first = provider.synthesize("你好，这是讲解。", "冰糖")
    second = provider.synthesize("你好，这是讲解。", "冰糖")

    assert first["from_cache"] is False
    assert second["from_cache"] is True
    assert first["duration_ms"] == 200
    assert post.call_count == 1
    assert (tmp_path / first["audio_url"].split("/")[-1]).is_file()


def test_mimo_tts_rejects_unknown_voice(tmp_path):
    provider = MimoTTSProvider(
        api_key="test-key",
        base_url="https://mimo.test/v1",
        model="mimo-v2.5-tts",
        timeout=10,
        cache_dir=tmp_path,
    )
    with pytest.raises(TTSProviderError, match="不支持"):
        provider.synthesize("你好", "unknown")
