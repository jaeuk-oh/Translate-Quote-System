import AdminHeader from '@/components/AdminHeader'

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <AdminHeader />
      <main className="max-w-5xl mx-auto px-6 py-8">
        {children}
      </main>
    </>
  )
}
