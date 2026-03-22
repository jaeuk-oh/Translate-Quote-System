# CLAUDE.md — Translate Quote System

Claude Code가 이 프로젝트에서 따라야 할 규칙과 컨텍스트 정리.

---

## 프로젝트 개요

번역 의뢰 → 견적 → 작업자 배정 → 완료 알림까지의 전 과정을 자동화하는 번역 플랫폼.
운영 개입 없이 동작하는 것이 핵심 목표. 포트폴리오 / 면접용 프로젝트.

---

## 기술 스택

| 영역 | 기술 | 선택 이유 |
|------|------|-----------|
| 프론트엔드 | Next.js 14 (App Router) | SSR, SSE 지원 |
| 백엔드 | Python + FastAPI | 비동기, Swagger 자동 문서화 |
| DB + Storage | Supabase (PostgreSQL + Storage) | 인프라 단순화, pg_trgm 내장 |
| TM 매칭 | pg_trgm (Supabase 내) | 글자 기반 유사도 → 업계 표준 CAT tool 방식. 벡터(의미) 기반이 아닌 글자 재사용률을 측정해야 하므로 pgvector 대신 선택. 외부 API 전송 없어 NDA 리스크 없음 |
| 큐 / 캐시 | Redis + Celery | 비동기 작업, 재시도 내장 |
| 이메일 | Resend | 무료 3,000건/월, Python SDK, 설정 단순 |
| 실시간 | SSE (Server-Sent Events) | 단방향 상태 push에 최적 |
| 인증 | JWT + Refresh Token | 무상태 인증 |

---

## 개발 규칙

### 커밋 & 푸시
- 기능 단위로 자동 커밋 + 푸시 (`origin main`)
- 커밋 메시지는 **한글**, 제목 + 간략한 설명(body) 포함
- `Co-Authored-By: Claude ...` 트레일러 **절대 포함하지 않음**

```
feat: FSM 상태 머신 구현

job 상태 전이 로직 및 전이 실패 시 롤백 처리 구현.
모든 전이는 job_events 테이블에 이력으로 기록됨.
```

### 코드 주석
- 핵심 로직(FSM 전이, 견적 계산, 배정 점수, 재시도 전략 등)에는 **한글 주석** 필수
- 자명한 CRUD나 단순 코드에는 달지 않음

```python
# 번역가 과부하 판단: workload_ratio가 1.0 이상이면 배정 대상에서 제외
workload_ratio = current_load / max_load

# TM 매칭률에 따라 할인율 결정 (업계 표준 CAT tool 방식)
# 100% 일치 → 무료, 75~99% → 70% 할인, 50~74% → 40% 할인, 미만 → 할인 없음
```

### README 문서화
- 모든 기술/라이브러리/알고리즘 선택에 대해 **"왜 이걸 썼는지"를 README에 명시**
- 코드 작성과 동시에 관련 README 섹션 업데이트

---

## 미결 사항

- 실행 환경 (Docker Compose 단독 vs 혼합) → 나중에 결정
- Slack Webhook URL, AWS/Supabase 키 → `.env.example` 플레이스홀더로 관리

---

## 개발 로드맵 요약

| Phase | 기간 | 핵심 |
|-------|------|------|
| Phase 1 | 2주 | 모노레포 초기화, DB 마이그레이션, FSM, JWT, S3 업로드 |
| Phase 2 | 3주 | Auto Quote, TM 매칭, Auto Assign, Celery 워커 |
| Phase 3 | 2주 | 알림 서비스, 중복 방지(Redis SETNX), DLQ + 지수 백오프 |
| Phase 4 | 2주 | SSE 대시보드, 감사 로그, Rate Limit, 통합/부하 테스트 |
