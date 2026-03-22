"""audit_logs 테이블 추가 마이그레이션.

모든 API 요청/응답을 기록하는 감사 로그 테이블 생성.
user_id, created_at 인덱스로 사용자별/시간순 조회 최적화.

Revision ID: 002
Revises: 001
Create Date: 2026-03-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── audit_logs 테이블 생성 ──────────────────────────────────────
    # 모든 API 요청/응답을 기록 — 보안 감사, 컴플라이언스, 장애 재현에 활용
    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # 인증된 사용자 ID (미인증 요청 시 NULL)
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        # HTTP 메서드: GET, POST, PUT, PATCH, DELETE
        sa.Column("method", sa.String(10), nullable=False),
        # 요청 경로 (쿼리스트링 제외)
        sa.Column("path", sa.Text, nullable=False),
        # HTTP 응답 상태 코드
        sa.Column("status_code", sa.Integer, nullable=True),
        # 클라이언트 IP 주소 (IPv6 포함 최대 45자)
        sa.Column("ip", sa.String(45), nullable=True),
        # 요청 처리 소요 시간 (밀리초) — 성능 모니터링용
        sa.Column("duration_ms", sa.Integer, nullable=True),
        # 요청 본문 (JSONB) — 민감 필드는 AuditLogMiddleware에서 마스킹 처리
        sa.Column("request_body", postgresql.JSONB, nullable=True),
        # 기록 시각 — DB 서버 시각 기준 (UTC)
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    # user_id 인덱스: 특정 사용자의 활동 이력 조회 최적화
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])

    # created_at 내림차순 인덱스: 최근 로그 우선 조회 최적화
    # DESC 인덱스: 최신 로그 페이지네이션 쿼리에 최적
    op.execute(
        "CREATE INDEX ix_audit_logs_created_at_desc ON audit_logs (created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_created_at_desc")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")
