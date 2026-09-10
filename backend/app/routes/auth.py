from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required

from ..extensions import db
from ..models import Profile, User, TaskActionLog
from ..services.local_generator import LocalStudyGenerator

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"message": "用户名和密码不能为空"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"message": "用户名已存在"}), 409

    user = User(username=username, role=data.get("role") or "student", email=data.get("email") or "")
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    generator = LocalStudyGenerator()
    profile_data = generator.extract_profile(data.get("profile") or {}, {})
    db.session.add(Profile(user_id=user.id, **profile_data))
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify({"token": token, "user": user.to_dict()}), 201


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"message": "用户名或密码错误"}), 401
    token = create_access_token(identity=str(user.id))
    # 登录时清空该用户今日的任务完成记录，使所有任务显示为未完成
    from datetime import datetime, timedelta
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    TaskActionLog.query.filter(
        TaskActionLog.user_id == user.id,
        TaskActionLog.created_at >= today_start,
        TaskActionLog.created_at < today_end,
    ).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"token": token, "user": user.to_dict()})


@auth_bp.get("/me")
@jwt_required()
def me():
    user = User.query.get_or_404(int(get_jwt_identity()))
    return jsonify({"user": user.to_dict(), "profile": user.profile.to_dict() if user.profile else None})
