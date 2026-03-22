"""
배정(Assignment) 라우터.
추천 번역가 조회, 배정 확정, 수락/거절 엔드포인트 제공.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, require_role
from db.session import get_db
from models.assignment import Assignment
from models.job import Job
from models.translator import Translator
from schemas.assignment import (
    AssignmentActionRequest,
    AssignmentResponse,
    AssignRequest,
    TranslatorCandidateResponse,
)
from services import assign_service, state_machine
from workers.assign_worker import auto_reassign

router = APIRouter(prefix="/jobs", tags=["배정"])


@router.get("/{job_id}/assign/recommend", response_model=list[TranslatorCandidateResponse])
async def recommend_translators(
    job_id: UUID,
    current_user: dict = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    배정 추천 번역가 목록 조회 (관리자 전용).
    언어쌍 + 가용성 필터 후 점수 내림차순 Top 3 반환.
    """
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    candidates = await assign_service.get_candidates(db=db, job=job)
    return [
        TranslatorCandidateResponse(
            translator_id=t.id,
            name=t.name,
            score=score,
            quality_score=float(t.quality_score) if t.quality_score else None,
            on_time_rate=float(t.on_time_rate) if t.on_time_rate else None,
            availability=t.availability,
            current_load=t.current_load,
            max_load=t.max_load,
        )
        for t, score in candidates
    ]


@router.post("/{job_id}/assign", response_model=AssignmentResponse)
async def assign_translator(
    job_id: UUID,
    body: AssignRequest,
    current_user: dict = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    배정 확정 (관리자 전용).
    추천 목록에서 선택한 번역가로 배정 레코드 생성.
    """
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    t_result = await db.execute(
        select(Translator).where(Translator.id == body.translator_id)
    )
    translator = t_result.scalar_one_or_none()
    if translator is None:
        raise HTTPException(status_code=404, detail="번역가를 찾을 수 없습니다.")

    score = assign_service.calculate_translator_score(translator)
    assignment = await assign_service.create_assignment(
        db=db, job=job, translator=translator, score=score
    )

    # FSM 전이: QUOTED → PENDING_ACCEPTANCE
    await state_machine.transition(
        db=db,
        job_id=job.id,
        to_status="PENDING_ACCEPTANCE",
        triggered_by="admin",
        actor_id=UUID(current_user["user_id"]),
        metadata={"assignment_id": str(assignment.id)},
    )

    return assignment


@router.get("/{job_id}/assignments", response_model=list[AssignmentResponse])
async def list_assignments(
    job_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return job.assignments


@router.post("/assignments/{assignment_id}/respond", response_model=AssignmentResponse)
async def respond_to_assignment(
    assignment_id: UUID,
    body: AssignmentActionRequest,
    current_user: dict = Depends(require_role("translator")),
    db: AsyncSession = Depends(get_db),
):
    """
    번역가의 수락/거절 응답.
    수락 시: FSM 전이 PENDING_ACCEPTANCE → ASSIGNED.
    거절 시: 배정 REJECTED + Celery 재배정 큐 등록.
    """
    result = await db.execute(
        select(Assignment).where(Assignment.id == assignment_id)
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="배정 건을 찾을 수 없습니다.")

    if assignment.status != "PENDING_ACCEPTANCE":
        raise HTTPException(
            status_code=400,
            detail=f"수락/거절은 PENDING_ACCEPTANCE 상태에서만 가능합니다. 현재: {assignment.status}",
        )

    if body.is_accept():
        # 수락 처리
        assignment = await assign_service.accept_assignment(db=db, assignment=assignment)

        # FSM 전이: PENDING_ACCEPTANCE → ASSIGNED
        await state_machine.transition(
            db=db,
            job_id=assignment.job_id,
            to_status="ASSIGNED",
            triggered_by="translator",
            actor_id=UUID(current_user["user_id"]),
            metadata={"assignment_id": str(assignment_id)},
        )
        return assignment
    else:
        # 거절 처리
        assignment = await assign_service.reject_assignment(db=db, assignment=assignment)

        # 현재 재배정 시도 횟수 파악 후 다음 순위로 재배정
        past_result = await db.execute(
            select(Assignment).where(
                Assignment.job_id == assignment.job_id,
            )
        )
        all_assignments = past_result.scalars().all()
        # 거절/만료 횟수 + 1 = 다음 시도 번호
        next_attempt = sum(
            1 for a in all_assignments if a.status in {"REJECTED", "EXPIRED"}
        ) + 1

        # 재배정 태스크 큐 등록 (즉시)
        auto_reassign.delay(str(assignment.job_id), next_attempt)
        return assignment
