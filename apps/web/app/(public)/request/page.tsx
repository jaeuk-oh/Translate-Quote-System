'use client'

import { useState, FormEvent } from 'react'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

const LANGUAGES = [
  { value: 'ko', label: '한국어' },
  { value: 'en', label: '영어' },
  { value: 'ja', label: '일본어' },
  { value: 'zh', label: '중국어' },
  { value: 'de', label: '독일어' },
  { value: 'fr', label: '프랑스어' },
  { value: 'es', label: '스페인어' },
]

const CONTENT_TYPES = [
  { value: 'legal', label: '법률/계약서' },
  { value: 'technical', label: '기술/IT' },
  { value: 'medical', label: '의료/제약' },
  { value: 'marketing', label: '마케팅/광고' },
  { value: 'general', label: '일반 문서' },
]

const QUALITY_LEVELS = [
  { value: 'standard', label: '스탠다드', desc: '일반 문서, 내부 자료' },
  { value: 'professional', label: '프로페셔널', desc: '공식 문서, 고객 대면' },
  { value: 'premium', label: '프리미엄', desc: '법률·의료 등 전문 분야' },
]

export default function RequestPage() {
  const [form, setForm] = useState({
    client_name: '',
    client_email: '',
    source_lang: 'en',
    target_lang: 'ko',
    content_type: 'general',
    quality_level: 'standard',
    word_count: '',
    deadline: '',
    notes: '',
  })
  const [isLoading, setIsLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }))
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setError(null)

    try {
      const res = await fetch(`${BASE_URL}/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          word_count: form.word_count ? Number(form.word_count) : null,
          deadline: form.deadline || null,
        }),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail ?? '요청 중 오류가 발생했습니다.')
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
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="max-w-md w-full text-center space-y-4">
          <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto">
            <svg className="w-8 h-8 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-gray-900">견적 요청이 접수되었습니다</h2>
          <p className="text-sm text-gray-500">
            영업일 기준 1일 이내에 입력하신 이메일로 견적서를 보내드립니다.
          </p>
          <button
            onClick={() => { setSubmitted(false); setForm({ client_name: '', client_email: '', source_lang: 'en', target_lang: 'ko', content_type: 'general', quality_level: 'standard', word_count: '', deadline: '', notes: '' }) }}
            className="text-sm text-blue-600 hover:underline"
          >
            새 견적 요청하기
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen py-12 px-4">
      <div className="max-w-xl mx-auto space-y-8">
        {/* 헤더 */}
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-bold text-gray-900">번역 견적 요청</h1>
          <p className="text-sm text-gray-500">아래 양식을 작성하시면 이메일로 견적서를 보내드립니다.</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 space-y-5">

          {/* 고객 정보 */}
          <div className="space-y-4">
            <h2 className="text-sm font-semibold text-gray-700 border-b pb-2">고객 정보</h2>
            <div>
              <label className="block text-sm text-gray-600 mb-1">이름 / 회사명 <span className="text-red-500">*</span></label>
              <input
                name="client_name"
                value={form.client_name}
                onChange={handleChange}
                required
                placeholder="홍길동 / (주)예시회사"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">이메일 <span className="text-red-500">*</span></label>
              <input
                name="client_email"
                type="email"
                value={form.client_email}
                onChange={handleChange}
                required
                placeholder="example@company.com"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          {/* 번역 정보 */}
          <div className="space-y-4">
            <h2 className="text-sm font-semibold text-gray-700 border-b pb-2">번역 정보</h2>

            {/* 언어쌍 */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">원본 언어 <span className="text-red-500">*</span></label>
                <select
                  name="source_lang"
                  value={form.source_lang}
                  onChange={handleChange}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {LANGUAGES.map((l) => (
                    <option key={l.value} value={l.value}>{l.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">번역 언어 <span className="text-red-500">*</span></label>
                <select
                  name="target_lang"
                  value={form.target_lang}
                  onChange={handleChange}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {LANGUAGES.map((l) => (
                    <option key={l.value} value={l.value}>{l.label}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* 콘텐츠 유형 */}
            <div>
              <label className="block text-sm text-gray-600 mb-1">문서 유형</label>
              <select
                name="content_type"
                value={form.content_type}
                onChange={handleChange}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {CONTENT_TYPES.map((c) => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
            </div>

            {/* 품질 등급 */}
            <div>
              <label className="block text-sm text-gray-600 mb-2">품질 등급</label>
              <div className="space-y-2">
                {QUALITY_LEVELS.map((q) => (
                  <label
                    key={q.value}
                    className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                      form.quality_level === q.value
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <input
                      type="radio"
                      name="quality_level"
                      value={q.value}
                      checked={form.quality_level === q.value}
                      onChange={handleChange}
                      className="mt-0.5 text-blue-600"
                    />
                    <div>
                      <p className="text-sm font-medium text-gray-900">{q.label}</p>
                      <p className="text-xs text-gray-500">{q.desc}</p>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            {/* 단어수 / 마감일 */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">예상 단어 수</label>
                <input
                  name="word_count"
                  type="number"
                  min="1"
                  value={form.word_count}
                  onChange={handleChange}
                  placeholder="예: 2000"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">희망 마감일</label>
                <input
                  name="deadline"
                  type="date"
                  value={form.deadline}
                  onChange={handleChange}
                  min={new Date().toISOString().split('T')[0]}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            {/* 메모 */}
            <div>
              <label className="block text-sm text-gray-600 mb-1">추가 요청 사항</label>
              <textarea
                name="notes"
                value={form.notes}
                onChange={handleChange}
                rows={3}
                placeholder="특이사항, 전문 용어 등 참고할 내용을 적어주세요."
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              />
            </div>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-3 bg-blue-600 text-white text-sm font-semibold rounded-xl hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {isLoading ? '요청 중...' : '견적 요청하기'}
          </button>

          <p className="text-xs text-gray-400 text-center">
            제출하신 정보는 견적 산출 목적으로만 사용됩니다.
          </p>
        </form>
      </div>
    </div>
  )
}
