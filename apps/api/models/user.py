"""
사용자 모델.
클라이언트, 번역가, 관리자 역할을 단일 테이블로 관리.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_pw: Mapped[str] = mapped_column(Text, nullable=False)
    # 역할: client | translator | admin
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="client")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # 관계
    jobs: Mapped[list["Job"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Job", back_populates="client", foreign_keys="Job.client_id"
    )
    translator_profile: Mapped["Translator"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Translator", back_populates="user", uselist=False
    )
