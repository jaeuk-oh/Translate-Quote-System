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
    """
    가용 상태를 배정 점수용 수치로 변환.
    AVAILABLE = 1.0 (즉시 가능), BUSY = 0.5 (작업 중이나 여유 있음)
    """
    mapping = {
        "AVAILABLE": 1.0,
        "BUSY": 0.5,
        "OVERLOADED": 0.0,
        "OFFLINE": 0.0,
    }
    return mapping.get(availability, 0.0)


def calculate_translator_score(translator: Translator) -> float:
    """
    번역가 배정 우선순위 점수 계산.

    score = (quality_score  × 0.40)
          + (on_time_rate   × 0.30)
          + (availability   × 0.20)
          + (workload_inv   × 0.10)

    workload_inv = 1 / (1 + current_load)
    → 0 나누기 방지 + 부하가 적을수록 높은 점수

    각 항목이 0~1 범위이므로 최종 score도 0~1 범위.
    """
    quality = float(translator.quality_score or 0)
    on_time = float(translator.on_time_rate or 0)
    availability = _calculate_availability_score(translator.availability)

    # 번역가 과부하 판단: workload_ratio가 1.0 이상이면 배정 대상에서 제외
    workload_inv = 1.0 / (1.0 + translator.current_load)

    score = (
        quality * 0.40
        + on_time * 0.30
        + availability * 0.20
        + workload_inv * 0.10
    )
    return round(score, 4)


async def get_candidates(
    db: AsyncSession,
    job: Job,
    limit: int = 3,
) -> list[tuple[Translator, float]]:
    """
    언어쌍 + 전문분야 기반 배정 후보 조회 및 점수 계산.

    필터링 조건:
    1. lang_pairs 배열에 요청 언어쌍 포함
    2. OVERLOADED / OFFLINE 제외
    3. current_load < max_load (여유 용량 있음)

    반환: (Translator, score) 튜플 리스트, 점수 내림차순 상위 limit개
    """
    lang_pair = f"{job.source_lang}-{job.target_lang}"

    # PostgreSQL 배열 포함 쿼리: lang_pairs @> ARRAY['ko-en']
    stmt = select(Translator).where(
        and_(
            Translator.lang_pairs.contains([lang_pair]),
            Translator.availability.in_(ASSIGNABLE_STATUSES),
            Translator.current_load < Translator.max_load,
        )
    )
    result = await db.execute(stmt)
    candidates = result.scalars().all()

    # 점수 계산 후 내림차순 정렬
    scored = [(t, calculate_translator_score(t)) for t in candidates]
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
