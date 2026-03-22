"""
번역 작업(Job) 라우터.
의뢰 등록, 파일 업로드, 상태 조회, SSE 스트림 엔드포인트 제공.
"""

import json
import asyncio
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.storage import upload_translation_file
from db.session import get_db
from models.job import Job
from schemas.job import JobCreate, JobEventResponse, JobResponse
from services import state_machine
from workers.quote_worker import calculate_quote

router = APIRouter(prefix="/jobs", tags=["번역 작업"])


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    body: JobCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    번역 의뢰 등록.
    즉시 job_id 반환 후 비동기로 견적 계산 (Celery 큐 등록).
    대용량 파일도 API 응답 블로킹 없이 처리.
    """
    job = Job(
        client_id=UUID(current_user["user_id"]),
        source_lang=body.source_lang,
        target_lang=body.target_lang,
        content_type=body.content_type,
        quality_level=body.quality_level,
        word_count=body.word_count,
        deadline=body.deadline,
        status="REQUESTED",
    )
    db.add(job)
    await db.flush()

    # word_count가 있으면 즉시 견적 계산 큐 등록
    if body.word_count:
        calculate_quote.delay(str(job.id))

    return job


@router.post("/{job_id}/upload", response_model=JobResponse)
async def upload_file(
    job_id: UUID,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    번역 파일 업로드 (S3).
    업로드 완료 후 자동으로 견적 계산 큐 등록.
    허용 포맷: docx, doc, pdf, txt, xlsx, pptx, xliff
    """
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    if str(job.client_id) != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")

    file_url = await upload_translation_file(file, str(job_id))
    job.file_url = file_url

    # 파일 업로드 완료 후 견적 계산 큐 등록
    if job.word_count:
        calculate_quote.delay(str(job.id))

    return job


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return job


@router.get("/{job_id}/events", response_model=list[JobEventResponse])
async def get_job_events(
    job_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FSM 상태 전이 이력 조회 — 감사 로그 및 디버깅용"""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return job.events


@router.get("/{job_id}/stream")
async def stream_job_status(
    job_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    SSE(Server-Sent Events) 실시간 상태 스트림.
    클라이언트가 구독하면 상태 변화 시 자동으로 이벤트 수신.
    단방향 push에 최적화 (WebSocket 대비 구현 단순, HTTP/2 호환).
    """
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    async def event_generator():
        """폴링 방식으로 상태 변화를 감지하여 SSE 이벤트 전송 (Phase 4에서 Redis pub/sub로 개선 예정)"""
        last_status = None
        async with AsyncSessionLocal() as stream_db:
            while True:
                result = await stream_db.execute(
                    select(Job).where(Job.id == job_id)
                )
                current_job = result.scalar_one_or_none()
                if current_job is None:
                    break

                if current_job.status != last_status:
                    last_status = current_job.status
                    data = json.dumps(
                        {
                            "status": current_job.status,
                            "updatedAt": current_job.updated_at.isoformat(),
                        }
                    )
                    yield f"event: STATUS_UPDATE\ndata: {data}\n\n"

                    if state_machine.is_terminal_status(current_job.status):
                        completed_data = json.dumps({"status": current_job.status})
                        yield f"event: COMPLETED\ndata: {completed_data}\n\n"
                        break

                await asyncio.sleep(3)  # 3초 폴링 간격

    from db.session import AsyncSessionLocal  # 순환 참조 방지
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
