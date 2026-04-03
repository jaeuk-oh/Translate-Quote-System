"""
애플리케이션 설정 모듈.
환경 변수를 pydantic-settings로 로드하여 타입 안전성을 보장.
"""

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings

# 프로젝트 루트의 .env 파일 경로 (apps/api/core/ → apps/api/ → apps/ → 프로젝트 루트)
_ENV_FILE = Path(__file__).resolve().parent.parent.parent.parent / ".env"


class Settings(BaseSettings):
    # ── Supabase ──────────────────────────────────────
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str  # service_role 키 (Storage 업로드 권한)

    # ── DB ────────────────────────────────────────────
    # Supabase free tier는 direct connection IPv4 미지원 → Transaction Pooler URL 사용
    # ex) postgresql+asyncpg://postgres.{ref}:{password}@{pooler-host}:6543/postgres
    DATABASE_URL: str

    # ── 필수 ──────────────────────────────────────────
    JWT_SECRET: str
    RESEND_API_KEY: str = ""

    # ── Redis (기본값으로 로컬 실행 가능) ─────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── 이메일 ────────────────────────────────────────
    EMAIL_FROM: str = "noreply@example.com"

    # ── Slack (선택) ──────────────────────────────────
    SLACK_WEBHOOK_URL: str = ""

    # ── Celery (REDIS_URL에서 자동 파생) ──────────────
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    # ── JWT 기본값 ─────────────────────────────────────
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── 앱 설정 ───────────────────────────────────────
    DEBUG: bool = False
    FRONTEND_URL: str = "http://localhost:3000"

    model_config = {"env_file": str(_ENV_FILE), "case_sensitive": True, "extra": "ignore"}

    @model_validator(mode="after")
    def derive_celery_urls(self) -> "Settings":
        # Celery URL을 별도 설정하지 않으면 REDIS_URL에서 자동 파생
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = self.REDIS_URL
        if not self.CELERY_RESULT_BACKEND:
            self.CELERY_RESULT_BACKEND = self.REDIS_URL.rstrip("/0123456789") + "/1"

        return self


settings = Settings()
