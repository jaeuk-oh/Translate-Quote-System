# 번역 플랫폼 — 자동 견적 · 배정 · 알림 시스템

번역 의뢰 접수부터 견적 산정, 번역가 배정, 작업 완료 알림까지
전 과정을 운영 개입 없이 자동화하는 플랫폼.

---

## 목차

1. [프로젝트 개요](#프로젝트-개요)
2. [기술 스택 및 선택 이유](#기술-스택-및-선택-이유)
3. [아키텍처](#아키텍처)
4. [핵심 설계 결정](#핵심-설계-결정)
5. [빠른 시작](#빠른-시작)
6. [API 문서](#api-문서)
7. [개발 로드맵](#개발-로드맵)

---

## 프로젝트 개요

기존 번역 프로세스의 비효율을 해결한다.

| 기존 방식 | 개선 후 |
|-----------|---------|
| 견적 산정 수 시간 (수작업) | 수 분 (비동기 자동 계산) |
| 작업자 배정 — 담당자 경험 의존 | 퍼포먼스 점수 기반 자동 배정 |
| 완료 확인 수동 | 이벤트 자동 감지 + 알림 |
| 상시 운영 개입 필요 | 예외 상황 한정 |

---

## 기술 스택 및 선택 이유

### 백엔드: Python + FastAPI

**선택 이유:**
- `async/await` 기반 비동기 처리로 견적 계산, 파일 업로드 등 I/O 집약 작업을 논블로킹으로 처리
- Pydantic v2 통합으로 요청/응답 스키마 자동 검증 및 Swagger 문서 자동 생성
- SSE(Server-Sent Events) 엔드포인트를 `StreamingResponse`로 간결하게 구현 가능
- Django보다 경량이며, 마이크로서비스 분리 시 독립 배포에 적합

### 데이터베이스: PostgreSQL (Supabase)

**선택 이유:**
- FSM 상태 전이 시 `SELECT FOR UPDATE` 행 잠금으로 동시 전이 충돌 방지
- JSONB 타입으로 `job_events.metadata` 비정형 데이터를 별도 테이블 없이 저장
- 트랜잭션 보장으로 상태 변경 + 이벤트 기록을 원자적으로 처리
- Supabase 선택 이유: pg_trgm, pgcrypto 확장이 기본 내장, 인프라 관리 최소화

### TM 매칭: pg_trgm (PostgreSQL 확장)

**선택 이유:**
- TM(Translation Memory)은 **의미적 유사도가 아닌 글자 재사용률**을 측정해야 함
  - 예: "계약서를 제출하시오" vs "계약서를 제출하십시오" → 95% 글자 유사도
  - 벡터 유사도(pgvector)는 의미가 같은 전혀 다른 표현도 높은 점수를 줘서 할인 과적용 위험
- pg_trgm의 `similarity()` 함수가 업계 표준 CAT(Computer-Assisted Translation) tool 방식과 동일한 측정 방식
- 번역 파일 내용을 외부 API(OpenAI 등)로 전송하지 않아 고객사 NDA 위반 리스크 없음
- PostgreSQL 내장 확장이므로 추가 인프라 불필요

### 비동기 작업 큐: Redis + Celery

**선택 이유:**
- **견적 계산**과 **번역가 배정**은 수 초~수 분이 소요되는 작업 → API 응답 블로킹 금지
- Celery의 `task_acks_late=True`로 워커 크래시 시 작업 자동 재큐 (유실 방지)
- 지수 백오프 재시도(`countdown = delay × 2^attempt`)를 코드 레벨에서 간결하게 구현
- Celery Beat으로 배정 만료 체크(24시간 타임아웃)를 별도 cron 없이 관리
- RabbitMQ 대비 운영 단순성 우선 (Redis를 캐시/락에도 동시 활용)

### 파일 스토리지: AWS S3 (또는 MinIO)

**선택 이유:**
- 번역 원본 파일과 결과물을 DB에 저장하면 용량 및 성능 문제 발생
- S3 presigned URL로 클라이언트가 직접 다운로드 (API 서버 트래픽 절감)
- 로컬 개발 시 MinIO로 동일한 S3 API 사용 가능 (코드 변경 없음)
- NDA 관점: 파일은 S3에만 저장되며, TM 분석은 pg_trgm이 DB 내에서 처리 (외부 전송 없음)

### 인증: JWT + Refresh Token

**선택 이유:**
- 세션 기반 인증은 서버 상태 저장 필요 → 수평 확장 시 세션 공유 문제
- JWT Access Token(30분) + Refresh Token(7일) 이중 토큰으로 보안과 UX 균형
- Access Token 만료 시 Refresh Token으로 자동 재발급 → 사용자 재로그인 최소화
- python-jose 라이브러리로 HS256 서명 검증

### 실시간 상태 스트림: SSE (Server-Sent Events)

**선택 이유:**
- 견적 계산 완료, 배정 확정 등 서버 → 클라이언트 단방향 알림에 최적
- WebSocket 대비 구현 단순 (일반 HTTP, 프록시 친화적)
- HTTP/2 멀티플렉싱과 자연스럽게 호환
- 클라이언트가 연결 끊기면 자동 재연결 시도 (브라우저 기본 동작)

### 이메일: Resend

**선택 이유:**
- 무료 3,000건/월으로 초기 운영 비용 없음
- Python SDK가 직관적이며 설정 최소화
- SendGrid 대비 API 단순성 우선

---

## 아키텍처

```
[클라이언트 / Next.js]
       │  REST + SSE
       ▼
[FastAPI API 서버]
       │  JWT 인증 미들웨어
       ├──────────────────────────────────────┐
       ▼                                      ▼
[Redis Celery 큐]                      [PostgreSQL]
  ┌────┴──────────────┐                      │
  ▼                   ▼                      │
[견적 워커]      [배정 워커]           [pg_trgm TM 매칭]
  └──────────┬────────┘
             ▼
    [FSM 상태 머신]
             │  상태 전이 + 이벤트 기록
             ▼
   [알림 서비스] (Phase 3)
   이메일 / Slack / Webhook
             │
             ▼
    [재시도 큐 + DLQ]

[S3]  — 번역 파일 원본/결과물
[Redis] — Celery 브로커 + 중복 방지 락
```

---

## 핵심 설계 결정

### 1. FSM 단일 관리

모든 상태 전이는 `services/state_machine.py`의 `transition()` 함수만 사용.

```
REQUESTED → QUOTE_PENDING → QUOTED → PENDING_ACCEPTANCE
→ ASSIGNED → IN_PROGRESS → REVIEW → QA → COMPLETED
                                         └→ IN_PROGRESS (QA 실패, 최대 3회)
```

- DB 트랜잭션 내에서 `job.status` 업데이트 + `job_events` 기록을 원자적으로 처리
- 허용되지 않은 전이 시 `FSMException` 발생 + 롤백
- `SELECT FOR UPDATE` 행 잠금으로 동시 전이 경쟁 조건 차단

### 2. 번역가를 상태 기반 리소스로 모델링

```python
workload_ratio = current_load / max_load

AVAILABLE   : workload_ratio = 0       # 즉시 배정 가능
BUSY        : 0 < ratio < 1.0         # 작업 중이나 여유 있음
OVERLOADED  : ratio >= 1.0            # 배정 불가 (자동 제외)
OFFLINE     : 비활성                  # 배정 불가
```

### 3. 번역가 배정 점수 공식

```
score = (quality_score × 0.40)
      + (on_time_rate  × 0.30)
      + (availability  × 0.20)
      + (workload_inv  × 0.10)

workload_inv = 1 / (1 + current_load)   ← 0 나누기 방지
```

가중치 설계 근거:
- 품질(0.40): 번역 정확도가 최우선
- 납기 준수(0.30): 납기 미준수는 클라이언트 신뢰 직결
- 가용성(0.20): 즉시 시작 가능 여부
- 부하(0.10): 과부하 방지 보조 지표

### 4. TM 할인율 (업계 표준 CAT tool 방식)

```
100% 일치 → 무료 (tm_discount = 0.0)
75~99%    → 70% 할인 (tm_discount = 0.3)
50~74%    → 40% 할인 (tm_discount = 0.6)
< 50%     → 할인 없음 (tm_discount = 1.0)
```

글자 기반 유사도 측정 — 의미적 유사도(벡터)가 아닌 실제 문자 재사용률 기준.

### 5. 재배정 전략

- 배정 후 24시간 내 미응답 → `EXPIRED` 처리 + 2순위 번역가로 재배정
- 번역가 거절 → 즉시 다음 순위로 재배정
- 최대 3회 재배정 실패 → 관리자 Slack 알림 (에스컬레이션)

---

## 빠른 시작

### 1. 환경 변수 설정

```bash
cp .env.example .env
# .env 파일을 열어 실제 값 입력
```

### 2. Docker Compose 실행

```bash
docker-compose up -d
```

### 3. 마이그레이션 실행

```bash
docker-compose exec api alembic upgrade head
```

### 4. API 문서 확인

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## API 문서

### 인증

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/auth/register` | 회원가입 |
| POST | `/auth/login` | 로그인 (토큰 발급) |
| POST | `/auth/refresh` | Access Token 재발급 |

### 번역 작업

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/jobs` | 번역 의뢰 등록 |
| GET | `/jobs/{id}` | 작업 상세 조회 |
| POST | `/jobs/{id}/upload` | 파일 업로드 (S3) |
| GET | `/jobs/{id}/events` | FSM 상태 이력 |
| GET | `/jobs/{id}/stream` | SSE 실시간 상태 스트림 |

### 견적

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/jobs/{id}/quote` | 견적 조회 |
| POST | `/jobs/{id}/quote/approve` | 견적 승인/거절 |

### 배정

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/jobs/{id}/assign/recommend` | 추천 번역가 목록 |
| POST | `/jobs/{id}/assign` | 배정 확정 |
| GET | `/jobs/{id}/assignments` | 배정 이력 |
| POST | `/assignments/{id}/respond` | 수락/거절 응답 |

---

## 개발 로드맵

| Phase | 기간 | 상태 | 핵심 |
|-------|------|------|------|
| Phase 1 | 2주 | 완료 | 모노레포 초기화, DB 마이그레이션, FSM, JWT, S3 업로드 |
| Phase 2 | 3주 | 예정 | Auto Quote TM 연동, Auto Assign 고도화, Celery 워커 |
| Phase 3 | 2주 | 예정 | 알림 서비스, Redis SETNX 중복 방지, DLQ + 지수 백오프 |
| Phase 4 | 2주 | 예정 | SSE 대시보드, 감사 로그, Rate Limit, 통합/부하 테스트 |
