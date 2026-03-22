"""
SQLAlchemy 비동기 세션 설정.
FastAPI의 lifespan + Depends 패턴으로 요청당 세션을 관리.
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings

# 비동기 엔진 생성 — asyncpg 드라이버 사용 (PostgreSQL 전용)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,   # DEBUG 모드에서 SQL 쿼리 출력
    pool_pre_ping=True,    # 연결 유효성 사전 확인 (재연결 자동화)
    pool_size=10,
    max_overflow=20,
)

# 세션 팩토리 — 요청마다 새 세션 생성
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # commit 후 객체 재로드 없이 사용 가능
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Depends()로 주입되는 DB 세션 의존성.
    요청 처리 완료 후 세션 자동 닫기 (컨텍스트 매니저 보장).
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
