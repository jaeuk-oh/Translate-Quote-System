"""
Celery 애플리케이션 설정.
Redis를 브로커와 결과 백엔드로 사용.
견적 계산 및 번역가 배정 작업을 비동기로 처리하여 API 응답 지연 방지.
"""

from celery import Celery

from core.config import settings

# Celery 앱 인스턴스 생성
# 브로커: Redis (메시지 큐)
# 백엔드: Redis (작업 결과 저장)
celery_app = Celery(
    "translate_platform",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "workers.quote_worker",
        "workers.assign_worker",
    ],
)

celery_app.conf.update(
    # 직렬화 형식
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # 타임존
    timezone="Asia/Seoul",
    enable_utc=True,

    # 재시도 전략 기본값 — 각 워커에서 개별 설정으로 덮어씀
    task_acks_late=True,      # 작업 완료 후 ACK (실패 시 재큐)
    task_reject_on_worker_lost=True,

    # 지수 백오프 재시도 기본 설정
    task_default_retry_delay=60,  # 기본 1분 후 재시도
    task_max_retries=3,

    # Beat 스케줄 — 배정 만료 체크 (매분 실행)
    beat_schedule={
        "check-expired-assignments": {
            "task": "workers.assign_worker.check_expired_assignments",
            "schedule": 60.0,  # 60초마다 실행
        },
    },
)
