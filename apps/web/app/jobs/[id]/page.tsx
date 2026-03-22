'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { getJob, getQuote, approveQuote, rejectQuote, JobResponse, QuoteResponse } from '@/lib/api'
import { useJobStream } from '@/lib/sse'

// FSM 단계 순서 — state_machine.py VALID_TRANSITIONS와 동기화
const FSM_STEPS = [
  { status: 'REQUESTED', label: '의뢰 접수' },
  { status: 'QUOTE_PENDING', label: '견적 계산 중' },
  { status: 'QUOTED', label: '견적 완료' },
  { status: 'PENDING_ACCEPTANCE', label: '번역가 배정 중' },
  { status: 'ASSIGNED', label: '배정 완료' },
  { status: 'IN_PROGRESS', label: '번역 진행 중' },
  { status: 'REVIEW', label: '검토 중' },
  { status: 'QA', label: 'QA 검수' },
  { status: 'COMPLETED', label: '완료' },
]

function getStepIndex(status: string): number {
  return FSM_STEPS.findIndex(s => s.status === status)
}

function StatusProgressBar({ currentStatus }: { currentStatus: string }) {
  const currentIndex = getStepIndex(currentStatus)

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-2">
        {FSM_STEPS.map((step, idx) => (
          <div key={step.status} className="flex flex-col items-center flex-1">
            {/* 단계 원형 아이콘 */}
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border-2 ${
                idx < currentIndex
                  ? 'bg-blue-600 border-blue-600 text-white'
                  : idx === currentIndex
                  ? 'bg-blue-100 border-blue-600 text-blue-600'
                  : 'bg-gray-100 border-gray-300 text-gray-400'
              }`}
            >
              {idx < currentIndex ? '✓' : idx + 1}
            </div>
            {/* 단계 레이블 */}
            <span
              className={`mt-1 text-xs text-center leading-tight ${
                idx === currentIndex ? 'text-blue-600 font-semibold' : 'text-gray-400'
              }`}
            >
              {step.label}
            </span>
            {/* 단계 연결선 (마지막 제외) */}
            {idx < FSM_STEPS.length - 1 && (
              <div
                className={`absolute h-0.5 w-full top-4 left-1/2 ${
                  idx < currentIndex ? 'bg-blue-600' : 'bg-gray-200'
                }`}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function QuoteCard({
  quote,
  onApprove,
  onReject,
  jobStatus,
}: {
  quote: QuoteResponse
  onApprove: () => void
  onReject: () => void
  jobStatus: string
}) {
  const canApprove = jobStatus === 'QUOTED' && quote.status === 'COMPLETED'

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">견적 정보</h2>
      <dl className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <dt className="text-gray-500">예상 금액</dt>
          <dd className="text-2xl font-bold text-blue-600 mt-1">
            {quote.estimated_price
              ? `${Number(quote.estimated_price).toLocaleString()}원`
              : '계산 중...'}
          </dd>
        </div>
        <div>
          <dt className="text-gray-500">예상 작업 시간</dt>
          <dd className="text-lg font-semibold mt-1">
            {quote.estimated_hours ? `${quote.estimated_hours}시간` : '-'}
          </dd>
        </div>
        <div>
          <dt className="text-gray-500">TM 매칭률</dt>
          <dd className="mt-1">
            {quote.tm_match_rate != null
              ? `${(Number(quote.tm_match_rate) * 100).toFixed(1)}%`
              : '-'}
          </dd>
        </div>
        <div>
          <dt className="text-gray-500">견적 신뢰도</dt>
          <dd className="mt-1">
            {quote.confidence != null
              ? `${(Number(quote.confidence) * 100).toFixed(0)}%`
              : '-'}
          </dd>
        </div>
        <div>
          <dt className="text-gray-500">난이도 승수</dt>
          <dd className="mt-1">{quote.difficulty ?? '-'}</dd>
        </div>
        <div>
          <dt className="text-gray-500">마감 승수</dt>
          <dd className="mt-1">{quote.deadline_multiplier ?? '-'}</dd>
        </div>
      </dl>

      {canApprove && (
        <div className="mt-6 flex gap-3">
          <button
            onClick={onApprove}
            className="flex-1 py-2 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition-colors"
          >
            견적 승인
          </button>
          <button
            onClick={onReject}
            className="flex-1 py-2 bg-white text-gray-700 font-semibold rounded-lg border border-gray-300 hover:bg-gray-50 transition-colors"
          >
            견적 거절
          </button>
        </div>
      )}
    </div>
  )
}

export default function JobDetailPage() {
  const params = useParams()
  const jobId = typeof params.id === 'string' ? params.id : null

  const [job, setJob] = useState<JobResponse | null>(null)
  const [quote, setQuote] = useState<QuoteResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // SSE로 실시간 상태 수신
  const { latestEvent, isConnected } = useJobStream(jobId)

  // 초기 작업/견적 로드
  useEffect(() => {
    if (!jobId) return

    const loadData = async () => {
      try {
        const jobData = await getJob(jobId)
        setJob(jobData)

        // 견적이 있을 수 있는 상태면 견적 조회 시도
        if (!['REQUESTED', 'QUOTE_PENDING'].includes(jobData.status)) {
          try {
            const quoteData = await getQuote(jobId)
            setQuote(quoteData)
          } catch {
            // 견적 없음 — 무시
          }
        }
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : '작업 정보를 불러오지 못했습니다.'
        setError(message)
      } finally {
        setIsLoading(false)
      }
    }

    loadData()
  }, [jobId])

  // SSE 이벤트 수신 시 상태 업데이트
  useEffect(() => {
    if (!latestEvent || !job) return

    if (latestEvent.type === 'STATUS_UPDATE' || latestEvent.type === 'COMPLETED') {
      // 서버에서 최신 상태 다시 조회
      getJob(job.id).then(updatedJob => {
        setJob(updatedJob)
        // QUOTED 상태가 되면 견적 조회
        if (updatedJob.status === 'QUOTED') {
          getQuote(job.id).then(setQuote).catch(() => {})
        }
      }).catch(() => {})
    }
  }, [latestEvent, job])

  const handleApproveQuote = async () => {
    if (!quote) return
    try {
      await approveQuote(quote.id)
      // 승인 후 최신 상태 조회
      if (jobId) {
        const updatedJob = await getJob(jobId)
        setJob(updatedJob)
        const updatedQuote = await getQuote(jobId)
        setQuote(updatedQuote)
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '견적 승인에 실패했습니다.'
      setError(message)
    }
  }

  const handleRejectQuote = async () => {
    if (!quote) return
    try {
      await rejectQuote(quote.id)
      if (jobId) {
        const updatedJob = await getJob(jobId)
        setJob(updatedJob)
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '견적 거절에 실패했습니다.'
      setError(message)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <div className="text-gray-500">작업 정보를 불러오는 중...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-red-700">
        {error}
      </div>
    )
  }

  if (!job) return null

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* 헤더 */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            작업 #{job.id.slice(0, 8)}
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            {job.source_lang.toUpperCase()} → {job.target_lang.toUpperCase()} |{' '}
            {job.content_type ?? '일반'} | {job.quality_level ?? 'translation'}
          </p>
        </div>
        {/* SSE 연결 상태 표시 */}
        <div className="flex items-center gap-2 text-xs">
          <div
            className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-gray-300'}`}
          />
          <span className="text-gray-500">
            {isConnected ? '실시간 연결됨' : '연결 종료'}
          </span>
        </div>
      </div>

      {/* FSM 상태 진행바 */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
        <h2 className="text-sm font-semibold text-gray-500 mb-4">작업 진행 상태</h2>
        <StatusProgressBar currentStatus={job.status} />

        {/* 현재 상태 강조 */}
        <div className="mt-4 text-center">
          <span className="inline-block px-4 py-1.5 bg-blue-50 text-blue-700 text-sm font-semibold rounded-full">
            현재: {FSM_STEPS.find(s => s.status === job.status)?.label ?? job.status}
          </span>
        </div>
      </div>

      {/* 견적 카드 */}
      {quote && (
        <QuoteCard
          quote={quote}
          onApprove={handleApproveQuote}
          onReject={handleRejectQuote}
          jobStatus={job.status}
        />
      )}

      {/* 작업 기본 정보 */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">작업 정보</h2>
        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-gray-500">단어 수</dt>
            <dd className="font-medium mt-1">
              {job.word_count ? `${job.word_count.toLocaleString()}단어` : '미산정'}
            </dd>
          </div>
          <div>
            <dt className="text-gray-500">마감일</dt>
            <dd className="font-medium mt-1">
              {job.deadline ? new Date(job.deadline).toLocaleDateString('ko-KR') : '미지정'}
            </dd>
          </div>
          <div>
            <dt className="text-gray-500">의뢰 일시</dt>
            <dd className="font-medium mt-1">
              {new Date(job.created_at).toLocaleString('ko-KR')}
            </dd>
          </div>
          <div>
            <dt className="text-gray-500">최종 수정</dt>
            <dd className="font-medium mt-1">
              {new Date(job.updated_at).toLocaleString('ko-KR')}
            </dd>
          </div>
        </dl>
      </div>
    </div>
  )
}
