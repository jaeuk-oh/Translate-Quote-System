import AdminHeader from '@/components/AdminHeader'
import AuthGuard from '@/components/AuthGuard'

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <AdminHeader />
      <main className="max-w-5xl mx-auto px-6 py-8">
        {children}
      </main>
    </AuthGuard>
  )
}
