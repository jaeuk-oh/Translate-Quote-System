'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'

export default function AdminHeader() {
  const router = useRouter()

  const handleLogout = () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    router.push('/auth/login')
  }

  return (
    <header className="bg-white border-b border-gray-200 px-6 py-4">
      <div className="max-w-5xl mx-auto flex items-center justify-between">
        <Link href="/dashboard" className="text-lg font-bold text-blue-600">
          번역 관리 시스템
        </Link>
        <nav className="flex items-center gap-6 text-sm">
          <Link href="/dashboard" className="text-gray-600 hover:text-blue-600 transition-colors">
            대시보드
          </Link>
          <button
            onClick={handleLogout}
            className="text-gray-500 hover:text-red-600 transition-colors"
          >
            로그아웃
          </button>
        </nav>
      </div>
    </header>
  )
}
