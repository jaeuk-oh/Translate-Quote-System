/**
 * 관리자 전용 API 클라이언트.
 * Authorization Bearer 헤더를 자동으로 첨부하는 fetchWithAuth 래퍼와
 * 도메인별 API 함수 모음.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// ── 타입 정의 ──────────────────────────────────────────────────────

export interface JobResponse {
  id: string
  client_name: string
  client_email: string
  source_lang: string
  target_lang: string
  content_type: string | null
  quality_level: string | null
  word_count: number | null
  status: string
  deadline: string | null
  notes: string | null
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

export interface TranslatorCandidate {
  translator_id: string
  name: string | null
  score: number
  quality_score: number | null
  on_time_rate: number | null
  availability: string
  current_load: number
  max_load: number
}

export interface AssignmentResponse {
  id: string
  job_id: string
  translator_id: string
  score: number | null
  status: string
  assigned_at: string
}

// ── fetchWithAuth ─────────────────────────────────────────────────

export async function fetchWithAuth(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const token =
    typeof window !== 'undefined'
      ? localStorage.getItem('access_token')
      : null

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(options.headers ?? {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }

  const response = await fetch(`${BASE_URL}${path}`, { ...options, headers })

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body?.detail ?? `API 오류: ${response.status}`)
  }

  return response
}

// ── 작업(Job) API ─────────────────────────────────────────────────

export async function listJobs(): Promise<JobResponse[]> {
  const res = await fetchWithAuth('/jobs')
  return res.json()
}

export async function getJob(id: string): Promise<JobResponse> {
  const res = await fetchWithAuth(`/jobs/${id}`)
  return res.json()
}

// ── 견적(Quote) API ───────────────────────────────────────────────

export async function getQuote(jobId: string): Promise<QuoteResponse> {
  const res = await fetchWithAuth(`/jobs/${jobId}/quote`)
  return res.json()
}

/** 담당자가 견적 검토 완료 후 고객에게 발송 (QUOTED_DRAFT → QUOTED) */
export async function sendQuoteToClient(
  jobId: string
): Promise<{ message: string; approval_url: string; rejection_url: string }> {
  const res = await fetchWithAuth(`/jobs/${jobId}/quote/send`, { method: 'POST' })
  return res.json()
}

// ── 배정(Assignment) API ──────────────────────────────────────────

/** 추천 번역가 목록 조회 (점수 내림차순 Top 3) */
export async function getRecommendedTranslators(
  jobId: string
): Promise<TranslatorCandidate[]> {
  const res = await fetchWithAuth(`/jobs/${jobId}/assign/recommend`)
  return res.json()
}

/** 담당자가 번역가 배정 확정 (ASSIGNED → IN_PROGRESS) */
export async function assignTranslator(
  jobId: string,
  translatorId: string
): Promise<AssignmentResponse> {
  const res = await fetchWithAuth(`/jobs/${jobId}/assign`, {
    method: 'POST',
    body: JSON.stringify({ translator_id: translatorId }),
  })
  return res.json()
}

export async function listAssignments(jobId: string): Promise<AssignmentResponse[]> {
  const res = await fetchWithAuth(`/jobs/${jobId}/assignments`)
  return res.json()
}
