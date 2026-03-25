"""
알림 발송 서비스.
이벤트 유형에 따라 수신자와 채널을 결정하고 Resend(이메일) 및 Slack Webhook으로 발송.

Redis SETNX로 중복 발송 방지: lock:notify:{job_id}:{event} EX 10
발송 성공/실패 결과를 notifications 테이블에 기록 (attempts 카운트 포함).

이벤트별 발송 매핑:
  QUOTED_DRAFT → 관리자     → 이메일 (내부 담당자에게 견적 검토 요청)
  QUOTED       → 클라이언트 → 이메일 (고객에게 견적 발송, 승인/거절 링크 포함)
  ASSIGNED     → 번역가     → 이메일 (배정 통보)
  COMPLETED    → 클라이언트 → 이메일 + Webhook
  QA_FAILED    → 번역가     → 이메일
  REASSIGNED   → 관리자     → Slack
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
import redis.asyncio as aioredis
import resend
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models.job import Job
from models.notification import Notification
from models.user import User

logger = logging.getLogger(__name__)

# Resend API 키 설정
resend.api_key = settings.RESEND_API_KEY

# Redis 클라이언트 (SETNX 중복 방지용)
_redis_client: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    """Redis 클라이언트 싱글턴 반환"""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


# ── 이벤트별 발송 채널 매핑 ─────────────────────────────────────────
# 수신자 역할과 채널 목록으로 구성
EVENT_CHANNEL_MAP: dict[str, dict[str, Any]] = {
    "QUOTED_DRAFT": {
        # 자동 견적 완료 → 내부 담당자에게 검토 요청 이메일
        "recipient_role": "admin",
        "channels": ["email"],
    },
    "QUOTED": {
        # 담당자 검토 완료 → 고객에게 견적 발송
        "recipient_role": "client",
        "channels": ["email"],
    },
    "ASSIGNED": {
        "recipient_role": "translator",
        "channels": ["email", "slack"],
    },
    "COMPLETED": {
        "recipient_role": "client",
        "channels": ["email", "webhook"],
    },
    "QA_FAILED": {
        "recipient_role": "translator",
        "channels": ["email"],
    },
    "REASSIGNED": {
        "recipient_role": "admin",
        "channels": ["slack"],
    },
}


def build_email_payload(event: str, job: Job, recipient_email: str) -> dict[str, Any]:
    """
    이벤트 유형과 작업 정보로 Resend API 이메일 페이로드 생성.
    수신자 이메일, 제목, 본문(HTML)을 포함한 딕셔너리 반환.
    """
    # 이벤트별 제목 및 본문 템플릿
    templates: dict[str, dict[str, str]] = {
        "QUOTED": {
            "subject": f"[번역 플랫폼] 견적이 완료되었습니다 - 작업 #{str(job.id)[:8]}",
            "body": f"""
                <h2>견적이 완료되었습니다</h2>
                <p>요청하신 번역 작업의 견적이 완료되었습니다.</p>
                <ul>
                    <li>언어쌍: {job.source_lang} → {job.target_lang}</li>
                    <li>콘텐츠 유형: {job.content_type or '미지정'}</li>
                    <li>단어 수: {job.word_count or '미산정'}</li>
                </ul>
                <p>플랫폼에 접속하여 견적을 확인하고 승인해주세요.</p>
            """,
        },
        "PENDING_ACCEPTANCE": {
            "subject": f"[번역 플랫폼] 새 번역 작업 배정 요청 - 작업 #{str(job.id)[:8]}",
            "body": f"""
                <h2>새 번역 작업 배정 요청</h2>
                <p>귀하에게 번역 작업이 배정되었습니다. 24시간 이내에 수락 여부를 결정해주세요.</p>
                <ul>
                    <li>언어쌍: {job.source_lang} → {job.target_lang}</li>
                    <li>콘텐츠 유형: {job.content_type or '미지정'}</li>
                    <li>마감일: {job.deadline.strftime('%Y-%m-%d') if job.deadline else '미지정'}</li>
                </ul>
            """,
        },
        "ASSIGNED": {
            "subject": f"[번역 플랫폼] 작업 배정 확정 - 작업 #{str(job.id)[:8]}",
            "body": f"""
                <h2>작업 배정이 확정되었습니다</h2>
                <p>번역 작업을 수락해주셔서 감사합니다. 작업을 시작해주세요.</p>
                <ul>
                    <li>언어쌍: {job.source_lang} → {job.target_lang}</li>
                    <li>마감일: {job.deadline.strftime('%Y-%m-%d') if job.deadline else '미지정'}</li>
                </ul>
            """,
        },
        "COMPLETED": {
            "subject": f"[번역 플랫폼] 번역이 완료되었습니다 - 작업 #{str(job.id)[:8]}",
            "body": f"""
                <h2>번역 작업이 완료되었습니다</h2>
                <p>요청하신 번역이 완료되어 결과물을 확인하실 수 있습니다.</p>
                <ul>
                    <li>언어쌍: {job.source_lang} → {job.target_lang}</li>
                </ul>
            """,
        },
        "QA_FAILED": {
            "subject": f"[번역 플랫폼] QA 검수 실패 - 수정 필요 - 작업 #{str(job.id)[:8]}",
            "body": f"""
                <h2>QA 검수에서 문제가 발견되었습니다</h2>
                <p>번역 결과물의 수정이 필요합니다. 플랫폼에서 상세 내용을 확인해주세요.</p>
                <ul>
                    <li>언어쌍: {job.source_lang} → {job.target_lang}</li>
                </ul>
            """,
        },
    }

    template = templates.get(event, {
        "subject": f"[번역 플랫폼] 작업 상태 업데이트 - {event}",
        "body": f"<p>작업 #{str(job.id)[:8]} 상태가 업데이트되었습니다: {event}</p>",
    })

    return {
        "from": settings.EMAIL_FROM,
        "to": [recipient_email],
        "subject": template["subject"],
        "html": template["body"],
    }


def build_slack_payload(event: str, job: Job) -> dict[str, Any]:
    """
    이벤트 유형과 작업 정보로 Slack Webhook 메시지 페이로드 생성.
    Slack Block Kit 형식 사용.
    """
    # 이벤트별 이모지와 메시지
    event_icons: dict[str, str] = {
        "ASSIGNED": ":white_check_mark:",
        "COMPLETED": ":tada:",
        "REASSIGNED": ":warning:",
        "QA_FAILED": ":x:",
    }
    icon = event_icons.get(event, ":bell:")

    return {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{icon} [{event}] 번역 작업 상태 변경",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*작업 ID:*\n`{str(job.id)[:8]}`"},
                    {"type": "mrkdwn", "text": f"*언어쌍:*\n{job.source_lang} → {job.target_lang}"},
                    {"type": "mrkdwn", "text": f"*콘텐츠:*\n{job.content_type or '미지정'}"},
                    {"type": "mrkdwn", "text": f"*상태:*\n{event}"},
                ],
            },
        ]
    }


async def _acquire_notify_lock(job_id: UUID, event: str, ttl: int = 10) -> bool:
    """
    Redis SETNX로 알림 발송 락 획득.
    동일 이벤트의 중복 발송을 방지하기 위한 분산 락.

    락 키: lock:notify:{job_id}:{event}
    TTL: 10초 (기본값) — 짧은 TTL로 일시적 장애 시 자동 해제

    반환: True = 락 획득 성공 (발송 진행), False = 락 획득 실패 (중복, 스킵)
    """
    redis = _get_redis()
    lock_key = f"lock:notify:{job_id}:{event}"
    # SET NX EX 조합 — 원자적으로 락 생성 + TTL 설정
    acquired = await redis.set(lock_key, "1", nx=True, ex=ttl)
    return bool(acquired)


async def _send_email(payload: dict[str, Any]) -> bool:
    """
    Resend Python SDK로 이메일 발송.
    발송 성공 시 True, 실패 시 False 반환.
    """
    try:
        resend.Emails.send(payload)
        return True
    except Exception as exc:
        logger.error("이메일 발송 실패: %s", exc)
        return False


async def _send_slack(payload: dict[str, Any]) -> bool:
    """
    httpx로 Slack Incoming Webhook POST 요청.
    SLACK_WEBHOOK_URL 미설정 시 스킵 (개발 환경 대응).
    """
    if not settings.SLACK_WEBHOOK_URL:
        logger.warning("SLACK_WEBHOOK_URL 미설정 — Slack 알림 스킵")
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(settings.SLACK_WEBHOOK_URL, json=payload)
            resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("Slack 알림 발송 실패: %s", exc)
        return False


async def send_notification_for_event(
    db: AsyncSession,
    job: Job,
    event: str,
    recipient_id: UUID,
    recipient_email: str,
) -> list[Notification]:
    """
    FSM 이벤트에 대응하는 알림 레코드를 생성하고 발송.

    처리 순서:
    1. Redis SETNX로 중복 발송 락 획득
    2. 이벤트 채널 매핑 조회
    3. 채널별 페이로드 생성
    4. 발송 시도 (이메일 / Slack)
    5. 결과를 notifications 테이블에 기록

    반환: 생성된 Notification 레코드 목록
    """
    # 중복 발송 방지 락 획득 시도
    lock_acquired = await _acquire_notify_lock(job.id, event)
    if not lock_acquired:
        logger.info("알림 락 획득 실패 (중복 발송 방지): job_id=%s, event=%s", job.id, event)
        return []

    event_config = EVENT_CHANNEL_MAP.get(event)
    if not event_config:
        logger.warning("알 수 없는 이벤트 유형 — 알림 스킵: %s", event)
        return []

    channels: list[str] = event_config["channels"]
    created_notifications: list[Notification] = []

    for channel in channels:
        # 채널별 페이로드 생성
        if channel == "email":
            payload = build_email_payload(event, job, recipient_email)
        elif channel in ("slack", "webhook"):
            payload = build_slack_payload(event, job)
        else:
            continue

        # Notification 레코드 생성 (PENDING 상태로 시작)
        notification = Notification(
            job_id=job.id,
            recipient_id=recipient_id,      # 외부 클라이언트/번역가는 None
            recipient_email=recipient_email,
            channel=channel,
            payload=payload,
            status="PENDING",
            attempts=0,
        )
        db.add(notification)
        await db.flush()  # ID 생성을 위해 flush

        # 즉시 발송 시도
        success = False
        if channel == "email":
            success = await _send_email(payload)
        elif channel in ("slack", "webhook"):
            success = await _send_slack(payload)

        # 발송 결과 기록
        notification.attempts += 1
        if success:
            notification.status = "SENT"
            notification.sent_at = datetime.now(timezone.utc)
            logger.info("알림 발송 성공: channel=%s, job_id=%s, event=%s", channel, job.id, event)
        else:
            notification.status = "FAILED"
            logger.warning("알림 발송 실패: channel=%s, job_id=%s, event=%s", channel, job.id, event)

        created_notifications.append(notification)

    return created_notifications


async def get_recipient_info(
    db: AsyncSession,
    job: Job,
    event: str,
) -> tuple[UUID, str] | None:
    """
    이벤트 유형에 따라 수신자 ID와 이메일 조회.

    이벤트별 수신자 역할:
    - client 역할: job.client_email 직접 사용 (users 테이블 조회 없음)
    - translator 역할: 배정된 Translator 레코드의 email 직접 사용 (계정 없음)
    - admin 역할: role='admin'인 첫 번째 사용자 조회

    반환: (recipient_id, recipient_email) 튜플, recipient_id는 외부 수신자의 경우 None
    """
    event_config = EVENT_CHANNEL_MAP.get(event)
    if not event_config:
        return None

    recipient_role = event_config["recipient_role"]

    if recipient_role == "client":
        # 고객은 users 테이블에 없음 — job에 직접 저장된 이메일 사용
        return (None, job.client_email)

    elif recipient_role == "translator":
        # 번역가는 계정 없음 — 배정된 translator 레코드의 email 직접 사용
        from models.assignment import Assignment
        from models.translator import Translator
        from sqlalchemy import and_
        result = await db.execute(
            select(Translator)
            .join(Assignment, Assignment.translator_id == Translator.id)
            .where(
                and_(
                    Assignment.job_id == job.id,
                    Assignment.status == "ASSIGNED",
                )
            )
            .order_by(Assignment.assigned_at.desc())
            .limit(1)
        )
        translator = result.scalar_one_or_none()
        if translator and translator.email:
            return (translator.id, translator.email)

    elif recipient_role == "admin":
        # 관리자 계정 조회 (Slack 전용 이벤트이므로 이메일은 플레이스홀더)
        result = await db.execute(
            select(User).where(User.role == "admin").limit(1)
        )
        user = result.scalar_one_or_none()
        if user:
            return user.id, user.email

    return None
