from __future__ import annotations

import json
import os
import random
import time
from collections.abc import Generator
from typing import Any

import requests


class QwenClient:
    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self.model = model or os.getenv("DASHSCOPE_MODEL", "qwen-max")
        self.endpoint = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        self._vision_model = os.getenv("DASHSCOPE_MULTIMODAL_UNDERSTAND_MODEL", "")
        self._text2image_model = self._parse_env_model("DASHSCOPE_TEXT2IMAGE_MODEL")
        self._text2video_model = self._parse_env_model("DASHSCOPE_TEXT2VIDEO_MODEL")
        self._text2video_audio = self._parse_env_bool_param("DASHSCOPE_TEXT2VIDEO_MODEL", "audio", True)
        self._enable_thinking = os.getenv("DASHSCOPE_ENABLE_THINKING", "false").strip().lower() in (
            "true",
            "1",
            "yes",
            "on",
        )
        self._task_endpoint = "https://dashscope.aliyuncs.com/api/v1/tasks"
        # 重试和超时配置（可通过环境变量覆盖）
        self.retry_count = int(os.getenv("LLM_RETRY_COUNT", "2"))
        chat_timeout_s = int(os.getenv("LLM_CHAT_TIMEOUT", "600"))
        multimodal_timeout_s = int(os.getenv("LLM_MULTIMODAL_TIMEOUT", "600"))

        self._timeout_map: dict[str, tuple[int, int]] = {
            "chat": (30, chat_timeout_s),
            "stream_chat": (30, max(chat_timeout_s, 600)),
            "chat_multimodal": (30, multimodal_timeout_s),
            "stream_chat_multimodal": (30, max(multimodal_timeout_s, 600)),
            "describe_images": (30, multimodal_timeout_s),
        }

    @staticmethod
    def _parse_env_model(env_key: str) -> str:
        raw = os.getenv(env_key, "").strip()
        if not raw:
            return ""
        return raw.split(";")[0].strip()

    @staticmethod
    def _parse_env_bool_param(env_key: str, param_name: str, default: bool = True) -> bool:
        raw = os.getenv(env_key, "").strip()
        if not raw:
            return default
        parts = raw.split(";")
        for part in parts[1:]:
            part = part.strip().lower()
            if part.startswith(param_name.lower() + "="):
                value = part.split("=", 1)[1].strip()
                return value in ("true", "1", "yes", "on")
        return default

    @property
    def text2image_enabled(self) -> bool:
        return bool(self.api_key and self._text2image_model)

    @property
    def text2video_enabled(self) -> bool:
        return bool(self.api_key and self._text2video_model)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    # ── 带重试的 HTTP 请求核心 ──────────────────────────────

    def _retry_on_transient(self, func, *args, **kwargs):
        """对瞬时错误（网络超时/断连、5xx、429）进行指数退避重试"""
        last_exception: Exception | None = None
        for attempt in range(self.retry_count + 1):
            try:
                return func(*args, **kwargs)
            except requests.Timeout as e:
                last_exception = e
            except requests.ConnectionError as e:
                last_exception = e
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if status in (429, 502, 503, 504):
                    last_exception = e
                else:
                    raise  # 4xx 客户端错误不重试
            if attempt < self.retry_count:
                delay = (2 ** attempt) + random.uniform(0, 0.5)
                time.sleep(delay)
        raise last_exception  # type: ignore[misc]

    def _post_json(self, payload: dict, timeout_key: str = "chat") -> dict:
        """POST JSON payload to endpoint, return parsed response dict"""
        timeout = self._timeout_map.get(timeout_key, (30, 300))

        def do_request() -> dict:
            response = requests.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()

        return self._retry_on_transient(do_request)

    def _post_stream(self, payload: dict, timeout_key: str = "stream_chat") -> requests.Response:
        """POST JSON payload to endpoint with streaming, return raw Response"""
        timeout = self._timeout_map.get(timeout_key, (30, 600))

        def do_request() -> requests.Response:
            response = requests.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
                stream=True,
            )
            response.raise_for_status()
            return response

        return self._retry_on_transient(do_request)

    def _chat_payload(self, payload: dict) -> dict:
        """DashScope OpenAI-compatible extra body: keep thinking mode off by default."""
        return {**payload, "enable_thinking": self._enable_thinking}

    # ── Chat (普通) ────────────────────────────────────────

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        if not self.enabled:
            raise RuntimeError("DashScope API Key 未配置")
        data = self._post_json(
            self._chat_payload({
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.6,
            }),
            timeout_key="chat",
        )
        return data["choices"][0]["message"]["content"]

    # ── Chat (流式) ────────────────────────────────────────

    def stream_chat(self, system_prompt: str, user_prompt: str) -> Generator[str, None, None]:
        if not self.enabled:
            raise RuntimeError("DashScope API Key 未配置")
        response = self._post_stream(
            self._chat_payload({
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.6,
                "stream": True,
            }),
            timeout_key="stream_chat",
        )
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line or not raw_line.startswith("data:"):
                continue
            payload = raw_line.removeprefix("data:").strip()
            if payload == "[DONE]":
                break
            data = json.loads(payload)
            delta = data["choices"][0].get("delta", {}).get("content", "")
            if delta:
                yield delta

    # ── Chat (多模态) ──────────────────────────────────────

    def chat_multimodal(self, system_prompt: str, text: str, images: list[str]) -> str:
        if not self.enabled:
            raise RuntimeError("DashScope API Key 未配置")
        content_parts: list[dict] = [{"type": "text", "text": text}]
        for img in images:
            content_parts.append({"type": "image_url", "image_url": {"url": img}})
        data = self._post_json(
            self._chat_payload({
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content_parts},
                ],
                "temperature": 0.6,
            }),
            timeout_key="chat_multimodal",
        )
        return data["choices"][0]["message"]["content"]

    def stream_chat_multimodal(self, system_prompt: str, text: str, images: list[str]) -> Generator[str, None, None]:
        if not self.enabled:
            raise RuntimeError("DashScope API Key 未配置")
        content_parts: list[dict] = [{"type": "text", "text": text}]
        for img in images:
            content_parts.append({"type": "image_url", "image_url": {"url": img}})
        response = self._post_stream(
            self._chat_payload({
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content_parts},
                ],
                "temperature": 0.6,
                "stream": True,
            }),
            timeout_key="stream_chat_multimodal",
        )
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line or not raw_line.startswith("data:"):
                continue
            payload = raw_line.removeprefix("data:").strip()
            if payload == "[DONE]":
                break
            data = json.loads(payload)
            delta = data["choices"][0].get("delta", {}).get("content", "")
            if delta:
                yield delta

    def describe_images(self, images: list[str]) -> str:
        if not self.enabled:
            raise RuntimeError("DashScope API Key 未配置")
        if not images:
            return ""

        model = self._vision_model or self.model
        content_parts: list[dict] = [
            {
                "type": "text",
                "text": "请详细描述这张图片里的所有内容，包括文字、图表、公式、题目、笔记等关键信息，不要遗漏任何细节。",
            }
        ]
        for img in images:
            content_parts.append({"type": "image_url", "image_url": {"url": img}})

        data = self._post_json(
            self._chat_payload({
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个专业的图片内容分析助手，擅长从图片中提取所有文字信息和视觉内容。",
                    },
                    {"role": "user", "content": content_parts},
                ],
                "temperature": 0.4,
                "max_tokens": 2048,
            }),
            timeout_key="describe_images",
        )
        return data["choices"][0]["message"]["content"]

    # ── 文生图 / 文生视频 ──────────────────────────────────

    def generate_text2image(self, prompt: str, size: str = "1024*1024", n: int = 1) -> dict[str, Any]:
        if not self.text2image_enabled:
            return {"enabled": False, "message": "未配置 DASHSCOPE_TEXT2IMAGE_MODEL"}
        endpoint = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
        payload = {
            "model": self._text2image_model,
            "input": {"prompt": prompt},
            "parameters": {"size": size, "n": n},
        }

        def do_request() -> dict:
            response = requests.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "X-DashScope-Async": "enable",
                },
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            return response.json()

        try:
            data = self._retry_on_transient(do_request)
        except Exception:
            return {"enabled": False, "message": "文生图 API 调用失败"}

        output = data.get("output", {})
        result: dict[str, Any] = {
            "enabled": True,
            "task_id": output.get("task_id", ""),
            "task_status": output.get("task_status", "UNKNOWN"),
        }
        results = output.get("results")
        if results:
            result["results"] = results
        return result

    def generate_text2video(self, prompt: str, duration: int = 10, audio: bool | None = None) -> dict[str, Any]:
        if not self.text2video_enabled:
            return {"enabled": False, "message": "未配置 DASHSCOPE_TEXT2VIDEO_MODEL"}
        if audio is None:
            audio = self._text2video_audio
        endpoint = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
        payload = {
            "model": self._text2video_model,
            "input": {"prompt": prompt, "duration": duration},
            "parameters": {"audio": audio},
        }

        def do_request() -> dict:
            response = requests.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "X-DashScope-Async": "enable",
                },
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            return response.json()

        try:
            data = self._retry_on_transient(do_request)
        except Exception:
            return {"enabled": False, "message": "文生视频 API 调用失败"}

        output = data.get("output", {})
        result: dict[str, Any] = {
            "enabled": True,
            "task_id": output.get("task_id", ""),
            "task_status": output.get("task_status", "UNKNOWN"),
        }
        results = output.get("results")
        if results:
            result["results"] = results
        else:
            video_url = output.get("video_url")
            if video_url:
                result["results"] = [{"url": video_url}]
        return result

    def query_task(self, task_id: str) -> dict[str, Any]:
        url = f"{self._task_endpoint}/{task_id}"

        def do_request() -> dict:
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30,
            )
            response.raise_for_status()
            return response.json()

        return self._retry_on_transient(do_request)
