-- PostgreSQL 초기화 스크립트
-- Docker Compose 최초 실행 시 자동 수행

-- pg_trgm 확장 활성화: TM(Translation Memory) 글자 유사도 매칭에 사용
-- 벡터(의미) 기반이 아닌 글자 재사용률 측정 → 업계 표준 CAT tool 방식
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- UUID 생성 함수 활성화
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
