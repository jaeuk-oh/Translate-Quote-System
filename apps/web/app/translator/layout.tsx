'use client'

import TranslatorGuard from '@/components/TranslatorGuard'
import { useRouter } from 'next/navigation'

export default function TranslatorLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()

  const handleLogout = () => {
    localStorage.removeItem('translator_token')
    localStorage.removeItem('translator_info')
    router.replace('/translator/login')
  }

  return (
    <TranslatorGuard>
      <div className="min-h-screen bg-gray-50">
        <header className="bg-white border-b border-gray-200 px-6 py-4">
          <div className="max-w-4xl mx-auto flex items-center justify-between">
            <h1 className="text-lg font-bold text-gray-900">번역가 포털</h1>
            <button
              onClick={handleLogout}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              로그아웃
            </button>
          </div>
        </header>
        <main className="max-w-4xl mx-auto px-6 py-8">
          {children}
        </main>
      </div>
    </TranslatorGuard>
  )
}
