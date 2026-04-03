"""
번역가 자동 배정 서비스.
언어쌍 + 전문분야로 후보를 필터링한 뒤, 성과 점수 기반으로 Top 3를 추천.
점수 공식: score = quality(0.40) + on_time(0.30) + availability(0.20) + workload_inv(0.10)

배정 거절 또는 24시간 타임아웃 시 Celery 워커가 다음 순위로 자동 재배정.
최대 3회 재배정 실패 시 관리자에게 에스컬레이션.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.assignment import Assignment
from models.job import Job
from models.translator import Translator

# ── 번역가 가용 상태 배정 가능 여부 ────────────────────────────
ASSIGNABLE_STATUSES = {"AVAILABLE", "BUSY"}

# 배정 수락 기한: 24시간
ASSIGNMENT_EXPIRES_HOURS = 24

# 최대 재배정 횟수 — 초과 시 관리자 알림
MAX_REASSIGN_ATTEMPTS = 3


def _calculate_availability_score(availability: str) -> float:
    # 가용 상태 문자열을 점수 숫자로 변환
    # AVAILABLE(즉시 가능) → 1.0 만점
    # BUSY(작업 중이지만 여유 있음) → 0.5 절반
    # OVERLOADED/OFFLINE → 0.0 (이 함수까지 올 일 없음 — 필터에서 이미 제외)
    mapping = {
        "AVAILABLE": 1.0,
        "BUSY": 0.5,
        "OVERLOADED": 0.0,
        "OFFLINE": 0.0,
    }
    return mapping.get(availability, 0.0)


def calculate_translator_score(translator: Translator) -> float:
    # quality_score, on_time_rate는 DB에 Decimal로 저장돼 있으므로 float으로 변환
    # None이면 0으로 처리 (데이터 없는 신규 번역가 대비)
    quality = float(translator.quality_score or 0)
    on_time = float(translator.on_time_rate or 0)

    # 가용 상태를 숫자로 변환 (위 함수 사용)
    availability = _calculate_availability_score(translator.availability)

    # 현재 작업이 적을수록 높은 점수를 주기 위해 역수 사용
    # current_load=0 → 1/(1+0) = 1.0 (여유 많음)
    # current_load=2 → 1/(1+2) = 0.33 (여유 적음)
    # +1을 더하는 이유: current_load=0일 때 0으로 나누는 것 방지
    workload_inv = 1.0 / (1.0 + translator.current_load)

    # 각 항목에 가중치를 곱해 최종 점수 합산
    # 품질(40%) + 납기준수(30%) + 가용성(20%) + 부하여유(10%) = 100%
    # 모든 항목이 0~1 사이 값이므로 최종 점수도 0~1 범위
    score = (
        quality      * 0.40   # 번역 품질이 가장 중요
        + on_time    * 0.30   # 마감 준수율이 두 번째
        + availability * 0.20  # 지금 바로 투입 가능한지
        + workload_inv * 0.10  # 현재 여유가 있는지 (가중치 낮음 — 보조 지표)
    )
    return round(score, 4)  # 소수점 4자리로 반올림


async def get_candidates(
    db: AsyncSession,
    job: Job,
    limit: int = 3,
) -> list[tuple[Translator, float]]:
    # 고객이 요청한 언어쌍을 'en-ko' 형식 문자열로 만들어
    # DB의 lang_pairs 배열에 포함되어 있는지 확인할 때 사용
    lang_pair = f"{job.source_lang}-{job.target_lang}"

    # DB에서 배정 가능한 번역가만 필터링
    # 조건 1: lang_pairs 배열에 요청 언어쌍이 포함된 번역가
    #          예) lang_pairs = ['en-ko', 'ko-en'] 이면 'en-ko' 요청에 매칭
    # 조건 2: AVAILABLE 또는 BUSY 상태 (OVERLOADED/OFFLINE 제외)
    # 조건 3: 현재 작업 수가 최대치 미만 (슬롯 여유 있음)
    stmt = select(Translator).where(
        and_(
            Translator.lang_pairs.contains([lang_pair]),
            Translator.availability.in_(ASSIGNABLE_STATUSES),
            Translator.current_load < Translator.max_load,
        )
    )
    result = await db.execute(stmt)
    candidates = result.scalars().all()

    # 필터링 통과한 번역가 각각의 점수를 계산해서 (번역가, 점수) 튜플 리스트로 만들기
    scored = [(t, calculate_translator_score(t)) for t in candidates]
    # 점수 높은 순으로 정렬 (reverse=True → 내림차순)
    scored.sort(key=lambda x: x[1], reverse=True)

    return scored[:limit]


async def create_assignment(
    db: AsyncSession,
    job: Job,
    translator: Translator,
    score: float,
) -> Assignment:
    """
    배정 레코드 생성.
    expires_at = 현재 시각 + 24시간 (Celery beat가 만료 체크)
    """
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ASSIGNMENT_EXPIRES_HOURS)

    assignment = Assignment(
        job_id=job.id,
        translator_id=translator.id,
        score=Decimal(str(score)),
        status="PENDING_ACCEPTANCE",
        expires_at=expires_at,
    )
    db.add(assignment)

    # 번역가 부하 증가 및 가용성 업데이트
    translator.current_load += 1
    _update_translator_availability(translator)

    await db.flush()
    return assignment


async def accept_assignment(
    db: AsyncSession,
    assignment: Assignment,
) -> Assignment:
    """번역가 수락 처리 — accepted_at 기록"""
    assignment.status = "ACCEPTED"
    assignment.accepted_at = datetime.now(timezone.utc)
    await db.flush()
    return assignment


async def reject_assignment(
    db: AsyncSession,
    assignment: Assignment,
) -> Assignment:
    """
    번역가 거절 처리.
    rejected_at 기록 후 번역가 부하 감소.
    Celery 워커(assign_worker.py)가 자동 재배정 트리거.
    """
    assignment.status = "REJECTED"
    assignment.rejected_at = datetime.now(timezone.utc)

    # 거절 시 번역가 부하 복원
    translator = assignment.translator
    if translator and translator.current_load > 0:
        translator.current_load -= 1
        _update_translator_availability(translator)

    await db.flush()
    return assignment


def _update_translator_availability(translator: Translator) -> None:
    """
    workload_ratio 기반으로 번역가 가용 상태 자동 갱신.

    AVAILABLE   : current_load = 0
    BUSY        : 0 < workload_ratio < 1.0
    OVERLOADED  : workload_ratio >= 1.0
    """
    ratio = translator.workload_ratio
    if ratio == 0:
        translator.availability = "AVAILABLE"
    elif ratio < 1.0:
        translator.availability = "BUSY"
    else:
        translator.availability = "OVERLOADED"
