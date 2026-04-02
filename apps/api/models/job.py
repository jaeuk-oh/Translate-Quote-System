"""
번역 작업(Job) 및 FSM 이벤트 이력(JobEvent) 모델.
상태 전이는 반드시 state_machine.py를 통해서만 수행되며,
모든 전이는 job_events 테이블에 원자적으로 기록된다.

고객은 회원가입 없이 폼 제출로만 의뢰 — client_name/client_email을 job에 직접 저장.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 고객 정보: FK 없이 직접 저장 (로그인 불필요)
    client_name: Mapped[str] = mapped_column(String(100), nullable=False)
    client_email: Mapped[str] = mapped_column(String(255), nullable=False)
    source_lang: Mapped[str] = mapped_column(String(10), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(10), nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(50))  # marketing | legal | technical | general
    quality_level: Mapped[Optional[str]] = mapped_column(String(20))  # translation | review | dtp
    file_url: Mapped[Optional[str]] = mapped_column(Text)       # 원본 파일 URL
    result_file_url: Mapped[Optional[str]] = mapped_column(Text)  # 번역가 제출 완료 파일 URL
    word_count: Mapped[Optional[int]] = mapped_column(Integer)
    # FSM 현재 상태 — state_machine.py가 단독 관리
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="REQUESTED")
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text)  # 고객 요청사항 메모
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # 관계
    quotes: Mapped[list["Quote"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Quote", back_populates="job"
    )
    assignments: Mapped[list["Assignment"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Assignment", back_populates="job"
    )
    events: Mapped[list["JobEvent"]] = relationship(
        "JobEvent", back_populates="job", order_by="JobEvent.created_at"
    )
    notifications: Mapped[list["Notification"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Notification", back_populates="job"
    )


class JobEvent(Base):
    """
    FSM 상태 전이 이력 테이블.
    이벤트 소싱(Event Sourcing) 패턴으로 모든 상태 변화를 추적.
    감사 로그 및 장애 재현에 활용.
    """
    __tablename__ = "job_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    from_status: Mapped[Optional[str]] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    # 전이 트리거: system | translator | client | admin
    triggered_by: Mapped[Optional[str]] = mapped_column(String(50))
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    # 추가 컨텍스트 (견적 ID, 배정 ID 등) — DB 컬럼명은 metadata, Python 속성은 event_data
    # SQLAlchemy DeclarativeBase가 metadata를 예약 속성으로 사용하므로 속성명을 변경
    event_data: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    job: Mapped["Job"] = relationship("Job", back_populates="events")
