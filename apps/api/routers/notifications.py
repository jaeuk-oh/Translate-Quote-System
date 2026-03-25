"""
알림 라우터.
내 알림 목록 조회, 수동 재시도(admin), 발송 통계(admin) 엔드포인트 제공.
"""

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from models.notification import Notification

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notifications", tags=["notifications"])


# ── 응답 스키마 ──────────────────────────────────────────────────────

class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: Optional[UUID] = None
    recipient_id: UUID
    channel: Optional[str] = None
    status: str
    attempts: int
    sent_at: Optional[Any] = None
    created_at: Any


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    page: int
    size: int


class NotificationStatsResponse(BaseModel):
    total: int
    sent: int
    failed: int
    dead_letter: int
    pending: int
    # 채널별 발송 수
    by_channel: dict[str, int]


# ── 임시 현재 사용자 조회 유틸 ─────────────────────────────────────
# TODO: 실제 JWT 인증 미들웨어로 교체
async def _get_current_user_id() -> UUID:
    """임시 구현 — JWT에서 user_id 추출. 실제 구현은 auth 의존성으로 교체 예정."""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증이 필요합니다.",
    )


async def _get_current_user_role() -> str:
    """임시 구현 — JWT에서 role 추출. 실제 구현은 auth 의존성으로 교체 예정."""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증이 필요합니다.",
    )


def _require_admin(role: str) -> None:
    """관리자 권한 검증 헬퍼"""
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다.",
        )


# ── 엔드포인트 ──────────────────────────────────────────────────────

@router.get("", response_model=NotificationListResponse)
async def list_my_notifications(
    page: int = Query(default=1, ge=1, description="페이지 번호 (1부터 시작)"),
    size: int = Query(default=20, ge=1, le=100, description="페이지 크기"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="상태 필터"),
    db: AsyncSession = Depends(get_db),
):
    """
    내 알림 목록 조회 (페이지네이션).
    현재 로그인한 사용자의 알림만 반환.
    status 쿼리 파라미터로 상태 필터링 가능.
    """
    # TODO: JWT 인증 미들웨어에서 current_user_id 주입
    # 현재는 테스트용 — 실제 인증 구현 후 아래 코드로 교체
    # current_user_id = get_current_user_id(request)

    # 임시: 전체 알림 조회 (인증 구현 전 개발용)
    query = select(Notification)

    if status_filter:
        query = query.where(Notification.status == status_filter.upper())

    # 전체 개수 조회 (페이지네이션용)
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    # 페이지네이션 적용
    offset = (page - 1) * size
    result = await db.execute(
        query.order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    notifications = result.scalars().all()

    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in notifications],
        total=total,
        page=page,
        size=size,
    )


@router.post("/{notification_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_notification(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    알림 수동 재시도 (admin only).
    FAILED 또는 DEAD_LETTER 상태의 알림을 즉시 재시도 큐에 등록.
    """
    # TODO: JWT 인증 미들웨어에서 role 확인
    # _require_admin(current_user_role)

    result = await db.execute(
        select(Notification).where(Notification.id == notification_id)
    )
    notification = result.scalar_one_or_none()

    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"알림을 찾을 수 없습니다: {notification_id}",
        )

    # PENDING, SENT 상태는 재시도 불필요
    if notification.status not in ("FAILED", "DEAD_LETTER"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"재시도 불가 상태입니다: {notification.status}. FAILED 또는 DEAD_LETTER 상태만 재시도 가능.",
        )

    # 상태 초기화 후 Celery 태스크 재등록
    notification.status = "PENDING"
    notification.attempts = 0
    await db.flush()

    # Celery 태스크 즉시 실행 예약
    from workers.notify_worker import send_notification
    task = send_notification.apply_async(
        args=[str(notification_id)],
        countdown=0,  # 즉시 실행
    )

    logger.info(
        "알림 수동 재시도 등록: notification_id=%s, task_id=%s",
        notification_id, task.id,
    )

    return {
        "message": "알림 재시도가 예약되었습니다.",
        "notification_id": str(notification_id),
        "task_id": task.id,
    }


@router.get("/stats", response_model=NotificationStatsResponse)
async def get_notification_stats(
    db: AsyncSession = Depends(get_db),
):
    """
    알림 발송 통계 조회 (admin only).
    전체 발송 현황 및 채널별 통계 반환.
    """
    # TODO: JWT 인증 미들웨어에서 role 확인
    # _require_admin(current_user_role)

    # 전체 상태별 카운트
    status_result = await db.execute(
        select(Notification.status, func.count(Notification.id).label("cnt"))
        .group_by(Notification.status)
    )
    status_rows = status_result.all()

    # 상태별 집계 초기화
    counts: dict[str, int] = {
        "PENDING": 0,
        "SENT": 0,
        "FAILED": 0,
        "DEAD_LETTER": 0,
    }
    for row in status_rows:
        counts[row.status] = row.cnt

    # 채널별 발송 성공 수
    channel_result = await db.execute(
        select(Notification.channel, func.count(Notification.id).label("cnt"))
        .where(Notification.status == "SENT")
        .group_by(Notification.channel)
    )
    by_channel = {row.channel: row.cnt for row in channel_result.all() if row.channel}

    total_result = await db.execute(select(func.count(Notification.id)))
    total = total_result.scalar_one()

    return NotificationStatsResponse(
        total=total,
        sent=counts.get("SENT", 0),
        failed=counts.get("FAILED", 0),
        dead_letter=counts.get("DEAD_LETTER", 0),
        pending=counts.get("PENDING", 0),
        by_channel=by_channel,
    )
