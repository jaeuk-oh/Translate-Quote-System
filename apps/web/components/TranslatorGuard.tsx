'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

export default function TranslatorGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const [checked, setChecked] = useState(false)

  useEffect(() => {
    const token = localStorage.getItem('translator_token')
    if (!token) {
      router.replace('/translator/login')
    }
    setChecked(true)
  }, [router])

  // 토큰 확인 전까지 아무것도 렌더링하지 않음 (깜빡임 방지)
  if (!checked) return null
  return <>{children}</>
}
