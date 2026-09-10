from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models import (
    AdaptiveExam,
    CognitiveDiagnosis,
    CognitiveStep,
    Course,
    LearningEvent,
    LearningPathVersion,
    MasteryDimension,
    MisconceptionEvidence,
    Profile,
    QuizResult,
    TeachingIntervention,
    TeachingStrategyStat,
    TransferAssessment,
    User,
    UserKnowledgeMastery,
    UserMisconception,
)
from app.services.cognitive_process_service import ErrorPropagationService
from app.services.intervention_service import (
    LearningInterventionService,
    TeachingEffectService,
)
from app.services.misconception_service import MisconceptionService
from app.services.teaching_strategy_service import TeachingStrategyEngine
from app.services.transfer_service import (
    CapabilityGateService,
    MasteryDimensionService,
    MetacognitiveCalibrationService,
    TransferAssessmentService,
)
from test_adaptive_learning_loop import _build_domain, _headers


def _record(user_id: int, *, score: float = 0) -> QuizResult:
    row = QuizResult(
        user_id=user_id,
        quiz_content="P2 test",
        answers={"submitted": {"1": "A"}},
        score=score,
        wrong_questions="",
        analysis="",
        category="evaluation",
    )
    db.session.add(row)
    db.session.flush()
    return row


def _diagnosis(
    domain: dict,
    *,
    record: QuizResult,
    status: str = "root_error",
    error_type: str = "concept_or_process_mismatch",
) -> CognitiveDiagnosis:
    diagnosis = CognitiveDiagnosis(
        user_id=domain["user_id"],
        assessment_id=record.id,
        question_id=f"q-{record.id}",
        knowledge_point_id=domain["point_a_id"],
        first_error_step=2 if status == "root_error" else None,
        root_cause_knowledge_point_id=(
            domain["point_a_id"] if status == "root_error" else None
        ),
        overall_status=status,
        confidence=0.82,
        summary="test",
        propagation_json={},
    )
    db.session.add(diagnosis)
    db.session.flush()
    if status == "root_error":
        db.session.add(CognitiveStep(
            diagnosis_id=diagnosis.id,
            step_index=2,
            knowledge_point_id=domain["point_a_id"],
            concept="监督学习的课程证据",
            expected_text="监督学习使用带标签的数据",
            student_text="监督学习不需要标签",
            status="incorrect",
            error_role="root_error",
            error_type=error_type,
            confidence=0.82,
            evidence_json=[],
            course_sources_json=[],
        ))
    db.session.flush()
    return diagnosis


def _create_exam(domain: dict, goal: str = "diagnosis") -> dict:
    response = domain["client"].post(
        "/api/adaptive-exams",
        headers=_headers(domain["token"]),
        json={
            "duration_minutes": 15,
            "goal": goal,
            "difficulty": "intermediate",
        },
    )
    assert response.status_code == 201
    return response.get_json()["exam"]


def _wrong_submission(exam: dict) -> tuple[dict, dict, dict]:
    answers = {}
    reasoning = {}
    confidence = {}
    for question in exam["quiz"]["questions"]:
        correct = question["answer"]
        answers[str(question["id"])] = (
            "B" if correct == "A" else "A"
        )
        reasoning[str(question["id"])] = (
            f"{question['concept']}\n忽略课程条件\n选择 {answers[str(question['id'])]}"
        )
        confidence[str(question["id"])] = 100
    return answers, reasoning, confidence


def test_first_error_step_is_located_from_observed_process():
    steps = [
        {"step_index": 1, "status": "correct", "concept": "识别概念"},
        {
            "step_index": 2,
            "status": "incorrect",
            "concept": "提取条件",
            "depends_on": 1,
        },
        {
            "step_index": 3,
            "status": "incorrect",
            "concept": "形成结论",
            "depends_on": 2,
        },
    ]
    result = ErrorPropagationService.classify(steps)
    assert result["root_error"]["step_index"] == 2
    assert steps[1]["error_role"] == "root_error"


def test_error_propagation_distinguishes_derived_and_independent_errors():
    steps = [
        {"step_index": 1, "status": "incorrect", "concept": "概念", "depends_on": 0},
        {"step_index": 2, "status": "incorrect", "concept": "应用", "depends_on": 1},
        {"step_index": 3, "status": "correct", "concept": "检查", "depends_on": 2},
        {"step_index": 4, "status": "incorrect", "concept": "计算", "depends_on": 1},
    ]
    result = ErrorPropagationService.classify(steps)
    assert result["derived_error_count"] == 1
    assert result["independent_error_count"] == 1
    assert steps[1]["error_role"] == "derived_error"
    assert steps[3]["error_role"] == "independent_error"


