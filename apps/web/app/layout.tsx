import type { Metadata } from 'next'
import './globals.css'
import AdminHeader from '@/components/AdminHeader'

export const metadata: Metadata = {
  title: '번역 관리 시스템',
  description: '번역 의뢰 견적·배정·완료 관리 대시보드',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-gray-50 text-gray-900">
        <AdminHeader />
        <main className="max-w-5xl mx-auto px-6 py-8">
          {children}
        </main>
      </body>
    </html>
  )
}
