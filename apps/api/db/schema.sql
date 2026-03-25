-- ================================================================
-- 번역 플랫폼 초기 스키마
-- Supabase SQL Editor에 그대로 붙여넣고 실행하면 됨
-- ================================================================

-- ── 확장 활성화 ─────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- TM 매칭 유사도 검색
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

-- ── updated_at 자동 갱신 트리거 함수 ────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- ── users ────────────────────────────────────────────────────────
CREATE TABLE users (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email      VARCHAR(255) NOT NULL UNIQUE,
    hashed_pw  TEXT NOT NULL,
    role       VARCHAR(20) NOT NULL DEFAULT 'client',  -- client | translator | admin
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE UNIQUE INDEX ix_users_email ON users (email);

-- ── jobs ─────────────────────────────────────────────────────────
-- client_id FK 제거: 고객은 회원가입 없이 폼 제출로만 의뢰
-- client_name, client_email을 job에 직접 저장
CREATE TABLE jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_name   VARCHAR(100) NOT NULL,
    client_email  VARCHAR(255) NOT NULL,
    source_lang   VARCHAR(10) NOT NULL,
    target_lang   VARCHAR(10) NOT NULL,
    content_type  VARCHAR(50),   -- marketing | legal | technical | general | medical
    quality_level VARCHAR(20),   -- translation | review | dtp
    file_url      TEXT,
    word_count    INTEGER,
    status        VARCHAR(30) NOT NULL DEFAULT 'REQUESTED',
    deadline      TIMESTAMPTZ,
    notes         TEXT,          -- 고객 요청사항 메모
    created_at    TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at    TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE INDEX ix_jobs_status       ON jobs (status);
CREATE INDEX ix_jobs_client_email ON jobs (client_email);
CREATE TRIGGER trg_jobs_updated_at
    BEFORE UPDATE ON jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE INDEX ix_jobs_source_target_lang_trgm
    ON jobs USING GIN ((source_lang || '-' || target_lang) gin_trgm_ops);
CREATE INDEX ix_jobs_content_type_trgm
    ON jobs USING GIN (content_type gin_trgm_ops);

-- ── job_events (FSM 이력) ────────────────────────────────────────
CREATE TABLE job_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id       UUID NOT NULL REFERENCES jobs(id),
    from_status  VARCHAR(30),
    to_status    VARCHAR(30) NOT NULL,
    triggered_by VARCHAR(50),  -- system | translator | client | admin
    actor_id     UUID,
    metadata     JSONB,
    created_at   TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE INDEX ix_job_events_job_id ON job_events (job_id);

-- ── quotes ───────────────────────────────────────────────────────
CREATE TABLE quotes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id              UUID NOT NULL REFERENCES jobs(id),
    estimated_price     NUMERIC(12, 2),
    currency            VARCHAR(10) DEFAULT 'KRW',
    estimated_hours     NUMERIC(6, 1),
    confidence          NUMERIC(4, 3),  -- 견적 신뢰도 0.000~1.000
    word_count          INTEGER,
    difficulty          NUMERIC(5, 3),  -- 난이도 승수
    deadline_multiplier NUMERIC(4, 2),  -- 마감 촉박 승수
    tm_match_rate       NUMERIC(4, 3),  -- TM 매칭률
    status              VARCHAR(20) DEFAULT 'PENDING',  -- PENDING | APPROVED | REJECTED
    created_at          TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE INDEX ix_quotes_status ON quotes (status);
CREATE INDEX ix_quotes_job_id ON quotes (job_id);

-- ── translators ──────────────────────────────────────────────────
CREATE TABLE translators (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID REFERENCES users(id),
    name          VARCHAR(100),
    email         VARCHAR(255),             -- 번역가 연락처 (계정 없이 이메일 통보만)
    lang_pairs    TEXT[],   -- ['ko-en', 'ko-ja']
    specialties   TEXT[],   -- ['marketing', 'legal']
    quality_score NUMERIC(4, 3),
    on_time_rate  NUMERIC(4, 3),
    throughput    NUMERIC(6, 2),
    responsiveness NUMERIC(4, 3),
    availability  VARCHAR(20) DEFAULT 'AVAILABLE',  -- AVAILABLE | BUSY | OVERLOADED | OFFLINE
    current_load  INTEGER DEFAULT 0,
    max_load      INTEGER DEFAULT 3,
    created_at    TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE INDEX ix_translators_availability ON translators (availability);

-- ── assignments ──────────────────────────────────────────────────
-- 번역가 수락/거절 없음: 내부 담당자가 직접 배정 확정
-- status: ASSIGNED(배정됨) | COMPLETED(완료) | CANCELLED(취소)
CREATE TABLE assignments (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id        UUID NOT NULL REFERENCES jobs(id),
    translator_id UUID NOT NULL REFERENCES translators(id),
    score         NUMERIC(5, 4),
    status        VARCHAR(20) DEFAULT 'ASSIGNED',  -- ASSIGNED | COMPLETED | CANCELLED
    assigned_at   TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE INDEX ix_assignments_status ON assignments (status);
CREATE INDEX ix_assignments_job_id ON assignments (job_id);

-- ── notifications ────────────────────────────────────────────────
-- recipient_id nullable: 외부 고객은 users 테이블에 없으므로 UUID 없음
-- recipient_email로 실제 발송 대상 식별
CREATE TABLE notifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID REFERENCES jobs(id),
    recipient_id    UUID,          -- 내부 사용자(관리자/번역가)만 해당, 외부 고객은 NULL
    recipient_email VARCHAR(255),  -- 실제 발송 이메일 주소
    channel         VARCHAR(20),   -- email | slack | webhook
    payload      JSONB,
    status       VARCHAR(20) DEFAULT 'PENDING',  -- PENDING | SENT | FAILED | DEAD_LETTER
    attempts     INTEGER DEFAULT 0,
    next_retry_at TIMESTAMPTZ,
    sent_at      TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE INDEX ix_notifications_status       ON notifications (status);
CREATE INDEX ix_notifications_recipient_id ON notifications (recipient_id);
CREATE INDEX ix_notifications_recipient_email ON notifications (recipient_email);

-- ── tm_segments (Translation Memory) ────────────────────────────
CREATE TABLE tm_segments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_lang VARCHAR(10) NOT NULL,
    target_lang VARCHAR(10) NOT NULL,
    source_text TEXT NOT NULL,
    target_text TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ix_tm_segments_source_trgm
    ON tm_segments USING GIN (source_text gin_trgm_ops);
CREATE INDEX ix_tm_segments_lang_pair
    ON tm_segments (source_lang, target_lang);

-- ── audit_logs ───────────────────────────────────────────────────
CREATE TABLE audit_logs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID,
    method       VARCHAR(10) NOT NULL,
    path         TEXT NOT NULL,
    status_code  INTEGER,
    ip           VARCHAR(45),
    duration_ms  INTEGER,
    request_body JSONB,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ix_audit_logs_user_id    ON audit_logs (user_id);
CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at DESC);
