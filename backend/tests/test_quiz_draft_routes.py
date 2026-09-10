from flask_jwt_extended import create_access_token

from app import create_app
from app.config import Config
from app.extensions import db
from app.models import QuizResult, User
from app.routes import learning


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    MIMO_API_KEY = ""


def build_client():
    app = create_app(TestConfig)
    with app.app_context():
        owner = User(username="draft-owner", role="student", email="")
        owner.set_password("test")
        stranger = User(username="draft-stranger", role="student", email="")
        stranger.set_password("test")
        db.session.add_all([owner, stranger])
        db.session.flush()

        quiz = {
            "title": "自动保存测试",
            "questions": [
                {
                    "id": 1,
                    "type": "single_choice",
                    "prompt": "单选题",
                    "options": ["选项 A", "选项 B"],
                    "answer": "A",
                    "concept": "单选知识点",
                    "explanation": "应选择 A。",
                },
                {
                    "id": 2,
                    "type": "multiple_choice",
                    "prompt": "多选题",
                    "options": ["选项 A", "选项 B", "选项 C"],
                    "answer": ["A", "B"],
                    "concept": "多选知识点",
                    "explanation": "应选择 A、B。",
                },
            ],
        }
        draft = QuizResult(
            user_id=owner.id,
            quiz_content="自动保存测试",
            answers={"quiz": quiz, "submitted": {}, "details": [], "completed": False},
            category="exercise",
        )
        completed = QuizResult(
            user_id=owner.id,
            quiz_content="已完成测试",
            answers={
                "quiz": quiz,
                "submitted": {"1": "A", "2": ["A", "B"]},
                "details": [{"id": 1, "status": "correct"}],
                "completed": True,
            },
            category="exercise",
        )
        db.session.add_all([draft, completed])
        db.session.commit()
        owner_token = create_access_token(identity=str(owner.id))
        stranger_token = create_access_token(identity=str(stranger.id))
        return (
            app.test_client(),
            owner_token,
            stranger_token,
            draft.id,
            completed.id,
        )


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_owner_can_autosave_and_reload_draft_answers():
    client, owner_token, _, draft_id, _ = build_client()
    response = client.patch(
        f"/api/quiz/{draft_id}/draft",
        headers=headers(owner_token),
        json={"answers": {"1": "B", "2": ["A", "C"], "unknown": "ignored"}},
    )
    assert response.status_code == 200
    payload = response.get_json()["record"]["answers"]
    assert payload["submitted"] == {"1": "B", "2": ["A", "C"]}
    assert payload["completed"] is False

    history = client.get(
        "/api/quiz/history?category=exercise",
        headers=headers(owner_token),
    ).get_json()["history"]
    restored = next(item for item in history if item["id"] == draft_id)
    assert restored["answers"]["submitted"]["1"] == "B"


def test_stranger_cannot_modify_draft():
    client, _, stranger_token, draft_id, _ = build_client()
    response = client.patch(
        f"/api/quiz/{draft_id}/draft",
        headers=headers(stranger_token),
        json={"answers": {"1": "A"}},
    )
    assert response.status_code == 404


def test_completed_quiz_cannot_be_modified_as_draft():
    client, owner_token, _, _, completed_id = build_client()
    response = client.patch(
        f"/api/quiz/{completed_id}/draft",
        headers=headers(owner_token),
        json={"answers": {"1": "B"}},
    )
    assert response.status_code == 409


def test_submit_updates_the_same_draft_and_marks_it_complete(monkeypatch):
    client, owner_token, _, draft_id, _ = build_client()
    monkeypatch.setattr(learning, "judge_open_answers", lambda *_args, **_kwargs: {})
    draft = client.get(
        "/api/quiz/history?category=exercise",
        headers=headers(owner_token),
    ).get_json()["history"]
    quiz = next(item for item in draft if item["id"] == draft_id)["answers"]["quiz"]

    response = client.post(
        "/api/quiz/submit-structured",
        headers=headers(owner_token),
        json={
            "record_id": draft_id,
            "category": "exercise",
            "quiz": quiz,
            "answers": {"1": "A", "2": ["A", "B"]},
        },
    )
    assert response.status_code == 200
    record = response.get_json()["record"]
    assert record["id"] == draft_id
    assert record["answers"]["completed"] is True
    assert len(record["answers"]["details"]) == 2
