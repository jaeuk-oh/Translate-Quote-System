# 번역 플랫폼 최종 개발 기획안

> 자동 견적 · 작업자 배정 · 완료 알림 시스템  
> 작성일: 2026-03-22 | 버전: v1.1

---

## 1. 프로젝트 개요

### 목표

번역 의뢰 → 견적 → 작업자 배정 → 진행 → 완료 알림까지의 전 과정을 자동화하여, 운영 개입 없이도 안정적으로 동작하는 번역 플랫폼을 구축한다.

### 핵심 원칙

- 각 기능은 독립 서비스로 분리하고 이벤트 기반으로 연결한다
- 상태 전이는 FSM(유한 상태 머신)으로 단일 관리한다
- 모든 외부 연동(알림, 웹훅)은 재시도 전략을 포함한다

---

## 2. 문제 정의

기존 번역 프로세스는 다음과 같은 비효율이 존재한다.

- 견적 산정이 수작업으로 이루어져 응답 시간이 느리고 일관성이 없음
- 작업자 배정이 담당자의 경험에 의존하여 객관적 기준이 부재함
- 작업 완료 여부를 수동으로 확인해야 하는 운영 부담이 큼
- 번역가의 실시간 상태 및 퍼포먼스를 반영한 운영이 어려움

---

## 3. 핵심 목표

1. 번역 난이도와 TM 매칭률을 기반으로 한 자동 견적 시스템 구축
2. 번역가를 "정적 인력"이 아닌 "상태 기반 리소스"로 모델링하여 자동 배정 로직 설계
3. 이벤트 기반 작업 완료 감지 및 알림 자동화
4. 전 과정을 데이터 기반으로 전환하여 경험 의존적 운영 방식 탈피

---

## 4. 기술 스택

| 영역 | 기술 | 선택 이유 |
|------|------|-----------|
| 프론트엔드 | Next.js 14 (App Router) | SSR, 실시간 SSE 지원 |
| 백엔드 | Python + FastAPI | 비동기 지원, 자동 문서화(Swagger) |
| DB | PostgreSQL | 트랜잭션, FSM 상태 관리 |
| 큐 / 캐시 | Redis + Celery | 비동기 작업, 재시도 내장 |
| 파일 스토리지 | S3 (or MinIO) | 번역 파일 원본·결과물 보관 |
| 실시간 | SSE (Server-Sent Events) | 단방향 상태 push에 최적 |
| 인증 | JWT + Refresh Token | 무상태 인증 |

---

## 5. 전체 아키텍처

```
[Client / Next.js]
       │  REST + SSE
       ▼
[API Gateway + Auth Middleware]
       │
       ▼
[Message Queue - Redis / Celery]
  ┌────┴──────────────────────┐
  ▼                           ▼
[Auto Quote Service]   [Auto Assign Service]
  └──────────┬───────────────┘
             ▼
     [State Machine Service]   ← FSM 단일 관리
             │
             ▼
   [Notification Service]
   (Email / Slack / Webhook)
             │
             ▼
     [Retry Queue + DLQ]       ← 실패 시 재시도

[PostgreSQL]  [Redis]  [S3]    ← 데이터 레이어
```

---

## 6. DB 스키마

### 핵심 테이블

