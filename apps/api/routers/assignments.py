"""
배정(Assignment) 라우터.

엔드포인트:
  GET  /jobs/{job_id}/assign/recommend                          — 추천 번역가 목록 조회 (관리자)
  POST /jobs/{job_id}/assign                                    — 번역가 배정 (관리자)
  GET  /jobs/{job_id}/assignments                               — 배정 이력 조회
  POST /jobs/{job_id}/assignments/{assignment_id}/accept        — 번역가 수락 (FSM → IN_PROGRESS)
  POST /jobs/{job_id}/assignments/{assignment_id}/reject        — 번역가 거절 (부하 복원)

흐름: 관리자가 배정 → 번역가가 수락/거절 → 수락 시 FSM 전이 + 제출 링크 이메일 발송.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, require_role, create_translator_submit_token
from core.config import settings
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


@router.post("/{job_id}/assignments/{assignment_id}/accept", response_model=AssignmentResponse)
async def accept_assignment(
    job_id: UUID,
    assignment_id: UUID,
    current_user: dict = Depends(require_role("translator")),
    db: AsyncSession = Depends(get_db),
):
    """
    번역가 일감 수락.
    Assignment PENDING_ACCEPTANCE → ACCEPTED, FSM ASSIGNED → IN_PROGRESS.
    수락 완료 후 번역가에게 완료 파일 제출 링크 이메일 발송.
    """
    result = await db.execute(
        select(Assignment).where(
            Assignment.id == assignment_id,
            Assignment.job_id == job_id,
            Assignment.translator_id == UUID(current_user["user_id"]),
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="배정 정보를 찾을 수 없습니다.")

    if assignment.status != "PENDING_ACCEPTANCE":
        raise HTTPException(status_code=400, detail=f"수락 가능한 상태가 아닙니다. 현재: {assignment.status}")

    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = job_result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    # 배정 수락 처리
    assignment.status = "ACCEPTED"
    from datetime import datetime, timezone as tz
    assignment.accepted_at = datetime.now(tz.utc)

    # FSM 전이: ASSIGNED → IN_PROGRESS
    await state_machine.transition(
        db=db,
        job_id=job.id,
        to_status="IN_PROGRESS",
        triggered_by="translator",
        metadata={"assignment_id": str(assignment.id)},
    )

    # 번역가에게 제출 링크 이메일 발송
    translator_result = await db.execute(
        select(Translator).where(Translator.id == assignment.translator_id)
    )
    translator = translator_result.scalar_one_or_none()
    if translator and translator.email:
        submit_token = create_translator_submit_token(str(job.id), str(translator.id))
        submit_url = f"{settings.FRONTEND_URL}/submit/{job.id}?token={submit_token}"
        await notification_service.send_notification_for_event(
            db=db,
            job=job,
            event="ASSIGNED",
            recipient_id=translator.id,
            recipient_email=translator.email,
            extra={"submit_url": submit_url},
        )

    await db.commit()
    return assignment


@router.post("/{job_id}/assignments/{assignment_id}/reject", response_model=AssignmentResponse)
async def reject_assignment(
    job_id: UUID,
    assignment_id: UUID,
    current_user: dict = Depends(require_role("translator")),
    db: AsyncSession = Depends(get_db),
):
    """
    번역가 일감 거절.
    Assignment PENDING_ACCEPTANCE → REJECTED.
    번역가 부하 복원 후 관리자에게 재배정 필요 알림.
    """
    result = await db.execute(
        select(Assignment).where(
            Assignment.id == assignment_id,
            Assignment.job_id == job_id,
            Assignment.translator_id == UUID(current_user["user_id"]),
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="배정 정보를 찾을 수 없습니다.")

    if assignment.status != "PENDING_ACCEPTANCE":
        raise HTTPException(status_code=400, detail=f"거절 가능한 상태가 아닙니다. 현재: {assignment.status}")

    # 배정 거절 처리
    assignment.status = "REJECTED"
    from datetime import datetime, timezone as tz
    assignment.rejected_at = datetime.now(tz.utc)

    # 번역가 부하 복원
    translator_result = await db.execute(
        select(Translator).where(Translator.id == assignment.translator_id)
    )
    translator = translator_result.scalar_one_or_none()
    if translator and translator.current_load > 0:
        translator.current_load -= 1
        from services.assign_service import _update_translator_availability
        _update_translator_availability(translator)

    await db.commit()
    return assignment
