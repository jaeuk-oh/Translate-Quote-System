'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { JobResponse } from '@/lib/api'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// 상태별 필터 탭 정의
const STATUS_TABS = [
  { key: 'all', label: '전체' },
  { key: 'in_progress', label: '진행중' },
  { key: 'completed', label: '완료' },
] as const

type TabKey = (typeof STATUS_TABS)[number]['key']

// 진행중 상태 목록 (FSM 기준)
const IN_PROGRESS_STATUSES = new Set([
  'REQUESTED',
  'QUOTE_PENDING',
  'QUOTED',
  'PENDING_ACCEPTANCE',
  'ASSIGNED',
  'IN_PROGRESS',
  'REVIEW',
  'QA',
])

// 상태별 배지 색상 매핑
const STATUS_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  REQUESTED: { bg: 'bg-gray-100', text: 'text-gray-700', label: '의뢰 접수' },
  QUOTE_PENDING: { bg: 'bg-yellow-50', text: 'text-yellow-700', label: '견적 계산 중' },
  QUOTED: { bg: 'bg-blue-50', text: 'text-blue-700', label: '견적 완료' },
  PENDING_ACCEPTANCE: { bg: 'bg-purple-50', text: 'text-purple-700', label: '배정 대기' },
  ASSIGNED: { bg: 'bg-indigo-50', text: 'text-indigo-700', label: '배정 완료' },
  IN_PROGRESS: { bg: 'bg-orange-50', text: 'text-orange-700', label: '번역 진행 중' },
  REVIEW: { bg: 'bg-cyan-50', text: 'text-cyan-700', label: '검토 중' },
  QA: { bg: 'bg-teal-50', text: 'text-teal-700', label: 'QA 검수' },
  COMPLETED: { bg: 'bg-green-50', text: 'text-green-700', label: '완료' },
  CANCELLED: { bg: 'bg-red-50', text: 'text-red-700', label: '취소됨' },
}

function StatusBadge({ status }: { status: string }) {
  const badge = STATUS_BADGE[status] ?? {
    bg: 'bg-gray-100',
    text: 'text-gray-600',
    label: status,
  }
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${badge.bg} ${badge.text}`}
    >
      {badge.label}
    </span>
  )
}

function JobCard({ job }: { job: JobResponse }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          {/* 언어쌍 */}
          <p className="text-sm font-semibold text-gray-900">
            {job.source_lang.toUpperCase()} → {job.target_lang.toUpperCase()}
          </p>
          {/* 콘텐츠 유형 및 품질 등급 */}
          <p className="text-xs text-gray-500 mt-0.5">
            {job.content_type ?? '일반'} | {job.quality_level ?? 'translation'}
            {job.word_count ? ` | ${job.word_count.toLocaleString()}단어` : ''}
          </p>
        </div>
        <StatusBadge status={job.status} />
      </div>

      <div className="mt-4 flex items-center justify-between text-xs text-gray-500">
        <div className="space-x-3">
          {/* 마감일 */}
          <span>
            마감:{' '}
            {job.deadline
              ? new Date(job.deadline).toLocaleDateString('ko-KR')
              : '미지정'}
          </span>
          {/* 의뢰일 */}
          <span>의뢰: {new Date(job.created_at).toLocaleDateString('ko-KR')}</span>
        </div>
        {/* 상세보기 링크 */}
        <Link
          href={`/jobs/${job.id}`}
          className="text-blue-600 hover:text-blue-800 font-medium transition-colors"
        >
          상세보기 →
        </Link>
      </div>
    </div>
  )
}

/**
 * fetchWithAuth — 대시보드 내부용 인증 API 호출 래퍼
 * lib/api.ts의 fetchWithAuth와 동일한 패턴
 */
async function fetchWithAuth(path: string): Promise<Response> {
  const token =
    typeof window !== 'undefined' ? localStorage.getItem('access_token') : null

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }

  const response = await fetch(`${BASE_URL}${path}`, { headers })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body?.detail ?? `API 오류: ${response.status}`)
  }
  return response
}

export default function DashboardPage() {
  const [jobs, setJobs] = useState<JobResponse[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabKey>('all')

  // 작업 목록 로드
  useEffect(() => {
    const loadJobs = async () => {
      try {
        setIsLoading(true)
        const response = await fetchWithAuth('/jobs')
        const data: JobResponse[] = await response.json()
        setJobs(data)
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : '작업 목록을 불러오지 못했습니다.'
        setError(message)
      } finally {
        setIsLoading(false)
      }
    }

    loadJobs()
  }, [])

  // 탭 기반 필터링
  const filteredJobs = jobs.filter((job) => {
    if (activeTab === 'all') return true
    if (activeTab === 'in_progress') return IN_PROGRESS_STATUSES.has(job.status)
    if (activeTab === 'completed') return job.status === 'COMPLETED'
    return true
  })

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      {/* 페이지 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">내 번역 작업</h1>
          <p className="text-sm text-gray-500 mt-1">
            의뢰한 번역 작업의 진행 상태를 확인하세요
          </p>
        </div>
        <Link
          href="/jobs/new"
          className="px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 transition-colors"
        >
          + 새 의뢰
        </Link>
      </div>

      {/* 상태 필터 탭 */}
      <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
              activeTab === tab.key
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab.label}
            {/* 탭별 카운트 */}
            {!isLoading && (
              <span className="ml-1.5 text-xs text-gray-400">
                (
                {tab.key === 'all'
                  ? jobs.length
                  : tab.key === 'in_progress'
                  ? jobs.filter((j) => IN_PROGRESS_STATUSES.has(j.status)).length
                  : jobs.filter((j) => j.status === 'COMPLETED').length}
                )
              </span>
            )}
          </button>
        ))}
      </div>

      {/* 컨텐츠 영역 */}
      {isLoading ? (
        // 로딩 중일 때는 loading.tsx 스켈레톤이 표시되지만
        // 클라이언트 컴포넌트이므로 자체 로딩 상태도 처리
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="bg-white rounded-xl border border-gray-200 p-5 animate-pulse"
            >
              <div className="flex items-start justify-between">
                <div className="space-y-2">
                  <div className="h-4 w-24 bg-gray-200 rounded" />
                  <div className="h-3 w-40 bg-gray-100 rounded" />
                </div>
                <div className="h-5 w-16 bg-gray-100 rounded-full" />
              </div>
              <div className="mt-4 flex justify-between">
                <div className="h-3 w-32 bg-gray-100 rounded" />
                <div className="h-3 w-16 bg-gray-100 rounded" />
              </div>
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-red-700 text-sm">
          {error}
        </div>
      ) : filteredJobs.length === 0 ? (
        <div className="bg-gray-50 rounded-xl border border-dashed border-gray-300 p-12 text-center">
          <p className="text-gray-500 text-sm">
            {activeTab === 'all'
              ? '아직 번역 의뢰가 없습니다.'
              : activeTab === 'in_progress'
              ? '진행 중인 작업이 없습니다.'
              : '완료된 작업이 없습니다.'}
          </p>
          {activeTab === 'all' && (
            <Link
              href="/jobs/new"
              className="mt-4 inline-block px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 transition-colors"
            >
              첫 번역 의뢰하기
            </Link>
          )}
        </div>
      ) : (
        // 작업 카드 목록
        <div className="space-y-4">
          {filteredJobs.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      )}
    </div>
  )
}
