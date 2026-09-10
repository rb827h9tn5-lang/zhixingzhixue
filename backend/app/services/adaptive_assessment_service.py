from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from ..extensions import db
from ..models import (
    AgentRun,
    AdaptiveExam,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgePoint,
    Profile,
    QuizResult,
    UserKnowledgeMastery,
)
from .agent_trace_service import AgentTraceService
from .cognitive_process_service import CognitiveProcessService
from .diagnosis_service import DiagnosisService
from .intervention_service import (
    LearningInterventionService,
    TeachingEffectService,
)
from .learning_event_service import LearningEventService
from .local_generator import LocalStudyGenerator
from .mastery_service import MasteryService
from .misconception_service import MisconceptionService
from .path_service import ReplanningService
from .teaching_strategy_service import TeachingStrategyEngine
from .transfer_service import (
    CapabilityGateService,
    MasteryDimensionService,
    MetacognitiveCalibrationService,
    TransferAssessmentService,
)


class AdaptiveAssessmentService:
    GOALS = {
        "diagnosis",
        "reinforcement",
        "mock",
        "comprehensive",
        "transfer",
    }

    @classmethod
    def create(
        cls,
        *,
        user_id: int,
        profile: Profile,
        duration_minutes: int,
        goal: str,
        difficulty: str = "intermediate",
        course_id: int | None = None,
        knowledge_point_id: int | None = None,
    ) -> dict[str, Any]:
        duration_minutes = max(10, min(int(duration_minutes), 120))
        if goal not in cls.GOALS:
            raise ValueError(
                "测评目标必须是 diagnosis、reinforcement、mock、"
                "comprehensive 或 transfer"
            )
        points = DiagnosisService._scoped_points(user_id, profile)
        if course_id:
            points = [point for point in points if point.course_id == course_id]
        if knowledge_point_id:
            points = [point for point in points if point.id == knowledge_point_id]
        if not points:
            raise ValueError("当前没有可用于组卷的课程知识点")

        run = AgentTraceService.start(
            user_id=user_id,
            task_type="adaptive_exam",
            input_data={
                "duration_minutes": duration_minutes,
                "goal": goal,
                "difficulty": difficulty,
                "course_id": course_id,
                "knowledge_point_id": knowledge_point_id,
            },
        )
        db.session.commit()
        try:
            mastery_by_point = {
                row.knowledge_point_id: row
                for row in UserKnowledgeMastery.query.filter(
                    UserKnowledgeMastery.user_id == user_id,
                    UserKnowledgeMastery.knowledge_point_id.in_(
                        [point.id for point in points]
                    ),
                ).all()
            }
            AgentTraceService.record_step(
                run,
                agent_name="Diagnostician",
                action="读取知识点掌握度和证据置信度",
                input_data={"knowledge_point_count": len(points)},
                output_data={
                    "assessed_count": len(mastery_by_point),
                    "unassessed_count": len(points) - len(mastery_by_point),
                },
                evidence_count=sum(
                    row.attempt_count for row in mastery_by_point.values()
                ),
            )

            blueprint = cls._build_blueprint(
                points=points,
                mastery_by_point=mastery_by_point,
                duration_minutes=duration_minutes,
                goal=goal,
            )
            AgentTraceService.record_step(
                run,
                agent_name="Planner",
                action="按掌握度、置信度和测评目标分配题量",
                input_data={
                    "duration_minutes": duration_minutes,
                    "goal": goal,
                },
                output_data=blueprint,
                evidence_count=len(blueprint["allocations"]),
            )

            quiz, source_count = cls._generate_grounded_quiz(
                user_id=user_id,
                profile=profile,
                blueprint=blueprint,
                difficulty=difficulty,
            )
            AgentTraceService.record_step(
                run,
                agent_name="Retriever",
                action="读取当前用户课程资料作为出题依据",
                input_data={
                    "knowledge_point_ids": [
                        item["knowledge_point_id"]
                        for item in blueprint["allocations"]
                    ]
                },
                output_data={"matched_chunk_count": source_count},
                evidence_count=source_count,
                status="passed" if source_count else "revised",
            )
            AgentTraceService.record_step(
                run,
                agent_name="Generator",
                action="依据测评蓝图生成可判分题目",
                input_data={"blueprint_question_count": blueprint["question_count"]},
                output_data={"generated_question_count": len(quiz["questions"])},
                evidence_count=len(quiz["questions"]),
            )

            actual_counts: dict[int, int] = defaultdict(int)
            for question in quiz["questions"]:
                actual_counts[int(question["primary_knowledge_point_id"])] += 1
            expected_counts = {
                item["knowledge_point_id"]: item["question_count"]
                for item in blueprint["allocations"]
            }
            verified = (
                len(quiz["questions"]) == blueprint["question_count"]
                and dict(actual_counts) == expected_counts
            )
            AgentTraceService.record_step(
                run,
                agent_name="Verifier",
                action="核对题量、知识点覆盖和蓝图配比",
                input_data={"expected": expected_counts},
                output_data={
                    "actual": dict(actual_counts),
                    "verified": verified,
                },
                evidence_count=len(quiz["questions"]),
                status="passed" if verified else "failed",
            )
            if not verified:
                raise RuntimeError("自适应测评题目未通过蓝图校验")

            pre_mastery = {
                str(point.id): (
                    round(float(mastery_by_point[point.id].mastery_score), 2)
                    if point.id in mastery_by_point
                    else None
                )
                for point in points
                if point.id in expected_counts
            }
            exam = AdaptiveExam(
                user_id=user_id,
                course_id=points[0].course_id,
                agent_run_id=run.id,
                duration_minutes=duration_minutes,
                goal=goal,
                difficulty=difficulty,
                status="ready",
                blueprint_json=blueprint,
                quiz_json=quiz,
                pre_mastery_json=pre_mastery,
            )
            db.session.add(exam)
            db.session.flush()
            AgentTraceService.finish(
                run,
                output_data={
                    "exam_id": exam.id,
                    "question_count": blueprint["question_count"],
                    "verified": True,
                },
            )
            db.session.commit()
            return {
                "exam": exam.to_dict(include_quiz=True),
                "agent_run": run.to_dict(include_steps=True),
            }
        except Exception as exc:
            run_id = run.id
            db.session.rollback()
            persisted_run = db.session.get(AgentRun, run_id)
            AgentTraceService.fail(persisted_run, exc)
            db.session.commit()
            raise

    @classmethod
    def submit(
        cls,
        *,
        user_id: int,
        profile: Profile,
        exam_id: int,
        answers: dict,
        reasoning_steps: dict | None = None,
        self_confidence: dict | None = None,
    ) -> dict[str, Any]:
        exam = AdaptiveExam.query.filter_by(id=exam_id, user_id=user_id).first()
        if not exam:
            raise LookupError("自适应测评不存在")
        if exam.status == "completed" and exam.result:
            return cls._completed_payload(exam)
        if exam.status not in {"ready", "in_progress"}:
            raise ValueError("当前测评还不能提交")
        run = exam.agent_run
        quiz = exam.quiz_json or {}
        result_data = LocalStudyGenerator(profile.to_dict()).grade_structured_quiz(
            quiz,
            answers,
        )
        AgentTraceService.record_step(
            run,
            agent_name="Evaluator",
            action="按题目标准答案完成客观判分",
            input_data={"answer_count": len(answers)},
            output_data={
                "score": result_data["score"],
                "detail_count": len(result_data["details"]),
            },
            evidence_count=len(result_data["details"]),
        )

        record = QuizResult(
            user_id=user_id,
            quiz_content=quiz.get("title") or "掌握度自适应测评",
            answers={
                "submitted": answers,
                "reasoning_steps": reasoning_steps or {},
                "self_confidence": self_confidence or {},
                "quiz": quiz,
                "details": result_data["details"],
                "completed": True,
                "adaptive_exam_id": exam.id,
            },
            score=result_data["score"],
            wrong_questions="; ".join(
                detail.get("concept") or str(detail["id"])
                for detail in result_data["details"]
                if not detail["is_correct"]
            ),
            analysis=result_data["summary"],
            category="evaluation",
        )
        db.session.add(record)
        db.session.flush()
        events, coverage = LearningEventService.record_assessment_events(
            user_id=user_id,
            record=record,
            quiz=quiz,
            details=result_data["details"],
        )
        mastery_changes = MasteryService.grouped_changes(
            MasteryService.apply_events(events)
        )
        AgentTraceService.record_step(
            run,
            agent_name="MasteryUpdater",
            action="把逐题结果写入学习事件并更新掌握度",
            input_data={
                "assessment_id": record.id,
                "event_count": len(events),
            },
            output_data={
                "mastery_changes": mastery_changes,
                "mapping_coverage": coverage,
            },
            evidence_count=len(events),
        )

        if record.wrong_questions:
            profile.weak_points = record.wrong_questions
        cognitive_diagnoses = CognitiveProcessService.diagnose_assessment(
            user_id=user_id,
            record=record,
            quiz=quiz,
            details=result_data["details"],
            reasoning_steps=reasoning_steps,
        )
        AgentTraceService.record_step(
            run,
            agent_name="Diagnostician",
            action="CognitiveProcessDiagnosis：定位第一错误步骤",
            input_data={
                "assessment_id": record.id,
                "reasoning_submission_count": len(reasoning_steps or {}),
            },
            output_data={
                "diagnosis_count": len(cognitive_diagnoses),
                "root_errors": [
                    {
                        "question_id": item.question_id,
                        "first_error_step": item.first_error_step,
                        "root_cause_knowledge_point_id": (
                            item.root_cause_knowledge_point_id
                        ),
                    }
                    for item in cognitive_diagnoses
                    if item.first_error_step
                ],
            },
            evidence_count=sum(len(item.steps) for item in cognitive_diagnoses),
            status=(
                "passed" if cognitive_diagnoses else "skipped"
            ),
        )
        misconception_rows = MisconceptionService.apply_diagnoses(
            user_id=user_id,
            diagnoses=cognitive_diagnoses,
        )
        AgentTraceService.record_step(
            run,
            agent_name="Diagnostician",
            action="MisconceptionDiagnosis：用重复 Evidence 更新认知误区",
            input_data={
                "cognitive_diagnosis_ids": [
                    item.id for item in cognitive_diagnoses
                ]
            },
            output_data={
                "misconceptions": [
                    {
                        "id": item.id,
                        "name": item.misconception.name,
                        "status": item.status,
                        "evidence_count": item.evidence_count,
                    }
                    for item in misconception_rows
                ]
            },
            evidence_count=sum(
                item.evidence_count for item in misconception_rows
            ),
            status="passed" if misconception_rows else "skipped",
        )
        dimension_changes = MasteryDimensionService.apply_assessment(
            user_id=user_id,
            record=record,
            quiz=quiz,
            details=result_data["details"],
            cognitive_diagnoses=cognitive_diagnoses,
        )
        transfer_rows = TransferAssessmentService.record_result(
            user_id=user_id,
            exam=exam,
            record=record,
            quiz=quiz,
            details=result_data["details"],
        )
        confidence_rows = MetacognitiveCalibrationService.record_submission(
            user_id=user_id,
            record=record,
            quiz=quiz,
            details=result_data["details"],
            self_confidence=self_confidence,
        )
        AgentTraceService.record_step(
            run,
            agent_name="Evaluator",
            action="TransferEvaluation：区分基础、变式与迁移证据",
            input_data={"assessment_id": record.id},
            output_data={
                "dimension_changes": dimension_changes,
                "transfer_assessments": [
                    item.to_dict() for item in transfer_rows
                ],
                "self_confidence_record_count": len(confidence_rows),
            },
            evidence_count=len(result_data["details"]),
        )
        observed_effects = TeachingEffectService.observe_after_assessment(
            user_id=user_id,
            record=record,
            mastery_changes=mastery_changes,
        )
        target_id = next(
            (
                item.root_cause_knowledge_point_id
                for item in cognitive_diagnoses
                if item.root_cause_knowledge_point_id
            ),
            None,
        ) or next(
            (
                int(item["knowledge_point_id"])
                for item in sorted(
                    mastery_changes,
                    key=lambda change: (
                        change.get("new", 101),
                        change["knowledge_point_id"],
                    ),
                )
            ),
            None,
        )
        strategy_decision = TeachingStrategyEngine.select(
            user_id=user_id,
            profile=profile,
            knowledge_point_id=target_id,
            assessment_id=record.id,
            agent_run_id=run.id,
        )
        AgentTraceService.record_step(
            run,
            agent_name="Planner",
            action="TeachingStrategySelection：选择下一步怎么教",
            input_data=strategy_decision.input_snapshot_json or {},
            output_data=TeachingStrategyEngine.payload(strategy_decision),
            evidence_count=(
                len(strategy_decision.reason_codes_json or [])
                + len(observed_effects)
            ),
            status="revised" if strategy_decision.switched else "passed",
        )
        intervention = LearningInterventionService.maybe_trigger(
            user_id=user_id,
            profile=profile,
            record=record,
            mastery_changes=mastery_changes,
            cognitive_diagnoses=cognitive_diagnoses,
            misconceptions=misconception_rows,
            strategy_decision=strategy_decision,
        )
        AgentTraceService.record_step(
            run,
            agent_name="Reviser",
            action="Intervention：判断学习阻塞并执行主动教学干预",
            input_data={
                "strategy_decision_id": strategy_decision.id,
                "assessment_id": record.id,
            },
            output_data=intervention,
            evidence_count=len(intervention.get("evidence") or {}),
            status=(
                "revised" if intervention.get("triggered") else "passed"
            ),
        )
        if intervention.get("triggered"):
            replanning = {
                "triggered": True,
                "reason": intervention.get("reason") or "",
                "version": intervention.get("path_version"),
                "diff": intervention.get("path_diff"),
                "intervention": True,
            }
        else:
            replanning = ReplanningService.maybe_replan(
                profile=profile,
                mastery_changes=mastery_changes,
                assessment_id=record.id,
            )

        exam.status = "completed"
        exam.result_id = record.id
        exam.completed_at = datetime.utcnow()
        post_mastery = {
            str(row.knowledge_point_id): round(float(row.mastery_score), 2)
            for row in UserKnowledgeMastery.query.filter(
                UserKnowledgeMastery.user_id == user_id,
                UserKnowledgeMastery.knowledge_point_id.in_(
                    [
                        item["knowledge_point_id"]
                        for item in (exam.blueprint_json or {}).get(
                            "allocations",
                            [],
                        )
                    ]
                ),
            ).all()
        }
        report = cls._build_report(
            exam=exam,
            result_data=result_data,
            post_mastery=post_mastery,
        )
        capability = {
            str(item["knowledge_point_id"]): CapabilityGateService.evaluate(
                user_id=user_id,
                knowledge_point_id=item["knowledge_point_id"],
            )
            for item in (exam.blueprint_json or {}).get("allocations", [])
        }
        record.answers = {
            **dict(record.answers or {}),
            "question_knowledge_point_coverage": coverage,
            "mastery_changes": mastery_changes,
            "replanning": replanning,
            "adaptive_report": report,
            "cognitive_diagnoses": [
                item.to_dict(include_steps=True)
                for item in cognitive_diagnoses
            ],
            "misconceptions": [
                item.to_dict(include_evidence=True)
                for item in misconception_rows
            ],
            "teaching_strategy": TeachingStrategyEngine.payload(
                strategy_decision
            ),
            "intervention": intervention,
            "observed_intervention_effects": [
                item.to_dict() for item in observed_effects
            ],
            "mastery_dimensions": dimension_changes,
            "transfer_assessments": [
                item.to_dict() for item in transfer_rows
            ],
            "capability": capability,
            "metacognitive_calibration": (
                MetacognitiveCalibrationService.report(user_id)
            ),
        }
        AgentTraceService.record_step(
            run,
            agent_name="Verifier",
            action="校验测评结果、掌握度变化和后续动作",
            input_data={"exam_id": exam.id, "result_id": record.id},
            output_data={
                "completed": True,
                "mastery_change_count": len(mastery_changes),
                "replanning_triggered": bool(replanning.get("triggered")),
                "cognitive_diagnosis_count": len(cognitive_diagnoses),
                "strategy": strategy_decision.strategy_type,
                "intervention_triggered": bool(
                    intervention.get("triggered")
                ),
            },
            evidence_count=(
                len(mastery_changes)
                + len(dimension_changes)
                + len(cognitive_diagnoses)
            ),
        )
        AgentTraceService.finish(
            run,
            output_data={
                "exam_id": exam.id,
                "result_id": record.id,
                "score": result_data["score"],
                "completed": True,
            },
            status="revised" if replanning.get("triggered") else "passed",
        )
        db.session.commit()
        return {
            "exam": exam.to_dict(include_quiz=False),
            "result": result_data,
            "record": record.to_dict(),
            "mastery_changes": mastery_changes,
            "replanning": replanning,
            "report": report,
            "cognitive_diagnoses": [
                item.to_dict(include_steps=True)
                for item in cognitive_diagnoses
            ],
            "misconceptions": [
                item.to_dict(include_evidence=True)
                for item in misconception_rows
            ],
            "teaching_strategy": TeachingStrategyEngine.payload(
                strategy_decision
            ),
            "intervention": intervention,
            "observed_intervention_effects": [
                item.to_dict() for item in observed_effects
            ],
            "mastery_dimensions": dimension_changes,
            "transfer_assessments": [
                item.to_dict() for item in transfer_rows
            ],
            "capability": capability,
            "metacognitive_calibration": (
                MetacognitiveCalibrationService.report(user_id)
            ),
            "agent_run": run.to_dict(include_steps=True),
        }

    @staticmethod
    def list_user(user_id: int) -> list[dict]:
        exams = (
            AdaptiveExam.query.filter_by(user_id=user_id)
            .order_by(AdaptiveExam.created_at.desc(), AdaptiveExam.id.desc())
            .limit(30)
            .all()
        )
        return [exam.to_dict(include_quiz=False) for exam in exams]

    @classmethod
    def _build_blueprint(
        cls,
        *,
        points: list[KnowledgePoint],
        mastery_by_point: dict[int, UserKnowledgeMastery],
        duration_minutes: int,
        goal: str,
    ) -> dict:
        question_count = max(5, min(30, round(duration_minutes / 3)))
        ranked = []
        for point in points:
            mastery = mastery_by_point.get(point.id)
            score = float(mastery.mastery_score) if mastery else None
            confidence = float(mastery.confidence) if mastery else 0.0
            if score is None:
                weight = 2.0 if goal == "diagnosis" else 1.3
                state = "unknown"
            elif score < 60:
                weight = 4.5 if goal == "reinforcement" else 3.5
                state = "focus"
            elif score < 75:
                weight = 2.5
                state = "consolidate"
            else:
                weight = 1.0 if goal != "comprehensive" else 1.6
                state = "stable"
            if confidence < 0.35:
                weight += 0.8
            ranked.append((weight, point, mastery, state))
        ranked.sort(
            key=lambda item: (
                -item[0],
                float(item[2].mastery_score) if item[2] else -1,
                item[1].code,
                item[1].id,
            )
        )
        selected_limit = 1 if goal == "transfer" else min(
            question_count,
            8,
            len(ranked),
        )
        selected = ranked[:selected_limit]
        allocations = {point.id: 1 for _, point, _, _ in selected}
        remaining = question_count - len(selected)
        weighted_cycle = sorted(
            selected,
            key=lambda item: (-item[0], item[1].id),
        )
        index = 0
        while remaining > 0 and weighted_cycle:
            _, point, _, _ = weighted_cycle[index % len(weighted_cycle)]
            allocations[point.id] += 1
            remaining -= 1
            index += 1

        payload = []
        for weight, point, mastery, state in selected:
            score = (
                round(float(mastery.mastery_score), 2) if mastery else None
            )
            confidence = (
                round(float(mastery.confidence), 4) if mastery else 0.0
            )
            payload.append({
                "knowledge_point_id": point.id,
                "code": point.code,
                "name": point.name,
                "state": state,
                "mastery_score": score,
                "confidence": confidence,
                "question_count": allocations[point.id],
                "weight": round(weight, 2),
                "reason": cls._allocation_reason(
                    point.name,
                    state,
                    score,
                    confidence,
                    goal,
                    allocations[point.id],
                ),
            })
        return {
            "duration_minutes": duration_minutes,
            "goal": goal,
            "question_count": question_count,
            "strategy": "掌握度越低、置信度越低，题目权重越高；同时保留课程覆盖",
            "allocations": payload,
        }

    @classmethod
    def _generate_grounded_quiz(
        cls,
        *,
        user_id: int,
        profile: Profile,
        blueprint: dict,
        difficulty: str,
    ) -> tuple[dict, int]:
        questions = []
        source_ids = set()
        question_id = 1
        for allocation in blueprint["allocations"]:
            point = db.session.get(
                KnowledgePoint,
                allocation["knowledge_point_id"],
            )
            chunks = cls._point_chunks(user_id, point)
            source_ids.update(chunk.id for chunk in chunks)
            for local_index in range(allocation["question_count"]):
                chunk = chunks[local_index % len(chunks)] if chunks else None
                excerpt = cls._excerpt(
                    chunk.chunk_text if chunk else point.description,
                    point.name,
                )
                distractors = [
                    f"只需记住“{point.name}”的名称，不必理解适用条件",
                    f"“{point.name}”与本课程其他知识点没有任何联系",
                    f"学习“{point.name}”不需要课程材料或练习验证",
                ]
                correct_index = (question_id + point.id) % 4
                options = distractors[:]
                options.insert(correct_index, excerpt)
                level = cls._transfer_level(
                    goal=blueprint["goal"],
                    local_index=local_index,
                )
                dimension = {
                    "L1": "conceptual_understanding",
                    "L2": "procedural_application",
                    "L3": "transfer",
                }[level]
                question_prompt = {
                    "L1": (
                        f"【L1 原型题】以下关于“{point.name}”的描述，"
                        "哪一项最符合已导入课程材料？"
                    ),
                    "L2": (
                        f"【L2 变式题】同学把“{point.name}”换成了不同表述，"
                        "哪一项仍保留课程材料中的核心含义与适用条件？"
                    ),
                    "L3": (
                        f"【L3 迁移题】在课程材料没有直接给出答案的新项目中，"
                        f"需要判断如何使用“{point.name}”。"
                        "哪一项课程原理最适合作为决策依据？"
                    ),
                }[level]
                answer_letter = chr(65 + correct_index)
                questions.append({
                    "id": question_id,
                    "type": "single_choice",
                    "concept": point.name,
                    "prompt": question_prompt,
                    "options": options,
                    "answer": answer_letter,
                    "explanation": (
                        f"正确描述来自当前用户课程资料"
                        f"{f'片段 #{chunk.id}' if chunk else '中的知识点说明'}："
                        f"{excerpt}"
                    ),
                    "hint": "回忆课程材料中的定义、作用或适用条件。",
                    "primary_knowledge_point_id": point.id,
                    "knowledge_point_mapping_status": "mapped",
                    "knowledge_point_mapping_method": "adaptive_blueprint",
                    "knowledge_point": {
                        "id": point.id,
                        "code": point.code,
                        "name": point.name,
                        "chapter_id": point.chapter_id,
                    },
                    "source_chunk_id": chunk.id if chunk else None,
                    "transfer_level": level,
                    "cognitive_level": {
                        "L1": "prototype",
                        "L2": "variation",
                        "L3": "transfer",
                    }[level],
                    "cognitive_dimension": dimension,
                    "scenario_type": {
                        "L1": "prototype_recall",
                        "L2": "rephrased_variation",
                        "L3": "new_context_transfer",
                    }[level],
                    "expected_steps": [
                        {
                            "step_id": 1,
                            "knowledge_point_id": point.id,
                            "concept": f"识别“{point.name}”",
                            "expected": f"明确本题考查知识点“{point.name}”",
                            "keywords": [point.name],
                        },
                        {
                            "step_id": 2,
                            "knowledge_point_id": point.id,
                            "concept": f"提取“{point.name}”的课程证据",
                            "expected": excerpt,
                            "keywords": cls._reasoning_keywords(
                                point.name,
                                excerpt,
                            ),
                            "depends_on": 1,
                        },
                        {
                            "step_id": 3,
                            "knowledge_point_id": point.id,
                            "concept": "比较选项并形成结论",
                            "expected": f"选择 {answer_letter}",
                            "keywords": [answer_letter],
                            "depends_on": 2,
                            "is_final_answer": True,
                        },
                    ],
                })
                question_id += 1
        return {
            "title": f"{profile.topic} 掌握度自适应测评",
            "difficulty": difficulty,
            "focus": blueprint["goal"],
            "questions": questions,
        }, len(source_ids)

    @staticmethod
    def _point_chunks(
        user_id: int,
        point: KnowledgePoint,
    ) -> list[KnowledgeChunk]:
        base = KnowledgeChunk.query.join(KnowledgeDocument).filter(
            KnowledgeDocument.user_id == user_id
        )
        chunks = (
            base.filter(KnowledgeChunk.knowledge_point_id == point.id)
            .order_by(KnowledgeChunk.chunk_index)
            .limit(4)
            .all()
        )
        if not chunks:
            chunks = (
                base.filter(KnowledgeChunk.chapter_id == point.chapter_id)
                .order_by(KnowledgeChunk.chunk_index)
                .limit(4)
                .all()
            )
        if not chunks:
            chunks = (
                base.filter(KnowledgeChunk.course_id == point.course_id)
                .order_by(KnowledgeChunk.chunk_index)
                .limit(4)
                .all()
            )
        return chunks

    @staticmethod
    def _excerpt(text: str, fallback: str) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        if not normalized:
            return f"“{fallback}”需要结合课程目标理解其定义、作用和应用条件"
        sentence = re.split(r"[。！？；\n]", normalized, maxsplit=1)[0].strip()
        return sentence[:120] or normalized[:120]

    @staticmethod
    def _reasoning_keywords(point_name: str, excerpt: str) -> list[str]:
        tokens = re.findall(
            r"[A-Za-z0-9_()+*-]+|[\u4e00-\u9fff]{2,6}",
            excerpt,
        )
        return list(dict.fromkeys([point_name, *tokens]))[:5]

    @staticmethod
    def _transfer_level(*, goal: str, local_index: int) -> str:
        if goal == "transfer":
            return ("L1", "L2", "L3", "L2", "L3")[local_index % 5]
        return ("L1", "L2", "L1", "L2", "L3")[local_index % 5]

    @staticmethod
    def _allocation_reason(
        name: str,
        state: str,
        score: float | None,
        confidence: float,
        goal: str,
        count: int,
    ) -> str:
        score_text = "尚未测评" if score is None else f"掌握度 {score}%"
        return (
            f"“{name}”{score_text}、置信度 {round(confidence * 100)}%，"
            f"在 {goal} 目标下分配 {count} 道题（状态：{state}）"
        )

    @staticmethod
    def _build_report(
        *,
        exam: AdaptiveExam,
        result_data: dict,
        post_mastery: dict[str, float],
    ) -> dict:
        breakdown: dict[int, dict] = {}
        for detail in result_data["details"]:
            point_id = int(detail.get("primary_knowledge_point_id") or 0)
            if not point_id:
                continue
            item = breakdown.setdefault(
                point_id,
                {"question_count": 0, "correct_count": 0, "partial_count": 0},
            )
            item["question_count"] += 1
            if detail["status"] == "correct":
                item["correct_count"] += 1
            elif detail["status"] == "partial":
                item["partial_count"] += 1
        rows = []
        for allocation in (exam.blueprint_json or {}).get("allocations", []):
            point_id = allocation["knowledge_point_id"]
            stats = breakdown.get(
                point_id,
                {"question_count": 0, "correct_count": 0, "partial_count": 0},
            )
            before = (exam.pre_mastery_json or {}).get(str(point_id))
            after = post_mastery.get(str(point_id))
            rows.append({
                "knowledge_point_id": point_id,
                "knowledge_point": allocation["name"],
                "question_count": stats["question_count"],
                "correct_count": stats["correct_count"],
                "partial_count": stats["partial_count"],
                "accuracy": (
                    round(
                        (
                            stats["correct_count"]
                            + stats["partial_count"] * 0.5
                        )
                        / stats["question_count"]
                        * 100,
                        2,
                    )
                    if stats["question_count"]
                    else 0.0
                ),
                "mastery_before": before,
                "mastery_after": after,
                "mastery_delta": (
                    round(after - before, 2)
                    if after is not None and before is not None
                    else None
                ),
            })
        return {
            "score": result_data["score"],
            "summary": result_data["summary"],
            "knowledge_point_breakdown": rows,
        }

    @staticmethod
    def _completed_payload(exam: AdaptiveExam) -> dict:
        answers = dict(exam.result.answers or {}) if exam.result else {}
        return {
            "exam": exam.to_dict(include_quiz=False),
            "result": {
                "score": exam.result.score if exam.result else 0,
                "details": answers.get("details", []),
                "summary": exam.result.analysis if exam.result else "",
            },
            "record": exam.result.to_dict() if exam.result else None,
            "mastery_changes": answers.get("mastery_changes", []),
            "replanning": answers.get("replanning", {}),
            "report": answers.get("adaptive_report", {}),
            "cognitive_diagnoses": answers.get(
                "cognitive_diagnoses",
                [],
            ),
            "misconceptions": answers.get("misconceptions", []),
            "teaching_strategy": answers.get("teaching_strategy"),
            "intervention": answers.get("intervention", {}),
            "observed_intervention_effects": answers.get(
                "observed_intervention_effects",
                [],
            ),
            "mastery_dimensions": answers.get("mastery_dimensions", []),
            "transfer_assessments": answers.get(
                "transfer_assessments",
                [],
            ),
            "capability": answers.get("capability", {}),
            "metacognitive_calibration": answers.get(
                "metacognitive_calibration",
                {},
            ),
            "agent_run": (
                exam.agent_run.to_dict(include_steps=True)
                if exam.agent_run
                else None
            ),
            "idempotent": True,
        }