```sql
-- 번역 의뢰
CREATE TABLE jobs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id     UUID NOT NULL REFERENCES users(id),
  source_lang   VARCHAR(10) NOT NULL,
  target_lang   VARCHAR(10) NOT NULL,
  content_type  VARCHAR(50),           -- marketing, legal, technical 등
  quality_level VARCHAR(20),           -- translation, review, dtp
  file_url      TEXT,
  word_count    INTEGER,
  status        VARCHAR(30) NOT NULL DEFAULT 'REQUESTED',
  deadline      TIMESTAMPTZ,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 자동 견적
CREATE TABLE quotes (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id               UUID NOT NULL REFERENCES jobs(id),
  estimated_price      NUMERIC(12, 2),
  currency             VARCHAR(10) DEFAULT 'KRW',
  estimated_hours      NUMERIC(6, 1),
  confidence           NUMERIC(4, 3),   -- 0.000 ~ 1.000
  word_count           INTEGER,
  difficulty           NUMERIC(5, 3),
  deadline_multiplier  NUMERIC(4, 2),
  tm_match_rate        NUMERIC(4, 3),   -- Translation Memory 매칭률
  status               VARCHAR(20) DEFAULT 'PENDING',
  created_at           TIMESTAMPTZ DEFAULT NOW()
);

-- 번역가
CREATE TABLE translators (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name            VARCHAR(100),
  lang_pairs      TEXT[],              -- ['ko-en', 'ko-ja']
  specialties     TEXT[],              -- ['marketing', 'legal']
  quality_score   NUMERIC(4, 3),
  on_time_rate    NUMERIC(4, 3),
  throughput      NUMERIC(6, 2),       -- 일 평균 처리 단어 수
  responsiveness  NUMERIC(4, 3),       -- 평균 응답 속도 점수
  availability    VARCHAR(20) DEFAULT 'AVAILABLE',
  current_load    INTEGER DEFAULT 0,
  max_load        INTEGER DEFAULT 3,   -- 최대 동시 작업 수
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 작업 배정
CREATE TABLE assignments (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id         UUID NOT NULL REFERENCES jobs(id),
  translator_id  UUID NOT NULL REFERENCES translators(id),
  score          NUMERIC(5, 4),
  status         VARCHAR(20) DEFAULT 'PENDING_ACCEPTANCE',
  assigned_at    TIMESTAMPTZ DEFAULT NOW(),
  accepted_at    TIMESTAMPTZ,
  rejected_at    TIMESTAMPTZ,
  expires_at     TIMESTAMPTZ           -- 수락 기한 초과 시 자동 재배정
);

-- 상태 이력 (FSM 이벤트 로그)
CREATE TABLE job_events (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id       UUID NOT NULL REFERENCES jobs(id),
  from_status  VARCHAR(30),
  to_status    VARCHAR(30) NOT NULL,
  triggered_by VARCHAR(50),            -- system | translator | client | admin
  actor_id     UUID,
  metadata     JSONB,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 알림 발송 이력
CREATE TABLE notifications (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id          UUID REFERENCES jobs(id),
  recipient_id    UUID NOT NULL,
  channel         VARCHAR(20),         -- email | slack | webhook
  payload         JSONB,
  status          VARCHAR(20) DEFAULT 'PENDING',
  attempts        INTEGER DEFAULT 0,
  next_retry_at   TIMESTAMPTZ,
  sent_at         TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 7. 상태 머신 (FSM)

### 작업 상태 전이

```
REQUESTED
   │
   ▼
QUOTE_PENDING       ← 견적 계산 중 (비동기)
   │
   ▼
QUOTED              ← 견적 완료, 클라이언트 승인 대기
   │ (승인)
   ▼
PENDING_ACCEPTANCE  ← 번역가 수락 대기
   │ (수락)         └─ 거절 or 타임아웃 → 자동 재배정
   ▼
ASSIGNED
   │
   ▼
IN_PROGRESS
   │
   ▼
REVIEW
   │
   ▼
QA
   │ (통과)         └─ 실패 → IN_PROGRESS 복귀
   ▼
COMPLETED
```

> 각 상태 전이는 `job_events` 테이블에 기록되며, 전이 실패 시 롤백된다.

### 번역가 상태 모델

번역가는 실시간 상태를 가지는 리소스로 정의한다.

| 상태 | 의미 | 배정 가능 여부 |
|------|------|---------------|
| AVAILABLE | 즉시 가능 | O |
| BUSY | 작업 중이나 여유 있음 | O |
| OVERLOADED | 과부하 (workload_ratio ≥ 1.0) | X |
| OFFLINE | 비활성 | X |

```
workload_ratio = current_load / max_load

AVAILABLE   : workload_ratio = 0
BUSY        : 0 < workload_ratio < 1.0
OVERLOADED  : workload_ratio >= 1.0
```

---

## 8. 서비스별 상세 설계

### 8-1. Auto Quote Service

**처리 흐름**

```
파일 업로드 (S3) → 큐 등록 → 비동기 분석 → 견적 저장 → SSE 응답
```

**API**

```
POST /jobs              → jobId 반환 (즉시)
GET  /jobs/:id/quote    → SSE 구독 or 폴링
```

**가격 계산 공식**

```
price = word_count × base_rate(lang_pair) × difficulty × deadline_multiplier × tm_discount

difficulty = content_weight × quality_weight × file_complexity
confidence = 1 - variance(difficulty factors)

