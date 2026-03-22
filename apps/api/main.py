"""
FastAPI 애플리케이션 진입점.
라우터 등록, CORS 설정, Swagger 자동 문서화 제공.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from routers import auth, jobs, quotes, assignments


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    앱 시작/종료 시 실행되는 lifespan 핸들러.
    DB 연결 풀 초기화 및 정리를 담당.
    """
    # 시작 시 — DB 연결 확인 (필요 시 마이그레이션 실행 여부 로깅)
    print("번역 플랫폼 API 서버 시작")
    yield
    # 종료 시 — 연결 풀 정리
    from db.session import engine
    await engine.dispose()
    print("번역 플랫폼 API 서버 종료")


app = FastAPI(
    title="번역 플랫폼 API",
    description=(
        "번역 의뢰 → 자동 견적 → 번역가 배정 → 완료 알림 전 과정 자동화 플랫폼.\n\n"
        "FSM 기반 상태 관리, TM 매칭 견적, 성과 점수 기반 자동 배정."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS 설정 ─────────────────────────────────────────────────
# 개발 환경에서는 모든 오리진 허용; 운영 환경에서는 허용 도메인 명시 권장
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else ["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 라우터 등록 ──────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(quotes.router)
app.include_router(assignments.router)


@app.get("/health", tags=["헬스체크"])
async def health_check():
    """서버 상태 확인 — 로드밸런서 헬스체크용"""
    return {"status": "ok", "service": "translate-platform-api"}
