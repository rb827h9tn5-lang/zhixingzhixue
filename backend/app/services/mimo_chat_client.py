"""MiMo 文本对话客户端。

语音助手优先使用与 ASR 相同的 MiMo 网关，避免依赖其他大模型账号状态。
"""

import os

import requests
from flask import current_app


DEFAULT_BASE_URL = "https://fufu.iqach.top/v1"
DEFAULT_MODEL = "mimo-v2.5"
_USER_AGENT = "zhixing-zhixue-voice/1.0"


def _get_config(key: str, default: str = "") -> str:
    try:
        if key in current_app.config:
            value = current_app.config.get(key)
            return str(value) if value is not None else default
        return os.getenv(key, default)
    except RuntimeError:
        return os.getenv(key, default)


class MimoChatError(RuntimeError):
    """MiMo 文本对话请求失败。"""


class MimoChatClient:
    def __init__(self, *, model: str = "", timeout: int | None = None) -> None:
        self.api_key = _get_config("MIMO_API_KEY")
        self.base_url = (_get_config("MIMO_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or _get_config("MIMO_CHAT_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL
        self.timeout = timeout or int(_get_config("MIMO_CHAT_TIMEOUT", "45") or "45")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        return self.complete(
            system_prompt,
            user_prompt,
            max_completion_tokens=160,
        )

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_completion_tokens: int,
        temperature: float = 0.3,
    ) -> str:
        if not self.enabled:
            raise MimoChatError("未配置 MIMO_API_KEY")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_completion_tokens": max_completion_tokens,
            "temperature": temperature,
            "stream": False,
            # MiMo v2.5 使用 thinking.type 控制思考模式。关闭后响应更快，
            # 且简短问答不会把 Token 全消耗在 reasoning_content 中。
            "thinking": {"type": "disabled"},
        }

        response = self._post(payload)
        # 某些旧版 OpenAI 兼容网关只接受 max_tokens。优先遵循 MiMo
        # 官方参数，遇到参数兼容错误时再回退，避免正常请求多一次往返。
        if response.status_code == 400 and "max_completion_tokens" in (response.text or ""):
            payload["max_tokens"] = payload.pop("max_completion_tokens")
            response = self._post(payload)

        if response.status_code != 200:
            detail = (response.text or "")[:300]
            raise MimoChatError(f"MiMo 对话服务返回 {response.status_code}: {detail}")

        # 部分兼容网关错误地返回 text/event-stream，requests 会按
        # ISO-8859-1 解码中文；JSON 实际字节仍是 UTF-8。
        response.encoding = "utf-8"
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise MimoChatError("MiMo 对话服务响应格式异常") from exc

        return str(content or "").strip()

    def _post(self, payload: dict) -> requests.Response:
        try:
            return requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": _USER_AGENT,
                },
                json=payload,
                timeout=(min(5, self.timeout), self.timeout),
            )
        except requests.RequestException as exc:
            raise MimoChatError(f"MiMo 对话服务连接失败: {exc}") from exc