tm_discount:
  100% match   → 0.0  (무료)
  75~99% match → 0.3  (70% 할인)
  50~74% match → 0.6  (40% 할인)
  < 50%        → 1.0  (할인 없음)
```

> TM(Translation Memory) 연동을 통해 반복 구간을 자동 감지하고 할인율에 반영한다. 업계 표준 CAT tool 방식과 동일.

---

### 8-2. Auto Assign Service

**번역가 점수 계산 공식**

```
score = (quality_score  × 0.40)
      + (on_time_rate   × 0.30)
      + (availability   × 0.20)
      + (throughput_inv × 0.10)

workload_inv = 1 / (1 + current_load)   ← 0 나누기 방지
```

**배정 플로우**

```
1. 언어쌍 + 전문분야로 후보 필터링
2. OVERLOADED / OFFLINE 제거
3. 점수 계산 → Top 3 추천
4. 최고 점수 번역가에게 수락 요청 발송
5. 24시간 내 미응답 or 거절 → 2순위 자동 재배정
6. 최대 3회 재배정 후 관리자 알림
```

**API**

```
POST /jobs/:id/assign/recommend   → 추천 번역가 목록
POST /jobs/:id/assign             → 배정 확정
POST /assignments/:id/accept      → 번역가 수락
POST /assignments/:id/reject      → 번역가 거절 (재배정 트리거)
```

---

### 8-3. Notification Service

**이벤트 → 알림 매핑**

| 이벤트 | 수신자 | 채널 |
|--------|--------|------|
| QUOTED | 클라이언트 | 이메일 |
| PENDING_ACCEPTANCE | 번역가 | 이메일 |
| ASSIGNED | 번역가 | 이메일 + Slack |
| COMPLETED | 클라이언트 | 이메일 + Webhook |
| QA_FAILED | 번역가 | 이메일 |
| REASSIGNED | 관리자 | Slack |

**중복 발송 방지**

```
Redis SETNX `lock:notify:{jobId}:{event}` EX 10
→ 획득 성공 시만 발송 진행
→ 실패 시 스킵 (이미 처리 중)
```

**재시도 전략 (Exponential Backoff)**

```
1차 실패 → 1분 후 재시도
2차 실패 → 5분 후 재시도
3차 실패 → 30분 후 재시도
4차 실패 → Dead Letter Queue → 관리자 알림
```

---

### 8-4. 실시간 대시보드

클라이언트가 번역 진행 상태를 실시간으로 확인할 수 있는 SSE 기반 상태 스트림을 제공한다.

```
GET /jobs/:id/stream   → SSE 연결

event: STATUS_UPDATE
data: { "status": "IN_PROGRESS", "progress": 42, "updatedAt": "..." }

event: COMPLETED
data: { "downloadUrl": "https://...", "completedAt": "..." }
```

---

## 9. 폴더 구조 (Next.js + FastAPI)

```
/
├── apps/
│   ├── web/                        # Next.js 14 (App Router)
│   │   ├── app/
│   │   │   ├── jobs/
│   │   │   │   ├── [id]/page.tsx   # 작업 상세 + 실시간 대시보드
│   │   │   │   └── new/page.tsx    # 의뢰 등록
│   │   │   └── dashboard/page.tsx
│   │   └── lib/
│   │       └── sse.ts              # SSE 훅
│   │
│   └── api/                        # Python + FastAPI
│       ├── main.py                 # FastAPI 앱 진입점
│       ├── routers/
│       │   ├── jobs.py
│       │   ├── quotes.py
│       │   ├── assignments.py
│       │   └── notifications.py
│       ├── services/
│       │   ├── quote_service.py
│       │   ├── assign_service.py
│       │   ├── notification_service.py
│       │   └── state_machine.py    # FSM 단일 관리
│       ├── workers/                # Celery 워커
│       │   ├── quote_worker.py
│       │   ├── assign_worker.py
│       │   └── notify_worker.py
│       ├── models/                 # SQLAlchemy 모델
│       │   ├── job.py
│       │   ├── quote.py
│       │   ├── translator.py
│       │   └── notification.py
│       ├── schemas/                # Pydantic 스키마
│       │   ├── job.py
│       │   └── quote.py
│       └── db/
│           ├── session.py          # DB 연결 설정
│           └── migrations/         # Alembic 마이그레이션
│
└── packages/
    └── shared/                     # 공통 타입, 상수
        └── enums.py                # 상태값 공유
