/**
 * 대시보드 로딩 상태 UI (Next.js App Router 자동 활성화).
 * 대시보드 페이지 초기 렌더링 시 스켈레톤 카드 3개를 표시.
 */

export default function DashboardLoading() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      {/* 헤더 스켈레톤 */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <div className="h-7 w-36 bg-gray-200 rounded animate-pulse" />
          <div className="h-4 w-52 bg-gray-100 rounded animate-pulse" />
        </div>
        <div className="h-9 w-24 bg-gray-200 rounded-lg animate-pulse" />
      </div>

      {/* 탭 스켈레톤 */}
      <div className="h-10 w-full bg-gray-100 rounded-lg animate-pulse" />

      {/* 작업 카드 스켈레톤 3개 */}
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm"
          >
            <div className="flex items-start justify-between gap-4">
              {/* 언어쌍 + 유형 */}
              <div className="space-y-2 flex-1">
                <div className="h-4 w-28 bg-gray-200 rounded animate-pulse" />
                <div className="h-3 w-44 bg-gray-100 rounded animate-pulse" />
              </div>
              {/* 상태 배지 */}
              <div className="h-5 w-20 bg-gray-100 rounded-full animate-pulse" />
            </div>

            {/* 하단 정보 */}
            <div className="mt-4 flex items-center justify-between">
              <div className="h-3 w-36 bg-gray-100 rounded animate-pulse" />
              <div className="h-3 w-16 bg-gray-100 rounded animate-pulse" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
