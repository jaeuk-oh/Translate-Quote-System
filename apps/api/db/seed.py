"""
더미 데이터 시딩 스크립트.
개발/테스트용으로 관리자 계정, 번역가, 다양한 FSM 상태의 작업을 생성.

실행 방법:
  cd apps/api
  python db/seed.py

주의: 기존 데이터를 삭제하고 새로 삽입함 (멱등 실행 가능).
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt

# apps/api를 패키지 루트로 설정
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete

def hash_password(plain: str) -> str:
    """bcrypt 직접 사용 — passlib/bcrypt 버전 충돌 우회"""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()
from db.session import AsyncSessionLocal
from models.assignment import Assignment
from models.job import Job, JobEvent
from models.notification import Notification
from models.quote import Quote
from models.translator import Translator
from models.user import User

# ── 시드 데이터 정의 ────────────────────────────────────────────────

ADMIN_USER = {
    "email": "admin@translate.co",
    "password": "admin1234",
    "role": "admin",
}

TRANSLATORS = [
    {
        "name": "김민준",
        "email": "minjun.kim@translator.co",
        "lang_pairs": ["ko-en", "ko-ja"],
        "specialties": ["marketing", "general"],
        "quality_score": 0.92,
        "on_time_rate": 0.95,
        "throughput": 3500.0,
        "responsiveness": 0.88,
        "availability": "AVAILABLE",
        "current_load": 1,
        "max_load": 3,
    },
    {
        "name": "이서연",
        "email": "seoyeon.lee@translator.co",
        "lang_pairs": ["ko-en", "ko-zh"],
        "specialties": ["legal", "technical"],
        "quality_score": 0.97,
        "on_time_rate": 0.90,
        "throughput": 2800.0,
        "responsiveness": 0.95,
        "availability": "AVAILABLE",
        "current_load": 2,
        "max_load": 3,
    },
    {
        "name": "박지호",
        "email": "jiho.park@translator.co",
        "lang_pairs": ["ko-en"],
        "specialties": ["medical", "technical"],
        "quality_score": 0.89,
        "on_time_rate": 0.98,
        "throughput": 4000.0,
        "responsiveness": 0.82,
        "availability": "BUSY",
        "current_load": 3,
        "max_load": 3,
    },
]

now = datetime.now(timezone.utc)

# 다양한 FSM 상태의 작업 — 각 단계를 대시보드에서 확인할 수 있도록 구성
JOBS = [
    # [1] 견적 검토 필요 (담당자 액션 필요)
    {
        "client_name": "삼성전자 마케팅팀",
        "client_email": "marketing@samsung.com",
        "source_lang": "ko",
        "target_lang": "en",
        "content_type": "marketing",
        "quality_level": "review",
        "word_count": 2500,
        "status": "QUOTED_DRAFT",
        "deadline": now + timedelta(days=7),
        "notes": "신제품 갤럭시 S25 마케팅 자료 번역. 전문 용어 일관성 유지 필요.",
        "quote": {
            "estimated_price": 375000,
            "currency": "KRW",
            "estimated_hours": 10.0,
            "confidence": 0.92,
            "word_count": 2500,
            "difficulty": 1.2,
            "deadline_multiplier": 1.0,
            "tm_match_rate": 0.15,
            "status": "PENDING",
        },
    },
    # [2] 번역가 배정 확정 필요 (담당자 액션 필요)
    {
        "client_name": "법무법인 태평양",
        "client_email": "contact@bkl.co.kr",
        "source_lang": "ko",
        "target_lang": "en",
        "content_type": "legal",
        "quality_level": "review",
        "word_count": 5000,
        "status": "ASSIGNED",
        "deadline": now + timedelta(days=5),
        "notes": "계약서 번역. 법률 용어 정확성 최우선.",
        "quote": {
            "estimated_price": 1250000,
            "currency": "KRW",
            "estimated_hours": 25.0,
            "confidence": 0.88,
            "word_count": 5000,
            "difficulty": 1.8,
            "deadline_multiplier": 1.1,
            "tm_match_rate": 0.05,
            "status": "APPROVED",
        },
    },
    # [3] 고객 확인 대기 중
    {
        "client_name": "카카오엔터프라이즈",
        "client_email": "global@kakaoenterprise.com",
        "source_lang": "ko",
        "target_lang": "en",
        "content_type": "technical",
        "quality_level": "translation",
        "word_count": 1800,
        "status": "QUOTED",
        "deadline": now + timedelta(days=10),
        "notes": "API 문서 영문화.",
        "quote": {
            "estimated_price": 216000,
            "currency": "KRW",
            "estimated_hours": 6.0,
            "confidence": 0.95,
            "word_count": 1800,
            "difficulty": 1.3,
            "deadline_multiplier": 1.0,
            "tm_match_rate": 0.35,
            "status": "PENDING",
        },
    },
    # [4] 번역 진행 중
    {
        "client_name": "현대자동차",
        "client_email": "global.ir@hyundai.com",
        "source_lang": "ko",
        "target_lang": "en",
        "content_type": "general",
        "quality_level": "translation",
        "word_count": 3200,
        "status": "IN_PROGRESS",
        "deadline": now + timedelta(days=3),
        "notes": "연간 보고서 영문 번역.",
        "quote": {
            "estimated_price": 384000,
            "currency": "KRW",
            "estimated_hours": 12.0,
            "confidence": 0.90,
            "word_count": 3200,
            "difficulty": 1.0,
            "deadline_multiplier": 1.2,
            "tm_match_rate": 0.20,
            "status": "APPROVED",
        },
    },
    # [5] 완료
    {
        "client_name": "네이버 글로벌",
        "client_email": "global@naver.com",
        "source_lang": "ko",
        "target_lang": "en",
        "content_type": "marketing",
        "quality_level": "dtp",
        "word_count": 900,
        "status": "COMPLETED",
        "deadline": now - timedelta(days=2),
        "notes": "앱 스토어 소개 문구.",
        "quote": {
            "estimated_price": 162000,
            "currency": "KRW",
            "estimated_hours": 4.0,
            "confidence": 0.97,
            "word_count": 900,
            "difficulty": 1.0,
            "deadline_multiplier": 1.0,
            "tm_match_rate": 0.55,
            "status": "APPROVED",
        },
    },
    # [6] 취소됨
    {
        "client_name": "SK텔레콤",
        "client_email": "b2b@sktelecom.com",
        "source_lang": "ko",
        "target_lang": "zh",
        "content_type": "technical",
        "quality_level": "translation",
        "word_count": 4000,
        "status": "CANCELLED",
        "deadline": now + timedelta(days=14),
        "notes": "5G 기술 문서 중문 번역. 고객 요청 취소.",
        "quote": {
            "estimated_price": 600000,
            "currency": "KRW",
            "estimated_hours": 20.0,
            "confidence": 0.85,
            "word_count": 4000,
            "difficulty": 1.5,
            "deadline_multiplier": 1.0,
            "tm_match_rate": 0.10,
            "status": "REJECTED",
        },
    },
    # [7] 견적 계산 중 (QUOTE_PENDING)
    {
        "client_name": "LG전자",
        "client_email": "global@lge.com",
        "source_lang": "ko",
        "target_lang": "en",
        "content_type": "technical",
        "quality_level": "review",
        "word_count": 7000,
        "status": "QUOTE_PENDING",
        "deadline": now + timedelta(days=20),
        "notes": "제품 사용 설명서 번역.",
        "quote": None,
    },
]


async def seed():
    print("🌱 더미 데이터 시딩 시작...")

    async with AsyncSessionLocal() as db:
        # ── 기존 데이터 정리 (외래키 순서 역순) ─────────────────────
        print("  기존 데이터 삭제 중...")
        await db.execute(delete(Notification))
        await db.execute(delete(Assignment))
        await db.execute(delete(Quote))
        await db.execute(delete(JobEvent))
        await db.execute(delete(Job))
        await db.execute(delete(Translator))
        await db.execute(delete(User))
        await db.commit()

        # ── 관리자 계정 생성 ─────────────────────────────────────────
        print("  관리자 계정 생성...")
        admin = User(
            email=ADMIN_USER["email"],
            hashed_pw=hash_password(ADMIN_USER["password"]),
            role=ADMIN_USER["role"],
        )
        db.add(admin)
        await db.flush()

        # ── 번역가 생성 ───────────────────────────────────────────────
        print("  번역가 생성...")
        translators = []
        for t_data in TRANSLATORS:
            translator = Translator(**t_data)
            db.add(translator)
            translators.append(translator)
        await db.flush()

        # ── 작업 + 견적 + 배정 생성 ──────────────────────────────────
        print("  작업 데이터 생성...")
        for i, job_data in enumerate(JOBS):
            quote_data = job_data.pop("quote")

            job = Job(**job_data)
            db.add(job)
            await db.flush()

            # 초기 FSM 이벤트 기록
            db.add(JobEvent(
                job_id=job.id,
                from_status=None,
                to_status="REQUESTED",
                triggered_by="system",
                event_data={"source": "seed"},
            ))

            # 견적 생성 (QUOTE_PENDING 이후 상태)
            if quote_data and job.status not in ("REQUESTED",):
                quote = Quote(job_id=job.id, **quote_data)
                db.add(quote)

                db.add(JobEvent(
                    job_id=job.id,
                    from_status="REQUESTED",
                    to_status="QUOTED_DRAFT",
                    triggered_by="system",
                    event_data={"source": "seed"},
                ))

            # 배정 레코드 생성 (ASSIGNED 이후 상태)
            if job.status in ("ASSIGNED", "IN_PROGRESS", "REVIEW", "QA", "COMPLETED"):
                translator = translators[i % len(translators)]
                assignment = Assignment(
                    job_id=job.id,
                    translator_id=translator.id,
                    score=0.85 + (i * 0.02),
                    status="ASSIGNED" if job.status != "COMPLETED" else "COMPLETED",
                )
                db.add(assignment)

                db.add(JobEvent(
                    job_id=job.id,
                    from_status="QUOTED",
                    to_status="ASSIGNED",
                    triggered_by="client",
                    event_data={"source": "seed"},
                ))

            if job.status in ("IN_PROGRESS", "REVIEW", "QA", "COMPLETED"):
                db.add(JobEvent(
                    job_id=job.id,
                    from_status="ASSIGNED",
                    to_status="IN_PROGRESS",
                    triggered_by="admin",
                    actor_id=admin.id,
                    event_data={"source": "seed"},
                ))

            print(f"    [{i+1}/{len(JOBS)}] {job.client_name} — {job.status}")

        await db.commit()

    print()
    print("✅ 시딩 완료!")
    print()
    print("  관리자 로그인 정보:")
    print(f"    이메일: {ADMIN_USER['email']}")
    print(f"    비밀번호: {ADMIN_USER['password']}")
    print()
    print(f"  번역가 {len(TRANSLATORS)}명, 작업 {len(JOBS)}건 생성됨")


if __name__ == "__main__":
    asyncio.run(seed())
