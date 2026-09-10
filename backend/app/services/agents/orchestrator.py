from __future__ import annotations

import json
import time
from typing import Any, Callable

from .base_agent import BaseAgent
from .resource_agent import (
    CourseDocumentAgent,
    ExtensionReadingAgent,
    MindMapAgent,
)
from .quiz_agent import QuizAgent
from .coding_agent import CodingCaseAgent
from .evaluation_agent import EvaluationAgent
from .multimedia_agent import MultimediaAgent


class AgentOrchestrator:
    """多智能体编排器：负责任务路由、Agent 调度和结果聚合

    架构说明：
    - 本编排器管理多个专用 Agent 角色，每个 Agent 有独立的 system prompt 和职责边界
    - 根据资源类型自动路由到对应的 Agent 处理
    - 支持链式编排（如先大纲 → 再并行章节）和条件回退（失败时降级到本地模板）
    - 提供编排元数据记录每个环节的 Agent 参与情况
    """

    def __init__(self, profile: dict):
        self.profile = profile
        self._agents: dict[str, BaseAgent] = {}
        self._init_agents()

    def _init_agents(self):
        """初始化所有专用 Agent 实例"""
        self._agents = {
            "course_document": CourseDocumentAgent(self.profile),
            "mind_map": MindMapAgent(self.profile),
            "extension_reading": ExtensionReadingAgent(self.profile),
            "exercise_bank": QuizAgent(self.profile),
            "coding_case": CodingCaseAgent(self.profile),
            "evaluation": EvaluationAgent(self.profile),
            "multimedia": MultimediaAgent(self.profile),
        }

    def get_agent(self, agent_key: str) -> BaseAgent | None:
        """按名称获取 Agent 实例"""
        return self._agents.get(agent_key)

    @property
    def all_agents(self) -> dict[str, BaseAgent]:
        """获取所有 Agent 列表"""
        return dict(self._agents)

    def dispatch_resource(self, resource_type: str, fallback: Callable[[], str], extra_input: str = "") -> tuple[str, dict[str, Any]]:
        """编排资源生成任务：根据资源类型路由到对应的 Agent

        编排流程：
        1. 检查 Agent 可用性 → 不可用则回退本地模板
        2. 按资源类型路由 → course_document → CourseDocumentAgent
                                     mind_map      → MindMapAgent
                                     extension_reading → ExtensionReadingAgent
        3. 各 Agent 内部独立编排 → 如 course_document 内部分两步（大纲生成 → 并行章节）
        4. 结果经 ContentGuard 安全审核后返回
        """
        agent_map = {
            "course_document": "course_document",
            "mind_map": "mind_map",
            "extension_reading": "extension_reading",
        }
        agent_key = agent_map.get(resource_type)
        if not agent_key:
            raise ValueError(f"未知资源类型: {resource_type}")

        agent = self._agents[agent_key]
        if not agent.enabled:
            return fallback(), agent.fallback_meta("Agent 不可用，已回退本地模板")

        return agent.generate(extra_input, fallback)

    def dispatch_quiz_generation(
        self, difficulty: str, focus: str, count: int, fallback: Callable[[], dict]
    ) -> tuple[dict, dict[str, Any]]:
        """编排题库生成任务 → 路由到 QuizAgent"""
        return self._agents["exercise_bank"].generate(difficulty, focus, count, fallback)

    def dispatch_coding_case(self, fallback: Callable[[], dict], extra_input: str = "") -> tuple[dict, dict[str, Any]]:
        """编排实操案例生成任务 → 路由到 CodingCaseAgent"""
        return self._agents["coding_case"].generate(fallback, extra_input)

    def dispatch_evaluation(self, quiz: dict, answers: dict, details: list, score: float) -> str:
        """编排学习评估任务 → 路由到 EvaluationAgent"""
        return self._agents["evaluation"].evaluate(quiz, answers, details, score)

    def dispatch_multimedia_video(self, extra_input: str, fallback: Callable[[], str]) -> tuple[str, dict[str, Any]]:
        """编排教学视频生成任务 → 路由到 MultimediaAgent（调用文生视频 API）"""
        return self._agents["multimedia"].generate_video(extra_input, fallback)

    def orchestration_report(self) -> dict[str, Any]:
        """生成编排报告，展示多智能体协同的元信息"""
        return {
            "orchestrator": "AgentOrchestrator",
            "version": "1.0",
            "agents": {
                name: {
                    "class": agent.__class__.__name__,
                    "enabled": agent.enabled,
                }
                for name, agent in self._agents.items()
            },
            "agent_count": len(self._agents),
            "strategy": "基于资源类型的路由分发 + 各 Agent 内部分步编排",
        }