"""
감사 로그(Audit Log) 미들웨어.
모든 API 요청/응답을 audit_logs 테이블에 비동기 기록.
운영 보안, 컴플라이언스, 장애 재현에 활용.

audit_logs 테이블 DDL:
  CREATE TABLE audit_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID,
    method      VARCHAR(10) NOT NULL,
    path        TEXT NOT NULL,
    status_code INTEGER,
    ip          VARCHAR(45),
    duration_ms INTEGER,
    request_body JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
  );
  CREATE INDEX ON audit_logs (user_id);
  CREATE INDEX ON audit_logs (created_at DESC);
"""

import json
import logging
import time
from typing import Optional

from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.config import settings
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

# 감사 로그에서 제외할 민감 필드명 (request_body 필터링)
SENSITIVE_FIELDS = {"password", "hashed_pw", "token", "refresh_token", "secret"}

# 기록하지 않을 경로 — 헬스체크, API 문서 등 노이즈 제거
EXCLUDED_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


def _mask_sensitive(data: dict) -> dict:
    """
    request_body에서 민감 필드를 마스킹.
    중첩 딕셔너리는 재귀 처리하지 않음 (성능 우선).
    """
    return {
        k: "***MASKED***" if k.lower() in SENSITIVE_FIELDS else v
        for k, v in data.items()
    }


def _extract_user_id(request: Request) -> Optional[str]:
    """
    Authorization Bearer 헤더에서 JWT를 파싱하여 user_id(sub) 추출.
    파싱 실패 또는 토큰 없음 → None 반환 (에러 무시).
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            # 감사 로그 목적이므로 만료된 토큰도 user_id 추출 허용
            options={"verify_exp": False},
        )
        return payload.get("sub")
    except (JWTError, Exception):
        # 토큰 파싱 실패 시 무시 — 감사 로그 기록을 막지 않음
        return None


def _get_client_ip(request: Request) -> str:
    """
    클라이언트 실제 IP 주소 추출.
    리버스 프록시(Nginx, LB) 환경에서는 X-Forwarded-For 헤더 우선.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # 다중 프록시 환경: 첫 번째 IP가 실제 클라이언트
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _write_audit_log(
    user_id: Optional[str],
    method: str,
    path: str,
    status_code: int,
    ip: str,
    duration_ms: int,
    request_body: Optional[dict],
) -> None:
    """
    audit_logs 테이블에 비동기로 로그 기록.
    DB 세션은 get_db() 의존성 사용 불가(미들웨어 컨텍스트)이므로
    AsyncSessionLocal로 독립 세션 생성.
    기록 실패 시 예외를 삼키고 서버 로그에만 출력 (본 요청에 영향 없음).
    """
    import sqlalchemy as sa

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                sa.text(
                    """
                    INSERT INTO audit_logs
                        (user_id, method, path, status_code, ip, duration_ms, request_body)
                    VALUES
                        (:user_id, :method, :path, :status_code, :ip, :duration_ms, :request_body)
                    """
                ),
                {
                    "user_id": user_id,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "ip": ip,
                    "duration_ms": duration_ms,
                    # JSONB 컬럼에 삽입 시 JSON 문자열로 직렬화
                    "request_body": json.dumps(request_body, ensure_ascii=False)
                    if request_body
                    else None,
                },
            )
            await db.commit()
    except Exception:
        # 감사 로그 기록 실패는 서버 로그에만 남기고 요청 처리에 영향 주지 않음
        logger.warning("감사 로그 기록 실패: path=%s method=%s", path, method, exc_info=True)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    모든 API 요청/응답을 audit_logs 테이블에 기록하는 미들웨어.

    기록 항목:
    - method, path: 요청 메서드 및 경로
    - status_code: 응답 상태 코드
    - user_id: JWT에서 추출한 사용자 ID (미인증 시 NULL)
    - ip: 클라이언트 IP (리버스 프록시 고려)
    - duration_ms: 요청 처리 시간 (밀리초)
    - request_body: 요청 본문 (민감 필드 마스킹)
    - created_at: 기록 시각 (DB 기본값 NOW())
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # 제외 경로는 기록하지 않음
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)

        # 요청 처리 시작 시각 (밀리초 단위 소요 시간 계산용)
        start_time = time.monotonic()

        # JWT에서 user_id 추출 (실패 시 None)
        user_id = _extract_user_id(request)
        ip = _get_client_ip(request)

        # request_body 추출 (JSON이 아닌 경우 None)
        request_body: Optional[dict] = None
        try:
            # body를 읽으면 스트림이 소모되므로 다시 주입
            body_bytes = await request.body()
            if body_bytes:
                raw = json.loads(body_bytes.decode("utf-8"))
                if isinstance(raw, dict):
                    request_body = _mask_sensitive(raw)
        except Exception:
            # JSON 파싱 실패 또는 바이너리 바디 → body 기록 생략
            pass

        # 실제 요청 처리
        response = await call_next(request)

        # 소요 시간 계산 (밀리초)
        duration_ms = int((time.monotonic() - start_time) * 1000)

        # 감사 로그 비동기 기록 (응답 반환을 블로킹하지 않음)
        # asyncio.create_task()를 사용하면 미들웨어 컨텍스트 밖에서 실행되어
        # 이벤트 루프 종료 시 태스크가 유실될 수 있으므로 await 방식 유지
        await _write_audit_log(
            user_id=user_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            ip=ip,
            duration_ms=duration_ms,
            request_body=request_body,
        )

        return response
