'use client'

import { useState, FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { createJob } from '@/lib/api'

// 지원 언어 목록
const LANGUAGES = [
  { value: 'ko', label: '한국어' },
  { value: 'en', label: '영어' },
  { value: 'ja', label: '일본어' },
  { value: 'zh', label: '중국어' },
]

// 콘텐츠 유형 — quote_service.py CONTENT_DIFFICULTY와 동기화
const CONTENT_TYPES = [
  { value: 'general', label: '일반 문서' },
  { value: 'marketing', label: '마케팅' },
  { value: 'technical', label: '기술 문서' },
  { value: 'legal', label: '법률 문서' },
  { value: 'medical', label: '의료 문서' },
]

// 품질 등급 — quote_service.py QUALITY_WEIGHTS와 동기화
const QUALITY_LEVELS = [
  { value: 'translation', label: '번역 (Translation)' },
  { value: 'review', label: '번역 + 검수 (Review)' },
  { value: 'dtp', label: '번역 + 검수 + 편집 (DTP)' },
]

export default function NewJobPage() {
  const router = useRouter()
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [form, setForm] = useState({
    source_lang: 'ko',
    target_lang: 'en',
    content_type: 'general',
    quality_level: 'translation',
    word_count: '',
    deadline: '',
  })

  const handleChange = (
    e: React.ChangeEvent<HTMLSelectElement | HTMLInputElement>
  ) => {
    setForm(prev => ({ ...prev, [e.target.name]: e.target.value }))
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)

    // 같은 언어 선택 방지
    if (form.source_lang === form.target_lang) {
      setError('소스 언어와 타겟 언어를 다르게 선택해주세요.')
      return
    }

    setIsLoading(true)
    try {
      const payload = {
        source_lang: form.source_lang,
        target_lang: form.target_lang,
        content_type: form.content_type,
        quality_level: form.quality_level,
        word_count: form.word_count ? parseInt(form.word_count, 10) : undefined,
        deadline: form.deadline || undefined,
      }

      const job = await createJob(payload)
      // 생성 완료 → 작업 상세 페이지로 이동
      router.push(`/jobs/${job.id}`)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '작업 생성에 실패했습니다.'
      setError(message)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">번역 의뢰 등록</h1>
        <p className="mt-1 text-sm text-gray-500">
          작업 정보를 입력하면 자동으로 견적이 산출됩니다.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-gray-200 p-8 space-y-6 shadow-sm">
        {/* 언어쌍 선택 */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              소스 언어 <span className="text-red-500">*</span>
            </label>
            <select
              name="source_lang"
              value={form.source_lang}
              onChange={handleChange}
              required
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {LANGUAGES.map(lang => (
                <option key={lang.value} value={lang.value}>{lang.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              타겟 언어 <span className="text-red-500">*</span>
            </label>
            <select
              name="target_lang"
              value={form.target_lang}
              onChange={handleChange}
              required
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {LANGUAGES.map(lang => (
                <option key={lang.value} value={lang.value}>{lang.label}</option>
              ))}
            </select>
          </div>
        </div>

        {/* 콘텐츠 유형 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            콘텐츠 유형
          </label>
          <select
            name="content_type"
            value={form.content_type}
            onChange={handleChange}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {CONTENT_TYPES.map(ct => (
              <option key={ct.value} value={ct.value}>{ct.label}</option>
            ))}
          </select>
          <p className="mt-1 text-xs text-gray-400">
            콘텐츠 유형에 따라 난이도 가중치가 적용됩니다 (법률 1.5x, 기술 1.3x, 마케팅 1.1x).
          </p>
        </div>

        {/* 품질 등급 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            품질 수준
          </label>
          <div className="space-y-2">
            {QUALITY_LEVELS.map(ql => (
              <label key={ql.value} className="flex items-center gap-3 cursor-pointer">
                <input
                  type="radio"
                  name="quality_level"
                  value={ql.value}
                  checked={form.quality_level === ql.value}
                  onChange={handleChange}
                  className="text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">{ql.label}</span>
              </label>
            ))}
          </div>
        </div>

        {/* 단어 수 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            예상 단어 수
          </label>
          <input
            type="number"
            name="word_count"
            value={form.word_count}
            onChange={handleChange}
            min="1"
            placeholder="예: 1000"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <p className="mt-1 text-xs text-gray-400">
            단어 수를 기반으로 견적 금액과 예상 작업 시간이 계산됩니다.
          </p>
        </div>

        {/* 파일 업로드 (UI 전용, 실제 업로드는 별도 API 필요) */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            파일 업로드
          </label>
          <div className="border-2 border-dashed border-gray-300 rounded-lg px-6 py-8 text-center hover:border-blue-400 transition-colors">
            <p className="text-sm text-gray-500">
              파일을 드래그하거나 클릭하여 업로드
            </p>
            <p className="text-xs text-gray-400 mt-1">
              .docx, .pdf, .txt, .xlsx 지원
            </p>
          </div>
        </div>

        {/* 마감일 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            마감일
          </label>
          <input
            type="datetime-local"
            name="deadline"
            value={form.deadline}
            onChange={handleChange}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <p className="mt-1 text-xs text-gray-400">
            마감이 촉박할수록 긴급 할증이 적용됩니다 (3일 미만 1.5x, 7일 미만 1.2x).
          </p>
        </div>

        {/* 에러 메시지 */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* 제출 버튼 */}
        <button
          type="submit"
          disabled={isLoading}
          className="w-full py-3 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isLoading ? '처리 중...' : '견적 요청하기'}
        </button>
      </form>
    </div>
  )
}
