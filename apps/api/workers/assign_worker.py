"""
번역가 자동 배정 Celery 워커.
24시간 수락 타임아웃 + 최대 3회 재배정 전략으로 운영 개입 없이 배정 완료.
3회 재배정 실패 시 관리자에게 에스컬레이션 알림 전송.
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select

from db.session import AsyncSessionLocal
from models.assignment import Assignment
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
    3. 배정 레코드 생성
    4. FSM 전이: QUOTED → PENDING_ACCEPTANCE
    5. 번역가에게 수락 요청 알림 (Phase 3에서 구현)

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
                        f"job_id={job_id} — 관리자 알림 전송 예정 (Phase 3)"
                    )
                    # TODO Phase 3: 관리자 Slack/이메일 알림 전송
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

                # 배정 레코드 생성
                assignment = await assign_service.create_assignment(
                    db=db,
                    job=job,
                    translator=translator,
                    score=score,
                )

                # FSM 전이: QUOTED → PENDING_ACCEPTANCE
                await state_machine.transition(
                    db=db,
                    job_id=job.id,
                    to_status="PENDING_ACCEPTANCE",
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
                    f"배정 완료: job_id={job_id}, "
                    f"translator_id={translator.id}, "
                    f"score={score}, attempt={attempt}"
                )

            except Exception as exc:
                await db.rollback()
                logger.exception(f"배정 실패: job_id={job_id}, error={exc}")
                raise

    try:
        _run_async(_assign())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)


@celery_app.task(name="workers.assign_worker.auto_reassign")
def auto_reassign(job_id: str, attempt: int):
    """
    배정 거절 또는 타임아웃 시 다음 순위 번역가로 재배정.
    auto_assign 태스크를 attempt+1로 재호출.
    """
    logger.info(f"재배정 시작: job_id={job_id}, attempt={attempt}")
    auto_assign.delay(job_id=job_id, attempt=attempt)


@celery_app.task(name="workers.assign_worker.check_expired_assignments")
def check_expired_assignments():
    """
    Celery Beat 스케줄 태스크 (매분 실행).
    expires_at가 현재 시각보다 이전이고 PENDING_ACCEPTANCE 상태인
    배정 건을 찾아 EXPIRED 처리 후 재배정 트리거.

    Redis SETNX 락을 사용하여 동시 실행 방지 (Phase 3 구현 예정).
    """

    async def _check():
        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)

            # 만료된 배정 조회
            result = await db.execute(
                select(Assignment).where(
                    and_(
                        Assignment.status == "PENDING_ACCEPTANCE",
                        Assignment.expires_at <= now,
                    )
                )
            )
            expired_assignments = result.scalars().all()

            for assignment in expired_assignments:
                try:
                    # 만료 처리
                    assignment.status = "EXPIRED"

                    # 번역가 부하 복원
                    if assignment.translator and assignment.translator.current_load > 0:
                        assignment.translator.current_load -= 1

                    # 현재 재배정 시도 횟수 계산 (이벤트 이력 기반)
                    job_result = await db.execute(
                        select(Job).where(Job.id == assignment.job_id)
                    )
                    job = job_result.scalar_one_or_none()
                    if job is None:
                        continue

                    # 이미 처리된 배정 수 = 다음 시도 번호
                    attempt_result = await db.execute(
                        select(Assignment).where(
                            and_(
                                Assignment.job_id == assignment.job_id,
                                Assignment.status.in_(["EXPIRED", "REJECTED"]),
                            )
                        )
                    )
                    past_attempts = len(attempt_result.scalars().all())
                    next_attempt = past_attempts + 1

                    await db.commit()

                    logger.info(
                        f"배정 만료 처리: assignment_id={assignment.id}, "
                        f"job_id={assignment.job_id}, next_attempt={next_attempt}"
                    )

                    # 재배정 태스크 큐 등록 (5분 후 실행 — 즉시 재시도 방지)
                    auto_reassign.apply_async(
                        args=[str(assignment.job_id), next_attempt],
                        countdown=300,
                    )

                except Exception as exc:
                    await db.rollback()
                    logger.exception(
                        f"배정 만료 처리 실패: assignment_id={assignment.id}, error={exc}"
                    )

    _run_async(_check())
