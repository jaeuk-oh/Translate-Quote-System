'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

interface JobInfo {
  id: string
  source_lang: string
  target_lang: string
  content_type: string | null
  word_count: number | null
  deadline: string | null
  notes: string | null
  status: string
}

interface MyJob {
  id: string
  job_id: string
  status: string
  assigned_at: string
  accepted_at: string | null
  rejected_at: string | null
  job: JobInfo
}

const STATUS_LABEL: Record<string, { label: string; color: string }> = {
  PENDING_ACCEPTANCE: { label: '수락 대기', color: 'bg-yellow-100 text-yellow-700' },
  ACCEPTED:          { label: '진행 중',   color: 'bg-blue-100 text-blue-700' },
  REJECTED:          { label: '거절함',    color: 'bg-gray-100 text-gray-500' },
  COMPLETED:         { label: '완료',      color: 'bg-green-100 text-green-700' },
  CANCELLED:         { label: '취소됨',    color: 'bg-red-100 text-red-700' },
}

export default function TranslatorDashboardPage() {
  const [jobs, setJobs] = useState<MyJob[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const token = localStorage.getItem('translator_token')
    fetch(`${BASE_URL}/translator/jobs`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`API 오류: ${r.status}`)
        return r.json()
      })
      .then(setJobs)
      .catch((err: Error) => setError(err.message))
      .finally(() => setIsLoading(false))
  }, [])

  if (isLoading) return <div className="text-sm text-gray-400 py-12 text-center">불러오는 중...</div>
  if (error) return <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">{error}</div>

  const pending = jobs.filter((j) => j.status === 'PENDING_ACCEPTANCE')
  const active  = jobs.filter((j) => j.status === 'ACCEPTED')
  const done    = jobs.filter((j) => ['COMPLETED', 'REJECTED', 'CANCELLED'].includes(j.status))

  const Section = ({ title, items }: { title: string; items: MyJob[] }) =>
    items.length === 0 ? null : (
      <div className="space-y-3">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">{title}</h2>
        {items.map((j) => {
          const badge = STATUS_LABEL[j.status] ?? { label: j.status, color: 'bg-gray-100 text-gray-600' }
          return (
            <Link
              key={j.id}
              href={`/translator/jobs/${j.job_id}?aid=${j.id}`}
              className="block bg-white rounded-xl border border-gray-200 p-4 hover:border-blue-300 transition-colors shadow-sm"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <p className="text-sm font-medium text-gray-900">
                    {j.job.source_lang.toUpperCase()} → {j.job.target_lang.toUpperCase()}
                    {j.job.content_type && <span className="ml-2 text-gray-400 font-normal">· {j.job.content_type}</span>}
                  </p>
                  <p className="text-xs text-gray-500">
                    {j.job.word_count ? `${j.job.word_count.toLocaleString()}단어` : '단어수 미정'}
                    {j.job.deadline && ` · 마감 ${new Date(j.job.deadline).toLocaleDateString('ko-KR')}`}
                  </p>
                  {j.job.notes && <p className="text-xs text-gray-400 truncate max-w-xs">{j.job.notes}</p>}
                </div>
                <span className={`shrink-0 text-xs px-2.5 py-1 rounded-full font-medium ${badge.color}`}>
                  {badge.label}
                </span>
              </div>
            </Link>
          )
        })}
      </div>
    )

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">내 작업 목록</h1>
        <p className="text-sm text-gray-500 mt-1">전체 {jobs.length}건</p>
      </div>

      {jobs.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-gray-300 p-12 text-center text-sm text-gray-400">
          배정된 작업이 없습니다.
        </div>
      ) : (
        <>
          <Section title="수락 대기" items={pending} />
          <Section title="진행 중" items={active} />
          <Section title="완료 / 거절" items={done} />
        </>
      )}
    </div>
  )
}
