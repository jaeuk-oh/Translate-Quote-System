"""
배정(Assignment) 관련 Pydantic v2 스키마.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, model_config


class AssignmentResponse(BaseModel):
    model_config = model_config(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    translator_id: uuid.UUID
    score: Optional[Decimal] = None
    status: str
    assigned_at: datetime
    accepted_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class TranslatorCandidateResponse(BaseModel):
    """배정 추천 번역가 정보"""
    translator_id: uuid.UUID
    name: Optional[str] = None
    score: float
    quality_score: Optional[float] = None
    on_time_rate: Optional[float] = None
    availability: str
    current_load: int
    max_load: int


class AssignRequest(BaseModel):
    """배정 확정 요청 — 추천 목록에서 선택"""
    translator_id: uuid.UUID


class AssignmentActionRequest(BaseModel):
    """번역가의 수락/거절 응답"""
    action: str  # accept | reject

    def is_accept(self) -> bool:
        return self.action == "accept"
