"""
번역 작업(Job) 라우터.
의뢰 등록, 파일 업로드, 상태 조회, SSE 스트림 엔드포인트 제공.
"""

import asyncio
import json
from typing import AsyncGenerator, Optional
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, decode_translator_submit_token
from core.config import settings
from core.rate_limit import limiter
from core.storage import upload_translation_file
from db.session import get_db
from models.job import Job
from schemas.job import JobCreate, JobEventResponse, JobResponse, JobStatusUpdate
from services import state_machine
from services.sse_service import build_completed_event, build_status_event
from workers.quote_worker import calculate_quote

router = APIRouter(prefix="/jobs", tags=["번역 작업"])

# SSE keepalive 핑 간격 (초) — 30초마다 `:ping\n\n` 전송으로 연결 유지
SSE_KEEPALIVE_INTERVAL = 30

# Redis pub/sub 채널 이름 템플릿
# 상태 변경 시 Celery 워커에서 이 채널로 PUBLISH
REDIS_CHANNEL_TEMPLATE = "channel:job:{job_id}"


@router.post("", response_model=JobResponse, status_code=201)
@limiter.limit("30/minute")
async def create_job(
    request: Request,
    body: JobCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    번역 의뢰 등록 — 인증 불필요, 고객이 폼으로 직접 제출.
    즉시 job_id 반환 후 비동기로 견적 계산 (Celery 큐 등록).
    """
    job = Job(
        client_name=body.client_name,
        client_email=body.client_email,
        source_lang=body.source_lang,
        target_lang=body.target_lang,
        content_type=body.content_type,
        quality_level=body.quality_level,
        word_count=body.word_count,
        deadline=body.deadline,
        notes=body.notes,
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
    번역 파일 업로드 (S3) — 내부 담당자 전용.
    업로드 완료 후 자동으로 견적 계산 큐 등록.
    허용 포맷: docx, doc, pdf, txt, xlsx, pptx, xliff
    """
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    file_url = await upload_translation_file(file, str(job_id))
    job.file_url = file_url

    # 파일 업로드 완료 후 견적 계산 큐 등록
    if job.word_count:
        calculate_quote.delay(str(job.id))

    return job


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status_filter: Optional[str] = None,
):
    """
    번역 작업 목록 조회 — 내부 담당자 전용.
    status_filter 파라미터로 특정 상태만 필터링 가능.
    """
    stmt = select(Job)

    # 상태 필터링 (선택적)
    if status_filter:
        stmt = stmt.where(Job.status == status_filter)

    # 최신 작업 우선 정렬
    stmt = stmt.order_by(Job.created_at.desc())

    result = await db.execute(stmt)
    return result.scalars().all()


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


