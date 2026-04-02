'use client'

import { useEffect, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  getJob, getQuote, sendQuoteToClient,
  getRecommendedTranslators, assignTranslator, advanceStatus,
  JobResponse, QuoteResponse, TranslatorCandidate,
} from '@/lib/api'

// FSM 단계 (관리자 관점)
const FSM_STEPS = [
  { status: 'REQUESTED',    label: '의뢰 접수' },
  { status: 'QUOTE_PENDING',label: '견적 계산 중' },
  { status: 'QUOTED_DRAFT', label: '견적 검토' },
  { status: 'QUOTED',       label: '고객 확인 중' },
  { status: 'ASSIGNED',     label: '배정 확정 대기' },
  { status: 'IN_PROGRESS',  label: '번역 진행 중' },
  { status: 'REVIEW',       label: '검토' },
  { status: 'QA',           label: 'QA' },
  { status: 'COMPLETED',    label: '완료' },
]

function ProgressBar({ status }: { status: string }) {
  const idx = FSM_STEPS.findIndex((s) => s.status === status)
  return (
    <div className="flex items-center gap-1 overflow-x-auto pb-1">
      {FSM_STEPS.map((step, i) => (
        <div key={step.status} className="flex items-center">
          <div className={`flex flex-col items-center min-w-[64px]`}>
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border-2 ${
              i < idx  ? 'bg-blue-600 border-blue-600 text-white'
              : i === idx ? 'bg-blue-100 border-blue-600 text-blue-700'
              : 'bg-gray-100 border-gray-300 text-gray-400'
            }`}>
              {i < idx ? '✓' : i + 1}
            </div>
            <span className={`mt-1 text-[10px] text-center leading-tight ${
              i === idx ? 'text-blue-600 font-semibold' : 'text-gray-400'
            }`}>{step.label}</span>
          </div>
          {i < FSM_STEPS.length - 1 && (
            <div className={`h-0.5 w-4 mx-1 mb-4 ${i < idx ? 'bg-blue-600' : 'bg-gray-200'}`} />
          )}
        </div>
      ))}
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex py-2 border-b border-gray-100 last:border-0">
      <span className="w-28 text-sm text-gray-500 shrink-0">{label}</span>
      <span className="text-sm text-gray-900">{value ?? '-'}</span>
    </div>
  )
}

// ── 견적 검토 패널 (QUOTED_DRAFT 상태) ──────────────────────────────
function QuotedDraftPanel({ jobId, quote, onDone }: {
  jobId: string
  quote: QuoteResponse | null
  onDone: () => void
}) {
  const [isLoading, setIsLoading] = useState(false)
  const [result, setResult] = useState<{ approval_url: string; rejection_url: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleSend = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const res = await sendQuoteToClient(jobId)
      setResult(res)
      setTimeout(onDone, 2000)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '오류 발생')
    } finally {
      setIsLoading(false)
    }
  }

  if (result) {
    return (
      <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-sm text-green-800">
        고객에게 견적 이메일을 발송했습니다. 페이지를 새로고침합니다...
      </div>
    )
  }

  return (
    <div className="bg-orange-50 border border-orange-200 rounded-xl p-5 space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-orange-600 font-semibold text-sm">● 견적 검토 필요</span>
      </div>

      {quote && (
        <div className="bg-white rounded-lg border border-orange-100 p-4 space-y-2">
          <InfoRow label="예상 금액" value={quote.estimated_price ? `${quote.estimated_price.toLocaleString()} ${quote.currency}` : '계산 중'} />
          <InfoRow label="예상 시간" value={quote.estimated_hours ? `${quote.estimated_hours}시간` : '-'} />
          <InfoRow label="TM 매칭률" value={quote.tm_match_rate ? `${(quote.tm_match_rate * 100).toFixed(0)}%` : '-'} />
          <InfoRow label="난이도" value={quote.difficulty ?? '-'} />
          <InfoRow label="신뢰도" value={quote.confidence ? `${(quote.confidence * 100).toFixed(0)}%` : '-'} />
        </div>
      )}

      {error && (
        <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</div>
      )}

      <button
        onClick={handleSend}
        disabled={isLoading}
        className="w-full py-2.5 bg-orange-600 text-white text-sm font-semibold rounded-lg hover:bg-orange-700 disabled:opacity-50 transition-colors"
      >
        {isLoading ? '발송 중...' : '고객에게 견적 발송'}
      </button>
    </div>
  )
}

// ── 번역가 배정 패널 (ASSIGNED 상태) ──────────────────────────────
function AssignPanel({ jobId, onDone }: { jobId: string; onDone: () => void }) {
  const [candidates, setCandidates] = useState<TranslatorCandidate[]>([])
  const [isLoadingCandidates, setIsLoadingCandidates] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [isAssigning, setIsAssigning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getRecommendedTranslators(jobId)
      .then(setCandidates)
      .catch((err: Error) => setError(err.message))
      .finally(() => setIsLoadingCandidates(false))
  }, [jobId])

  const handleAssign = async () => {
    if (!selectedId) return
    setIsAssigning(true)
    setError(null)
    try {
      await assignTranslator(jobId, selectedId)
      setTimeout(onDone, 1000)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '오류 발생')
    } finally {
      setIsAssigning(false)
    }
  }

  return (
    <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-5 space-y-4">
      <span className="text-indigo-700 font-semibold text-sm">● 번역가 배정 확정 필요</span>

      {isLoadingCandidates ? (
        <div className="text-sm text-gray-400">추천 번역가 조회 중...</div>
      ) : candidates.length === 0 ? (
        <div className="text-sm text-gray-500">배정 가능한 번역가가 없습니다.</div>
      ) : (
        <div className="space-y-2">
          {candidates.map((c) => (
            <label
              key={c.translator_id}
              className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                selectedId === c.translator_id
                  ? 'border-indigo-500 bg-indigo-100'
                  : 'border-gray-200 bg-white hover:border-indigo-300'
              }`}
            >
              <input
                type="radio"
                name="translator"
                value={c.translator_id}
                checked={selectedId === c.translator_id}
                onChange={() => setSelectedId(c.translator_id)}
                className="text-indigo-600"
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900">{c.name ?? '이름 없음'}</p>
                <p className="text-xs text-gray-500">
                  점수 {c.score.toFixed(1)}
                  {c.quality_score ? ` · 품질 ${(c.quality_score * 100).toFixed(0)}%` : ''}
                  {c.on_time_rate ? ` · 납기 ${(c.on_time_rate * 100).toFixed(0)}%` : ''}
                  {` · ${c.current_load}/${c.max_load} 작업`}
                </p>
              </div>
              <span className={`text-xs px-2 py-0.5 rounded-full ${
                c.availability === 'AVAILABLE' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
              }`}>
                {c.availability === 'AVAILABLE' ? '가용' : c.availability}
              </span>
            </label>
          ))}
        </div>
      )}

      {error && (
        <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</div>
      )}

      <button
        onClick={handleAssign}
        disabled={!selectedId || isAssigning}
        className="w-full py-2.5 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
      >
        {isAssigning ? '배정 중...' : '배정 확정'}
      </button>
    </div>
  )
}