```

---

## 10. 단계별 개발 로드맵

### Phase 1 — 기반 구축 (2주)

- [ ] DB 스키마 작성 및 마이그레이션 설정
- [ ] FSM(상태 머신) 서비스 구현
- [ ] JWT 인증 미들웨어
- [ ] 파일 업로드 → S3 연동

### Phase 2 — 핵심 서비스 (3주)

- [ ] Auto Quote Service (비동기 처리 + TM 연동)
- [ ] Auto Assign Service (점수 계산 + 수락/거절 플로우)
- [ ] Redis 큐 + Celery 워커 구성

### Phase 3 — 알림 · 안정성 (2주)

- [ ] Notification Service (이메일 + Slack + Webhook)
- [ ] 중복 방지 (Redis SETNX)
- [ ] 재시도 전략 + Dead Letter Queue
- [ ] 관리자 알림 (3회 재배정 실패 시)

### Phase 4 — 실시간 · 완성도 (2주)

- [ ] SSE 기반 실시간 대시보드
- [ ] 감사 로그(Audit Log) 구현
- [ ] Rate Limiting 미들웨어
- [ ] 통합 테스트 + 부하 테스트

---

## 11. 기대 효과

| 항목 | 기존 | 개선 후 |
|------|------|---------|
| 견적 산정 시간 | 수 시간 (수작업) | 수 분 (자동 비동기) |
| 작업자 배정 기준 | 담당자 경험 | 퍼포먼스 점수 기반 |
| 완료 확인 방식 | 수동 확인 | 이벤트 자동 감지 |
| 운영 개입 | 상시 필요 | 예외 상황 한정 |

---

## 12. 리스크 및 대응

| 리스크 | 가능성 | 대응 |
|--------|--------|------|
| 견적 API 타임아웃 (대용량 파일) | 높음 | 비동기 처리 + SSE 응답 |
| 알림 중복 발송 | 중간 | Redis SETNX 락 |
| 번역가 전원 거절 | 낮음 | 3회 후 관리자 에스컬레이션 |
| FSM 상태 불일치 | 중간 | DB 트랜잭션 + 이벤트 로그 |
| QA 무한 루프 | 낮음 | 최대 재시도 횟수 제한 (3회) |
| LLM API 도입 | 검토 후 제외 | 번역 파일 특성상 외부 API 전송은 고객사 NDA 위반 가능성이 높고, 미전환 견적 요청에도 비용이 발생하여 비용 구조가 불리함. 온프레미스 모델(Ollama 등) 연동은 추후 확장 옵션으로 유보 |
| 로컬 모델 파인튜닝 도입 | 검토 후 유보 | 초기 비용(서버·학습) 약 600만원, 월 운영비 약 35만원 소요. AI가 PM 업무를 대체하는 것이 아니라 시간을 확보해주는 구조이므로, 그 시간을 매출로 연결할 수 있는 상황인지에 따라 ROI가 달라짐. 현 단계에서는 도입 근거가 불명확하여 유보 |

---

## 13. 면접·포폴 핵심 포인트 정리

> "견적, 배정, 알림을 독립 서비스로 분리하고 이벤트 기반으로 연결했습니다.
> 번역가를 상태 기반 리소스로 모델링하여 실시간 부하를 배정 점수에 반영하고,
> 상태 전이는 FSM으로 단일 관리하여 일관성을 보장했습니다.
> 알림은 Redis 락과 지수 백오프 재시도로 중복·유실을 모두 방지했습니다."

설계 차별점 요약:

- 단순 CRUD가 아닌 **이벤트 소싱** 구조 (job_events 테이블)
- 번역가를 **상태 기반 리소스**로 모델링 (AVAILABLE / BUSY / OVERLOADED / OFFLINE)
- **workload_ratio** 기반 실시간 과부하 감지 및 자동 필터링
- 견적에 **TM 매칭률** 반영으로 업계 표준 모델링
- 배정에 **수락/거절 + 자동 재배정** 플로우 설계
- 알림에 **DLQ + 지수 백오프**로 운영 안정성 확보
- SSE 기반 **실시간 대시보드**로 기술 스택 활용 근거 명확화
