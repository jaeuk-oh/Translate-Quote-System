'use client'

import { useEffect, useState } from 'react'
import { useParams, useSearchParams, useRouter } from 'next/navigation'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

interface JobDetail {
  id: string
  source_lang: string
  target_lang: string
  content_type: string | null
  quality_level: string | null
  word_count: number | null
  deadline: string | null
  notes: string | null
  status: string
  file_url: string | null
}

const ALLOWED_EXTENSIONS = ['.docx', '.doc', '.pdf', '.txt', '.xlsx', '.pptx', '.xliff']

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex py-2 border-b border-gray-100 last:border-0">
      <span className="w-24 text-sm text-gray-500 shrink-0">{label}</span>
      <span className="text-sm text-gray-900">{value ?? '-'}</span>
    </div>
  )
}

// ── AI 번역 어시스턴트 패널 ───────────────────────────────────
function AIPanel({ sourceLang, targetLang, contentType }: {
  sourceLang: string
  targetLang: string
  contentType: string | null
}) {
  const [sourceText, setSourceText] = useState('')
  const [result, setResult] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleTranslate = async () => {
    if (!sourceText.trim()) return
    setIsLoading(true)
    setError(null)
    setResult('')

    try {
      const res = await fetch('/api/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: sourceText, sourceLang, targetLang, contentType }),
      })
      if (!res.ok) throw new Error('번역 요청에 실패했습니다.')
      const data = await res.json()
      setResult(data.translation)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '오류가 발생했습니다.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-gray-900">AI 번역 어시스턴트</h2>
        <span className="text-xs text-gray-400">{sourceLang.toUpperCase()} → {targetLang.toUpperCase()}</span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-500">원문</label>
          <textarea
            value={sourceText}
            onChange={(e) => setSourceText(e.target.value)}
            placeholder="번역할 원문을 입력하세요..."
            rows={8}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-500">AI 번역 초안</label>
          <textarea
            value={result}
            onChange={(e) => setResult(e.target.value)}
            placeholder="번역 결과가 여기에 표시됩니다. 직접 수정도 가능합니다."
            rows={8}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 bg-gray-50"
          />
        </div>
      </div>

      {error && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</div>}

      <button
        onClick={handleTranslate}
        disabled={isLoading || !sourceText.trim()}
        className="w-full py-2.5 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
      >
        {isLoading ? '번역 중...' : 'AI 번역 초안 생성'}
      </button>
      <p className="text-xs text-gray-400 text-center">AI 초안을 참고용으로만 사용하고 전문가 검토 후 제출하세요.</p>
    </div>
  )
}

// ── 파일 제출 패널 ────────────────────────────────────────────
function SubmitPanel({ jobId, submitToken }: { jobId: string; submitToken: string }) {
  const [file, setFile] = useState<File | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0] ?? null
    if (!selected) return
    const ext = '.' + selected.name.split('.').pop()?.toLowerCase()
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      setError(`지원하지 않는 파일 형식입니다. 허용: ${ALLOWED_EXTENSIONS.join(', ')}`)
      return
    }
    setError(null)
    setFile(selected)
  }

  const handleSubmit = async () => {
    if (!file) return
    setIsLoading(true)
    setError(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch(
        `${BASE_URL}/jobs/${jobId}/complete?token=${encodeURIComponent(submitToken)}`,
        { method: 'POST', body: formData }
      )
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail ?? '제출 중 오류가 발생했습니다.')
      }
      setSubmitted(true)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '오류가 발생했습니다.')
    } finally {
      setIsLoading(false)
    }
  }

  if (submitted) {
    return (
      <div className="bg-green-50 border border-green-200 rounded-xl p-5 text-center text-sm text-green-800 font-medium">
        결과물이 성공적으로 제출되었습니다. 수고하셨습니다!
      </div>
    )
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm space-y-4">
      <h2 className="text-base font-semibold text-gray-900">완료 파일 제출</h2>
      <label className={`flex flex-col items-center justify-center w-full h-28 border-2 border-dashed rounded-xl cursor-pointer transition-colors ${file ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-gray-400 bg-gray-50'}`}>
        <input type="file" className="hidden" accept={ALLOWED_EXTENSIONS.join(',')} onChange={handleFileChange} />
        {file ? (
          <div className="text-center">
            <p className="text-sm font-medium text-blue-700">{file.name}</p>
            <p className="text-xs text-gray-400 mt-1">클릭하여 변경</p>
          </div>
        ) : (
          <div className="text-center">
            <p className="text-sm text-gray-500">클릭하여 파일 선택</p>
            <p className="text-xs text-gray-400 mt-1">{ALLOWED_EXTENSIONS.join(', ')}</p>
          </div>
        )}
      </label>
      {error && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</div>}
      <button
        onClick={handleSubmit}
        disabled={!file || isLoading}
        className="w-full py-2.5 bg-green-600 text-white text-sm font-semibold rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
      >
        {isLoading ? '제출 중...' : '최종 제출'}
      </button>
    </div>
  )
}

