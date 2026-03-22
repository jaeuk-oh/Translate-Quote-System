"""
알림 발송 이력(Notification) 모델.
지수 백오프 재시도 전략을 위한 attempts, next_retry_at 필드 포함.
최대 재시도 초과 시 status = DLQ로 마킹하여 관리자에게 에스컬레이션.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id")
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # 발송 채널: email | slack | webhook
    channel: Mapped[Optional[str]] = mapped_column(String(20))
    # 알림 내용 (제목, 본문, 링크 등)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    # PENDING | SENT | FAILED | DLQ
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    # 재시도 횟수 — 지수 백오프: 1분 → 5분 → 30분 → DLQ
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    job: Mapped[Optional["Job"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Job", back_populates="notifications"
    )
