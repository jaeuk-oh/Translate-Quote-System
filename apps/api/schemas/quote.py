"""
견적(Quote) 관련 Pydantic v2 스키마.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class QuoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    estimated_price: Optional[Decimal] = None
    currency: str
    estimated_hours: Optional[Decimal] = None
    confidence: Optional[Decimal] = None
    word_count: Optional[int] = None
    difficulty: Optional[Decimal] = None
    deadline_multiplier: Optional[Decimal] = None
    tm_match_rate: Optional[Decimal] = None
    status: str
    created_at: datetime


class QuoteApproveRequest(BaseModel):
    """클라이언트의 견적 승인/거절 요청"""
    approved: bool
