import Link from 'next/link'

const ROLES = [
  {
    href: '/request',
    label: '고객',
    desc: '번역 견적을 요청합니다',
    icon: (
      <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    ),
    color: 'hover:border-blue-400 hover:bg-blue-50',
    iconColor: 'text-blue-500',
  },
  {
    href: '/dashboard',
    label: '관리자',
    desc: '작업 현황을 관리합니다',
    icon: (
      <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
      </svg>
    ),
    color: 'hover:border-indigo-400 hover:bg-indigo-50',
    iconColor: 'text-indigo-500',
  },
  {
    href: null,
    label: '번역가',
    desc: '배정 이메일의 링크로 접속하세요',
    icon: (
      <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    ),
    color: 'border-gray-200 cursor-default opacity-70',
    iconColor: 'text-gray-400',
  },
]

export default function LandingPage() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4">
      <div className="max-w-lg w-full space-y-10">
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold text-gray-900">번역 플랫폼</h1>
          <p className="text-sm text-gray-500">접속 유형을 선택해주세요</p>
        </div>

        <div className="space-y-3">
          {ROLES.map((role) =>
            role.href ? (
              <Link
                key={role.label}
                href={role.href}
                className={`flex items-center gap-4 w-full p-5 bg-white rounded-2xl border border-gray-200 shadow-sm transition-colors ${role.color}`}
              >
                <span className={role.iconColor}>{role.icon}</span>
                <div>
                  <p className="text-base font-semibold text-gray-900">{role.label}</p>
                  <p className="text-sm text-gray-500">{role.desc}</p>
                </div>
                <svg className="w-4 h-4 text-gray-400 ml-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </Link>
            ) : (
              <div
                key={role.label}
                className={`flex items-center gap-4 w-full p-5 bg-white rounded-2xl border shadow-sm ${role.color}`}
              >
                <span className={role.iconColor}>{role.icon}</span>
                <div>
                  <p className="text-base font-semibold text-gray-700">{role.label}</p>
                  <p className="text-sm text-gray-400">{role.desc}</p>
                </div>
              </div>
            )
          )}
        </div>
      </div>
    </div>
  )
}
