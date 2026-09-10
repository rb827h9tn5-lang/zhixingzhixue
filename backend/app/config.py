import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env", override=False)

# 调试：确认 XFYUN 环境变量是否被正确加载
import sys as _sys
_xfyun_app_id = os.getenv("XFYUN_APP_ID", "")
_xfyun_api_secret = os.getenv("XFYUN_API_SECRET", "")
# print(f"[config] XFYUN_APP_ID={repr(_xfyun_app_id)[:30]} XFYUN_API_SECRET={'***' if _xfyun_api_secret else repr(_xfyun_api_secret)}", file=_sys.stderr)


def _runtime_environment() -> str:
    return (os.getenv("APP_ENV") or os.getenv("FLASK_ENV") or "development").strip().lower()


def _hmac_key(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    if not value and _runtime_environment() in {"production", "prod"}:
        raise RuntimeError(f"{name} must be configured in production")
    value = value or default
    if len(value.encode("utf-8")) >= 32:
        return value
    return f"{value}-multi-agent-study-assistant-dev-secret-key"


def _env_bool(name: str, default: bool) -> bool:
    fallback = "true" if default else "false"
    return os.getenv(name, fallback).strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _cors_origins() -> list[str]:
    local_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    origins = _env_list("CORS_ORIGINS", local_origins)
    return local_origins if "*" in origins else origins


class Config:
    SECRET_KEY = _hmac_key("SECRET_KEY", "multi-agent-study-assistant-flask-secret")
    JWT_SECRET_KEY = _hmac_key("JWT_SECRET_KEY", SECRET_KEY)
    JWT_VERIFY_SUB = False
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.getenv("JWT_EXPIRES_HOURS", "12")))

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or (
        "mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4".format(
            user=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD", "root"),
            host=os.getenv("MYSQL_HOST", ""),
            port=os.getenv("MYSQL_PORT", "3306"),
            database=os.getenv("MYSQL_DATABASE", "study_ai"),
        )
        if os.getenv("MYSQL_HOST")
        else "sqlite:///study_ai.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_AS_ASCII = False
    AUTO_CREATE_DB = _env_bool(
        "AUTO_CREATE_DB",
        _runtime_environment() not in {"production", "prod"},
    )

    CORS_ORIGINS = _cors_origins()
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
    DASHSCOPE_MODEL = os.getenv("DASHSCOPE_MODEL", "qwen-max")
    USE_REMOTE_LLM = os.getenv("USE_REMOTE_LLM", "auto")

    XFYUN_APP_ID = os.getenv("XFYUN_APP_ID", "")
    XFYUN_API_SECRET = os.getenv("XFYUN_API_SECRET", "")
    XFYUN_PPT_API_BASE = os.getenv("XFYUN_PPT_API_BASE", "https://zwapi.xfyun.cn/api/aippt")

    # MiMo 语音识别（mimo-v2.5-asr）。前端使用简单端点检测，
    # 在停顿后将一句话封装成 WAV 调用 /api/voice/transcribe。
    MIMO_API_KEY = os.getenv("MIMO_API_KEY", "")
    MIMO_BASE_URL = os.getenv("MIMO_BASE_URL", "https://fufu.iqach.top/v1")
    MIMO_ASR_MODEL = os.getenv("MIMO_ASR_MODEL", "mimo-v2.5-asr")
    MIMO_ASR_LANGUAGE = os.getenv("MIMO_ASR_LANGUAGE", "zh")
    MIMO_CHAT_MODEL = os.getenv("MIMO_CHAT_MODEL", "mimo-v2.5")
    MIMO_CHAT_TIMEOUT = int(os.getenv("MIMO_CHAT_TIMEOUT", "45"))
    MIMO_CODE_MODEL = os.getenv("MIMO_CODE_MODEL", MIMO_CHAT_MODEL)
    MIMO_CODE_TIMEOUT = int(os.getenv("MIMO_CODE_TIMEOUT", "45"))
    MIMO_DIGITAL_HUMAN_MODEL = os.getenv(
        "MIMO_DIGITAL_HUMAN_MODEL",
        MIMO_CHAT_MODEL,
    )
    MIMO_DIGITAL_HUMAN_TIMEOUT = int(
        os.getenv("MIMO_DIGITAL_HUMAN_TIMEOUT", "20")
    )
    MIMO_TTS_MODEL = os.getenv("MIMO_TTS_MODEL", "mimo-v2.5-tts")
    MIMO_TTS_DEFAULT_VOICE = os.getenv("MIMO_TTS_DEFAULT_VOICE", "冰糖")
    MIMO_TTS_TIMEOUT = int(os.getenv("MIMO_TTS_TIMEOUT", "15"))
    MIMO_TIMEOUT = int(os.getenv("MIMO_TIMEOUT", "30"))
    QUIZ_OPEN_ANSWER_TIMEOUT = int(os.getenv("QUIZ_OPEN_ANSWER_TIMEOUT", "6"))
    VOICE_CHUNK_MS = int(os.getenv("VOICE_CHUNK_MS", "5000"))

    DIGITAL_HUMAN_ENABLED = _env_bool("DIGITAL_HUMAN_ENABLED", True)
    DIGITAL_HUMAN_SCRIPT_MAX_CHARS = int(
        os.getenv("DIGITAL_HUMAN_SCRIPT_MAX_CHARS", "320")
    )
    DIGITAL_HUMAN_RATE_LIMIT_PER_MINUTE = int(
        os.getenv("DIGITAL_HUMAN_RATE_LIMIT_PER_MINUTE", "10")
    )

    PISTON_API_URL = os.getenv("PISTON_API_URL", "http://localhost:2000")
    CODE_MAX_CHARS = int(os.getenv("CODE_MAX_CHARS", "50000"))
    CODE_STDIN_MAX_CHARS = int(os.getenv("CODE_STDIN_MAX_CHARS", "10000"))
    CODE_OUTPUT_MAX_CHARS = int(os.getenv("CODE_OUTPUT_MAX_CHARS", "20000"))
    CODE_COMPILE_TIMEOUT_MS = int(os.getenv("CODE_COMPILE_TIMEOUT_MS", "10000"))
    CODE_RUN_TIMEOUT_MS = int(os.getenv("CODE_RUN_TIMEOUT_MS", "5000"))
    CODE_COMPILE_MEMORY_BYTES = int(
        os.getenv("CODE_COMPILE_MEMORY_BYTES", str(256 * 1024 * 1024))
    )
    CODE_RUN_MEMORY_BYTES = int(
        os.getenv("CODE_RUN_MEMORY_BYTES", str(128 * 1024 * 1024))
    )
    CODE_RATE_LIMIT_PER_MINUTE = int(
        os.getenv("CODE_RATE_LIMIT_PER_MINUTE", "20")
    )
    CODE_AI_RATE_LIMIT_PER_MINUTE = int(
        os.getenv("CODE_AI_RATE_LIMIT_PER_MINUTE", "6")
    )

    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(100 * 1024 * 1024)))
