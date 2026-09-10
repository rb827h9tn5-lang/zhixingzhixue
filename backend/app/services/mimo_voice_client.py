"""MiMo 语音识别客户端。

MiMo 网关是 OpenAI 兼容风格，但没有 /v1/audio/transcriptions 端点，
ASR 通过 /v1/chat/completions 传多模态 input_audio 实现。

实测结论（决定了下面的实现细节）：
1. 只接受 WAV，mp3/webm/ogg/pcm16 一律返回 400「音频格式转换失败」。
2. 16kHz 单声道 16bit 体积最小且识别正常。
3. 单次识别延迟 4~7 秒，随音频时长增加，没有流式接口。
4. 静音音频会返回「呃。」这类短噪声文本，不会返回空串，
   因此调用方必须按文本过滤，不能靠判空。
5. 必须带 User-Agent，否则网关的 CDN 返回 403 error code: 1010。
"""

import base64
import os

import requests
from flask import current_app


DEFAULT_BASE_URL = "https://fufu.iqach.top/v1"
DEFAULT_MODEL = "mimo-v2.5-asr"

# 不带 UA 会被网关 CDN 拦为 403 (error code: 1010)
_USER_AGENT = "zhixing-zhixue-voice/1.0"


def _get_config(key: str, default: str = "") -> str:
    try:
        return current_app.config.get(key, "") or os.getenv(key, default)
    except RuntimeError:
        return os.getenv(key, default)


class MimoVoiceError(RuntimeError):
    """MiMo 语音识别失败，调用方需要向用户提示但不应中断页面功能。"""


class MimoVoiceClient:
    def __init__(self) -> None:
        self.api_key = _get_config("MIMO_API_KEY")
        self.base_url = (_get_config("MIMO_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL).rstrip("/")
        self.model = _get_config("MIMO_ASR_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL
        self.language = _get_config("MIMO_ASR_LANGUAGE", "zh") or "zh"
        self.timeout = int(_get_config("MIMO_ASR_TIMEOUT", "30") or "30")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def transcribe(self, audio_bytes: bytes, audio_format: str = "wav") -> str:
        """识别一段音频，返回转写文本。

        audio_bytes 必须是完整的 WAV（含 44 字节头），前端 AudioWorklet
        采集 PCM 后自行封头，因为浏览器 MediaRecorder 只能产出 webm/opus。
        """
        if not self.enabled:
            raise MimoVoiceError("未配置 MIMO_API_KEY")
        if not audio_bytes:
            raise MimoVoiceError("音频数据为空")

        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        audio_format = audio_format.lower()
        mime_type = "audio/mpeg" if audio_format == "mp3" else "audio/wav"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": f"data:{mime_type};base64,{audio_b64}",
                                "format": audio_format,
                            },
                        },
                    ],
                }
            ],
            # 明确中文可减少语言检测耗时和同音字误判；需要中英混说时可改为 auto。
            "asr_options": {"language": self.language},
            "stream": False,
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": _USER_AGENT,
                },
                json=payload,
                timeout=(15, self.timeout),
            )
        except requests.RequestException as exc:
            raise MimoVoiceError(f"语音服务连接失败: {exc}") from exc

        if response.status_code != 200:
            detail = (response.text or "")[:200]
            raise MimoVoiceError(f"语音服务返回 {response.status_code}: {detail}")

        response.encoding = "utf-8"
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise MimoVoiceError("语音服务响应格式异常") from exc

        return (content or "").strip()


def transcribe_audio(audio_bytes: bytes, audio_format: str = "wav") -> str:
    return MimoVoiceClient().transcribe(audio_bytes, audio_format)
