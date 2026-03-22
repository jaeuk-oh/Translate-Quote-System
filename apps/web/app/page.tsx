import Link from 'next/link'

export default function HomePage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center gap-8">
      <div className="space-y-4">
        <h1 className="text-4xl font-bold text-gray-900">
          전문 번역 서비스
        </h1>
        <p className="text-lg text-gray-500 max-w-xl">
          의뢰 접수부터 견적, 번역가 배정, 납품까지
          <br />
          운영 개입 없이 자동으로 처리되는 번역 플랫폼입니다.
        </p>
      </div>

      <div className="flex gap-4">
        <Link
          href="/jobs/new"
          className="px-8 py-3 bg-blue-600 text-white text-base font-semibold rounded-lg hover:bg-blue-700 transition-colors"
        >
          번역 의뢰하기
        </Link>
        <a
          href="#features"
          className="px-8 py-3 bg-white text-gray-700 text-base font-semibold rounded-lg border border-gray-300 hover:bg-gray-50 transition-colors"
        >
          서비스 소개
        </a>
      </div>

      <section id="features" className="mt-16 grid grid-cols-1 md:grid-cols-3 gap-6 w-full max-w-4xl">
        <FeatureCard
          title="자동 견적"
          description="단어 수, 언어쌍, 난이도, TM 매칭률을 반영한 즉각적인 견적 산출"
        />
        <FeatureCard
          title="자동 배정"
          description="성과 점수 기반으로 최적 번역가를 자동 선별하여 배정"
        />
        <FeatureCard
          title="실시간 추적"
          description="SSE 기반 실시간 상태 업데이트로 작업 진행 상황 즉시 확인"
        />
      </section>
    </div>
  )
}

function FeatureCard({ title, description }: { title: string; description: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 text-left shadow-sm">
      <h3 className="text-lg font-semibold text-gray-900 mb-2">{title}</h3>
      <p className="text-sm text-gray-500 leading-relaxed">{description}</p>
    </div>
  )
}
