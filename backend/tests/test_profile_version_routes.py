from flask_jwt_extended import create_access_token

from app import create_app
from app.config import Config
from app.extensions import db
from app.models import Profile, ProfileEvidence, ProfileVersion, User
from app.services.profile_service import record_behavior_profile_change


class ProfileTestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    MIMO_API_KEY = ""


def build_client():
    app = create_app(ProfileTestConfig)
    with app.app_context():
        user = User(username="profile-owner", role="student", email="")
        user.set_password("test")
        db.session.add(user)
        db.session.commit()
        token = create_access_token(identity=str(user.id))
        return app, app.test_client(), token, user.id


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_profile_intake_requires_confirmation_and_creates_evidence():
    app, client, token, user_id = build_client()

    initial = client.get("/api/profile", headers=headers(token))
    assert initial.status_code == 200
    assert initial.get_json()["current_version"]["version"] == 1

    draft_response = client.post(
        "/api/profile/intake/draft",
        headers=headers(token),
        json={
            "dialogue": "我是计算机专业学生，一个月后参加考试，喜欢图解和实践。",
            "major": "计算机科学与技术",
            "learning_goal": "一个月后通过课程考试",
            "learning_style": "visual",
            "preferred_resource_types": ["思维导图", "代码实践"],
            "weekly_time_minutes": 420,
        },
    )
    assert draft_response.status_code == 200
    draft_payload = draft_response.get_json()
    assert draft_payload["current_version"] == 1
    assert draft_payload["extraction"]["provider"] == "local"
    assert draft_payload["draft"]["major"] == "计算机科学与技术"
    assert draft_payload["draft"]["preferred_resource_types"] == ["思维导图", "代码实践"]

    with app.app_context():
        profile = Profile.query.filter_by(user_id=user_id).one()
        assert profile.major != "计算机科学与技术"
        assert ProfileVersion.query.filter_by(user_id=user_id).count() == 1

    confirm = client.post(
        "/api/profile/intake/confirm",
        headers=headers(token),
        json={
            "draft": draft_payload["draft"],
            "dialogue": "我是计算机专业学生，一个月后参加考试，喜欢图解和实践。",
            "confidence": draft_payload["extraction"]["confidence"],
            "expected_version": 1,
        },
    )
    assert confirm.status_code == 200
    confirmed = confirm.get_json()
    assert confirmed["idempotent"] is False
    assert confirmed["version"]["version"] == 2
    assert confirmed["profile"]["major"] == "计算机科学与技术"
    assert confirmed["evidence"]
    assert all(item["evidence_type"] == "dialogue" for item in confirmed["evidence"])

    versions = client.get("/api/profile/versions", headers=headers(token)).get_json()["versions"]
    assert [item["version"] for item in versions] == [2, 1]
    assert versions[0]["evidence"]


def test_profile_confirm_is_idempotent_and_rejects_stale_version():
    _, client, token, _ = build_client()
    current = client.get("/api/profile", headers=headers(token)).get_json()["profile"]
    current["learning_goal"] = "通过期末考试"

    first = client.post(
        "/api/profile/intake/confirm",
        headers=headers(token),
        json={"draft": current, "expected_version": 1},
    )
    assert first.status_code == 200
    assert first.get_json()["version"]["version"] == 2

    repeated = client.post(
        "/api/profile/intake/confirm",
        headers=headers(token),
        json={"draft": current, "expected_version": 2},
    )
    assert repeated.status_code == 200
    assert repeated.get_json()["idempotent"] is True
    assert repeated.get_json()["version"]["version"] == 2

    context_only = client.post(
        "/api/profile/intake/confirm",
        headers=headers(token),
        json={
            "draft": current,
            "dialogue": "我还希望保持当前目标，暂时不调整画像字段。",
            "expected_version": 2,
        },
    )
    assert context_only.status_code == 200
    assert context_only.get_json()["version"]["version"] == 2
    assert context_only.get_json()["evidence"][0]["dimension"] == "dialogue_context"

    current["learning_goal"] = "变更后的目标"
    stale = client.post(
        "/api/profile/intake/confirm",
        headers=headers(token),
        json={"draft": current, "expected_version": 1},
    )
    assert stale.status_code == 409


def test_behavior_change_creates_version_without_polluting_raw_dialogue():
    app, client, token, user_id = build_client()
    client.get("/api/profile", headers=headers(token))

    with app.app_context():
        profile = Profile.query.filter_by(user_id=user_id).one()
        previous = profile.to_dict()
        profile.knowledge_level = "intermediate"
        version, evidence = record_behavior_profile_change(
            profile,
            previous=previous,
            action="submit_quiz",
            evidence_payload={"record_id": 18, "score": 82},
        )
        db.session.commit()

        assert version is not None
        assert version.version == 2
        assert evidence[0].evidence_type == "assessment"
        assert evidence[0].evidence_source_id == "18"
        assert profile.raw_dialogue == ""
        assert ProfileEvidence.query.filter_by(user_id=user_id).count() == 2
