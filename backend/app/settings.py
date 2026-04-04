import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_list(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings:
    report_brand_name: str = os.getenv("REPORT_BRAND_NAME", "AI Smart Exam System")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://exam_user:exam_pass@127.0.0.1:5432/exam_system",
    )
    cors_allowed_origins: list[str] = _get_list("CORS_ALLOWED_ORIGINS", ["*"])
    rate_limit_window_seconds: int = _get_int("RATE_LIMIT_WINDOW_SECONDS", 60)
    rate_limit_max_requests: int = _get_int("RATE_LIMIT_MAX_REQUESTS", 180)
    max_request_body_bytes: int = _get_int("MAX_REQUEST_BODY_BYTES", 1024 * 1024)
    ai_classifier_url: str = os.getenv("AI_CLASSIFIER_URL", "").strip()
    ai_classifier_timeout_seconds: int = _get_int("AI_CLASSIFIER_TIMEOUT_SECONDS", 3)


settings = Settings()
