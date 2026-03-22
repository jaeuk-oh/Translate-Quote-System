/**
 * API 클라이언트.
 * Authorization Bearer 헤더를 자동으로 첨부하는 fetchWithAuth 래퍼와
 * 도메인별 API 함수 모음.
 *
 * BASE_URL은 환경 변수 NEXT_PUBLIC_API_URL에서 로드.
 * 미설정 시 로컬 개발 서버(http://localhost:8000) 사용.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// ── 타입 정의 ──────────────────────────────────────────────────────

export interface JobCreatePayload {
  source_lang: string
  target_lang: string
  content_type?: string
  quality_level?: string
  word_count?: number
  deadline?: string
}

export interface JobResponse {
  id: string
  client_id: string
  source_lang: string
  target_lang: string
  content_type: string | null
  quality_level: string | null
  file_url: string | null
  word_count: number | null
  status: string
  deadline: string | null
  created_at: string
  updated_at: string
}

export interface QuoteResponse {
  id: string
  job_id: string
  estimated_price: number | null
  currency: string
  estimated_hours: number | null
  confidence: number | null
  word_count: number | null
  difficulty: number | null
  deadline_multiplier: number | null
  tm_match_rate: number | null
  status: string
  created_at: string
}

// ── fetchWithAuth: Authorization Bearer 헤더 자동 첨부 ─────────────

async function fetchWithAuth(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  // 클라이언트 사이드에서만 localStorage 접근 가능
  const token =
    typeof window !== 'undefined'
      ? localStorage.getItem('access_token')
      : null

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(options.headers ?? {}),
    // 토큰이 있을 때만 Authorization 헤더 추가
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  })

  // 4xx / 5xx 응답을 에러로 변환
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const message = body?.detail ?? `API 오류: ${response.status}`
    throw new Error(message)
  }

  return response
}

// ── 작업(Job) API ──────────────────────────────────────────────────

/**
 * 번역 의뢰 생성.
 * 생성 완료 후 Celery 워커가 자동으로 견적 계산을 시작함.
 */
export async function createJob(data: JobCreatePayload): Promise<JobResponse> {
  const response = await fetchWithAuth('/jobs', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  return response.json()
}

/**
 * 작업 상세 조회.
 */
export async function getJob(id: string): Promise<JobResponse> {
  const response = await fetchWithAuth(`/jobs/${id}`)
  return response.json()
}

// ── 견적(Quote) API ────────────────────────────────────────────────

/**
 * 특정 작업의 견적 조회.
 * Celery 워커가 견적 계산을 완료한 후 조회 가능 (status=COMPLETED).
 */
export async function getQuote(jobId: string): Promise<QuoteResponse> {
  const response = await fetchWithAuth(`/quotes/${jobId}`)
  return response.json()
}

/**
 * 견적 승인.
 * 승인 시 FSM: QUOTED → PENDING_ACCEPTANCE 전이 트리거.
 */
export async function approveQuote(quoteId: string): Promise<QuoteResponse> {
  const response = await fetchWithAuth(`/quotes/${quoteId}/approve`, {
    method: 'POST',
  })
  return response.json()
}

/**
 * 견적 거절.
 * 거절 시 FSM: QUOTED → CANCELLED 전이 트리거.
 */
export async function rejectQuote(quoteId: string): Promise<QuoteResponse> {
  const response = await fetchWithAuth(`/quotes/${quoteId}/reject`, {
    method: 'POST',
  })
  return response.json()
}
