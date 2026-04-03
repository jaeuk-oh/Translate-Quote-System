"""
인증 라우터.
회원가입, 로그인, Access Token 재발급 엔드포인트 제공.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from db.session import get_db
from models.user import User
from schemas.user import LoginRequest, RefreshRequest, TokenResponse, TranslatorLoginRequest, UserCreate, UserResponse

router = APIRouter(prefix="/auth", tags=["인증"])


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: UserCreate, db: AsyncSession = Depends(get_db)):
    """회원가입 — 이메일 중복 검사 후 bcrypt 해시 저장"""
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 등록된 이메일입니다.",
        )

    user = User(
        email=body.email,
        hashed_pw=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    await db.flush()
    return user


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """로그인 — 패스워드 검증 후 Access + Refresh Token 발급"""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.hashed_pw):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 패스워드가 올바르지 않습니다.",
        )

    return TokenResponse(
        access_token=create_access_token(str(user.id), user.role),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """
    Refresh Token으로 새 Access Token 발급.
    Refresh Token 타입 검증으로 Access Token 오용 방지.
    """
    payload = decode_token(body.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token이 아닙니다.",
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
        )

    return TokenResponse(
        access_token=create_access_token(str(user.id), user.role),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/translator-login", response_model=TokenResponse)
async def translator_login(body: TranslatorLoginRequest, db: AsyncSession = Depends(get_db)):
    """
    번역가 로그인 — 이름 + 이메일을 translators 테이블과 단순 비교.
    비밀번호 없음: 번역가는 별도 가입 없이 이름/이메일 일치만으로 인증.
    포트폴리오 수준 인증 — 실서비스라면 매직링크 또는 OTP 방식 권장.
    """
    from sqlalchemy import and_
    from models.translator import Translator
    result = await db.execute(
        select(Translator).where(
            and_(Translator.name == body.name, Translator.email == body.email)
        )
    )
    translator = result.scalar_one_or_none()
    if translator is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이름 또는 이메일이 일치하지 않습니다.",
        )
    return TokenResponse(
        access_token=create_access_token(str(translator.id), "translator"),
        refresh_token=create_refresh_token(str(translator.id)),
    )
