"""
번역 작업(Job) 관련 Pydantic v2 스키마.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class JobCreate(BaseModel):
    """고객 폼 제출 스키마 — 인증 불필요, 이름/이메일 직접 입력"""
    model_config = ConfigDict(str_strip_whitespace=True)

    client_name: str
    client_email: EmailStr
    source_lang: str
    target_lang: str
    content_type: Optional[str] = None
    quality_level: Optional[str] = None
    word_count: Optional[int] = None
    deadline: Optional[datetime] = None
    notes: Optional[str] = None  # 고객 요청사항 메모


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_name: str
    client_email: str
    source_lang: str
    target_lang: str
    content_type: Optional[str] = None
    quality_level: Optional[str] = None
    file_url: Optional[str] = None
    word_count: Optional[int] = None
    status: str
    deadline: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class JobStatusUpdate(BaseModel):
    """관리자용 수동 상태 변경 요청"""
    to_status: str
    triggered_by: str = "admin"
    metadata: Optional[dict] = None


class JobEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    from_status: Optional[str] = None
    to_status: str
    triggered_by: Optional[str] = None
    actor_id: Optional[uuid.UUID] = None
    event_data: Optional[dict] = None
    created_at: datetime
