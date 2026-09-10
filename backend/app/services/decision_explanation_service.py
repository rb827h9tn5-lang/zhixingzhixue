from __future__ import annotations

from typing import Any

from ..models import (
    AdaptiveExam,
    LearningPath,
    LearningPathNode,
    LearningPathVersion,
    Profile,
)
from .diagnosis_service import DiagnosisService
from .path_service import StructuredPathService


class DecisionExplanationService:
    @classmethod
    def explain(
        cls,
        *,
        user_id: int,
        profile: Profile,
        decision_type: str,
        knowledge_point_id: int | None = None,
        node_id: int | None = None,
        path_version_id: int | None = None,
        exam_id: int | None = None,
    ) -> dict[str, Any]:
        if decision_type in {"remediation", "next_learning"}:
            return cls._explain_learning_target(
                user_id=user_id,
                profile=profile,
                decision_type=decision_type,
                knowledge_point_id=knowledge_point_id,
            )
        if decision_type == "path_change":
            return cls._explain_path_change(
                user_id=user_id,
                path_version_id=path_version_id,
            )
        if decision_type == "resource":
            return cls._explain_resource(user_id=user_id, node_id=node_id)
        if decision_type == "exam_question":
            return cls._explain_exam(user_id=user_id, exam_id=exam_id)
        raise ValueError("不支持的决策解释类型")

    @classmethod
    def _explain_learning_target(
        cls,
        *,
        user_id: int,
        profile: Profile,
        decision_type: str,
        knowledge_point_id: int | None,
    ) -> dict:
        diagnosis = DiagnosisService.build(user_id=user_id, profile=profile)
        target = diagnosis["recommended_target"]
        target_id = knowledge_point_id or (
            target["knowledge_point_id"] if target else None
        )
        if not target_id:
            return {
                "decision_type": decision_type,
                "decision": "先完成一次诊断测评",
                "reasons": ["当前没有足够的知识点作答证据"],
                "evidence": [],
                "alternatives": ["导入课程资料", "生成自适应诊断测评"],
                "trigger": "学习证据不足",
            }
        detail = DiagnosisService.detail(
            user_id=user_id,
            profile=profile,
            knowledge_point_id=target_id,
        )
        point = detail["knowledge_point"]
        evidence = detail["mastery"].get("evidence", [])[:6]
        return {
            "decision_type": decision_type,
            "decision": (
                f"为“{point['name']}”生成补救计划"
                if decision_type == "remediation"
                else f"下一步学习“{point['name']}”"
            ),
            "reasons": detail["reasons"],
            "evidence": evidence,
            "alternatives": detail["recommendations"],
            "trigger": (
                f"诊断状态为 {detail['diagnosis_state']}，"
                f"证据事件 {sum(detail['event_summary'].values())} 条"
            ),
        }

    @staticmethod
    def _explain_path_change(
        *,
        user_id: int,
        path_version_id: int | None,
    ) -> dict:
        if path_version_id:
            version = (
                LearningPathVersion.query.join(LearningPath)
                .filter(
                    LearningPathVersion.id == path_version_id,
                    LearningPath.user_id == user_id,
                )
                .first()
            )
        else:
            _, version = StructuredPathService.latest_user_path(user_id)
        if not version:
            raise LookupError("当前没有学习路径版本")
        diff = None
        if version.parent_version_id:
            diff = StructuredPathService.diff_versions(
                user_id=user_id,
                from_version_id=version.parent_version_id,
                to_version_id=version.id,
            )
        return {
            "decision_type": "path_change",
            "decision": f"学习路径已调整为 v{version.version_number}",
            "reasons": [
                version.replanning_reason or "依据最新掌握度和先修关系生成",
            ],
            "evidence": (
                [diff["mastery_change"]]
                if diff and diff.get("mastery_change")
                else []
            ),
            "alternatives": (
                [
                    f"保留 v{version.version_number - 1} 作为历史版本",
                    "完成补救节点后重新测评",
                ]
                if version.parent_version_id
                else ["完成当前节点后依据新证据动态调整"]
            ),
            "trigger": (
                f"学习事件 #{version.reason_event_id}"
                if version.reason_event_id
                else "首次生成结构化路径"
            ),
            "diff": diff,
        }

    @staticmethod
    def _explain_resource(*, user_id: int, node_id: int | None) -> dict:
        if not node_id:
            raise ValueError("缺少学习节点 ID")
        node = (
            LearningPathNode.query.join(LearningPathVersion)
            .join(LearningPath)
            .filter(
                LearningPathNode.id == node_id,
                LearningPath.user_id == user_id,
            )
            .first()
        )
        if not node:
            raise LookupError("学习节点不存在")
        bindings = [binding.to_dict() for binding in node.resources]
        return {
            "decision_type": "resource",
            "decision": (
                f"为“{node.knowledge_point.name}”绑定 {len(bindings)} 个课程资源"
                if node.knowledge_point
                else f"为节点绑定 {len(bindings)} 个课程资源"
            ),
            "reasons": [
                binding["personalization_reason"]
                for binding in bindings
                if binding["personalization_reason"]
            ] or ["当前知识库没有可绑定的课程片段"],
            "evidence": [
                {
                    "resource_id": binding["resource_id"],
                    "resource_type": binding["resource_type"],
                    "title": (
                        binding["resource"]["title"]
                        if binding.get("resource")
                        else ""
                    ),
                }
                for binding in bindings
            ],
            "alternatives": ["上传更多课程资料", "完成资源后进入节点测评"],
            "trigger": node.reason or "节点学习需要课程材料支撑",
        }

    @staticmethod
    def _explain_exam(*, user_id: int, exam_id: int | None) -> dict:
        if not exam_id:
            raise ValueError("缺少自适应测评 ID")
        exam = AdaptiveExam.query.filter_by(id=exam_id, user_id=user_id).first()
        if not exam:
            raise LookupError("自适应测评不存在")
        allocations = (exam.blueprint_json or {}).get("allocations", [])
        return {
            "decision_type": "exam_question",
            "decision": (
                f"按 {exam.duration_minutes} 分钟、{exam.goal} 目标生成"
                f" {sum(item.get('question_count', 0) for item in allocations)} 道题"
            ),
            "reasons": [
                item.get("reason", "")
                for item in allocations
                if item.get("reason")
            ],
            "evidence": allocations,
            "alternatives": [
                "调整测评时长以改变题量",
                "切换诊断、强化、模拟或综合目标",
            ],
            "trigger": "当前掌握度、置信度和知识点覆盖共同决定题目配比",
            "blueprint": exam.blueprint_json or {},
        }
