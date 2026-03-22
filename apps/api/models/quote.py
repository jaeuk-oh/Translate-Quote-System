"""
견적(Quote) 모델.
자동 견적 서비스가 계산한 결과를 저장.
TM 매칭률, 난이도, 마감 승수 등 견적 근거를 모두 보관하여 투명성 확보.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    estimated_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(10), default="KRW")
    estimated_hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 1))
    # 견적 신뢰도: 0.000 ~ 1.000 (난이도 인자 분산 기반)
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    word_count: Mapped[Optional[int]] = mapped_column(Integer)
    # 난이도 승수 — content_type × quality_level × 파일 복잡도
    difficulty: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 3))
    # 마감 촉박도에 따른 가격 승수
    deadline_multiplier: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    # TM(Translation Memory) 매칭률 — 업계 표준 CAT tool 방식
    tm_match_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    job: Mapped["Job"] = relationship("Job", back_populates="quotes")  # type: ignore[name-defined]  # noqa: F821
