from flask_jwt_extended import create_access_token

from app import create_app
from app.config import Config
from app.extensions import db
from app.models import (
    Chapter,
    Course,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgePoint,
    KnowledgeRelation,
    LearningEvent,
    LearningPathVersion,
    MasteryEvidence,
    NodeResource,
    Profile,
    QuizResult,
    User,
    UserKnowledgeMastery,
)
from app.services.learning_event_service import LearningEventService
from app.services.mastery_service import MasteryService
from app.services.path_service import ReplanningService, StructuredPathService
from app.services.question_mapping import map_quiz_questions


class AdaptiveTestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    DASHSCOPE_API_KEY = ""
    MIMO_API_KEY = ""


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _build_domain():
    app = create_app(AdaptiveTestConfig)
    with app.app_context():
        user = User(username="adaptive-owner", role="student", email="")
        user.set_password("test")
        db.session.add(user)
        db.session.flush()
        profile = Profile(
            user_id=user.id,
            topic="人工智能导论",
            learning_goal="掌握课程核心概念",
            weekly_time_minutes=300,
        )
        course = Course(code="AI-INTRO", title="人工智能导论", status="partial")
        db.session.add_all([profile, course])
        db.session.flush()
        chapter = Chapter(
            course_id=course.id,
            title="机器学习基础",
            chapter_order=1,
        )
        db.session.add(chapter)
        db.session.flush()
        point_a = KnowledgePoint(
            course_id=course.id,
            chapter_id=chapter.id,
            code="KP-001",
            name="监督学习",
            aliases_json=["有监督学习"],
        )
        point_b = KnowledgePoint(
            course_id=course.id,
            chapter_id=chapter.id,
            code="KP-002",
            name="损失函数",
        )
        db.session.add_all([point_a, point_b])
        db.session.flush()
        db.session.add(KnowledgeRelation(
            course_id=course.id,
            source_knowledge_point_id=point_a.id,
            target_knowledge_point_id=point_b.id,
            relation_type="prerequisite",
        ))
        document = KnowledgeDocument(
            user_id=user.id,
            course_id=course.id,
            chapter_id=chapter.id,
            title="人工智能导论课程材料",
            source_filename="ai-intro.pdf",
            page_count=12,
            content_hash="adaptive-doc",
            content="监督学习和损失函数课程正文",
        )
        db.session.add(document)
        db.session.flush()
        db.session.add_all([
            KnowledgeChunk(
                document_id=document.id,
                course_id=course.id,
                chapter_id=chapter.id,
                knowledge_point_id=point_a.id,
                chunk_index=0,
                page_start=2,
                page_end=2,
                section="监督学习",
                chunk_text="监督学习使用带标签的数据训练模型。",
                content_hash="adaptive-chunk-a",
            ),
            KnowledgeChunk(
                document_id=document.id,
                course_id=course.id,
                chapter_id=chapter.id,
                knowledge_point_id=point_b.id,
                chunk_index=1,
                page_start=3,
                page_end=3,
                section="损失函数",
                chunk_text="损失函数用于衡量预测值与真实值之间的差异。",
                content_hash="adaptive-chunk-b",
            ),
        ])
        db.session.commit()
        token = create_access_token(identity=str(user.id))
        return {
            "app": app,
            "client": app.test_client(),
            "token": token,
            "user_id": user.id,
            "profile_id": profile.id,
            "point_a_id": point_a.id,
            "point_b_id": point_b.id,
        }


def test_question_mapping_only_accepts_real_knowledge_points():
    domain = _build_domain()
    with domain["app"].app_context():
        points = KnowledgePoint.query.order_by(KnowledgePoint.id).all()
        quiz = {
            "questions": [
                {
                    "id": "q1",
                    "concept": "有监督学习",
                    "primary_knowledge_point_id": domain["point_a_id"],
                },
                {
                    "id": "q2",
                    "concept": "课程中不存在的量子魔法",
                    "primary_knowledge_point_id": 999999,
                },
            ],
        }
        mapped, coverage = map_quiz_questions(quiz, points)

        assert mapped["questions"][0]["knowledge_point_mapping_status"] == "mapped"
        assert mapped["questions"][0]["primary_knowledge_point_id"] == domain["point_a_id"]
        assert mapped["questions"][1]["knowledge_point_mapping_status"] == "unmapped"
        assert mapped["questions"][1]["primary_knowledge_point_id"] is None
        assert coverage == {"total": 2, "mapped": 1, "unmapped": 1, "coverage": 0.5}


