"""
번역가 자동 배정 Celery 워커.
고객 견적 승인 시 자동으로 최적 번역가 배정.
번역가 수락/거절 없음 — 배정 즉시 확정.
"""

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select

from db.session import AsyncSessionLocal
from models.job import Job
from services import assign_service, state_machine
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """동기 Celery 컨텍스트에서 비동기 함수 실행 헬퍼"""
    return asyncio.get_event_loop().run_until_complete(coro)


@celery_app.task(
    name="workers.assign_worker.auto_assign",
    bind=True,
    max_retries=3,
)
def auto_assign(self, job_id: str, attempt: int = 1):
    """
    자동 배정 태스크.

    처리 흐름:
    1. 후보 번역가 조회 (언어쌍 + 가용 상태 필터)
    2. 점수 계산 → Top 3 중 attempt번째 선택
    3. 배정 레코드 생성 (즉시 확정, ASSIGNED 상태)
    4. FSM 전이: ASSIGNED → IN_PROGRESS
    5. 번역가에게 이메일 통보 (TODO)

    attempt: 재배정 시도 횟수 (1 = 최초 배정, 최대 3)
    """

    async def _assign():
        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(
                    select(Job).where(Job.id == UUID(job_id))
                )
                job = result.scalar_one_or_none()
                if job is None:
                    logger.error(f"배정 실패: job_id={job_id} 를 찾을 수 없음")
                    return

                # 최대 재배정 횟수 초과 → 관리자 에스컬레이션
                if attempt > assign_service.MAX_REASSIGN_ATTEMPTS:
                    logger.warning(
                        f"최대 재배정 횟수({assign_service.MAX_REASSIGN_ATTEMPTS}) 초과: "
                        f"job_id={job_id} — 관리자 알림 전송 필요"
                    )
                    # TODO: 관리자 Slack/이메일 알림 전송
                    return

                # 후보 번역가 조회 (상위 3명)
                candidates = await assign_service.get_candidates(db=db, job=job, limit=3)
                if not candidates:
                    logger.warning(f"배정 가능한 번역가 없음: job_id={job_id}, attempt={attempt}")
                    # 1시간 후 재시도 (번역가 가용 상태 변경 기대)
                    raise self.retry(countdown=3600)

                # attempt 순서의 번역가 선택 (1번째 시도 → 1위, 재배정 → 2위, 3위)
                idx = min(attempt - 1, len(candidates) - 1)
                translator, score = candidates[idx]

                # 배정 레코드 생성 (즉시 ASSIGNED 상태)
                assignment = await assign_service.create_assignment(
                    db=db,
                    job=job,
                    translator=translator,
                    score=score,
                )

                # FSM 전이: ASSIGNED → IN_PROGRESS (배정 즉시 작업 시작)
                await state_machine.transition(
                    db=db,
                    job_id=job.id,
                    to_status="IN_PROGRESS",
                    triggered_by="system",
                    metadata={
                        "assignment_id": str(assignment.id),
                        "translator_id": str(translator.id),
                        "score": str(score),
                        "attempt": attempt,
                    },
                )

                await db.commit()
                logger.info(
                    f"자동 배정 완료: job_id={job_id}, "
                    f"translator_id={translator.id}, "
                    f"score={score}, attempt={attempt}"
                )

                # TODO: 번역가 이메일 통보

            except Exception as exc:
                await db.rollback()
                logger.exception(f"배정 실패: job_id={job_id}, error={exc}")
                raise

    try:
        _run_async(_assign())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)
