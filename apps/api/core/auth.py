"""
JWT 인증 미들웨어.
Access Token (30분) + Refresh Token (7일) 이중 토큰 전략으로 무상태 인증 구현.
토큰 재발급 시 Refresh Token을 검증하여 새로운 Access Token 발급.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.session import get_db

# bcrypt 해시 컨텍스트 — 패스워드 저장 시 단방향 해시
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Bearer 토큰 추출기
bearer_scheme = HTTPBearer()


def hash_password(plain: str) -> str:
    """평문 패스워드를 bcrypt 해시로 변환"""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """입력 패스워드와 저장된 해시를 검증"""
    return pwd_context.verify(plain, hashed)


def _create_token(data: dict, expires_delta: timedelta) -> str:
    """JWT 토큰 생성 내부 함수 — 만료 시각을 UTC 기준으로 삽입"""
    payload = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    payload.update({"exp": expire})
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str, role: str) -> str:
    """
    Access Token 생성.
    만료: ACCESS_TOKEN_EXPIRE_MINUTES (기본 30분)
    페이로드: sub(user_id), role, type=access
    """
    return _create_token(
        data={"sub": user_id, "role": role, "type": "access"},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: str) -> str:
    """
    Refresh Token 생성.
    만료: REFRESH_TOKEN_EXPIRE_DAYS (기본 7일)
    페이로드: sub(user_id), type=refresh — 역할 정보 미포함으로 최소 권한 원칙 적용
    """
    return _create_token(
        data={"sub": user_id, "type": "refresh"},
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict:
    """
    JWT 디코딩 및 서명 검증.
    만료 또는 서명 불일치 시 HTTPException 401 발생.
    """
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않거나 만료된 토큰입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    현재 요청의 Access Token에서 사용자 정보를 추출하는 의존성 함수.
    FastAPI Depends()로 라우터에 주입하여 인증 게이트 역할 수행.
    """
    payload = decode_token(credentials.credentials)

    # Access Token 타입 검증 — Refresh Token으로 API 호출 차단
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access Token이 아닙니다.",
        )

    user_id: Optional[str] = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰에서 사용자 정보를 찾을 수 없습니다.",
        )

    return {"user_id": user_id, "role": payload.get("role")}


def create_quote_approval_token(job_id: str) -> str:
    """
    고객 견적 승인/거절용 단기 토큰 생성 (7일 유효).
    이메일 링크에 포함되어 로그인 없이 승인 처리에 사용.
    페이로드: job_id, type=quote_approval
    """
    return _create_token(
        data={"job_id": job_id, "type": "quote_approval"},
        expires_delta=timedelta(days=7),
    )


def decode_quote_approval_token(token: str) -> str:
    """
    견적 승인 토큰 검증 후 job_id 반환.
    타입 불일치 또는 만료 시 HTTPException 400 발생.
    """
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="유효하지 않거나 만료된 견적 승인 링크입니다.",
        )

    if payload.get("type") != "quote_approval":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="잘못된 토큰 타입입니다.",
        )

    job_id = payload.get("job_id")
    if not job_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="토큰에서 작업 정보를 찾을 수 없습니다.",
        )
    return job_id


def require_role(*roles: str):
    """
    특정 역할을 가진 사용자만 접근을 허용하는 의존성 팩토리.
    사용 예: Depends(require_role("admin", "translator"))
    """

    async def _check_role(
        current_user: dict = Depends(get_current_user),
    ) -> dict:
        if current_user["role"] not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"접근 권한이 없습니다. 필요 역할: {', '.join(roles)}",
            )
        return current_user

    return _check_role