def test_assessment_mastery_replanning_and_replay_form_a_closed_loop():
    domain = _build_domain()
    with domain["app"].app_context():
        profile = db.session.get(Profile, domain["profile_id"])
        path, version_one = StructuredPathService.create_version(
            profile=profile,
            legacy_content="初始路径",
        )
        assert [node.knowledge_point_id for node in version_one.nodes] == [
            domain["point_a_id"],
            domain["point_b_id"],
        ]
        assert NodeResource.query.count() == 2

        quiz = {
            "title": "闭环测评",
            "questions": [
                {
                    "id": "q1",
                    "type": "single_choice",
                    "prompt": "监督学习使用什么数据？",
                    "answer": "A",
                    "concept": "监督学习",
                    "primary_knowledge_point_id": domain["point_a_id"],
                },
            ],
        }
        quiz, _ = map_quiz_questions(
            quiz,
            KnowledgePoint.query.order_by(KnowledgePoint.id).all(),
        )
        details = [{
            "id": "q1",
            "status": "wrong",
            "is_correct": False,
            "concept": "监督学习",
            "user_answer": "B",
            "reference_answer": "A",
        }]
        record = QuizResult(
            user_id=domain["user_id"],
            quiz_content="闭环测评",
            answers={"quiz": quiz, "details": details, "completed": True},
            score=0,
            wrong_questions="监督学习",
            analysis="需要补救学习",
            category="exercise",
        )
        db.session.add(record)
        db.session.flush()

        events, coverage = LearningEventService.record_assessment_events(
            user_id=domain["user_id"],
            record=record,
            quiz=quiz,
            details=details,
        )
        changes = MasteryService.grouped_changes(MasteryService.apply_events(events))
        replanning = ReplanningService.maybe_replan(
            profile=profile,
            mastery_changes=changes,
            assessment_id=record.id,
        )
        db.session.commit()

        mastery = UserKnowledgeMastery.query.filter_by(
            user_id=domain["user_id"],
            knowledge_point_id=domain["point_a_id"],
        ).one()
        assert coverage["coverage"] == 1.0
        assert round(mastery.mastery_score, 2) == 33.33
        failed_score = float(mastery.mastery_score)
        assert mastery.attempt_count == 1
        assert replanning["triggered"] is True
        assert LearningPathVersion.query.filter_by(path_id=path.id).count() == 2
        assert len(version_one.nodes) == 2
        assert any(
            node["node_type"] == "remediation"
            for node in replanning["version"]["nodes"]
        )
        assert replanning["diff"]["added_nodes"]

        original_event_count = LearningEvent.query.count()
        repeated_events, _ = LearningEventService.record_assessment_events(
            user_id=domain["user_id"],
            record=record,
            quiz=quiz,
            details=details,
        )
        MasteryService.apply_events(repeated_events)
        repeated_replanning = ReplanningService.maybe_replan(
            profile=profile,
            mastery_changes=changes,
            assessment_id=record.id,
        )
        db.session.commit()
        assert LearningEvent.query.count() == original_event_count
        assert UserKnowledgeMastery.query.one().attempt_count == 1
        assert repeated_replanning["idempotent"] is True

        second_record = QuizResult(
            user_id=domain["user_id"],
            quiz_content="补救后复测",
            answers={"quiz": quiz, "completed": True},
            score=100,
            wrong_questions="",
            analysis="复测通过",
            category="exercise",
        )
        db.session.add(second_record)
        db.session.flush()
        correct_details = [{
            "id": "q1",
            "status": "correct",
            "is_correct": True,
            "concept": "监督学习",
            "user_answer": "A",
            "reference_answer": "A",
        }]
        correct_events, _ = LearningEventService.record_assessment_events(
            user_id=domain["user_id"],
            record=second_record,
            quiz=quiz,
            details=correct_details,
        )
        correct_changes = MasteryService.grouped_changes(
            MasteryService.apply_events(correct_events),
        )
        no_replan = ReplanningService.maybe_replan(
            profile=profile,
            mastery_changes=correct_changes,
            assessment_id=second_record.id,
        )
        db.session.commit()
        improved_score = UserKnowledgeMastery.query.one().mastery_score
        assert improved_score > failed_score
        assert no_replan["triggered"] is False

        score_before_replay = improved_score
        replay_changes = MasteryService.replay_user(domain["user_id"])
        db.session.commit()
        assert replay_changes
        assert UserKnowledgeMastery.query.one().mastery_score == score_before_replay
        assert MasteryEvidence.query.count() == 2


