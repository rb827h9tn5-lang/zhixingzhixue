import os

from flask import Flask, jsonify

from .config import Config
from .extensions import cors, db, jwt, migrate
from .routes.auth import auth_bp
from .routes.code_execution import code_execution_bp
from .routes.digital_human import digital_human_bp
from .routes.knowledge import knowledge_bp
from .routes.learning import learning_bp
from .routes.ppt import ppt_bp
from .routes.voice import voice_bp


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(
        app,
        resources={
            r"/api/*": {
                "origins": app.config["CORS_ORIGINS"],
                "supports_credentials": False,
                "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
                "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            }
        },
    )

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(code_execution_bp, url_prefix="/api/code")
    app.register_blueprint(digital_human_bp, url_prefix="/api")
    app.register_blueprint(learning_bp, url_prefix="/api")
    app.register_blueprint(knowledge_bp, url_prefix="/api/knowledge")
    app.register_blueprint(ppt_bp, url_prefix="/api/ppt")
    app.register_blueprint(voice_bp, url_prefix="/api/voice")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "multi-agent-study-assistant"})

    with app.app_context():
        if app.config.get("AUTO_CREATE_DB", app.testing):
            db.create_all()
        # 预加载向量嵌入模型（sentence-transformers 首次导入 torch 会写临时文件，
        # 若在请求处理时触发会导致 Flask 调试重载器重启，连接断开报 Network Error）。
        # 在启动时提前加载，避免请求期间的不必要重载。
        try:
            from .services.vector_store import get_embedding_model
            get_embedding_model()
        except Exception:
            app.logger.warning("向量嵌入模型预加载失败，将在首次使用时重试")

    return app
