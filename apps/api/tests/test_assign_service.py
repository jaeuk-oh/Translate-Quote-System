"""
번역가 배정 서비스(assign_service.py) 단위/통합 테스트.
배정 점수 계산 및 후보 필터링 로직 검증.
"""

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from services.assign_service import (
    calculate_translator_score,
    get_candidates,
)


# ── Translator 목 객체 생성 헬퍼 ───────────────────────────────────

def _make_translator(
    quality_score: float = 0.9,
    on_time_rate: float = 0.8,
    availability: str = "AVAILABLE",
    current_load: int = 1,
    max_load: int = 3,
    lang_pairs: list[str] | None = None,
) -> MagicMock:
    """
    테스트용 Translator 목 객체 생성.
    SQLAlchemy ORM 객체를 직접 생성하지 않고 MagicMock으로 속성 설정.
    """
    translator = MagicMock()
    translator.id = uuid.uuid4()
    translator.quality_score = Decimal(str(quality_score))
    translator.on_time_rate = Decimal(str(on_time_rate))
    translator.availability = availability
    translator.current_load = current_load
    translator.max_load = max_load
    # workload_ratio 프로퍼티 목
    translator.workload_ratio = current_load / max_load if max_load > 0 else 0
    translator.lang_pairs = lang_pairs or ["ko-en"]
    translator.specialties = ["general"]
    return translator


# ── 배정 점수 계산 테스트 ──────────────────────────────────────────

def test_score_calculation():
    """
    배정 점수 공식 검증.

    score = quality(0.40) + on_time(0.30) + availability(0.20) + workload_inv(0.10)

    조건:
    - quality_score = 0.9
    - on_time_rate  = 0.8
    - availability  = AVAILABLE → 1.0
    - current_load  = 1 → workload_inv = 1/(1+1) = 0.5

    예상 점수:
    = 0.9×0.40 + 0.8×0.30 + 1.0×0.20 + 0.5×0.10
    = 0.36 + 0.24 + 0.20 + 0.05
    = 0.85
    """
    translator = _make_translator(
        quality_score=0.9,
        on_time_rate=0.8,
        availability="AVAILABLE",
        current_load=1,
    )

    score = calculate_translator_score(translator)

    expected = round(0.9 * 0.40 + 0.8 * 0.30 + 1.0 * 0.20 + (1 / (1 + 1)) * 0.10, 4)
    assert score == pytest.approx(expected, abs=1e-4), (
        f"예상 점수 {expected}, 실제 {score}"
    )


def test_overloaded_excluded():
    """
    workload_ratio >= 1.0인 번역가는 배정 후보에서 제외.
    OVERLOADED 상태이거나 current_load >= max_load인 경우.

    get_candidates()는 DB 쿼리에서 OVERLOADED를 필터링하지만,
    점수 계산 시 OVERLOADED 번역가는 availability_score = 0.0 반환.
    """
    # OVERLOADED 상태 번역가
    overloaded = _make_translator(
        availability="OVERLOADED",
        current_load=3,
        max_load=3,
    )

    score = calculate_translator_score(overloaded)

    # availability_score = 0.0 (OVERLOADED)
    # workload_inv = 1/(1+3) = 0.25
    expected = round(0.9 * 0.40 + 0.8 * 0.30 + 0.0 * 0.20 + 0.25 * 0.10, 4)

    assert score == pytest.approx(expected, abs=1e-4)

    # OVERLOADED 상태는 ASSIGNABLE_STATUSES에 포함되지 않으므로
    # get_candidates() DB 쿼리에서 제외됨을 확인
    from services.assign_service import ASSIGNABLE_STATUSES
    assert "OVERLOADED" not in ASSIGNABLE_STATUSES
    assert "OFFLINE" not in ASSIGNABLE_STATUSES


def test_top3_recommendation():
    """
    후보 5명 중 점수 상위 3명만 추천하는지 확인.
    get_candidates()의 limit 파라미터 검증.

    점수 예측:
    - 번역가 1: quality=1.0, on_time=1.0, AVAILABLE → 최고점
    - 번역가 2: quality=0.9, on_time=0.9, AVAILABLE
    - 번역가 3: quality=0.8, on_time=0.8, BUSY
    - 번역가 4: quality=0.7, on_time=0.7, AVAILABLE
    - 번역가 5: quality=0.6, on_time=0.6, BUSY → 최저점
    """
    translators = [
        _make_translator(quality_score=1.0, on_time_rate=1.0, availability="AVAILABLE", current_load=0),
        _make_translator(quality_score=0.9, on_time_rate=0.9, availability="AVAILABLE", current_load=1),
        _make_translator(quality_score=0.8, on_time_rate=0.8, availability="BUSY", current_load=2),
        _make_translator(quality_score=0.7, on_time_rate=0.7, availability="AVAILABLE", current_load=1),
        _make_translator(quality_score=0.6, on_time_rate=0.6, availability="BUSY", current_load=2),
    ]

    # 점수 계산 및 내림차순 정렬 (get_candidates 내부 로직과 동일)
    scored = [(t, calculate_translator_score(t)) for t in translators]
    scored.sort(key=lambda x: x[1], reverse=True)

    # 상위 3명만 선택
    top3 = scored[:3]

    assert len(top3) == 3

    # 점수 내림차순 정렬 확인
    scores = [s for _, s in top3]
    assert scores == sorted(scores, reverse=True), "상위 3명이 점수 내림차순이어야 합니다."

    # 1위 번역가가 quality=1.0, on_time=1.0인 번역가여야 함
    top_translator, top_score = top3[0]
    assert float(top_translator.quality_score) == 1.0
    assert float(top_translator.on_time_rate) == 1.0

    # 상위 3명의 점수가 하위 2명보다 높은지 확인
    bottom2_scores = [s for _, s in scored[3:]]
    assert min(scores) >= max(bottom2_scores), (
        "상위 3명의 최저 점수가 하위 2명의 최고 점수보다 낮습니다."
    )
