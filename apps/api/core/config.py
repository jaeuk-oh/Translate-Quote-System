"""
애플리케이션 설정 모듈.
환경 변수를 pydantic-settings로 로드하여 타입 안전성을 보장.
"""

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── 필수 ──────────────────────────────────────────
    DATABASE_URL: str
    JWT_SECRET: str

    # ── Redis (기본값으로 로컬 실행 가능) ─────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── JWT 인증 기본값 ────────────────────────────────
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── AWS S3 ────────────────────────────────────────
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = ""
    AWS_REGION: str = "ap-northeast-2"

    # ── 이메일 (Resend) ───────────────────────────────
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "noreply@example.com"

    # ── Slack (선택) ──────────────────────────────────
    SLACK_WEBHOOK_URL: str = ""

    # ── Celery: REDIS_URL에서 자동 파생 ───────────────
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    # ── 앱 설정 ───────────────────────────────────────
    DEBUG: bool = False

    model_config = {"env_file": ".env", "case_sensitive": True}

    @model_validator(mode="after")
    def derive_celery_urls(self) -> "Settings":
        # Celery URL을 별도 설정하지 않으면 REDIS_URL에서 자동 파생
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = self.REDIS_URL
        if not self.CELERY_RESULT_BACKEND:
            # 결과 백엔드는 DB 1번 사용 (브로커와 분리)
            self.CELERY_RESULT_BACKEND = self.REDIS_URL.rstrip("/0123456789") + "/1"
        return self


settings = Settings()
