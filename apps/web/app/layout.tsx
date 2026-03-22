import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: '번역 플랫폼',
  description: '번역 의뢰부터 납품까지 자동화된 번역 플랫폼',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-gray-50 text-gray-900">
        <header className="bg-white border-b border-gray-200 px-6 py-4">
          <div className="max-w-5xl mx-auto flex items-center justify-between">
            <a href="/" className="text-xl font-bold text-blue-600">
              번역 플랫폼
            </a>
            <nav className="flex gap-6 text-sm text-gray-600">
              <a href="/jobs/new" className="hover:text-blue-600">번역 의뢰</a>
            </nav>
          </div>
        </header>
        <main className="max-w-5xl mx-auto px-6 py-10">
          {children}
        </main>
      </body>
    </html>
  )
}
