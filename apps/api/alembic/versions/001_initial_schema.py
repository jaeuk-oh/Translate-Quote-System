"""초기 스키마 생성 마이그레이션.

모든 테이블 생성 + pg_trgm, pgcrypto 확장 활성화.
FSM 상태 전이 이력, 견적, 배정, 알림 테이블 포함.
jobs.updated_at 자동 갱신 트리거 함수 포함.

Revision ID: 001
Revises:
Create Date: 2026-03-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── PostgreSQL 확장 활성화 ───────────────────────────────────────
    # pg_trgm: 문자열 유사도 기반 TM 매칭 (업계 표준 CAT tool 방식)
    # pgcrypto: gen_random_uuid() 함수 제공
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ── updated_at 자동 갱신 트리거 함수 ───────────────────────────
    # jobs 테이블에 적용 — 레코드 수정 시 updated_at을 현재 시각으로 자동 갱신
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)

    # ── users 테이블 ────────────────────────────────────────────────
    # 클라이언트, 번역가, 관리자를 단일 테이블로 관리 (STI 패턴)
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_pw", sa.Text, nullable=False),
        # 역할: client | translator | admin
        sa.Column("role", sa.String(20), nullable=False, server_default="client"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── jobs 테이블 ─────────────────────────────────────────────────
    # FSM 상태 머신이 관리하는 번역 작업 레코드
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_lang", sa.String(10), nullable=False),
        sa.Column("target_lang", sa.String(10), nullable=False),
        # 콘텐츠 유형: marketing | legal | technical | general | medical
        sa.Column("content_type", sa.String(50)),
        # 품질 등급: translation | review | dtp
        sa.Column("quality_level", sa.String(20)),
        sa.Column("file_url", sa.Text),
        sa.Column("word_count", sa.Integer),
        # FSM 현재 상태 — state_machine.py가 단독 관리
        sa.Column("status", sa.String(30), nullable=False, server_default="REQUESTED"),
        sa.Column("deadline", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    # 상태 기반 조회 최적화 인덱스
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_client_id", "jobs", ["client_id"])
    # updated_at 자동 갱신 트리거 연결
    op.execute("""
        CREATE TRIGGER trg_jobs_updated_at
        BEFORE UPDATE ON jobs
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # pg_trgm GIN 인덱스: 언어쌍 + 콘텐츠 유형 기반 유사도 검색
    # 번역 의뢰 분류 및 필터링 성능 향상에 활용
    op.execute("""
        CREATE INDEX ix_jobs_source_target_lang_trgm
        ON jobs USING GIN ((source_lang || '-' || target_lang) gin_trgm_ops);
    """)
    op.execute("""
        CREATE INDEX ix_jobs_content_type_trgm
        ON jobs USING GIN (content_type gin_trgm_ops);
    """)

    # ── job_events 테이블 ───────────────────────────────────────────
    # FSM 상태 전이 이력 — 이벤트 소싱 패턴으로 모든 변화 추적
    op.create_table(
        "job_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("from_status", sa.String(30)),
        sa.Column("to_status", sa.String(30), nullable=False),
        # 전이 트리거: system | translator | client | admin
        sa.Column("triggered_by", sa.String(50)),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
        # 추가 컨텍스트 — 견적 ID, 배정 ID 등
        sa.Column("metadata", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_job_events_job_id", "job_events", ["job_id"])

    # ── quotes 테이블 ───────────────────────────────────────────────
    # 자동 견적 계산 결과 저장 — TM 매칭률, 난이도, 마감 승수 등 근거 보관
    op.create_table(
        "quotes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("estimated_price", sa.Numeric(12, 2)),
        sa.Column("currency", sa.String(10), server_default="KRW"),
        sa.Column("estimated_hours", sa.Numeric(6, 1)),
        # 견적 신뢰도: 0.000 ~ 1.000 (난이도 인자 분산 기반)
        sa.Column("confidence", sa.Numeric(4, 3)),
        sa.Column("word_count", sa.Integer),
        # 난이도 승수 — content_type × quality_level
        sa.Column("difficulty", sa.Numeric(5, 3)),
        # 마감 촉박도에 따른 가격 승수
        sa.Column("deadline_multiplier", sa.Numeric(4, 2)),
        # TM(Translation Memory) 매칭률 — pg_trgm 유사도 결과
        sa.Column("tm_match_rate", sa.Numeric(4, 3)),
        # 견적 상태: PENDING | COMPLETED | APPROVED | REJECTED
        sa.Column("status", sa.String(20), server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    # 상태 기반 필터링 인덱스 (승인 대기 견적 빠른 조회)
    op.create_index("ix_quotes_status", "quotes", ["status"])
    op.create_index("ix_quotes_job_id", "quotes", ["job_id"])

    # ── translators 테이블 ──────────────────────────────────────────
    # 번역가를 상태 기반 리소스로 모델링 — workload_ratio로 가용성 자동 갱신
    op.create_table(
        "translators",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id")),
        sa.Column("name", sa.String(100)),
        # 언어쌍 배열: ['ko-en', 'ko-ja'] — 배정 후보 필터링
        sa.Column("lang_pairs", postgresql.ARRAY(sa.String)),
        # 전문분야 배열: ['marketing', 'legal']
        sa.Column("specialties", postgresql.ARRAY(sa.String)),
        # ── 성과 지표 (배정 점수 계산에 사용) ──────────────────
        sa.Column("quality_score", sa.Numeric(4, 3)),    # 번역 품질 점수
        sa.Column("on_time_rate", sa.Numeric(4, 3)),     # 납기 준수율
        sa.Column("throughput", sa.Numeric(6, 2)),       # 일 평균 처리 단어 수
        sa.Column("responsiveness", sa.Numeric(4, 3)),  # 평균 응답 속도 점수
        # 가용 상태: AVAILABLE | BUSY | OVERLOADED | OFFLINE
        sa.Column("availability", sa.String(20), server_default="AVAILABLE"),
        sa.Column("current_load", sa.Integer, server_default="0"),  # 현재 진행 중인 작업 수
        sa.Column("max_load", sa.Integer, server_default="3"),      # 최대 동시 작업 수
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    # 가용 상태 인덱스 — 배정 후보 필터링 쿼리 최적화
    op.create_index("ix_translators_availability", "translators", ["availability"])

    # ── assignments 테이블 ──────────────────────────────────────────
    # 번역가 배정 수락/거절 이력 — 자동 재배정 트리거에 활용
    op.create_table(
        "assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("translator_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("translators.id"), nullable=False),
        # 배정 점수: score = quality(0.4) + on_time(0.3) + availability(0.2) + workload_inv(0.1)
        sa.Column("score", sa.Numeric(5, 4)),
        # 배정 상태: PENDING_ACCEPTANCE | ACCEPTED | REJECTED | EXPIRED
        sa.Column("status", sa.String(20), server_default="PENDING_ACCEPTANCE"),
        sa.Column("assigned_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("rejected_at", sa.DateTime(timezone=True)),
        # 수락 기한: 초과 시 Celery beat가 자동 재배정 트리거
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    # 배정 상태 인덱스 — 만료 배정 자동 체크 쿼리 최적화
    op.create_index("ix_assignments_status", "assignments", ["status"])
    op.create_index("ix_assignments_job_id", "assignments", ["job_id"])

    # ── notifications 테이블 ────────────────────────────────────────
    # 알림 발송 이력 — 지수 백오프 재시도 전략용 attempts 필드 포함
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("jobs.id")),
        sa.Column("recipient_id", postgresql.UUID(as_uuid=True), nullable=False),
        # 발송 채널: email | slack | webhook
        sa.Column("channel", sa.String(20)),
        # 알림 내용 (제목, 본문, 링크 등)
        sa.Column("payload", postgresql.JSONB),
        # 발송 상태: PENDING | SENT | FAILED | DEAD_LETTER
        sa.Column("status", sa.String(20), server_default="PENDING"),
        # 재시도 횟수 — 지수 백오프: 1분 → 5분 → 30분 → DLQ
        sa.Column("attempts", sa.Integer, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_notifications_status", "notifications", ["status"])
    op.create_index("ix_notifications_recipient_id", "notifications", ["recipient_id"])

    # ── tm_segments 테이블 ──────────────────────────────────────────
    # Translation Memory 세그먼트 저장소
    # GIN 인덱스로 pg_trgm similarity() 검색 고속화 (full scan 방지)
    op.execute("""
        CREATE TABLE tm_segments (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_lang VARCHAR(10) NOT NULL,
            target_lang VARCHAR(10) NOT NULL,
            source_text TEXT NOT NULL,
            target_text TEXT NOT NULL,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    # GIN 인덱스: source_text 유사도 검색 고속화 (pg_trgm 필수)
    op.execute("""
        CREATE INDEX ix_tm_segments_source_trgm
        ON tm_segments USING GIN (source_text gin_trgm_ops);
    """)
    op.execute("""
        CREATE INDEX ix_tm_segments_lang_pair
        ON tm_segments (source_lang, target_lang);
    """)


def downgrade() -> None:
    # 역순으로 삭제 (외래 키 의존성 고려)
    op.execute("DROP TABLE IF EXISTS tm_segments")
    op.drop_table("notifications")
    op.drop_table("assignments")
    op.drop_table("translators")
    op.drop_table("quotes")
    op.drop_table("job_events")
    op.drop_table("jobs")
    op.drop_table("users")

    # 트리거 함수 삭제
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")

    # 확장은 다른 DB 객체가 의존할 수 있으므로 주의하여 삭제
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