def test_adaptive_path_and_mastery_apis_return_persisted_state():
    domain = _build_domain()
    with domain["app"].app_context():
        profile = db.session.get(Profile, domain["profile_id"])
        _, version = StructuredPathService.create_version(
            profile=profile,
            legacy_content="初始路径",
        )
        node_id = version.nodes[0].id
        db.session.commit()

    latest = domain["client"].get(
        "/api/path/latest",
        headers=_headers(domain["token"]),
    )
    assert latest.status_code == 200
    assert latest.get_json()["version"]["version_number"] == 1
    assert latest.get_json()["version"]["nodes"][0]["resources"]

    opened = domain["client"].post(
        f"/api/path/nodes/{node_id}/open",
        headers=_headers(domain["token"]),
    )
    assert opened.status_code == 200
    assert opened.get_json()["node"]["status"] == "learning"

    completed = domain["client"].post(
        f"/api/path/nodes/{node_id}/complete",
        headers=_headers(domain["token"]),
    )
    assert completed.status_code == 200
    assert completed.get_json()["node"]["status"] == "completed"
    assert completed.get_json()["mastery_changes"]

    mastery = domain["client"].get(
        "/api/mastery?include_evidence=true",
        headers=_headers(domain["token"]),
    )
    assert mastery.status_code == 200
    mastery_payload = mastery.get_json()
    assert mastery_payload["summary"]["total_knowledge_points"] == 2
    assessed = next(
        item
        for item in mastery_payload["mastery"]
        if item["knowledge_point_id"] == domain["point_a_id"]
    )
    assert assessed["state"] == "insufficient_evidence"
    assert assessed["evidence"][0]["event_type"] == "resource_complete"


def test_path_resources_never_use_another_users_private_chunks():
    domain = _build_domain()
    with domain["app"].app_context():
        stranger = User(username="adaptive-stranger", role="student", email="")
        stranger.set_password("test")
        db.session.add(stranger)
        db.session.flush()
        stranger_profile = Profile(
            user_id=stranger.id,
            topic="人工智能导论",
            learning_goal="隔离测试",
        )
        db.session.add(stranger_profile)
        db.session.flush()

        _, version = StructuredPathService.create_version(
            profile=stranger_profile,
            legacy_content="无私有课程材料时只保留兼容内容",
        )
        db.session.commit()

        assert version.nodes == []
        assert NodeResource.query.count() == 0


def test_diagnosis_remediation_and_agent_trace_are_real_and_persisted():
    domain = _build_domain()
    headers = _headers(domain["token"])
    with domain["app"].app_context():
        wrong_event, _ = LearningEventService.record_event(
            user_id=domain["user_id"],
            event_type="question_wrong",
            event_key="diagnosis:point-b:wrong",
            knowledge_point_id=domain["point_b_id"],
            question_id="diagnosis-q1",
            source_type="test_assessment",
            source_id="diagnosis-test",
            value={"concept": "损失函数"},
        )
        MasteryService.apply_event(wrong_event)
        db.session.commit()

    diagnosis = domain["client"].get("/api/diagnosis", headers=headers)
    assert diagnosis.status_code == 200
    payload = diagnosis.get_json()["diagnosis"]
    assert payload["overall"]["knowledge_point_count"] == 2
    assert payload["overall"]["unknown_count"] == 1
    assert payload["overall"]["focus_count"] == 1
    assert payload["recommended_target"]["knowledge_point_id"] == domain["point_b_id"]
    assert payload["recommended_target"]["mastery_score"] == 33.33

    target_id = domain["point_b_id"]
    created = domain["client"].post(
        "/api/remediation-plans",
        headers=headers,
        json={"knowledge_point_id": target_id},
    )
    assert created.status_code == 201
    result = created.get_json()
    plan = result["plan"]
    assert plan["target_knowledge_point_id"] == target_id
    assert plan["steps"]
    assert plan["steps"][-1]["step_type"] == "assessment"
    assert all(step["resource"] for step in plan["steps"])
    assert result["path_version"]["parent_version_id"] is not None
    assert result["diff"]["added_nodes"]

    trace = result["agent_run"]
    assert trace["status"] == "passed"
    assert [step["agent_name"] for step in trace["steps"]] == [
        "Diagnostician",
        "Planner",
        "Retriever",
        "Generator",
        "Verifier",
    ]
    assert trace["steps"][2]["evidence_count"] == 2
    assert trace["steps"][-1]["output"]["verified"] is True

    repeated = domain["client"].post(
        "/api/remediation-plans",
        headers=headers,
        json={"knowledge_point_id": target_id},
    )
    assert repeated.status_code == 200
    assert repeated.get_json()["reused"] is True
    assert repeated.get_json()["plan"]["id"] == plan["id"]

    started = domain["client"].post(
        f"/api/remediation-plans/{plan['id']}/start",
        headers=headers,
    )
    assert started.status_code == 200
    assert started.get_json()["plan"]["status"] == "active"
    assert started.get_json()["current_node"]["status"] == "learning"

    explanation = domain["client"].post(
        "/api/decision-explanations",
        headers=headers,
        json={
            "decision_type": "remediation",
            "knowledge_point_id": target_id,
        },
    )
    assert explanation.status_code == 200
    assert explanation.get_json()["explanation"]["reasons"]

    path_explanation = domain["client"].post(
        "/api/decision-explanations",
        headers=headers,
        json={
            "decision_type": "path_change",
            "path_version_id": result["path_version"]["id"],
        },
    )
    assert path_explanation.status_code == 200
    assert path_explanation.get_json()["explanation"]["diff"]["added_nodes"]

    resource_explanation = domain["client"].post(
        "/api/decision-explanations",
        headers=headers,
        json={
            "decision_type": "resource",
            "node_id": result["path_version"]["nodes"][0]["id"],
        },
    )
    assert resource_explanation.status_code == 200
    assert resource_explanation.get_json()["explanation"]["evidence"]


