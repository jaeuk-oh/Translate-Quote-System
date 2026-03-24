"""
Supabase Storage 파일 업로드 서비스.
번역 원본 파일 및 완료 결과물을 Supabase Storage에 보관.
NDA 준수: 파일 내용 자체는 외부 AI API로 전송하지 않으며, 스토리지 저장만 수행.
"""

import uuid
from typing import Optional

from fastapi import HTTPException, UploadFile, status
from supabase import create_client

from core.config import settings

# 허용 번역 파일 포맷
ALLOWED_EXTENSIONS = {".docx", ".doc", ".pdf", ".txt", ".xlsx", ".pptx", ".xliff"}

# Supabase Storage 버킷명 (Supabase 대시보드에서 미리 생성 필요)
BUCKET_NAME = "translations"


def _get_supabase():
    """Supabase 클라이언트 생성. URL과 서비스 롤 키로 인증."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)


async def upload_translation_file(
    file: UploadFile,
    job_id: str,
    file_type: str = "source",
) -> str:
    """
    번역 파일을 Supabase Storage에 업로드하고 공개 URL 반환.

    경로 구조: translations/{job_id}/{file_type}/{uuid}_{original_filename}
    - job_id: 작업 단위로 파일 격리
    - file_type: source(원본) | result(결과물)
    - uuid prefix: 동일 파일명 충돌 방지
    """
    # 파일 확장자 검증
    original_name = file.filename or "unknown"
    ext = "." + original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"지원하지 않는 파일 형식입니다. 허용: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # 경로 중복 방지를 위해 UUID prefix 추가
    unique_prefix = str(uuid.uuid4())[:8]
    storage_path = f"{job_id}/{file_type}/{unique_prefix}_{original_name}"

    try:
        supabase = _get_supabase()
        content = await file.read()

        supabase.storage.from_(BUCKET_NAME).upload(
            path=storage_path,
            file=content,
            file_options={"content-type": file.content_type or "application/octet-stream"},
        )

        # Supabase Storage 공개 URL 반환
        result = supabase.storage.from_(BUCKET_NAME).get_public_url(storage_path)
        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"파일 업로드 실패: {e}",
        )


def generate_signed_url(storage_path: str, expires_in: int = 3600) -> Optional[str]:
    """
    Supabase Storage 객체에 대한 임시 서명 URL 생성.
    완료된 번역 파일 다운로드 시 사용 (기본 1시간 유효).
    """
    try:
        supabase = _get_supabase()
        result = supabase.storage.from_(BUCKET_NAME).create_signed_url(
            path=storage_path,
            expires_in=expires_in,
        )
        return result.get("signedURL")
    except Exception:
        return None