// ── 메인 페이지 ───────────────────────────────────────────────
export default function TranslatorJobDetailPage() {
  const { id } = useParams<{ id: string }>()
  const searchParams = useSearchParams()
  const assignmentId = searchParams.get('aid')
  const submitToken = searchParams.get('token')
  const router = useRouter()

  const [job, setJob] = useState<JobDetail | null>(null)
  const [assignmentStatus, setAssignmentStatus] = useState<string>('')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState(false)

  useEffect(() => {
    const token = localStorage.getItem('translator_token')
    Promise.all([
      fetch(`${BASE_URL}/jobs/${id}`, { headers: { Authorization: `Bearer ${token}` } }),
      assignmentId
        ? fetch(`${BASE_URL}/translator/jobs`, { headers: { Authorization: `Bearer ${token}` } })
        : Promise.resolve(null),
    ])
      .then(async ([jobRes, assignRes]) => {
        if (!jobRes.ok) throw new Error('작업 정보를 불러올 수 없습니다.')
        const jobData = await jobRes.json()
        setJob(jobData)
        if (assignRes) {
          const assignments = await assignRes.json()
          const myAssignment = assignments.find((a: { id: string; status: string }) => a.id === assignmentId)
          if (myAssignment) setAssignmentStatus(myAssignment.status)
        }
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setIsLoading(false))
  }, [id, assignmentId])

  const handleAction = async (action: 'accept' | 'reject') => {
    if (!assignmentId) return
    setActionLoading(true)
    const token = localStorage.getItem('translator_token')
    try {
      const res = await fetch(`${BASE_URL}/jobs/${id}/assignments/${assignmentId}/${action}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail ?? '처리 중 오류가 발생했습니다.')
      }
      setAssignmentStatus(action === 'accept' ? 'ACCEPTED' : 'REJECTED')
      if (action === 'reject') {
        // 거절 후 1초 뒤 대시보드로 이동
        setTimeout(() => router.push('/translator/dashboard'), 1000)
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '오류가 발생했습니다.')
    } finally {
      setActionLoading(false)
    }
  }

  if (isLoading) return <div className="text-sm text-gray-400 py-12 text-center">불러오는 중...</div>
  if (error || !job) return <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">{error ?? '작업을 찾을 수 없습니다.'}</div>

  return (
    <div className="space-y-6 max-w-3xl">
      <button onClick={() => router.back()} className="text-sm text-gray-500 hover:text-gray-700">
        ← 목록으로
      </button>

      {/* 작업 기본 정보 */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
        <h2 className="text-base font-semibold text-gray-900 mb-3">작업 정보</h2>
        <InfoRow label="언어쌍" value={`${job.source_lang.toUpperCase()} → ${job.target_lang.toUpperCase()}`} />
        <InfoRow label="문서 유형" value={job.content_type} />
        <InfoRow label="품질 등급" value={job.quality_level} />
        <InfoRow label="단어 수" value={job.word_count?.toLocaleString()} />
        <InfoRow label="마감일" value={job.deadline ? new Date(job.deadline).toLocaleDateString('ko-KR') : null} />
        {job.notes && <InfoRow label="요청사항" value={job.notes} />}
        {job.file_url && (
          <InfoRow label="원본 파일" value={
            <a href={job.file_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
              다운로드 →
            </a>
          } />
        )}
      </div>

      {/* 수락/거절 패널 (PENDING_ACCEPTANCE 상태일 때) */}
      {assignmentStatus === 'PENDING_ACCEPTANCE' && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-5 space-y-4">
          <p className="text-sm font-semibold text-yellow-800">이 작업을 수락하시겠습니까?</p>
          <p className="text-sm text-yellow-700">
            {job.word_count ? `${job.word_count.toLocaleString()}단어` : ''}
            {job.deadline ? ` · 마감 ${new Date(job.deadline).toLocaleDateString('ko-KR')}` : ''}
          </p>
          <div className="flex gap-3">
            <button
              onClick={() => handleAction('accept')}
              disabled={actionLoading}
              className="flex-1 py-2.5 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {actionLoading ? '처리 중...' : '수락'}
            </button>
            <button
              onClick={() => handleAction('reject')}
              disabled={actionLoading}
              className="flex-1 py-2.5 bg-gray-200 text-gray-700 text-sm font-semibold rounded-lg hover:bg-gray-300 disabled:opacity-50 transition-colors"
            >
              거절
            </button>
          </div>
        </div>
      )}

      {assignmentStatus === 'REJECTED' && (
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 text-sm text-gray-500 text-center">
          거절한 작업입니다.
        </div>
      )}

      {/* 수락한 작업 — AI 어시스턴트 + 파일 제출 */}
      {assignmentStatus === 'ACCEPTED' && (
        <>
          <AIPanel
            sourceLang={job.source_lang}
            targetLang={job.target_lang}
            contentType={job.content_type}
          />
          {submitToken && (
            <SubmitPanel jobId={job.id} submitToken={submitToken} />
          )}
          {!submitToken && (
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-700">
              파일 제출은 배정 이메일의 링크를 통해 접근하세요.
            </div>
          )}
        </>
      )}
    </div>
  )
}
