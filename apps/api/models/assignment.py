"""
작업 배정(Assignment) 모델.
내부 담당자가 직접 배정 확정 — 번역가 수락/거절 없음.
번역가에게는 이메일로 배정 통보만 발송.
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
    # PENDING_ACCEPTANCE(수락대기) | ACCEPTED(수락) | REJECTED(거절) | COMPLETED(완료) | CANCELLED(취소)
    status: Mapped[str] = mapped_column(String(20), default="PENDING_ACCEPTANCE")
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # 번역가 수락/거절/만료 시각 (배정 후 24시간 이내 미응답 시 자동 재배정)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped["Job"] = relationship("Job", back_populates="assignments")  # type: ignore[name-defined]  # noqa: F821
    translator: Mapped["Translator"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Translator", back_populates="assignments"
    )
