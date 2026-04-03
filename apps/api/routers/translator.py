"""
번역가 전용 라우터.
번역가 포털에서 사용 — 내 배정 작업 목록 조회.
인증: JWT translator role 필수.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from core.auth import require_role
from db.session import get_db
from models.assignment import Assignment
from models.job import Job
from schemas.assignment import AssignmentResponse
from schemas.job import JobResponse

router = APIRouter(prefix="/translator", tags=["번역가"])


class MyJobResponse(AssignmentResponse):
    """배정 정보 + 작업 상세를 합친 번역가 대시보드용 응답"""
    job: JobResponse


@router.get("/jobs", response_model=list[MyJobResponse])
async def my_jobs(
    current_user: dict = Depends(require_role("translator")),
    db: AsyncSession = Depends(get_db),
):
    """
    내 배정 작업 목록 조회.
    translator_id가 현재 로그인한 번역가와 일치하는 Assignment를 최신순으로 반환.
    """
    translator_id = UUID(current_user["user_id"])

    result = await db.execute(
        select(Assignment)
        .options(joinedload(Assignment.job))
        .where(Assignment.translator_id == translator_id)
        .order_by(Assignment.assigned_at.desc())
    )
    assignments = result.scalars().all()

    return [
        MyJobResponse(
            id=a.id,
            job_id=a.job_id,
            translator_id=a.translator_id,
            score=a.score,
            status=a.status,
            assigned_at=a.assigned_at,
            accepted_at=getattr(a, "accepted_at", None),
            rejected_at=getattr(a, "rejected_at", None),
            expires_at=getattr(a, "expires_at", None),
            job=a.job,
        )
        for a in assignments
    ]