def test_adaptive_exam_blueprint_submission_growth_and_trace():
    domain = _build_domain()
    headers = _headers(domain["token"])

    created = domain["client"].post(
        "/api/adaptive-exams",
        headers=headers,
        json={
            "duration_minutes": 15,
            "goal": "reinforcement",
            "difficulty": "intermediate",
        },
    )
    assert created.status_code == 201
    payload = created.get_json()
    exam = payload["exam"]
    blueprint = exam["blueprint"]
    questions = exam["quiz"]["questions"]
    assert blueprint["question_count"] == 5
    assert sum(
        item["question_count"] for item in blueprint["allocations"]
    ) == 5
    assert len(questions) == 5
    actual_counts = {}
    for question in questions:
        point_id = question["primary_knowledge_point_id"]
        actual_counts[point_id] = actual_counts.get(point_id, 0) + 1
        assert question["source_chunk_id"] is not None
        assert question["knowledge_point_mapping_status"] == "mapped"
    assert actual_counts == {
        item["knowledge_point_id"]: item["question_count"]
        for item in blueprint["allocations"]
    }
    assert payload["agent_run"]["steps"][-1]["output"]["verified"] is True

    answers = {
        str(question["id"]): question["answer"]
        for question in questions
    }
    submitted = domain["client"].post(
        f"/api/adaptive-exams/{exam['id']}/submit",
        headers=headers,
        json={"answers": answers},
    )
    assert submitted.status_code == 200
    submitted_payload = submitted.get_json()
    assert submitted_payload["result"]["score"] == 100
    assert submitted_payload["mastery_changes"]
    assert submitted_payload["report"]["knowledge_point_breakdown"]
    assert any(
        step["agent_name"] == "MasteryUpdater"
        for step in submitted_payload["agent_run"]["steps"]
    )

    growth = domain["client"].get(
        "/api/growth-report?days=30",
        headers=headers,
    )
    assert growth.status_code == 200
    growth_payload = growth.get_json()["growth"]
    assert growth_payload["metrics"]["question_count"] == 5
    assert growth_payload["metrics"]["accuracy"] == 100
    assert growth_payload["knowledge_growth"]
    assert growth_payload["score_trend"][0]["result_id"] == (
        submitted_payload["record"]["id"]
    )


def test_new_decision_features_do_not_leak_cross_user_state():
    domain = _build_domain()
    owner_headers = _headers(domain["token"])
    created = domain["client"].post(
        "/api/adaptive-exams",
        headers=owner_headers,
        json={"duration_minutes": 15, "goal": "diagnosis"},
    )
    assert created.status_code == 201
    exam_id = created.get_json()["exam"]["id"]
    run_id = created.get_json()["agent_run"]["id"]

    with domain["app"].app_context():
        stranger = User(username="decision-stranger", role="student", email="")
        stranger.set_password("test")
        db.session.add(stranger)
        db.session.flush()
        db.session.add(Profile(
            user_id=stranger.id,
            topic="人工智能导论",
            learning_goal="隔离测试",
        ))
        db.session.commit()
        stranger_token = create_access_token(identity=str(stranger.id))
    stranger_headers = _headers(stranger_token)

    assert domain["client"].get(
        f"/api/adaptive-exams/{exam_id}",
        headers=stranger_headers,
    ).status_code == 404
    assert domain["client"].get(
        f"/api/agent-runs/{run_id}",
        headers=stranger_headers,
    ).status_code == 404
    assert domain["client"].get(
        "/api/remediation-plans",
        headers=stranger_headers,
    ).get_json()["plans"] == []
    stranger_diagnosis = domain["client"].get(
        "/api/diagnosis",
        headers=stranger_headers,
    ).get_json()["diagnosis"]
    assert stranger_diagnosis["closed_loop"]["evidence_events"] == 0
