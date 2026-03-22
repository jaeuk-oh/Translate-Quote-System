"""
알림 발송 Celery 워커.
지수 백오프 재시도 전략으로 일시적 발송 실패에 대응.

재시도 일정:
  1차 실패 → 60초 후 재시도
  2차 실패 → 300초(5분) 후 재시도
  3차 실패 → 1800초(30분) 후 재시도
  4차 실패 → DEAD_LETTER 처리 + 관리자 Slack 알림

Redis SETNX 락 획득 실패 시 즉시 스킵 (중복 방지).
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from celery import Task
from sqlalchemy import select

from core.config import settings
from db.session import AsyncSessionLocal
from models.notification import Notification
from services.notification_service import (
    _acquire_notify_lock,
    _send_email,
    _send_slack,
    build_slack_payload,
)
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# 지수 백오프 재시도 대기 시간 (초)
# 1분 → 5분 → 30분 → DLQ
RETRY_COUNTDOWNS = [60, 300, 1800]


class NotifyTask(Task):
    """
    알림 태스크 기반 클래스.
    on_failure 훅으로 최종 실패 시 DLQ 처리.
    """

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """max_retries 초과 시 호출 — DEAD_LETTER 상태로 마킹"""
        notification_id = args[0] if args else kwargs.get("notification_id")
        if notification_id:
            # 동기적으로 DLQ 처리 실행
            asyncio.run(_mark_dead_letter(str(notification_id)))
        logger.critical(
            "알림 최종 실패 — DEAD_LETTER 처리: notification_id=%s, 예외=%s",
            notification_id, exc,
        )


@celery_app.task(
    base=NotifyTask,
    bind=True,
    name="workers.notify_worker.send_notification",
    max_retries=3,
    # acks_late=True — 태스크 완료 후 ACK (실패 시 재큐)
    acks_late=True,
)
def send_notification(self: Task, notification_id: str) -> dict:
    """
    알림 발송 Celery 태스크.

    처리 순서:
    1. DB에서 Notification 레코드 조회
    2. Redis SETNX로 락 획득 (중복 방지)
    3. 채널별 발송 (이메일 / Slack / Webhook)
    4. 발송 성공 → status=SENT, sent_at 기록
    5. 발송 실패 → 지수 백오프로 재시도
    6. max_retries 초과 → DEAD_LETTER 처리 (on_failure 훅)
    """
    return asyncio.run(_execute_send_notification(self, notification_id))


async def _execute_send_notification(task: Task, notification_id: str) -> dict:
    """send_notification 태스크의 비동기 실행 본체"""
    async with AsyncSessionLocal() as db:
        try:
            # Notification 레코드 조회
            result = await db.execute(
                select(Notification).where(
                    Notification.id == UUID(notification_id)
                )
            )
            notification = result.scalar_one_or_none()

            if notification is None:
                logger.error("알림 레코드 없음: notification_id=%s", notification_id)
                return {"status": "not_found"}

            # 이미 발송 완료된 알림은 스킵
            if notification.status == "SENT":
                logger.info("이미 발송된 알림 스킵: notification_id=%s", notification_id)
                return {"status": "already_sent"}

            # DLQ 상태는 수동 재시도 외에는 처리하지 않음
            if notification.status == "DEAD_LETTER":
                logger.warning("DEAD_LETTER 알림 스킵: notification_id=%s", notification_id)
                return {"status": "dead_letter"}

            # Redis SETNX 락 획득 시도
            # 현재 시도 횟수에 따라 락 TTL 조정 (재시도 간격보다 짧게)
            lock_acquired = await _acquire_notify_lock(
                notification.job_id,
                f"send:{notification_id}",
                ttl=30,
            )
            if not lock_acquired:
                logger.info("락 획득 실패 (중복 실행 방지): notification_id=%s", notification_id)
                return {"status": "skipped_duplicate"}

            # 채널별 발송 실행
            payload = notification.payload or {}
            success = False

            if notification.channel == "email":
                success = await _send_email(payload)
            elif notification.channel in ("slack", "webhook"):
                success = await _send_slack(payload)
            else:
                logger.error("알 수 없는 채널: %s", notification.channel)
                return {"status": "unknown_channel"}

            # 발송 결과 기록
            notification.attempts += 1

            if success:
                notification.status = "SENT"
                notification.sent_at = datetime.now(timezone.utc)
                await db.commit()
                logger.info(
                    "알림 발송 성공: notification_id=%s, channel=%s, attempts=%d",
                    notification_id, notification.channel, notification.attempts,
                )
                return {"status": "sent", "attempts": notification.attempts}
            else:
                # 발송 실패 — 재시도 대기 시간 계산 (지수 백오프)
                retry_index = task.request.retries  # 현재 재시도 횟수 (0-based)
                countdown = RETRY_COUNTDOWNS[retry_index] if retry_index < len(RETRY_COUNTDOWNS) else RETRY_COUNTDOWNS[-1]

                notification.status = "FAILED"
                notification.next_retry_at = datetime.now(timezone.utc).replace(
                    second=datetime.now(timezone.utc).second + countdown
                )
                await db.commit()

                logger.warning(
                    "알림 발송 실패 — %d초 후 재시도: notification_id=%s, attempts=%d",
                    countdown, notification_id, notification.attempts,
                )

                # 지수 백오프 재시도 예약
                raise task.retry(
                    countdown=countdown,
                    exc=RuntimeError(f"알림 발송 실패: channel={notification.channel}"),
                )

        except task.MaxRetriesExceededError:
            # on_failure 훅으로 위임 (DEAD_LETTER 처리)
            raise
        except Exception as exc:
            await db.rollback()
            logger.exception("알림 태스크 예외: notification_id=%s", notification_id)
            raise task.retry(
                countdown=RETRY_COUNTDOWNS[min(task.request.retries, len(RETRY_COUNTDOWNS) - 1)],
                exc=exc,
            )


async def _mark_dead_letter(notification_id: str) -> None:
    """
    최대 재시도 초과 시 알림 상태를 DEAD_LETTER로 마킹.
    관리자에게 Slack 알림 발송 (Slack은 별도 재시도 없이 best-effort).
    """
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(Notification).where(
                    Notification.id == UUID(notification_id)
                )
            )
            notification = result.scalar_one_or_none()

            if notification:
                notification.status = "DEAD_LETTER"
                await db.commit()
                logger.critical(
                    "DEAD_LETTER 마킹 완료: notification_id=%s, channel=%s, attempts=%d",
                    notification_id, notification.channel, notification.attempts,
                )

            # 관리자 Slack 알림 (best-effort, 실패해도 예외 무시)
            admin_payload = {
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": ":rotating_light: [DEAD_LETTER] 알림 최종 발송 실패",
                        },
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Notification ID:*\n`{notification_id}`"},
                            {
                                "type": "mrkdwn",
                                "text": f"*채널:*\n{notification.channel if notification else 'unknown'}",
                            },
                        ],
                    },
                ]
            }
            await _send_slack(admin_payload)

        except Exception:
            logger.exception("DEAD_LETTER 처리 중 오류: notification_id=%s", notification_id)
            # 예외를 삼킴 — 이미 실패한 태스크에서 추가 예외 방지
