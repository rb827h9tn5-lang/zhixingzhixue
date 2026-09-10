import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

from .ai_client import QwenClient
from .guardrails import ContentGuard


class ExternalModelClient:
    def __init__(self, url_env: str, key_env: str):
        self.url = os.getenv(url_env, "")
        self.key = os.getenv(key_env, "")

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        response = requests.post(self.url, json=payload, headers=headers, timeout=120)
        response.raise_for_status()
        data = response.json()
        data["enabled"] = True
        return data


def _parse_mermaid_to_mindmap(mermaid_text: str, default_topic: str) -> dict:
    """
    从 Mermaid mindmap 文本中解析出 central_topic 和 branches。

    支持的格式示例：
      mindmap
        root((人工智能))
          学习路径
            基础概念
              机器学习定义
          实践项目
            模型评估
              准确率
    """
    text = mermaid_text.strip()
    match = re.search(r"```mermaid\n?(.*?)```", text, flags=re.S)
    if match:
        text = match.group(1).strip()
    lines = text.split("\n")
    if lines and lines[0].strip().lower() == "mindmap":
        lines = lines[1:]

    central_topic = default_topic
    branches = []
    current_branch = None

    indent_levels = []
    for line in lines:
        raw = line
        stripped = line.strip()
        if not stripped:
            continue
        if "root((" in stripped:
            continue
        indent = len(raw) - len(raw.lstrip())
        indent_levels.append(indent)

    if not indent_levels:
        return {"central_topic": central_topic, "branches": []}

    base_indent = min(indent_levels)

    for line in lines:
        raw = line
        stripped = line.strip()
        if not stripped:
            continue
        if "root((" in stripped:
            m = re.search(r"root\(\((.+?)\)\)", stripped)
            if m:
                central_topic = m.group(1).strip()
            continue
        indent = len(raw) - len(raw.lstrip())
        relative_indent = indent - base_indent

        text_content = stripped.lstrip("- ")
        if ":" in text_content and not text_content.startswith("http"):
            text_content = text_content.split(":", 1)[0].strip()

        if relative_indent <= 1:
            if current_branch is not None:
                branches.append(current_branch)
            current_branch = {"branch": text_content, "points": []}
        elif relative_indent >= 2 and current_branch is not None:
            current_branch["points"].append(text_content)
        elif current_branch is not None:
            current_branch["points"].append(text_content)

    if current_branch is not None:
        branches.append(current_branch)

    return {"central_topic": central_topic, "branches": branches}


def generate_mind_map_image(topic: str, profile: dict, content: str) -> dict[str, Any]:
    """
    从已有的资源内容中解析 Mermaid mindmap 文本提取结构化数据，
    然后调用外部 mindmap API 创建思维导图。
    如果解析失败，回退到 LLM 生成。
    """
    mind_map_data = _parse_mermaid_to_mindmap(content, topic)
    if not mind_map_data.get("branches"):
        mind_map_data = {"central_topic": topic, "branches": []}
        level_map = {
            "beginner": "入门基础",
            "intermediate": "中级进阶",
            "advanced": "高级深入",
        }
        level = level_map.get(profile.get("knowledge_level", ""), "综合")
        goal = profile.get("learning_goal", topic)[:60]
        qwen = QwenClient()
        if qwen.enabled:
            system_prompt = (
                "你是思维导图生成专家。根据输入生成如下 JSON："
                '{"central_topic":"...","branches":[{"branch":"...","points":["...","..."]}]}。'
                "只能输出纯 JSON。"
            )
            user_prompt = (
                f"为学习「{topic}」生成一份中文思维导图的结构化数据。\n"
                f"学生水平：{level}\n"
                f"学习目标：{goal}\n"
                "要求：向外辐射3-4个一级分支，每个分支2-4个要点。"
            )
            try:
                raw = qwen.chat(system_prompt, user_prompt).strip()
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                parsed = json.loads(raw)
                if parsed.get("branches"):
                    mind_map_data = parsed
            except Exception:
                pass

    central_topic = mind_map_data.get("central_topic", topic)
    branches = mind_map_data.get("branches", [])
    if not branches:
        return {"enabled": False, "message": "未能生成有效的思维导图分支结构，无法调用外部 API"}

    mindmap_api_url = os.getenv("MINDMAP_API_URL", "https://ai-mindmap.app/api/imports")
    payload = {
        "title": f"{topic} 思维导图",
        "source": "agent",
        "data": {
            "central_topic": central_topic,
            "branches": branches,
        },
    }

    try:
        resp = requests.post(mindmap_api_url, json=payload, headers={"Content-Type": "application/json"}, timeout=60)
        resp.raise_for_status()
        api_result = resp.json()
        mindmap_url = api_result.get("url") or api_result.get("data", {}).get("url", "")
        return {
            "enabled": True,
            "image_url": mindmap_url,
            "mindmap_url": mindmap_url,
            "mindmap_data": mind_map_data,
            "api_response": api_result,
            "message": "思维导图已生成",
        }
    except requests.RequestException as e:
        return {
            "enabled": True,
            "mindmap_data": mind_map_data,
            "message": f"已生成思维导图数据，但调用外部 API 失败: {str(e)[:200]}",
        }


def generate_mind_map_artifact(topic: str, profile: dict, mermaid: str) -> Any:
    client = ExternalModelClient("MINDMAP_MODEL_API_URL", "MINDMAP_MODEL_API_KEY")
    guard = ContentGuard()
    payload = {
        "task": "mind_map",
        "topic": topic,
        "profile": profile,
        "mermaid": mermaid,
        "prompt": f"请将 {topic} 的 Mermaid 思维导图渲染成清晰的中文知识结构图。{guard.agent_constraints()}",
        "safety_constraints": guard.agent_constraints(),
    }
    if client.enabled:
        return client.generate(payload)
    return {
        "enabled": False,
        "message": "未配置 MINDMAP_MODEL_API_URL，当前返回 Mermaid 结构，配置后可调用画图模型生成图片。",
    }