from __future__ import annotations

import base64
import hashlib
import os
import tempfile
import wave
from pathlib import Path

import requests


SUPPORTED_VOICES = {
    "冰糖": {"label": "冰糖", "gender": "女声"},
    "茉莉": {"label": "茉莉", "gender": "女声"},
    "苏打": {"label": "苏打", "gender": "男声"},
    "白桦": {"label": "白桦", "gender": "男声"},
}
_USER_AGENT = "zhixing-zhixue-digital-human/1.0"
MAX_AUDIO_BYTES = 20 * 1024 * 1024


class TTSProviderError(RuntimeError):
    pass


class MimoTTSProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int,
        cache_dir: Path,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.cache_dir = cache_dir

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def synthesize(self, text: str, voice: str) -> dict:
        text = str(text or "").strip()
        if not self.enabled:
            raise TTSProviderError("未配置 MIMO_API_KEY")
        if not text:
            raise TTSProviderError("讲解文本不能为空")
        if voice not in SUPPORTED_VOICES:
            raise TTSProviderError("不支持所选音色")

        cache_key = hashlib.sha256(
            f"{self.model}\0{voice}\0{text}".encode("utf-8")
        ).hexdigest()
        filename = f"{cache_key}.wav"
        target = self.cache_dir / filename
        if target.is_file() and target.stat().st_size > 44:
            return self._result(target, filename, from_cache=True)

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": "请用清晰、耐心、自然的普通话教师语气，语速适中，重点处稍作停顿。",
                },
                {"role": "assistant", "content": text},
            ],
            "audio": {"format": "wav", "voice": voice},
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
                timeout=(5, self.timeout),
            )
        except requests.RequestException as exc:
            raise TTSProviderError("MiMo TTS 连接失败") from exc

        if response.status_code != 200:
            raise TTSProviderError(
                f"MiMo TTS 网关返回 {response.status_code}"
            )

        response.encoding = "utf-8"
        try:
            data = response.json()
            encoded = data["choices"][0]["message"]["audio"]["data"]
            audio_bytes = base64.b64decode(encoded, validate=True)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise TTSProviderError("MiMo TTS 返回的音频格式异常") from exc

        if len(audio_bytes) <= 44 or len(audio_bytes) > MAX_AUDIO_BYTES:
            raise TTSProviderError("MiMo TTS 返回的音频大小异常")
        if not audio_bytes.startswith(b"RIFF"):
            raise TTSProviderError("MiMo TTS 没有返回有效 WAV 音频")

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(
            prefix=".tts-",
            suffix=".wav",
            dir=self.cache_dir,
        )
        try:
            with os.fdopen(handle, "wb") as temporary:
                temporary.write(audio_bytes)
            os.replace(temporary_name, target)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
        return self._result(target, filename, from_cache=False)

    def _result(self, target: Path, filename: str, *, from_cache: bool) -> dict:
        duration_ms = _wav_duration_ms(target)
        return {
            "audio_url": f"/api/uploads/digital_human/audio/{filename}",
            "duration_ms": duration_ms,
            "provider": "mimo",
            "model": self.model,
            "from_cache": from_cache,
        }


def _wav_duration_ms(path: Path) -> int:
    try:
        with wave.open(str(path), "rb") as audio:
            if not audio.getframerate():
                return 0
            return round(audio.getnframes() / audio.getframerate() * 1000)
    except (wave.Error, OSError):
        return 0