// ── 검토 패널 (REVIEW 상태) ──────────────────────────────────────
function ReviewPanel({ jobId, job, onDone }: { jobId: string; job: JobResponse; onDone: () => void }) {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleAdvance = async () => {
    setIsLoading(true)
    setError(null)
    try {
      await advanceStatus(jobId, 'QA')
      setTimeout(onDone, 500)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '오류 발생')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="bg-cyan-50 border border-cyan-200 rounded-xl p-5 space-y-4">
      <span className="text-cyan-700 font-semibold text-sm">● 검토 필요</span>
      <p className="text-sm text-gray-600">번역가가 완료 파일을 제출했습니다. 내용을 검토한 후 QA로 넘기세요.</p>
      {job.result_file_url && (
        <a
          href={job.result_file_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline"
        >
          완료 파일 다운로드 →
        </a>
      )}
      {error && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</div>}
      <button
        onClick={handleAdvance}
        disabled={isLoading}
        className="w-full py-2.5 bg-cyan-600 text-white text-sm font-semibold rounded-lg hover:bg-cyan-700 disabled:opacity-50 transition-colors"
      >
        {isLoading ? '처리 중...' : 'QA로 이관'}
      </button>
    </div>
  )
}

// ── QA 패널 (QA 상태) ────────────────────────────────────────────
function QAPanel({ jobId, onDone }: { jobId: string; onDone: () => void }) {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handle = async (toStatus: 'COMPLETED' | 'IN_PROGRESS') => {
    setIsLoading(true)
    setError(null)
    try {
      await advanceStatus(jobId, toStatus)
      setTimeout(onDone, 500)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '오류 발생')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="bg-teal-50 border border-teal-200 rounded-xl p-5 space-y-4">
      <span className="text-teal-700 font-semibold text-sm">● QA 검수</span>
      <p className="text-sm text-gray-600">QA 검수 결과를 선택하세요.</p>
      {error && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</div>}
      <div className="flex gap-3">
        <button
          onClick={() => handle('COMPLETED')}
          disabled={isLoading}
          className="flex-1 py-2.5 bg-green-600 text-white text-sm font-semibold rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
        >
          통과 → 완료
        </button>
        <button
          onClick={() => handle('IN_PROGRESS')}
          disabled={isLoading}
          className="flex-1 py-2.5 bg-red-500 text-white text-sm font-semibold rounded-lg hover:bg-red-600 disabled:opacity-50 transition-colors"
        >
          반려 → 재작업
        </button>
      </div>
    </div>
  )
}

// ── 메인 페이지 ───────────────────────────────────────────────────
export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const [job, setJob] = useState<JobResponse | null>(null)
  const [quote, setQuote] = useState<QuoteResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const j = await getJob(id)
      setJob(j)
      // 견적은 QUOTE_PENDING 이후 상태면 조회 시도
      if (!['REQUESTED'].includes(j.status)) {
        getQuote(id).then(setQuote).catch(() => {})
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '오류 발생')
    } finally {
      setIsLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  if (isLoading) return <div className="text-sm text-gray-400 py-12 text-center">불러오는 중...</div>
  if (error || !job) return (
    <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">{error ?? '작업을 찾을 수 없습니다.'}</div>
  )

  return (
    <div className="space-y-6 max-w-2xl">
      {/* 뒤로가기 */}
      <button onClick={() => router.back()} className="text-sm text-gray-500 hover:text-gray-700">
        ← 목록으로
      </button>

      {/* 진행 상태 바 */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm overflow-x-auto">
        <ProgressBar status={job.status} />
      </div>

      {/* 작업 기본 정보 */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
        <h2 className="text-base font-semibold text-gray-900 mb-3">작업 정보</h2>
        <InfoRow label="고객" value={`${job.client_name} (${job.client_email})`} />
        <InfoRow label="언어쌍" value={`${job.source_lang.toUpperCase()} → ${job.target_lang.toUpperCase()}`} />
        <InfoRow label="콘텐츠 유형" value={job.content_type} />
        <InfoRow label="품질 등급" value={job.quality_level} />
        <InfoRow label="단어 수" value={job.word_count?.toLocaleString()} />
        <InfoRow label="마감일" value={job.deadline ? new Date(job.deadline).toLocaleDateString('ko-KR') : null} />
        <InfoRow label="의뢰일" value={new Date(job.created_at).toLocaleString('ko-KR')} />
        {job.notes && <InfoRow label="메모" value={job.notes} />}
      </div>

      {/* 상태별 액션 패널 */}
      {job.status === 'QUOTED_DRAFT' && (
        <QuotedDraftPanel jobId={id} quote={quote} onDone={load} />
      )}
      {job.status === 'ASSIGNED' && (
        <AssignPanel jobId={id} onDone={load} />
      )}
      {job.status === 'REVIEW' && (
        <ReviewPanel jobId={id} job={job} onDone={load} />
      )}
      {job.status === 'QA' && (
        <QAPanel jobId={id} onDone={load} />
      )}

      {/* 견적 정보 (QUOTED 이후) */}
      {quote && !['REQUESTED', 'QUOTE_PENDING', 'QUOTED_DRAFT'].includes(job.status) && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h2 className="text-base font-semibold text-gray-900 mb-3">견적 정보</h2>
          <InfoRow label="예상 금액" value={quote.estimated_price ? `${quote.estimated_price.toLocaleString()} ${quote.currency}` : '-'} />
          <InfoRow label="예상 시간" value={quote.estimated_hours ? `${quote.estimated_hours}시간` : '-'} />
          <InfoRow label="TM 매칭률" value={quote.tm_match_rate ? `${(quote.tm_match_rate * 100).toFixed(0)}%` : '-'} />
          <InfoRow label="견적 상태" value={quote.status} />
        </div>
      )}
    </div>
  )
}
