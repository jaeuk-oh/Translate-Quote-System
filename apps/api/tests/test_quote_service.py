"""
견적 계산 서비스(quote_service.py) 단위 테스트.
DB 접근 없이 순수 함수 테스트 (unit test).
TM 매칭률 할인 및 최종 가격 계산 검증.
"""

from decimal import Decimal

import pytest

from services.quote_service import (
    BASE_RATES,
    _calculate_tm_discount,
    calculate_quote,
)


# ── TM 할인 계수 테스트 ─────────────────────────────────────────────

def test_tm_discount_100():
    """
    TM 매칭률 100% → 완전 일치, 무료 처리.
    할인 계수 = 0.0 (가격 × 0.0 = 0원)
    """
    discount = _calculate_tm_discount(1.0)
    assert discount == 0.0


def test_tm_discount_75_99():
    """
    TM 매칭률 75~99% → 70% 할인 (계수 0.3).
    업계 표준 CAT tool 방식: 대부분 재사용 가능하므로 대폭 할인.
    """
    # 80% 매칭률
    discount = _calculate_tm_discount(0.8)
    assert discount == 0.3

    # 경계값 75% 확인
    discount_boundary = _calculate_tm_discount(0.75)
    assert discount_boundary == 0.3

    # 99% 매칭률
    discount_high = _calculate_tm_discount(0.99)
    assert discount_high == 0.3


def test_tm_discount_50_74():
    """
    TM 매칭률 50~74% → 40% 할인 (계수 0.6).
    부분 재사용 가능 — 적정 할인 적용.
    """
    # 60% 매칭률
    discount = _calculate_tm_discount(0.6)
    assert discount == 0.6

    # 경계값 50% 확인
    discount_boundary = _calculate_tm_discount(0.50)
    assert discount_boundary == 0.6

    # 74% 매칭률
    discount_high = _calculate_tm_discount(0.74)
    assert discount_high == 0.6


def test_tm_discount_below_50():
    """
    TM 매칭률 50% 미만 → 할인 없음 (계수 1.0).
    재사용률이 낮아 전체 번역 비용 청구.
    """
    # 30% 매칭률
    discount = _calculate_tm_discount(0.3)
    assert discount == 1.0

    # 0% 매칭률 (완전 새 문서)
    discount_zero = _calculate_tm_discount(0.0)
    assert discount_zero == 1.0

    # 경계값 49.9%
    discount_boundary = _calculate_tm_discount(0.499)
    assert discount_boundary == 1.0


# ── 최종 가격 계산 테스트 ──────────────────────────────────────────

def test_price_calculation():
    """
    전체 견적 계산 통합 테스트.

    조건:
    - 단어 수: 1,000단어
    - 언어쌍: ko-en (기본 단가 80원/단어)
    - 콘텐츠 유형: general (난이도 1.0)
    - 품질 등급: translation (품질 가중치 1.0)
    - 마감 승수: 1.0 (deadline=None → 기본값)
    - TM 매칭률: 0% → tm_discount = 1.0 (할인 없음)

    예상 가격:
    price = 1000 × 80.0 × 1.0 × 1.0 × 1.0 = 80,000원
    """
    result = calculate_quote(
        word_count=1000,
        source_lang="ko",
        target_lang="en",
        content_type="general",
        quality_level="translation",
        deadline=None,
        tm_match_rate=0.0,  # TM 할인 없음 (discount = 1.0)
    )

    # ko-en 기본 단가 확인
    expected_base_rate = BASE_RATES["ko-en"]  # 80.0

    # 가격 검증: 1000 × 80 × 1.0 × 1.0 × 1.0 = 80,000
    expected_price = Decimal("80000.00")
    assert result["estimated_price"] == expected_price, (
        f"예상 가격 {expected_price}원, 실제 {result['estimated_price']}원"
    )

    # 난이도 승수 확인 (general × translation = 1.0 × 1.0)
    assert result["difficulty"] == Decimal("1.0")

    # 마감 승수 확인 (deadline=None → 1.0)
    assert result["deadline_multiplier"] == Decimal("1.0")

    # word_count 확인
    assert result["word_count"] == 1000

    # TM 매칭률 확인
    assert result["tm_match_rate"] == Decimal("0.0")

    # 예상 작업 시간 확인 (1000단어 / 300단어/시간 = 3.3시간)
    assert result["estimated_hours"] == Decimal("3.3")