def test_repeated_real_evidence_confirms_a_misconception():
    domain = _build_domain()
    with domain["app"].app_context():
        first = _diagnosis(domain, record=_record(domain["user_id"]))
        first_rows = MisconceptionService.apply_diagnoses(
            user_id=domain["user_id"],
            diagnoses=[first],
        )
        assert first_rows[0].status == "suspected"
        second = _diagnosis(domain, record=_record(domain["user_id"]))
        second_rows = MisconceptionService.apply_diagnoses(
            user_id=domain["user_id"],
            diagnoses=[second],
        )
        assert second_rows[0].status == "confirmed"
        assert second_rows[0].evidence_count == 2
        assert MisconceptionEvidence.query.count() == 2


def test_misconception_moves_from_confirmed_to_improving_then_resolved():
    domain = _build_domain()
    with domain["app"].app_context():
        for _ in range(2):
            diagnosis = _diagnosis(
                domain,
                record=_record(domain["user_id"]),
            )
            MisconceptionService.apply_diagnoses(
                user_id=domain["user_id"],
                diagnoses=[diagnosis],
            )
        correct_record = _record(domain["user_id"], score=100)
        correct = _diagnosis(
            domain,
            record=correct_record,
            status="no_error",
        )
        MisconceptionService.apply_diagnoses(
            user_id=domain["user_id"],
            diagnoses=[correct],
        )
        row = UserMisconception.query.one()
        assert row.status == "improving"
        MisconceptionService.resolve_after_transfer(
            user_id=domain["user_id"],
            knowledge_point_id=domain["point_a_id"],
            assessment_id=correct_record.id,
            passed=True,
            confidence=0.8,
        )
        assert row.status == "resolved"


def test_strategy_selection_uses_prerequisite_and_mastery_evidence():
    domain = _build_domain()
    with domain["app"].app_context():
        profile = db.session.get(Profile, domain["profile_id"])
        decision = TeachingStrategyEngine.select(
            user_id=domain["user_id"],
            profile=profile,
            knowledge_point_id=domain["point_b_id"],
        )
        assert decision.strategy_type == "FOUNDATION_REBUILD"
        assert "weak_prerequisite" in decision.reason_codes_json


def test_strategy_switch_is_persisted_when_evidence_changes():
    domain = _build_domain()
    with domain["app"].app_context():
        profile = db.session.get(Profile, domain["profile_id"])
        first = TeachingStrategyEngine.select(
            user_id=domain["user_id"],
            profile=profile,
            knowledge_point_id=domain["point_b_id"],
        )
        db.session.add_all([
            UserKnowledgeMastery(
                user_id=domain["user_id"],
                knowledge_point_id=domain["point_a_id"],
                mastery_score=85,
                confidence=0.8,
            ),
            UserKnowledgeMastery(
                user_id=domain["user_id"],
                knowledge_point_id=domain["point_b_id"],
                mastery_score=75,
                confidence=0.8,
            ),
            MasteryDimension(
                user_id=domain["user_id"],
                knowledge_point_id=domain["point_b_id"],
                dimension="transfer",
                mastery_score=20,
                confidence=0.5,
                evidence_count=2,
            ),
        ])
        db.session.flush()
        second = TeachingStrategyEngine.select(
            user_id=domain["user_id"],
            profile=profile,
            knowledge_point_id=domain["point_b_id"],
        )
        assert first.strategy_type == "FOUNDATION_REBUILD"
        assert second.strategy_type == "TRANSFER_TRAINING"
        assert second.switched is True


def test_three_consecutive_wrong_events_meet_learning_block_threshold():
    domain = _build_domain()
    with domain["app"].app_context():
        for index in range(3):
            db.session.add(LearningEvent(
                user_id=domain["user_id"],
                event_key=f"wrong-{index}",
                event_type="question_wrong",
                knowledge_point_id=domain["point_a_id"],
                source_type="test",
                source_id=str(index),
                value_json={},
            ))
        db.session.flush()
        assert LearningInterventionService._consecutive_wrong_count(
            domain["user_id"],
            domain["point_a_id"],
        ) == 3


