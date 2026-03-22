"""
Translation Memory(TM) 매칭 서비스.
PostgreSQL pg_trgm 확장의 similarity() 함수로 문자열 유사도를 측정.

업계 표준 CAT tool 방식: 의미(벡터) 기반이 아닌 글자 재사용률 기반.
NDA 리스크 없이 Supabase 내에서 처리 (외부 AI API 미사용).

tm_segments 테이블 DDL:
    CREATE TABLE tm_segments (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        source_lang VARCHAR(10) NOT NULL,
        target_lang VARCHAR(10) NOT NULL,
        source_text TEXT NOT NULL,
        target_text TEXT NOT NULL,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX ON tm_segments USING GIN (source_text gin_trgm_ops);
"""

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# similarity() 함수 결과가 이 임계값 이상인 세그먼트만 TM 매칭 대상으로 판단
DEFAULT_SIMILARITY_THRESHOLD = 0.5

# TM 매칭 결과 최대 반환 개수
MAX_SIMILAR_SEGMENTS = 5


async def calculate_tm_match_rate(
    db: AsyncSession,
    source_text: str,
    source_lang: str,
    target_lang: str,
) -> float:
    """
    입력 텍스트에 대한 TM 최대 매칭률 계산.

    PostgreSQL similarity() 함수(pg_trgm)로 문자열 유사도 측정.
    같은 언어쌍 세그먼트 중 similarity > 0.5인 것만 대상.
    최대 similarity 값을 반환 (0.0 ~ 1.0).

    반환값을 quote_service._calculate_tm_discount()에 그대로 전달하여
    업계 표준 CAT tool 방식 할인율 계산에 활용.
    """
    # pg_trgm similarity() 함수로 소스 텍스트와 TM 세그먼트 비교
    # 언어쌍 필터링 후 임계값 이상인 것 중 최대값 반환
    stmt = text("""
        SELECT COALESCE(MAX(similarity(source_text, :source_text)), 0.0) AS max_similarity
        FROM tm_segments
        WHERE source_lang = :source_lang
          AND target_lang = :target_lang
          AND similarity(source_text, :source_text) > :threshold
    """)

    result = await db.execute(stmt, {
        "source_text": source_text,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "threshold": DEFAULT_SIMILARITY_THRESHOLD,
    })
    row = result.fetchone()

    # 매칭 결과가 없으면 0.0 반환 (할인 없음)
    if row is None or row.max_similarity is None:
        return 0.0

    return float(row.max_similarity)


async def find_similar_segments(
    db: AsyncSession,
    source_text: str,
    source_lang: str,
    target_lang: str,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> list[dict[str, Any]]:
    """
    입력 텍스트와 유사한 TM 세그먼트 목록 조회.

    GIN 인덱스(gin_trgm_ops)를 활용하여 전체 스캔 없이 고속 검색.
    similarity 내림차순으로 상위 5개 반환.

    반환 형식:
    [
        {
            "source": str,       # TM 원문 텍스트
            "target": str,       # TM 번역문 텍스트
            "similarity": float, # 유사도 (0.0 ~ 1.0)
            "created_at": datetime,
        },
        ...
    ]
    """
    # GIN 인덱스 활성화: set_limit()으로 similarity 검색 임계값 설정
    # pg_trgm은 set_limit() 이상의 유사도만 인덱스로 필터링
    await db.execute(text("SELECT set_limit(:threshold)"), {"threshold": threshold})

    stmt = text("""
        SELECT
            source_text AS source,
            target_text AS target,
            similarity(source_text, :source_text) AS similarity,
            created_at
        FROM tm_segments
        WHERE source_lang = :source_lang
          AND target_lang = :target_lang
          AND source_text % :source_text
        ORDER BY similarity(source_text, :source_text) DESC
        LIMIT :limit
    """)

    result = await db.execute(stmt, {
        "source_text": source_text,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "limit": MAX_SIMILAR_SEGMENTS,
    })
    rows = result.fetchall()

    return [
        {
            "source": row.source,
            "target": row.target,
            "similarity": float(row.similarity),
            "created_at": row.created_at,
        }
        for row in rows
    ]
