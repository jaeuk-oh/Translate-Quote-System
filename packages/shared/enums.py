"""
공유 열거형 상수 모듈.
백엔드 서비스와 워커 간에 동일한 상태값을 사용하기 위해 단일 파일로 관리.
"""

from enum import Enum


class JobStatus(str, Enum):
    """번역 작업 상태 열거형 — FSM 상태 머신이 관리하는 전이 단위"""
    REQUESTED = "REQUESTED"                  # 의뢰 접수
    QUOTE_PENDING = "QUOTE_PENDING"          # 견적 계산 중 (비동기)
    QUOTED = "QUOTED"                        # 견적 완료, 클라이언트 승인 대기
    PENDING_ACCEPTANCE = "PENDING_ACCEPTANCE"  # 번역가 수락 대기
    ASSIGNED = "ASSIGNED"                    # 번역가 배정 완료
    IN_PROGRESS = "IN_PROGRESS"              # 번역 진행 중
    REVIEW = "REVIEW"                        # 검토 단계
    QA = "QA"                                # 품질 검수 단계
    COMPLETED = "COMPLETED"                  # 최종 완료
    CANCELLED = "CANCELLED"                  # 취소


class TranslatorAvailability(str, Enum):
    """번역가 가용 상태 — workload_ratio 기반으로 자동 갱신"""
    AVAILABLE = "AVAILABLE"      # 즉시 배정 가능 (workload_ratio = 0)
    BUSY = "BUSY"                # 작업 중이나 여유 있음 (0 < ratio < 1.0)
    OVERLOADED = "OVERLOADED"    # 과부하 상태 (ratio >= 1.0), 배정 불가
    OFFLINE = "OFFLINE"          # 비활성, 배정 불가


class AssignmentStatus(str, Enum):
    """배정 수락/거절 상태"""
    PENDING_ACCEPTANCE = "PENDING_ACCEPTANCE"  # 수락 대기 중
    ACCEPTED = "ACCEPTED"                      # 번역가 수락
    REJECTED = "REJECTED"                      # 번역가 거절
    EXPIRED = "EXPIRED"                        # 24시간 타임아웃


class QuoteStatus(str, Enum):
    """견적 상태"""
    PENDING = "PENDING"      # 계산 대기
    COMPLETED = "COMPLETED"  # 견적 완료
    APPROVED = "APPROVED"    # 클라이언트 승인
    REJECTED = "REJECTED"    # 클라이언트 거절


class NotificationChannel(str, Enum):
    """알림 발송 채널"""
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"


class NotificationStatus(str, Enum):
    """알림 발송 상태"""
    PENDING = "PENDING"    # 발송 대기
    SENT = "SENT"          # 발송 완료
    FAILED = "FAILED"      # 발송 실패
    DLQ = "DLQ"            # Dead Letter Queue (최대 재시도 초과)


class UserRole(str, Enum):
    """사용자 역할"""
    CLIENT = "client"
    TRANSLATOR = "translator"
    ADMIN = "admin"


class ContentType(str, Enum):
    """번역 콘텐츠 유형 — 난이도 계산에 사용"""
    MARKETING = "marketing"
    LEGAL = "legal"
    TECHNICAL = "technical"
    GENERAL = "general"
    MEDICAL = "medical"


class QualityLevel(str, Enum):
    """품질 등급 — 견적 단가에 영향"""
    TRANSLATION = "translation"  # 번역만
    REVIEW = "review"            # 번역 + 검수
    DTP = "dtp"                  # 번역 + 검수 + 편집
