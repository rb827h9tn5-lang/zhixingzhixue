from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import requests

from .base_agent import BaseAgent


class MultimediaAgent(BaseAgent):
    """多媒体教学 Agent：基于学生画像调用文生视频模型生成教学视频"""

    def __init__(self, profile: dict):
        super().__init__(profile, "多媒体教学 Agent")

    def generate_video(self, extra_input: str, fallback: Callable[[], str]) -> tuple[str, dict[str, Any]]:
        """基于学生画像调用文生视频 API 生成教学视频

        先通过 LLM 根据画像构造精准的视频描述 prompt，
        再调用 DashScope 文生视频 API 生成视频，
        异步任务最多等 180 秒，超时后返回 task_id 供前端轮询。

        返回:
            content: 视频 URL 或任务状态信息（JSON 字符串）
            meta: Agent 元信息
        """
        if not self.qwen.text2video_enabled:
            return fallback(), self.fallback_meta("未配置 DASHSCOPE_TEXT2VIDEO_MODEL，已使用本地模板生成。")

        # 用 LLM 根据学生画像构造视频描述 prompt
        extra_note = f"\n用户额外要求：{extra_input}" if extra_input else ""
        topic = self.profile.get("topic", "人工智能导论")
        level = self.profile.get("knowledge_level", "beginner")
        goal = self.profile.get("learning_goal", "系统掌握课程核心知识")

        prompt_builder_prompt = (
            "你是一个专业的教学视频 prompt 工程师。请根据以下信息，生成一段适合输入文生视频模型的视频描述。\n"
            f"课程主题：{topic}\n"
            f"学生水平：{level}\n"
            f"学习目标：{goal}\n"
            f"{extra_note}\n"
            "要求：\n"
            "1. 描述画面内容、风格、色调，字数 100-200 字\n"
            "2. 适合教学场景，画面清晰流畅\n"
            "3. 包含关键知识点的视觉化展示\n"
            "4. 仅返回视频描述文本，不要多余内容"
        )
        try:
            video_prompt = self.qwen.chat(self.role_prompt(), prompt_builder_prompt).strip()
            if not video_prompt:
                raise RuntimeError("生成的视频描述为空")
        except Exception as exc:
            return fallback(), self.fallback_meta(f"视频描述生成失败：{exc}")

        # 调用文生视频 API
        try:
            result = self.qwen.generate_text2video(video_prompt, duration=10)
        except Exception as exc:
            return fallback(), self.fallback_meta(f"文生视频 API 调用失败：{exc}")

        task_id = result.get("task_id", "")
        if not task_id:
            return fallback(), self.fallback_meta("文生视频 API 未返回 task_id")

        task_status = result.get("task_status", "UNKNOWN")
        results = result.get("results")

        # 如果同步返回了结果直接使用
        if results:
            results = self._save_video_results(results)
            content = json.dumps({
                "task_id": task_id,
                "task_status": task_status,
                "prompt": video_prompt,
                "results": results,
            }, ensure_ascii=False)
            return content, self.agent_meta("生成教学视频（同步完成）")

        # 异步任务：轮询等待最多 180 秒
        meta = self.agent_meta("生成教学视频（异步等待）")
        wait_interval = 5
        max_wait = 300
        waited = 0
        while waited < max_wait:
            time.sleep(wait_interval)
            waited += wait_interval
            try:
                status_result = self.qwen.query_task(task_id)
                task_output = status_result.get("output", {})
                status = task_output.get("task_status", "UNKNOWN")
                if status == "SUCCEEDED":
                    video_results = task_output.get("results", [])
                    if not video_results:
                        video_url = task_output.get("video_url", "")
                        if video_url:
                            video_results = [{"url": video_url}]
                    video_results = self._save_video_results(video_results)
                    content = json.dumps({
                        "task_id": task_id,
                        "task_status": status,
                        "prompt": video_prompt,
                        "results": video_results,
                    }, ensure_ascii=False)
                    return content, self.agent_meta("生成教学视频（异步完成）")
                if status == "FAILED":
                    error_msg = task_output.get("message", "视频生成失败")
                    return fallback(), self.fallback_meta(f"文生视频任务失败：{error_msg}")
            except Exception:
                continue

        # 超时，返回 task_id 供前端轮询
        content = json.dumps({
            "task_id": task_id,
            "task_status": "RUNNING",
            "prompt": video_prompt,
            "message": "视频生成中，请稍后查询状态",
        }, ensure_ascii=False)
        return content, self.agent_meta("生成教学视频（任务提交，需轮询）")

    def _save_video_results(self, results: list) -> list:
        """将视频文件下载到本地 uploads/generated_videos/，替换远程 URL 为本地地址"""
        saved = []
        for item in results:
            url = item.get("url") if isinstance(item, dict) else item
            if url and "/api/uploads/" not in url:
                local_url = self._download_video(url)
                if local_url != url:
                    if isinstance(item, dict):
                        item = {**item, "url": local_url}
                    else:
                        item = local_url
            saved.append(item)
        return saved

    @staticmethod
    def _download_video(url: str) -> str:
        """下载单个视频文件到 uploads/generated_videos/"""
        try:
            backend_dir = Path(__file__).resolve().parents[3]
            target_dir = backend_dir / "uploads" / "generated_videos"
            target_dir.mkdir(parents=True, exist_ok=True)

            resp = requests.get(url, timeout=120, stream=True)
            resp.raise_for_status()

            filename = f"{uuid.uuid4().hex}.mp4"
            local_path = target_dir / filename

            with open(local_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            if local_path.exists() and local_path.stat().st_size > 0:
                return f"/api/uploads/generated_videos/{filename}"
        except Exception:
            pass
        return url  # 下载失败回退到原 URL
