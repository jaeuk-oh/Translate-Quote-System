"""
FSM(유한 상태 머신) 서비스.
번역 작업의 모든 상태 전이를 단일 진입점에서 관리하여 일관성 보장.
상태 변경과 이벤트 기록을 하나의 DB 트랜잭션 내에서 원자적으로 처리.
전이 실패 시 FSMException 발생 + 트랜잭션 롤백.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.job import Job, JobEvent

# ── FSM 전이 테이블 ─────────────────────────────────────────────
# 허용된 전이만 등록. 리스트 = 같은 from_status에서 여러 to_status 가능.
#
# 플로우:
#   REQUESTED → QUOTE_PENDING (Celery 견적 계산 시작)
#   QUOTE_PENDING → QUOTED_DRAFT (자동 견적 완료, 내부 담당자 검토 대기)
#   QUOTED_DRAFT → QUOTED (내부 담당자 승인 후 고객에게 발송)
#   QUOTED → ASSIGNED (고객 이메일 링크 승인 → 번역가 배정 완료)
#   ASSIGNED → IN_PROGRESS → REVIEW → QA → COMPLETED
VALID_TRANSITIONS: dict[str, list[str]] = {
    "REQUESTED":    ["QUOTE_PENDING"],
    "QUOTE_PENDING": ["QUOTED_DRAFT"],          # 자동 견적 완료
    "QUOTED_DRAFT": ["QUOTED"],                  # 내부 담당자 검토 → 고객 발송
    "QUOTED":       ["ASSIGNED"],                # 고객 승인 → 배정 (PENDING_ACCEPTANCE 제거)
    "ASSIGNED":     ["IN_PROGRESS"],
    "IN_PROGRESS":  ["REVIEW"],
    "REVIEW":       ["QA"],
    # QA 분기: 통과 → COMPLETED, 실패 → IN_PROGRESS (최대 3회, 워커에서 제한)
    "QA":           ["COMPLETED", "IN_PROGRESS"],
    # 어느 상태에서든 취소 가능
    "CANCELLED":    [],
}


class FSMException(Exception):
    """
    FSM 전이 실패 예외.
    허용되지 않은 전이 시도 또는 존재하지 않는 작업에 발생.
    """
    pass


async def transition(
    db: AsyncSession,
    job_id: UUID,
    to_status: str,
    triggered_by: str = "system",
    actor_id: Optional[UUID] = None,
    metadata: Optional[dict] = None,
) -> Job:
    """
    Job 상태 전이 핵심 함수.

    처리 순서:
    1. 현재 Job 상태 조회 (행 잠금: FOR UPDATE)
    2. 전이 허용 여부 검증
    3. Job.status 업데이트
    4. job_events에 이력 기록
    5. 커밋 (호출자가 세션 관리)

    트랜잭션은 get_db() 의존성이 관리하며, 예외 발생 시 자동 롤백됨.
    """
    # 행 잠금으로 동시 전이 충돌 방지 (경쟁 조건 차단)
    result = await db.execute(
        select(Job).where(Job.id == job_id).with_for_update()
    )
    job = result.scalar_one_or_none()

    if job is None:
        raise FSMException(f"작업을 찾을 수 없습니다: job_id={job_id}")

    from_status = job.status

    # ── 전이 유효성 검증 ─────────────────────────────────────────
    # 취소 전이는 어느 상태에서든 허용 (단, 이미 완료된 작업 제외)
    if to_status == "CANCELLED":
        if from_status == "COMPLETED":
            raise FSMException("완료된 작업은 취소할 수 없습니다.")
    else:
        allowed = VALID_TRANSITIONS.get(from_status, [])
        if to_status not in allowed:
            raise FSMException(
                f"허용되지 않은 상태 전이: {from_status} → {to_status}. "
                f"허용 전이: {allowed}"
            )

    # ── Job 상태 업데이트 ──────────────────────────────────────
    job.status = to_status

    # ── 이벤트 이력 기록 (이벤트 소싱) ────────────────────────
    event = JobEvent(
        job_id=job_id,
        from_status=from_status,
        to_status=to_status,
        triggered_by=triggered_by,
        actor_id=actor_id,
        event_data=metadata or {},
    )
    db.add(event)

    # 세션 flush — 커밋 전 변경사항을 DB에 반영 (같은 트랜잭션 내)
    await db.flush()

    return job


def get_allowed_transitions(current_status: str) -> list[str]:
    """현재 상태에서 가능한 다음 상태 목록 반환 (UI 표시용)"""
    return VALID_TRANSITIONS.get(current_status, [])


def is_terminal_status(status: str) -> bool:
    """종료 상태 여부 확인 — 완료/취소는 더 이상 전이 불가"""
    return status in {"COMPLETED", "CANCELLED"}
