"""
애플리케이션 설정 모듈.
환경 변수를 pydantic-settings로 로드하여 타입 안전성을 보장.
"""

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Supabase (DB + Storage 통합) ─────────────────
    # SUPABASE_URL과 SUPABASE_DB_PASSWORD로 DATABASE_URL 자동 파생
    # ex) https://abc123.supabase.co → db.abc123.supabase.co
    SUPABASE_URL: str
    SUPABASE_DB_PASSWORD: str
    SUPABASE_SERVICE_KEY: str  # service_role 키 (Storage 업로드 권한)

    # ── 필수 ──────────────────────────────────────────
    JWT_SECRET: str
    RESEND_API_KEY: str = ""

    # ── Redis (기본값으로 로컬 실행 가능) ─────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── 이메일 ────────────────────────────────────────
    EMAIL_FROM: str = "noreply@example.com"

    # ── Slack (선택) ──────────────────────────────────
    SLACK_WEBHOOK_URL: str = ""

    # ── 자동 파생 (직접 설정 불필요) ─────────────────
    DATABASE_URL: str = ""
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    # ── JWT 기본값 ─────────────────────────────────────
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── 앱 설정 ───────────────────────────────────────
    DEBUG: bool = False

    model_config = {"env_file": ".env", "case_sensitive": True}

    @model_validator(mode="after")
    def derive_urls(self) -> "Settings":
        # SUPABASE_URL에서 프로젝트 ref 추출 후 DATABASE_URL 자동 조립
        # ex) https://abc123.supabase.co → postgresql+asyncpg://postgres:pw@db.abc123.supabase.co:5432/postgres
        if not self.DATABASE_URL and self.SUPABASE_URL:
            ref = self.SUPABASE_URL.replace("https://", "").split(".")[0]
            self.DATABASE_URL = (
                f"postgresql+asyncpg://postgres:{self.SUPABASE_DB_PASSWORD}"
                f"@db.{ref}.supabase.co:5432/postgres"
            )

        # Celery URL을 별도 설정하지 않으면 REDIS_URL에서 자동 파생
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = self.REDIS_URL
        if not self.CELERY_RESULT_BACKEND:
            self.CELERY_RESULT_BACKEND = self.REDIS_URL.rstrip("/0123456789") + "/1"

        return self


settings = Settings()
