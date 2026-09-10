from flask_jwt_extended import create_access_token

from app import create_app
from app.config import Config
from app.extensions import db
from app.models import QuizResult, User


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    DIGITAL_HUMAN_ENABLED = True
    MIMO_API_KEY = ""


def build_client():
    app = create_app(TestConfig)
    with app.app_context():
        owner = User(username="owner", role="student", email="")
        owner.set_password("test")
        stranger = User(username="stranger", role="student", email="")
        stranger.set_password("test")
        db.session.add_all([owner, stranger])
        db.session.flush()
        record = QuizResult(
            user_id=owner.id,
            quiz_content="测试测评",
            score=50,
            category="evaluation",
            answers={
                "quiz": {
                    "questions": [{
                        "id": 1,
                        "prompt": "测试题",
                        "concept": "测试知识点",
                    }]
                },
                "details": [{
                    "id": 1,
                    "status": "wrong",
                    "is_correct": False,
                    "concept": "测试知识点",
                    "user_answer": "A",
                    "reference_answer": "B",
                    "explanation": "应该选择 B。",
                }],
            },
        )
        db.session.add(record)
        db.session.commit()
        owner_token = create_access_token(identity=owner.id)
        stranger_token = create_access_token(identity=stranger.id)
        record_id = record.id
    return app.test_client(), owner_token, stranger_token, record_id


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_owner_can_prepare_with_local_fallback():
    client, owner_token, _, record_id = build_client()
    response = client.post(
        f"/api/quiz/{record_id}/digital-human/prepare",
        headers=headers(owner_token),
        json={},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ready"
    assert payload["script_provider"] == "local"
    assert payload["lessons"][0]["reference_answer"] == "B"


def test_other_user_cannot_access_record():
    client, _, stranger_token, record_id = build_client()
    response = client.post(
        f"/api/quiz/{record_id}/digital-human/prepare",
        headers=headers(stranger_token),
        json={},
    )
    assert response.status_code == 404
