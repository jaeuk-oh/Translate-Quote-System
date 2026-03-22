"""
SSE(Server-Sent Events) 서비스.
FSM 상태별 진행률 계산 및 SSE 이벤트 페이로드 생성.

진행률은 클라이언트 대시보드의 프로그레스 바에 사용됨.
COMPLETED 이벤트에는 다운로드 URL 포함 (파일 번역 완료 시).
"""

from datetime import datetime, timezone
from typing import Optional

# FSM 상태별 진행률 매핑 (%)
# 각 단계의 가중치는 실제 소요 시간 비율을 반영하여 설정
STATUS_PROGRESS: dict[str, int] = {
    "REQUESTED": 5,            # 의뢰 접수 (초기 상태)
    "QUOTE_PENDING": 15,       # 견적 계산 중 (Celery 워커 처리 중)
    "QUOTED": 25,              # 견적 완료, 클라이언트 승인 대기
    "PENDING_ACCEPTANCE": 35,  # 번역가 배정 및 수락 대기
    "ASSIGNED": 45,            # 번역가 배정 완료
    "IN_PROGRESS": 65,         # 번역 진행 중 (가장 긴 단계)
    "REVIEW": 80,              # 검토 단계
    "QA": 90,                  # 품질 검수 단계
    "COMPLETED": 100,          # 최종 완료
}

# 취소/알 수 없는 상태의 기본 진행률
DEFAULT_PROGRESS = 0


def calculate_progress(status: str) -> int:
    """
    FSM 상태 문자열을 진행률(0~100)로 변환.
    등록되지 않은 상태(CANCELLED 등)는 0 반환.
    """
    return STATUS_PROGRESS.get(status, DEFAULT_PROGRESS)


def build_status_event(job) -> dict:
    """
    일반 상태 업데이트 SSE 이벤트 페이로드 생성.
    클라이언트는 이 이벤트를 수신하여 프로그레스 바와 상태 배지를 갱신.

    Args:
        job: Job ORM 객체 (status, updated_at 필드 사용)

    Returns:
        dict: SSE data 필드에 JSON 직렬화할 페이로드
    """
    progress = calculate_progress(job.status)

    # updated_at이 없는 경우 현재 시각으로 폴백
    updated_at = (
        job.updated_at.isoformat()
        if job.updated_at
        else datetime.now(timezone.utc).isoformat()
    )

    return {
        "status": job.status,
        "progress": progress,
        "updatedAt": updated_at,
    }


def build_completed_event(job, download_url: Optional[str] = None) -> dict:
    """
    COMPLETED 상태 SSE 이벤트 페이로드 생성.
    번역 파일이 있을 경우 downloadUrl 포함.
    클라이언트는 이 이벤트 수신 후 SSE 연결을 종료.

    Args:
        job: Job ORM 객체
        download_url: S3 presigned URL 또는 파일 다운로드 URL (없으면 None)

    Returns:
        dict: COMPLETED 이벤트 페이로드
    """
    completed_at = (
        job.updated_at.isoformat()
        if job.updated_at
        else datetime.now(timezone.utc).isoformat()
    )

    return {
        "status": "COMPLETED",
        "progress": 100,
        "downloadUrl": download_url,
        "completedAt": completed_at,
    }
