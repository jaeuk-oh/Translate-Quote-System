"""
Rate Limiting 미들웨어.
slowapi + Redis 백엔드로 요청 빈도를 제한하여 API 남용 방지.

기본 제한:
  - 일반 엔드포인트: 60 req/min
  - 인증 엔드포인트(/auth/*): 10 req/min (브루트포스 공격 방지)

main.py에 아래 코드를 추가해야 함:
  from core.rate_limit import limiter
  from slowapi import _rate_limit_exceeded_handler
  from slowapi.errors import RateLimitExceeded

  app.state.limiter = limiter
  app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

라우터 엔드포인트에 적용 예시:
  @router.post("/login")
  @limiter.limit("10/minute")
  async def login(request: Request, ...):
      ...
"""

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import settings


def _get_limiter_key(request: Request) -> str:
    """
    Rate Limit 키 결정 함수.
    JWT 인증된 요청은 user_id 기반, 미인증 요청은 IP 기반으로 제한.
    IP 기반은 NAT 환경에서 공유될 수 있으므로 인증 사용자에게 별도 한도 부여.
    """
    # Authorization 헤더에서 user 식별자 추출 시도
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        # 토큰 자체를 키로 사용 (디코딩 비용 없이 식별)
        token = auth_header[7:]
        return f"user:{token[:32]}"
    # 미인증 요청: IP 주소로 제한
    return get_remote_address(request)


# slowapi Limiter 인스턴스 생성
# Redis 백엔드 사용 — 다중 워커 환경에서도 카운터 공유
limiter = Limiter(
    key_func=_get_limiter_key,
    storage_uri=settings.REDIS_URL,
    # 기본 제한: 60 req/min (라우터에서 개별 오버라이드 가능)
    default_limits=["60/minute"],
)


def get_limiter() -> Limiter:
    """Limiter 인스턴스 반환 — 의존성 주입용"""
    return limiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    전역 Rate Limit 미들웨어.
    slowapi의 @limiter.limit 데코레이터 방식과 병용 가능.
    초과 시 HTTP 429 + 한글 에러 메시지 반환.
    """

    # Rate Limit 제외 경로 — 헬스체크, API 문서 등
    EXCLUDED_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next) -> Response:
        # 제외 경로는 Rate Limit 적용 안 함
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        # 실제 Rate Limit 처리는 slowapi가 라우터 레벨에서 수행
        # 이 미들웨어는 429 응답을 한글 메시지로 변환하는 후처리 역할
        response = await call_next(request)

        if response.status_code == 429:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.",
                    "code": "RATE_LIMIT_EXCEEDED",
                },
                headers={"Retry-After": "60"},
            )

        return response