@router.post("/{job_id}/complete", response_model=JobResponse)
@limiter.limit("10/minute")
async def submit_completed_file(
    request: Request,
    job_id: UUID,
    token: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    번역 완료 파일 제출 — 번역가 전용 (토큰 인증).
    배정 확정 이메일의 링크에 포함된 토큰으로 인증하며 로그인 불필요.

    처리 흐름:
    1. 제출 토큰 검증 (job_id 일치 여부 포함)
    2. 결과 파일을 Supabase Storage에 업로드 (file_type=result)
    3. FSM 전이: IN_PROGRESS → REVIEW
    4. 관리자에게 검토 요청 알림 발송
    """
    from services import notification_service

    # 토큰 검증 — job_id 불일치 시 400
    token_data = decode_translator_submit_token(token)
    if token_data["job_id"] != str(job_id):
        raise HTTPException(status_code=400, detail="토큰의 작업 정보가 일치하지 않습니다.")

    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    if job.status != "IN_PROGRESS":
        raise HTTPException(
            status_code=400,
            detail=f"완료 파일 제출은 IN_PROGRESS 상태에서만 가능합니다. 현재: {job.status}",
        )

    # 완료 파일 업로드 (file_type=result로 원본과 경로 분리)
    result_url = await upload_translation_file(file, str(job_id), file_type="result")
    job.result_file_url = result_url

    # FSM 전이: IN_PROGRESS → REVIEW
    await state_machine.transition(
        db=db,
        job_id=job.id,
        to_status="REVIEW",
        triggered_by="translator",
        metadata={"translator_id": token_data["translator_id"], "result_file_url": result_url},
    )

    # 관리자에게 검토 요청 알림 (대시보드 링크 포함)
    recipient = await notification_service.get_recipient_info(db, job, "SUBMITTED")
    if recipient:
        recipient_id, recipient_email = recipient
        dashboard_url = f"{settings.FRONTEND_URL}/jobs/{job_id}"
        await notification_service.send_notification_for_event(
            db=db,
            job=job,
            event="SUBMITTED",
            recipient_id=recipient_id,
            recipient_email=recipient_email,
            extra={"dashboard_url": dashboard_url},
        )

    await db.commit()
    await db.refresh(job)
    return job


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

    동작 방식:
    1. 연결 시 현재 상태로 즉시 초기 이벤트 발송
    2. Redis pub/sub channel:job:{job_id}를 구독하여 상태 변화 감지
    3. COMPLETED 이벤트 수신 시 스트림 종료
    4. 30초 keepalive ping으로 연결 유지
    5. 클라이언트 disconnect 시 Redis 구독 해제
    """
    # job 존재 여부 확인
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    # 이미 종료 상태인 경우 즉시 단일 이벤트 후 스트림 종료
    initial_job = job

    async def event_generator() -> AsyncGenerator[str, None]:
        """
        Redis pub/sub 기반 SSE 이벤트 제너레이터.
        연결 시 즉시 현재 상태 발송 후 상태 변화 구독 대기.
        """
        # Redis 연결 생성 (각 SSE 스트림마다 독립 연결)
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        channel_name = REDIS_CHANNEL_TEMPLATE.format(job_id=str(job_id))

        try:
            # ── 초기 이벤트: 현재 상태 즉시 발송 ──────────────────
            if state_machine.is_terminal_status(initial_job.status):
                # 이미 완료/취소 상태인 경우 COMPLETED 이벤트 발송 후 종료
                completed_payload = build_completed_event(initial_job)
                yield f"event: COMPLETED\ndata: {json.dumps(completed_payload, ensure_ascii=False)}\n\n"
                return

            # 진행 중 상태: 현재 상태 이벤트 발송
            status_payload = build_status_event(initial_job)
            yield f"event: STATUS_UPDATE\ndata: {json.dumps(status_payload, ensure_ascii=False)}\n\n"

            # ── Redis pub/sub 구독 시작 ─────────────────────────
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(channel_name)

            # keepalive 타이머 초기화
            last_ping_time = asyncio.get_event_loop().time()

            try:
                while True:
                    # keepalive ping 전송 (30초 간격)
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_ping_time >= SSE_KEEPALIVE_INTERVAL:
                        yield ": ping\n\n"
                        last_ping_time = current_time

                    # Redis 메시지 비동기 수신 (타임아웃: 1초)
                    # get_message()는 non-blocking이므로 sleep으로 CPU 사용 제어
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    )

                    if message is None:
                        # 메시지 없음 — 짧게 대기 후 재시도
                        await asyncio.sleep(0.1)
                        continue

                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                        except (json.JSONDecodeError, TypeError):
                            continue

                        new_status = data.get("status", "")

                        if state_machine.is_terminal_status(new_status):
                            # 완료/취소: COMPLETED 이벤트 발송 후 스트림 종료
                            download_url = data.get("downloadUrl")
                            # DB에서 최신 job 조회
                            from db.session import AsyncSessionLocal
                            async with AsyncSessionLocal() as stream_db:
                                res = await stream_db.execute(
                                    select(Job).where(Job.id == job_id)
                                )
                                final_job = res.scalar_one_or_none()

                            if final_job:
                                completed_payload = build_completed_event(
                                    final_job, download_url
                                )
                            else:
                                completed_payload = {
                                    "status": new_status,
                                    "progress": 100,
                                    "downloadUrl": download_url,
                                }

                            yield f"event: COMPLETED\ndata: {json.dumps(completed_payload, ensure_ascii=False)}\n\n"
                            return
                        else:
                            # 중간 상태 업데이트: DB에서 최신 job 조회 후 이벤트 발송
                            from db.session import AsyncSessionLocal
                            async with AsyncSessionLocal() as stream_db:
                                res = await stream_db.execute(
                                    select(Job).where(Job.id == job_id)
                                )
                                updated_job = res.scalar_one_or_none()

                            if updated_job:
                                status_payload = build_status_event(updated_job)
                                yield f"event: STATUS_UPDATE\ndata: {json.dumps(status_payload, ensure_ascii=False)}\n\n"

            except asyncio.CancelledError:
                # 클라이언트 disconnect 시 구독 해제 후 정리
                await pubsub.unsubscribe(channel_name)
                raise

        except Exception:
            # 예기치 않은 오류: 연결 오류 이벤트 발송
            error_payload = json.dumps({"error": "스트림 연결 오류가 발생했습니다."})
            yield f"event: ERROR\ndata: {error_payload}\n\n"
        finally:
            # Redis 연결 항상 정리
            await redis_client.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
