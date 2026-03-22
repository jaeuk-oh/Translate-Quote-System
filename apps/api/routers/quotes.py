"""
견적(Quote) 라우터.
견적 조회 및 클라이언트 승인/거절 엔드포인트 제공.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from db.session import get_db
from models.job import Job
from models.quote import Quote
from schemas.quote import QuoteApproveRequest, QuoteResponse
from services import state_machine
from workers.assign_worker import auto_assign

router = APIRouter(prefix="/jobs", tags=["견적"])


@router.get("/{job_id}/quote", response_model=QuoteResponse)
async def get_quote(
    job_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    특정 작업의 최신 견적 조회.
    견적 계산 중(QUOTE_PENDING)이면 null 반환 → 클라이언트가 폴링 또는 SSE 구독.
    """
    result = await db.execute(
        select(Quote)
        .where(Quote.job_id == job_id)
        .order_by(Quote.created_at.desc())
        .limit(1)
    )
    quote = result.scalar_one_or_none()
    if quote is None:
        raise HTTPException(status_code=404, detail="견적이 아직 준비되지 않았습니다.")
    return quote


@router.post("/{job_id}/quote/approve")
async def approve_quote(
    job_id: UUID,
    body: QuoteApproveRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    클라이언트 견적 승인/거절.
    승인 시: FSM 전이 QUOTED → PENDING_ACCEPTANCE + 자동 배정 큐 등록.
    거절 시: 견적 상태 REJECTED 처리.
    """
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    if str(job.client_id) != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")

    if job.status != "QUOTED":
        raise HTTPException(
            status_code=400,
            detail=f"견적 승인은 QUOTED 상태에서만 가능합니다. 현재: {job.status}",
        )

    # 최신 견적 조회
    q_result = await db.execute(
        select(Quote)
        .where(Quote.job_id == job_id)
        .order_by(Quote.created_at.desc())
        .limit(1)
    )
    quote = q_result.scalar_one_or_none()

    if body.approved:
        if quote:
            quote.status = "APPROVED"
        # 자동 배정 큐 등록 (attempt=1: 최초 배정)
        auto_assign.delay(str(job_id), attempt=1)
        return {"message": "견적이 승인되었습니다. 번역가 배정을 시작합니다."}
    else:
        if quote:
            quote.status = "REJECTED"
        return {"message": "견적이 거절되었습니다."}
