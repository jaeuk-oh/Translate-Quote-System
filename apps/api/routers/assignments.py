"""
배정(Assignment) 라우터.

엔드포인트 (모두 관리자 전용):
  GET  /jobs/{job_id}/assign/recommend — 추천 번역가 목록 조회
  POST /jobs/{job_id}/assign           — 번역가 배정 확정 (번역가에게 이메일 통보)
  GET  /jobs/{job_id}/assignments      — 배정 이력 조회

번역가 수락/거절 제거: 내부 담당자가 직접 배정 확정하고 번역가는 이메일 통보만 받음.
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
    AssignmentResponse,
    AssignRequest,
    TranslatorCandidateResponse,
)
from services import assign_service, notification_service, state_machine

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
    번역가 수락/거절 없음 — 배정 즉시 확정되고 번역가에게 이메일 통보.
    FSM 전이: ASSIGNED → IN_PROGRESS (배정 확정 후 바로 진행 중으로 전환)
    """
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    if job.status != "ASSIGNED":
        raise HTTPException(
            status_code=400,
            detail=f"번역가 배정은 ASSIGNED 상태에서만 가능합니다. 현재: {job.status}",
        )

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

    # FSM 전이: ASSIGNED → IN_PROGRESS (담당자가 배정 확정 = 작업 즉시 시작)
    await state_machine.transition(
        db=db,
        job_id=job.id,
        to_status="IN_PROGRESS",
        triggered_by="admin",
        actor_id=UUID(current_user["user_id"]),
        metadata={"assignment_id": str(assignment.id), "translator_id": str(translator.id)},
    )

    # 번역가에게 배정 확정 이메일 발송
    recipient = await notification_service.get_recipient_info(db, job, "ASSIGNED")
    if recipient:
        recipient_id, recipient_email = recipient
        await notification_service.send_notification_for_event(
            db=db,
            job=job,
            event="ASSIGNED",
            recipient_id=recipient_id,
            recipient_email=recipient_email,
        )
    await db.commit()

    return assignment


@router.get("/{job_id}/assignments", response_model=list[AssignmentResponse])
async def list_assignments(
    job_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """배정 이력 조회"""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return job.assignments
