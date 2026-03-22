"""
pytest 공유 픽스처 모음.
각 테스트는 독립 트랜잭션 내에서 실행되며 테스트 종료 시 롤백.
PostgreSQL(asyncpg) 사용 — 실제 DB와 동일한 환경에서 테스트.

.env.test 파일 예시:
  DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/translate_test
  REDIS_URL=redis://localhost:6379/15
  JWT_SECRET=test-secret-key
"""

import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis as fakeredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# .env.test 환경 변수 로드 (DATABASE_URL 등)
from dotenv import load_dotenv
load_dotenv(".env.test", override=True)

from core.config import settings
from db.base import Base
from db.session import get_db
from main import app


# ── 이벤트 루프 픽스처 ─────────────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop():
    """
    세션 범위 이벤트 루프.
    DB 엔진을 세션 전체에서 재사용하기 위해 필요.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── DB 엔진 / 세션 팩토리 (세션 범위) ──────────────────────────────
@pytest_asyncio.fixture(scope="session")
async def async_engine():
    """
    테스트용 PostgreSQL 비동기 엔진.
    세션 시작 시 테이블 생성, 종료 시 전체 삭제.
    """
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )

    async with engine.begin() as conn:
        # 테스트 시작 시 스키마 초기화
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        # 테스트 종료 후 스키마 삭제
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    테스트마다 독립 트랜잭션 내에서 실행.
    테스트 종료 시 ROLLBACK으로 DB 상태 복원 (테스트 격리).
    """
    # 중첩 트랜잭션(SAVEPOINT) 사용으로 외부 트랜잭션 보존
    async with async_engine.connect() as conn:
        await conn.begin()
        # SAVEPOINT 생성
        await conn.begin_nested()

        session_factory = async_sessionmaker(
            bind=conn,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        async with session_factory() as session:
            yield session

        # 테스트 종료 후 ROLLBACK (변경사항 원상 복원)
        await conn.rollback()


@pytest_asyncio.fixture
async def test_client(async_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    FastAPI 테스트 클라이언트 (httpx AsyncClient).
    get_db 의존성을 테스트 세션으로 오버라이드.
    """

    async def override_get_db():
        yield async_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    # 오버라이드 정리
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def mock_redis():
    """
    fakeredis 기반 Redis 목 픽스처.
    실제 Redis 서버 없이 Rate Limit, 락, pub/sub 테스트 가능.
    """
    # fakeredis 서버 인스턴스 생성 (인메모리)
    fake_server = fakeredis.FakeServer()
    redis_client = fakeredis.FakeRedis(server=fake_server, decode_responses=True)

    with patch("redis.asyncio.from_url", return_value=redis_client):
        yield redis_client

    await redis_client.aclose()
