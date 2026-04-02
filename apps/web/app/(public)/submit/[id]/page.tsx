'use client'

import { useState, FormEvent, useEffect } from 'react'
import { useParams, useSearchParams } from 'next/navigation'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

const ALLOWED_EXTENSIONS = ['.docx', '.doc', '.pdf', '.txt', '.xlsx', '.pptx', '.xliff']

export default function SubmitPage() {
  const { id } = useParams<{ id: string }>()
  const searchParams = useSearchParams()
  const token = searchParams.get('token')

  const [file, setFile] = useState<File | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tokenError, setTokenError] = useState(false)

  useEffect(() => {
    if (!token) setTokenError(true)
  }, [token])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0] ?? null
    if (!selected) return

    const ext = '.' + selected.name.split('.').pop()?.toLowerCase()
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      setError(`지원하지 않는 파일 형식입니다. 허용: ${ALLOWED_EXTENSIONS.join(', ')}`)
      setFile(null)
      return
    }
    setError(null)
    setFile(selected)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!file || !token) return

    setIsLoading(true)
    setError(null)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const res = await fetch(`${BASE_URL}/jobs/${id}/complete?token=${encodeURIComponent(token)}`, {
        method: 'POST',
        body: formData,
      })

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

  // 토큰 없음
  if (tokenError) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="max-w-md w-full text-center space-y-3">
          <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto">
            <svg className="w-8 h-8 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-gray-900">유효하지 않은 링크입니다</h2>
          <p className="text-sm text-gray-500">배정 이메일의 링크를 통해 접근해주세요.</p>
        </div>
      </div>
    )
  }

  // 제출 완료
  if (submitted) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="max-w-md w-full text-center space-y-4">
          <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto">
            <svg className="w-8 h-8 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-gray-900">결과물이 제출되었습니다</h2>
          <p className="text-sm text-gray-500">담당자 검토 후 최종 납품이 진행됩니다. 수고하셨습니다.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen py-12 px-4">
      <div className="max-w-md mx-auto space-y-8">
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-bold text-gray-900">번역 완료 파일 제출</h1>
          <p className="text-sm text-gray-500">번역이 완료된 파일을 업로드해주세요.</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 space-y-5">

          {/* 파일 업로드 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              완료 파일 <span className="text-red-500">*</span>
            </label>
            <label className={`flex flex-col items-center justify-center w-full h-36 border-2 border-dashed rounded-xl cursor-pointer transition-colors ${
              file ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-gray-400 bg-gray-50'
            }`}>
              <input
                type="file"
                className="hidden"
                accept={ALLOWED_EXTENSIONS.join(',')}
                onChange={handleFileChange}
              />
              {file ? (
                <div className="text-center space-y-1">
                  <p className="text-sm font-medium text-blue-700">{file.name}</p>
                  <p className="text-xs text-blue-500">{(file.size / 1024).toFixed(1)} KB</p>
                  <p className="text-xs text-gray-400">클릭하여 파일 변경</p>
                </div>
              ) : (
                <div className="text-center space-y-1">
                  <svg className="w-8 h-8 text-gray-400 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  <p className="text-sm text-gray-500">클릭하여 파일 선택</p>
                  <p className="text-xs text-gray-400">{ALLOWED_EXTENSIONS.join(', ')}</p>
                </div>
              )}
            </label>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={!file || isLoading}
            className="w-full py-3 bg-blue-600 text-white text-sm font-semibold rounded-xl hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {isLoading ? '제출 중...' : '제출하기'}
          </button>
        </form>
      </div>
    </div>
  )
}
