import signal
import sys

from app import create_app
from app.services.db_channel import shutdown as shutdown_db_channel


app = create_app()


def _handle_sigint(signum, frame):
    print("\n✅ 正在关闭后台任务...")
    shutdown_db_channel()
    print("✅ 服务器已正常关闭")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _handle_sigint)

    database_uri = app.config["SQLALCHEMY_DATABASE_URI"]
    safe_database_uri = database_uri
    if "://" in database_uri and "@" in database_uri:
        prefix, suffix = database_uri.split("@", 1)
        safe_database_uri = f"{prefix.split(':', 2)[0]}://***:***@{suffix}"
    print(f"Database: {safe_database_uri}")
    # 开发期开启 debug + 自动重载，改 app/ 或 run.py 后无需手动重启。
    # exclude_patterns 排除“非源码”目录：否则 SQLite 每次写库(instance/*.db)、
    # 上传/生成文件/uploads、日志 *.log 都会触发重载，导致请求期间反复重启、端口卡死。
    # 端口用 5050：本机 5000 被 cc-switch 占用（它对 HTTP 返回空 404）。
    # 同步 frontend/.env 的 VITE_API_BASE_URL。
    app.run(
        host="0.0.0.0",
        port=5050,
        debug=True,
        use_reloader=True,
        exclude_patterns=[
            ".venv/**", "instance/**", "uploads/**", "knowledge_base/**",
            "__pycache__/**", "*.log", "*.db", "*.sqlite", "*.sqlite3",
        ],
    )
