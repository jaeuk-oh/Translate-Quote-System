"""
S3 파일 업로드 서비스.
번역 원본 파일 및 완료 결과물을 S3에 보관.
NDA 준수: 파일 내용 자체는 외부 API로 전송하지 않으며, S3 저장만 수행.
"""

import uuid
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile, status

from core.config import settings


def _get_s3_client():
    """
    boto3 S3 클라이언트 생성.
    AWS 자격증명은 환경 변수에서 로드 (IAM Role 사용 가능).
    """
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
    )


async def upload_translation_file(
    file: UploadFile,
    job_id: str,
    file_type: str = "source",
) -> str:
    """
    번역 파일을 S3에 업로드하고 접근 URL을 반환.

    경로 구조: translations/{job_id}/{file_type}/{uuid}_{original_filename}
    - job_id: 작업 단위로 파일 격리
    - file_type: source(원본) | result(결과물)
    - uuid prefix: 동일 파일명 충돌 방지

    반환: S3 객체 URL (https://bucket.s3.region.amazonaws.com/...)
    """
    if not settings.AWS_S3_BUCKET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="S3 스토리지가 설정되지 않았습니다.",
        )

    # 파일 확장자 검증 — 허용 포맷만 수락
    allowed_extensions = {".docx", ".doc", ".pdf", ".txt", ".xlsx", ".pptx", ".xliff"}
    original_name = file.filename or "unknown"
    ext = "." + original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"지원하지 않는 파일 형식입니다. 허용: {', '.join(allowed_extensions)}",
        )

    # S3 키 생성: 경로 중복 방지를 위해 UUID prefix 추가
    unique_prefix = str(uuid.uuid4())[:8]
    s3_key = f"translations/{job_id}/{file_type}/{unique_prefix}_{original_name}"

    try:
        s3 = _get_s3_client()
        content = await file.read()

        s3.put_object(
            Bucket=settings.AWS_S3_BUCKET,
            Key=s3_key,
            Body=content,
            ContentType=file.content_type or "application/octet-stream",
        )

        # presigned URL 대신 공개 URL 반환 (버킷 정책에 따라 변경 가능)
        url = f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"
        return url

    except ClientError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"파일 업로드 실패: {e.response['Error']['Message']}",
        )


def generate_presigned_url(s3_key: str, expires_in: int = 3600) -> Optional[str]:
    """
    S3 객체에 대한 임시 접근 URL 생성.
    완료된 번역 파일 다운로드 시 사용 (기본 1시간 유효).
    """
    if not settings.AWS_S3_BUCKET:
        return None
    try:
        s3 = _get_s3_client()
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.AWS_S3_BUCKET, "Key": s3_key},
            ExpiresIn=expires_in,
        )
        return url
    except ClientError:
        return None
