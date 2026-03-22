"""
애플리케이션 설정 모듈.
환경 변수를 pydantic-settings로 로드하여 타입 안전성을 보장.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── 데이터베이스 ──────────────────────────────────
    DATABASE_URL: str

    # ── Redis ─────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── JWT 인증 ──────────────────────────────────────
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── AWS S3 파일 스토리지 ──────────────────────────
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = ""
    AWS_REGION: str = "ap-northeast-2"

    # ── 이메일 (Resend) ───────────────────────────────
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "noreply@example.com"

    # ── Slack 알림 ────────────────────────────────────
    SLACK_WEBHOOK_URL: str = ""

    # ── Celery ───────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ── 앱 설정 ───────────────────────────────────────
    APP_ENV: str = "development"
    DEBUG: bool = False

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
