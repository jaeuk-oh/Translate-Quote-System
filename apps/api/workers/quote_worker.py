"""
견적 계산 Celery 워커.
파일 업로드 완료 → Celery 큐 등록 → 비동기 견적 계산 → SSE 응답.
API 응답 블로킹 없이 대용량 파일도 처리 가능.
"""

import asyncio
import logging
from uuid import UUID

from celery import Task
from sqlalchemy import select

from db.session import AsyncSessionLocal
from models.job import Job
from services import quote_service, state_machine
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """동기 Celery 컨텍스트에서 비동기 함수 실행 헬퍼"""
    return asyncio.get_event_loop().run_until_complete(coro)


@celery_app.task(
    name="workers.quote_worker.calculate_quote",
    bind=True,
    max_retries=3,
    # 지수 백오프 재시도 전략:
    # 1차 실패 → 60초, 2차 → 120초, 3차 → 240초
    default_retry_delay=60,
)
def calculate_quote(self: Task, job_id: str, tm_match_rate: float = 0.0):
    """
    견적 계산 Celery 태스크.

    처리 흐름:
    1. Job 조회
    2. FSM 전이: REQUESTED → QUOTE_PENDING
    3. 견적 계산 (quote_service.create_quote)
    4. FSM 전이: QUOTE_PENDING → QUOTED
    5. 견적 저장 + 상태 업데이트 커밋

    실패 시 지수 백오프로 자동 재시도 (최대 3회).
    """

    async def _calculate():
        async with AsyncSessionLocal() as db:
            try:
                # Job 조회
                result = await db.execute(
                    select(Job).where(Job.id == UUID(job_id))
                )
                job = result.scalar_one_or_none()
                if job is None:
                    logger.error(f"견적 계산 실패: job_id={job_id} 를 찾을 수 없음")
                    return

                # FSM 전이: REQUESTED → QUOTE_PENDING (견적 계산 시작)
                if job.status == "REQUESTED":
                    await state_machine.transition(
                        db=db,
                        job_id=job.id,
                        to_status="QUOTE_PENDING",
                        triggered_by="system",
                        metadata={"task_id": self.request.id},
                    )

                # 견적 계산 및 저장
                quote = await quote_service.create_quote(
                    db=db,
                    job=job,
                    tm_match_rate=tm_match_rate,
                )

                # FSM 전이: QUOTE_PENDING → QUOTED (견적 완료, 클라이언트 승인 대기)
                await state_machine.transition(
                    db=db,
                    job_id=job.id,
                    to_status="QUOTED",
                    triggered_by="system",
                    metadata={"quote_id": str(quote.id)},
                )

                await db.commit()
                logger.info(
                    f"견적 계산 완료: job_id={job_id}, "
                    f"price={quote.estimated_price}, quote_id={quote.id}"
                )

            except Exception as exc:
                await db.rollback()
                logger.exception(f"견적 계산 실패: job_id={job_id}, error={exc}")
                raise

    try:
        _run_async(_calculate())
    except Exception as exc:
        # 지수 백오프 재시도: countdown = delay × 2^(attempt)
        retry_in = self.default_retry_delay * (2 ** self.request.retries)
        logger.warning(
            f"견적 계산 재시도 예정: job_id={job_id}, "
            f"attempt={self.request.retries + 1}, "
            f"retry_in={retry_in}s"
        )
        raise self.retry(exc=exc, countdown=retry_in)
