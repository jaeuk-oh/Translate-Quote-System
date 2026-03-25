"""
견적(Quote) 라우터.

엔드포인트:
  GET  /jobs/{job_id}/quote         — 내부 담당자: 견적 조회
  POST /jobs/{job_id}/quote/send    — 내부 담당자: 견적 검토 후 고객에게 발송 (QUOTED_DRAFT → QUOTED)
  GET  /quotes/approve              — 고객: 이메일 링크 클릭으로 승인/거절 (인증 불필요)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import (
    create_quote_approval_token,
    decode_quote_approval_token,
    get_current_user,
    require_role,
)
from db.session import get_db
from models.job import Job
from models.quote import Quote
from schemas.quote import QuoteResponse
from services import notification_service, state_machine
from workers.assign_worker import auto_assign

router = APIRouter(tags=["견적"])


@router.get("/jobs/{job_id}/quote", response_model=QuoteResponse)
async def get_quote(
    job_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    특정 작업의 최신 견적 조회 — 내부 담당자 전용.
    QUOTE_PENDING 상태면 아직 계산 중.
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


@router.post("/jobs/{job_id}/quote/send")
async def send_quote_to_client(
    job_id: UUID,
    current_user: dict = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    내부 담당자가 견적 검토 완료 후 고객에게 이메일 발송.

    처리 순서:
    1. QUOTED_DRAFT 상태 확인
    2. FSM 전이: QUOTED_DRAFT → QUOTED
    3. 7일 유효 승인 토큰 생성
    4. 고객 이메일에 승인/거절 링크 포함하여 발송
    """
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    if job.status != "QUOTED_DRAFT":
        raise HTTPException(
            status_code=400,
            detail=f"고객 발송은 QUOTED_DRAFT 상태에서만 가능합니다. 현재: {job.status}",
        )

    # 최신 견적 조회
    q_result = await db.execute(
        select(Quote)
        .where(Quote.job_id == job_id)
        .order_by(Quote.created_at.desc())
        .limit(1)
    )
    quote = q_result.scalar_one_or_none()
    if quote is None:
        raise HTTPException(status_code=404, detail="발송할 견적이 없습니다.")

    # FSM 전이: QUOTED_DRAFT → QUOTED
    await state_machine.transition(
        db=db,
        job_id=job_id,
        to_status="QUOTED",
        triggered_by="admin",
        actor_id=UUID(current_user["user_id"]),
    )
    await db.commit()

    # 고객 이메일 발송용 승인 토큰 생성 (7일 유효)
    token = create_quote_approval_token(str(job_id))
    approval_url = f"http://localhost:8000/quotes/approve?token={token}&action=approve"
    rejection_url = f"http://localhost:8000/quotes/approve?token={token}&action=reject"

    # 고객에게 견적 이메일 발송 (승인/거절 링크 포함)
    await notification_service.send_notification_for_event(
        db=db,
        job=job,
        event="QUOTED",
        recipient_id=None,
        recipient_email=job.client_email,
        extra={"approval_url": approval_url, "rejection_url": rejection_url},
    )
    await db.commit()

    return {
        "message": f"{job.client_email}에 견적서를 발송했습니다.",
        "approval_url": approval_url,
        "rejection_url": rejection_url,
    }


@router.get("/quotes/approve")
async def approve_quote_by_token(
    token: str = Query(..., description="이메일 링크의 서명된 토큰"),
    action: str = Query(..., description="approve 또는 reject"),
    db: AsyncSession = Depends(get_db),
):
    """
    고객 견적 승인/거절 — 인증 불필요, 이메일 링크 클릭으로 처리.

    승인(approve): FSM 전이 QUOTED → ASSIGNED + 번역가 자동 배정 큐 등록
    거절(reject):  FSM 전이 QUOTED → CANCELLED + 견적 상태 REJECTED
    """
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action은 approve 또는 reject여야 합니다.")

    # 토큰 검증 및 job_id 추출
    job_id_str = decode_quote_approval_token(token)
    job_id = UUID(job_id_str)

    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    if job.status != "QUOTED":
        raise HTTPException(
            status_code=400,
            detail=f"이미 처리된 견적입니다. 현재 상태: {job.status}",
        )

    # 최신 견적 조회
    q_result = await db.execute(
        select(Quote)
        .where(Quote.job_id == job_id)
        .order_by(Quote.created_at.desc())
        .limit(1)
    )
    quote = q_result.scalar_one_or_none()

    if action == "approve":
        if quote:
            quote.status = "APPROVED"

        # FSM 전이: QUOTED → ASSIGNED (번역가 배정 단계로 이동)
        await state_machine.transition(
            db=db,
            job_id=job_id,
            to_status="ASSIGNED",
            triggered_by="client",
            metadata={"client_email": job.client_email},
        )
        await db.commit()

        # 번역가 자동 배정 큐 등록 (attempt=1: 최초 배정)
        auto_assign.delay(str(job_id), attempt=1)

        return {"message": "견적을 승인했습니다. 번역가를 배정 중입니다."}

    else:  # reject
        if quote:
            quote.status = "REJECTED"

        # FSM 전이: QUOTED → CANCELLED
        await state_machine.transition(
            db=db,
            job_id=job_id,
            to_status="CANCELLED",
            triggered_by="client",
            metadata={"client_email": job.client_email},
        )
        await db.commit()

        return {"message": "견적을 거절했습니다."}
