"""
번역 작업(Job) 관련 Pydantic v2 스키마.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, model_config


class JobCreate(BaseModel):
    model_config = model_config(str_strip_whitespace=True)

    source_lang: str
    target_lang: str
    content_type: Optional[str] = None
    quality_level: Optional[str] = None
    word_count: Optional[int] = None
    deadline: Optional[datetime] = None


class JobResponse(BaseModel):
    model_config = model_config(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    source_lang: str
    target_lang: str
    content_type: Optional[str] = None
    quality_level: Optional[str] = None
    file_url: Optional[str] = None
    word_count: Optional[int] = None
    status: str
    deadline: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class JobStatusUpdate(BaseModel):
    """관리자용 수동 상태 변경 요청"""
    to_status: str
    triggered_by: str = "admin"
    metadata: Optional[dict] = None


class JobEventResponse(BaseModel):
    model_config = model_config(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    from_status: Optional[str] = None
    to_status: str
    triggered_by: Optional[str] = None
    actor_id: Optional[uuid.UUID] = None
    metadata: Optional[dict] = None
    created_at: datetime
