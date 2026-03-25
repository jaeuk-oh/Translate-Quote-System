'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { listJobs, JobResponse } from '@/lib/api'

// 상태별 배지 설정
const STATUS_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  REQUESTED:    { bg: 'bg-gray-100',    text: 'text-gray-700',   label: '의뢰 접수' },
  QUOTE_PENDING:{ bg: 'bg-yellow-50',   text: 'text-yellow-700', label: '견적 계산 중' },
  QUOTED_DRAFT: { bg: 'bg-orange-50',   text: 'text-orange-700', label: '검토 필요' },
  QUOTED:       { bg: 'bg-blue-50',     text: 'text-blue-700',   label: '고객 확인 중' },
  ASSIGNED:     { bg: 'bg-indigo-50',   text: 'text-indigo-700', label: '배정 확정 필요' },
  IN_PROGRESS:  { bg: 'bg-purple-50',   text: 'text-purple-700', label: '번역 진행 중' },
  REVIEW:       { bg: 'bg-cyan-50',     text: 'text-cyan-700',   label: '검토 중' },
  QA:           { bg: 'bg-teal-50',     text: 'text-teal-700',   label: 'QA 검수' },
  COMPLETED:    { bg: 'bg-green-50',    text: 'text-green-700',  label: '완료' },
  CANCELLED:    { bg: 'bg-red-50',      text: 'text-red-700',    label: '취소됨' },
}

// 담당자 액션이 필요한 상태
const ACTION_NEEDED = new Set(['QUOTED_DRAFT', 'ASSIGNED'])

const TABS = [
  { key: 'all',    label: '전체' },
  { key: 'action', label: '액션 필요' },
  { key: 'active', label: '진행 중' },
  { key: 'done',   label: '완료/취소' },
] as const

type TabKey = (typeof TABS)[number]['key']

function StatusBadge({ status }: { status: string }) {
  const b = STATUS_BADGE[status] ?? { bg: 'bg-gray-100', text: 'text-gray-600', label: status }
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${b.bg} ${b.text}`}>
      {ACTION_NEEDED.has(status) && <span className="mr-1 text-orange-500">●</span>}
      {b.label}
    </span>
  )
}

function JobRow({ job }: { job: JobResponse }) {
  return (
    <tr className="hover:bg-gray-50 transition-colors">
      <td className="px-4 py-3 text-sm text-gray-900 font-medium">
        {job.client_name}
        <div className="text-xs text-gray-400">{job.client_email}</div>
      </td>
      <td className="px-4 py-3 text-sm text-gray-700">
        {job.source_lang.toUpperCase()} → {job.target_lang.toUpperCase()}
        {job.content_type && <div className="text-xs text-gray-400">{job.content_type}</div>}
      </td>
      <td className="px-4 py-3 text-sm text-gray-500">
        {job.word_count ? job.word_count.toLocaleString() : '-'}
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={job.status} />
      </td>
      <td className="px-4 py-3 text-sm text-gray-500">
        {job.deadline ? new Date(job.deadline).toLocaleDateString('ko-KR') : '-'}
      </td>
      <td className="px-4 py-3 text-sm">
        <Link
          href={`/jobs/${job.id}`}
          className="text-blue-600 hover:text-blue-800 font-medium"
        >
          상세 →
        </Link>
      </td>
    </tr>
  )
}

export default function DashboardPage() {
  const [jobs, setJobs] = useState<JobResponse[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabKey>('all')

  useEffect(() => {
    listJobs()
      .then(setJobs)
      .catch((err: Error) => setError(err.message))
      .finally(() => setIsLoading(false))
  }, [])

  const filtered = jobs.filter((job) => {
    if (activeTab === 'all') return true
    if (activeTab === 'action') return ACTION_NEEDED.has(job.status)
    if (activeTab === 'active')
      return !ACTION_NEEDED.has(job.status) && !['COMPLETED', 'CANCELLED'].includes(job.status)
    return ['COMPLETED', 'CANCELLED'].includes(job.status)
  })

  const actionCount = jobs.filter((j) => ACTION_NEEDED.has(j.status)).length

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">번역 작업 현황</h1>
        <p className="text-sm text-gray-500 mt-1">
          전체 {jobs.length}건
          {actionCount > 0 && (
            <span className="ml-2 text-orange-600 font-medium">· 액션 필요 {actionCount}건</span>
          )}
        </p>
      </div>

      {/* 탭 */}
      <div className="flex gap-1 bg-gray-100 rounded-lg p-1 w-fit">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${
              activeTab === tab.key
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab.label}
            {tab.key === 'action' && actionCount > 0 && (
              <span className="ml-1.5 bg-orange-500 text-white text-xs rounded-full px-1.5 py-0.5">
                {actionCount}
              </span>
            )}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="text-sm text-gray-400 py-12 text-center">불러오는 중...</div>
      ) : error ? (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          {error}
          {(error.includes('401') || error.includes('인증')) && (
            <Link href="/auth/login" className="ml-2 underline">로그인</Link>
          )}
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-gray-300 p-12 text-center text-sm text-gray-400">
          해당하는 작업이 없습니다.
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">고객</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">언어쌍</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">단어수</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">상태</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">마감일</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map((job) => (
                <JobRow key={job.id} job={job} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
