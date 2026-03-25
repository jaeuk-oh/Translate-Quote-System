import { redirect } from 'next/navigation'

// 루트 접근 시 대시보드로 리다이렉트
export default function HomePage() {
  redirect('/dashboard')
}