def test_learning_block_creates_persisted_intervention_and_path_version():
    domain = _build_domain()
    exam = _create_exam(domain)
    answers, reasoning, confidence = _wrong_submission(exam)
    response = domain["client"].post(
        f"/api/adaptive-exams/{exam['id']}/submit",
        headers=_headers(domain["token"]),
        json={
            "answers": answers,
            "reasoning_steps": reasoning,
            "self_confidence": confidence,
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["intervention"]["triggered"] is True
    with domain["app"].app_context():
        row = TeachingIntervention.query.filter_by(
            user_id=domain["user_id"],
        ).one()
        assert row.status == "active"
        assert row.path_version_id is not None
        assert db.session.get(LearningPathVersion, row.path_version_id)


def test_observed_teaching_effect_is_persisted_without_causal_claim():
    domain = _build_domain()
    with domain["app"].app_context():
        before = _record(domain["user_id"], score=40)
        after = _record(domain["user_id"], score=80)
        mastery = UserKnowledgeMastery(
            user_id=domain["user_id"],
            knowledge_point_id=domain["point_a_id"],
            mastery_score=75,
            confidence=0.7,
        )
        intervention = TeachingIntervention(
            user_id=domain["user_id"],
            knowledge_point_id=domain["point_a_id"],
            strategy_type="WORKED_EXAMPLE",
            block_type="PROCESS_ERROR",
            status="active",
            assessment_before=before.id,
            mastery_before=50,
            confidence_before=0.4,
        )
        db.session.add_all([mastery, intervention])
        db.session.flush()
        rows = TeachingEffectService.observe_after_assessment(
            user_id=domain["user_id"],
            record=after,
            mastery_changes=[{
                "knowledge_point_id": domain["point_a_id"],
                "delta": 25,
            }],
        )
        assert rows[0].status == "completed"
        assert rows[0].observed_gain == 25
        assert "观察到" in rows[0].to_dict()["effect_statement"]
        assert "导致" not in rows[0].to_dict()["effect_statement"]


def test_strategy_history_requires_three_completed_effect_records():
    domain = _build_domain()
    with domain["app"].app_context():
        for gain in (5, 7):
            db.session.add(TeachingIntervention(
                user_id=domain["user_id"],
                knowledge_point_id=domain["point_a_id"],
                strategy_type="WORKED_EXAMPLE",
                block_type="PROCESS_ERROR",
                status="completed",
                observed_gain=gain,
            ))
        db.session.flush()
        TeachingEffectService._refresh_strategy_stat(
            domain["user_id"],
            "WORKED_EXAMPLE",
        )
        assert TeachingStrategyEngine._historical_preference(
            domain["user_id"]
        ) is None
        db.session.add(TeachingIntervention(
            user_id=domain["user_id"],
            knowledge_point_id=domain["point_a_id"],
            strategy_type="WORKED_EXAMPLE",
            block_type="PROCESS_ERROR",
            status="completed",
            observed_gain=6,
        ))
        db.session.flush()
        TeachingEffectService._refresh_strategy_stat(
            domain["user_id"],
            "WORKED_EXAMPLE",
        )
        stat = TeachingStrategyStat.query.one()
        assert stat.completed_count == 3
        assert TeachingStrategyEngine._historical_preference(
            domain["user_id"]
        ) == "WORKED_EXAMPLE"


def test_transfer_exam_contains_prototype_variation_and_transfer_levels():
    domain = _build_domain()
    exam = _create_exam(domain, goal="transfer")
    levels = {
        question["transfer_level"]
        for question in exam["quiz"]["questions"]
    }
    assert levels == {"L1", "L2", "L3"}
    assert len(exam["blueprint"]["allocations"]) == 1


def test_multidimensional_mastery_keeps_missing_dimensions_unknown():
    domain = _build_domain()
    with domain["app"].app_context():
        record = _record(domain["user_id"], score=100)
        MasteryDimensionService.apply_assessment(
            user_id=domain["user_id"],
            record=record,
            quiz={"questions": [{
                "id": 1,
                "primary_knowledge_point_id": domain["point_a_id"],
                "transfer_level": "L1",
                "cognitive_dimension": "conceptual_understanding",
            }]},
            details=[{"id": 1, "score_fraction": 1.0}],
        )
        dimensions = MasteryDimensionService.get_dimensions(
            domain["user_id"],
            domain["point_a_id"],
        )
        assert dimensions["conceptual_understanding"]["evidence_count"] == 1
        assert dimensions["coding"]["state"] == "unknown"
        assert dimensions["coding"]["mastery_score"] is None


def test_capability_gate_blocks_advanced_learning_without_evidence():
    domain = _build_domain()
    with domain["app"].app_context():
        capability = CapabilityGateService.evaluate(
            user_id=domain["user_id"],
            knowledge_point_id=domain["point_a_id"],
        )
        assert capability["capability_state"] == "FOUNDATION_GAP"
        assert capability["advanced_gate_passed"] is False
        assert capability["gaps"]


def test_self_confidence_requires_repeated_calibration_evidence():
    domain = _build_domain()
    with domain["app"].app_context():
        record = _record(domain["user_id"], score=0)
        quiz = {"questions": [
            {"id": 1, "primary_knowledge_point_id": domain["point_a_id"]},
            {"id": 2, "primary_knowledge_point_id": domain["point_a_id"]},
        ]}
        details = [
            {"id": 1, "score_fraction": 0.0},
            {"id": 2, "score_fraction": 0.0},
        ]
        MetacognitiveCalibrationService.record_submission(
            user_id=domain["user_id"],
            record=record,
            quiz=quiz,
            details=details,
            self_confidence={"1": 100, "2": 100},
        )
        report = MetacognitiveCalibrationService.report(domain["user_id"])
        assert report["record_count"] == 2
        assert report["state"] == "OVERCONFIDENT"


def test_cognitive_diagnosis_endpoint_is_isolated_by_user():
    domain = _build_domain()
    with domain["app"].app_context():
        record = _record(domain["user_id"])
        _diagnosis(domain, record=record)
        stranger = User(username="p2-stranger", role="student", email="")
        stranger.set_password("test")
        db.session.add(stranger)
        db.session.flush()
        db.session.add(Profile(user_id=stranger.id, topic="其他课程"))
        db.session.commit()
        stranger_token = create_access_token(identity=str(stranger.id))
        record_id = record.id
    response = domain["client"].get(
        f"/api/cognitive-diagnoses/{record_id}",
        headers=_headers(stranger_token),
    )
    assert response.status_code == 404


def test_transfer_result_persists_level_scores_and_pass_state():
    domain = _build_domain()
    exam_payload = _create_exam(domain, goal="transfer")
    with domain["app"].app_context():
        exam = db.session.get(AdaptiveExam, exam_payload["id"])
        record = _record(domain["user_id"], score=100)
        questions = exam.quiz_json["questions"]
        details = [
            {
                "id": question["id"],
                "score_fraction": 1.0,
            }
            for question in questions
        ]
        rows = TransferAssessmentService.record_result(
            user_id=domain["user_id"],
            exam=exam,
            record=record,
            quiz=exam.quiz_json,
            details=details,
        )
        assert rows[0].passed is True
        assert all(
            rows[0].levels_json[level]["score"] == 100
            for level in ("L1", "L2", "L3")
        )
        assert TransferAssessment.query.count() == 1


def test_p2_submission_artifacts_are_replayable_and_queryable():
    domain = _build_domain()
    exam = _create_exam(domain)
    answers, reasoning, confidence = _wrong_submission(exam)
    submitted = domain["client"].post(
        f"/api/adaptive-exams/{exam['id']}/submit",
        headers=_headers(domain["token"]),
        json={
            "answers": answers,
            "reasoning_steps": reasoning,
            "self_confidence": confidence,
        },
    )
    assert submitted.status_code == 200
    payload = submitted.get_json()
    assessment_id = payload["record"]["id"]
    replay = domain["client"].post(
        f"/api/adaptive-exams/{exam['id']}/submit",
        headers=_headers(domain["token"]),
        json={"answers": answers},
    )
    assert replay.get_json()["idempotent"] is True
    diagnosis = domain["client"].get(
        f"/api/cognitive-diagnoses/{assessment_id}",
        headers=_headers(domain["token"]),
    ).get_json()
    assert diagnosis["diagnoses"]
    assert domain["client"].get(
        "/api/misconceptions",
        headers=_headers(domain["token"]),
    ).get_json()["misconceptions"]
    assert domain["client"].get(
        "/api/teaching-strategies/current",
        headers=_headers(domain["token"]),
    ).get_json()["strategy"]
