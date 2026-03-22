"""
작업 배정(Assignment) 모델.
번역가의 수락/거절 및 타임아웃을 추적하여 자동 재배정 트리거에 활용.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    translator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("translators.id"), nullable=False
    )
    # 배정 점수: score = quality(0.4) + on_time(0.3) + availability(0.2) + workload_inv(0.1)
    score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    # PENDING_ACCEPTANCE | ACCEPTED | REJECTED | EXPIRED
    status: Mapped[str] = mapped_column(String(20), default="PENDING_ACCEPTANCE")
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # 수락 기한: 초과 시 Celery beat가 자동 재배정 트리거
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    job: Mapped["Job"] = relationship("Job", back_populates="assignments")  # type: ignore[name-defined]  # noqa: F821
    translator: Mapped["Translator"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Translator", back_populates="assignments"
    )
