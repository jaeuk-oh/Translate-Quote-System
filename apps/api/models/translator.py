"""
번역가(Translator) 모델.
번역가를 단순 인력이 아닌 "상태 기반 리소스"로 모델링.
workload_ratio = current_load / max_load 기반으로 실시간 가용성 자동 갱신.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Translator(Base):
    __tablename__ = "translators"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    name: Mapped[Optional[str]] = mapped_column(String(100))
    # 번역가 연락처 — 계정 없이 이메일 통보만 수신
    email: Mapped[Optional[str]] = mapped_column(String(255))
    # 언어쌍 배열: ['ko-en', 'ko-ja'] — 배정 후보 필터링에 사용
    lang_pairs: Mapped[Optional[list]] = mapped_column(ARRAY(String))
    # 전문분야 배열: ['marketing', 'legal'] — 전문성 매칭에 사용
    specialties: Mapped[Optional[list]] = mapped_column(ARRAY(String))

    # ── 성과 지표 (배정 점수 계산에 사용) ──────────────────
    quality_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))   # 번역 품질 점수
    on_time_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))    # 납기 준수율
    throughput: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))      # 일 평균 처리 단어 수
    responsiveness: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))  # 평균 응답 속도 점수

    # ── 실시간 상태 ─────────────────────────────────────────
    # AVAILABLE | BUSY | OVERLOADED | OFFLINE
    availability: Mapped[str] = mapped_column(String(20), default="AVAILABLE")
    current_load: Mapped[int] = mapped_column(Integer, default=0)   # 현재 진행 중인 작업 수
    max_load: Mapped[int] = mapped_column(Integer, default=3)       # 최대 동시 작업 수

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped[Optional["User"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", back_populates="translator_profile"
    )
    assignments: Mapped[list["Assignment"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Assignment", back_populates="translator"
    )

    @property
    def workload_ratio(self) -> float:
        """
        번역가 과부하 판단 지표.
        0.0 = 유휴, 1.0 이상 = OVERLOADED (배정 대상 제외)
        """
        if self.max_load == 0:
            return 1.0
        return self.current_load / self.max_load
