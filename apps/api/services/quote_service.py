"""
자동 견적 계산 서비스.
가격 공식: price = word_count × base_rate × difficulty × deadline_multiplier × tm_discount
TM(Translation Memory) 매칭률을 반영한 업계 표준 CAT tool 방식 할인 적용.
신뢰도(confidence)는 난이도 인자들의 분산으로 계산 (인자 불확실성 반영).
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from models.job import Job
from models.quote import Quote

# ── 언어쌍별 기본 단가 (원/단어) ───────────────────────────────
# 실제 운영 시 DB 또는 설정 파일로 관리 권장
BASE_RATES: dict[str, float] = {
    "ko-en": 80.0,
    "en-ko": 70.0,
    "ko-ja": 90.0,
    "ja-ko": 80.0,
    "ko-zh": 85.0,
    "zh-ko": 75.0,
    "en-ja": 100.0,
    "default": 100.0,
}

# ── 콘텐츠 유형별 난이도 가중치 ────────────────────────────────
CONTENT_DIFFICULTY: dict[str, float] = {
    "legal": 1.5,       # 법률 문서: 최고 난이도
    "medical": 1.4,     # 의료 문서
    "technical": 1.3,   # 기술 문서
    "marketing": 1.1,   # 마케팅 콘텐츠
    "general": 1.0,     # 일반 문서 (기준)
}

# ── 품질 등급별 가중치 ─────────────────────────────────────────
QUALITY_WEIGHTS: dict[str, float] = {
    "translation": 1.0,   # 번역만
    "review": 1.4,        # 번역 + 검수
    "dtp": 1.7,           # 번역 + 검수 + 편집
}


def _get_base_rate(source_lang: str, target_lang: str) -> float:
    """언어쌍 기본 단가 조회 — 등록되지 않은 언어쌍은 기본값 적용"""
    key = f"{source_lang}-{target_lang}"
    return BASE_RATES.get(key, BASE_RATES["default"])


def _calculate_deadline_multiplier(deadline: Optional[datetime]) -> float:
    """
    마감 촉박도에 따른 가격 승수 계산.
    - 3일 미만: 1.5배 (긴급)
    - 7일 미만: 1.2배 (빠름)
    - 14일 미만: 1.0배 (표준)
    - 14일 이상: 0.9배 (여유)
    """
    if deadline is None:
        return 1.0

    now = datetime.now(timezone.utc)
    # 타임존 정보가 없는 경우 UTC로 가정
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)

    days_remaining = (deadline - now).days

    if days_remaining < 3:
        return 1.5
    elif days_remaining < 7:
        return 1.2
    elif days_remaining < 14:
        return 1.0
    else:
        return 0.9


def _calculate_tm_discount(tm_match_rate: float) -> float:
    """
    TM(Translation Memory) 매칭률에 따른 할인 계수.
    업계 표준 CAT tool 방식:
    - 100% 일치 → 무료 (계수 0.0)
    - 75~99% → 70% 할인 (계수 0.3)
    - 50~74% → 40% 할인 (계수 0.6)
    - 50% 미만 → 할인 없음 (계수 1.0)

    글자 재사용률 기반이므로 의미적 유사도(벡터)가 아닌
    pg_trgm의 문자열 유사도 측정 결과를 사용.
    """
    if tm_match_rate >= 1.0:
        return 0.0   # 완전 일치 — 무료
    elif tm_match_rate >= 0.75:
        return 0.3   # 70% 할인
    elif tm_match_rate >= 0.50:
        return 0.6   # 40% 할인
    else:
        return 1.0   # 할인 없음


def _calculate_difficulty(content_type: Optional[str], quality_level: Optional[str]) -> float:
    """
    종합 난이도 승수 계산.
    content_type × quality_level 조합으로 결정.
    """
    content_w = CONTENT_DIFFICULTY.get(content_type or "general", 1.0)
    quality_w = QUALITY_WEIGHTS.get(quality_level or "translation", 1.0)
    return content_w * quality_w


def _calculate_confidence(difficulty: float, deadline_multiplier: float, tm_match_rate: float) -> float:
    """
    견적 신뢰도 계산 (0.0 ~ 1.0).
    난이도 인자들의 편차가 클수록 신뢰도 하락.
    모든 인자가 1.0에 가까울수록 예측 신뢰도 상승.
    """
    # 각 인자의 기준값(1.0) 대비 편차
    factors = [difficulty, deadline_multiplier, 1.0 + (1.0 - tm_match_rate)]
    mean = sum(factors) / len(factors)
    variance = sum((f - mean) ** 2 for f in factors) / len(factors)
    # 분산이 클수록 신뢰도 감소 (0.3을 최대 분산 기준으로 정규화)
    confidence = max(0.0, 1.0 - variance / 0.3)
    return round(min(confidence, 1.0), 3)


def _estimate_hours(word_count: int, difficulty: float) -> float:
    """
    예상 작업 시간 계산.
    숙련 번역가 기준 시간당 평균 300단어 처리,
    난이도 승수 적용으로 조정.
    """
    base_words_per_hour = 300.0
    adjusted_rate = base_words_per_hour / difficulty
    hours = word_count / adjusted_rate
    return round(hours, 1)


def calculate_quote(
    word_count: int,
    source_lang: str,
    target_lang: str,
    content_type: Optional[str] = None,
    quality_level: Optional[str] = None,
    deadline: Optional[datetime] = None,
    tm_match_rate: float = 0.0,
) -> dict:
    """
    견적 계산 메인 함수.

    반환 딕셔너리:
    - estimated_price: 최종 견적 금액 (원)
    - estimated_hours: 예상 작업 시간
    - confidence: 신뢰도 (0~1)
    - difficulty: 난이도 승수
    - deadline_multiplier: 마감 승수
    - tm_match_rate: TM 매칭률
    - word_count: 단어 수
    """
    base_rate = _get_base_rate(source_lang, target_lang)
    difficulty = _calculate_difficulty(content_type, quality_level)
    deadline_multiplier = _calculate_deadline_multiplier(deadline)

    # TM 할인 계수 (0.0 = 무료, 1.0 = 할인 없음)
    tm_discount = _calculate_tm_discount(tm_match_rate)

    # 최종 가격 공식:
    # price = word_count × base_rate × difficulty × deadline_multiplier × tm_discount
    price = word_count * base_rate * difficulty * deadline_multiplier * tm_discount
    estimated_hours = _estimate_hours(word_count, difficulty)
    confidence = _calculate_confidence(difficulty, deadline_multiplier, tm_match_rate)

    return {
        "estimated_price": round(Decimal(str(price)), 2),
        "estimated_hours": Decimal(str(estimated_hours)),
        "confidence": Decimal(str(confidence)),
        "difficulty": Decimal(str(round(difficulty, 3))),
        "deadline_multiplier": Decimal(str(deadline_multiplier)),
        "tm_match_rate": Decimal(str(tm_match_rate)),
        "word_count": word_count,
    }


async def create_quote(
    db: AsyncSession,
    job: Job,
    tm_match_rate: float = 0.0,
) -> Quote:
    """
    견적 계산 결과를 DB에 저장.
    Celery 워커(quote_worker.py)에서 비동기로 호출됨.
    """
    if not job.word_count:
        raise ValueError("word_count가 없어 견적을 계산할 수 없습니다.")

    calc = calculate_quote(
        word_count=job.word_count,
        source_lang=job.source_lang,
        target_lang=job.target_lang,
        content_type=job.content_type,
        quality_level=job.quality_level,
        deadline=job.deadline,
        tm_match_rate=tm_match_rate,
    )

    quote = Quote(
        job_id=job.id,
        status="COMPLETED",
        currency="KRW",
        **calc,
    )
    db.add(quote)
    await db.flush()
    return quote
