'use client'

import { useEffect, useRef, useState } from 'react'

// SSE 이벤트 유형 — FastAPI /jobs/:id/stream 엔드포인트가 발행하는 이벤트
export type JobStreamEventType = 'STATUS_UPDATE' | 'COMPLETED' | 'ERROR'

export interface JobStreamEvent {
  type: JobStreamEventType
  job_id: string
  status: string
  timestamp: string
  data?: Record<string, unknown>
}

interface UseJobStreamReturn {
  latestEvent: JobStreamEvent | null
  isConnected: boolean
  error: string | null
}

/**
 * SSE(Server-Sent Events)로 작업 상태를 실시간 구독하는 커스텀 훅.
 *
 * GET /jobs/:id/stream 엔드포인트에 연결하여
 * STATUS_UPDATE, COMPLETED 이벤트를 처리.
 * COMPLETED 이벤트 수신 시 자동으로 연결 종료.
 * 컴포넌트 언마운트 시 EventSource.close()로 정리.
 */
export function useJobStream(jobId: string | null): UseJobStreamReturn {
  const [latestEvent, setLatestEvent] = useState<JobStreamEvent | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // EventSource 인스턴스를 ref로 관리 (리렌더링 무관)
  const eventSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    // jobId가 없으면 SSE 연결하지 않음
    if (!jobId) return

    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
    const streamUrl = `${apiUrl}/jobs/${jobId}/stream`

    const eventSource = new EventSource(streamUrl)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => {
      setIsConnected(true)
      setError(null)
    }

    eventSource.onmessage = (ev: MessageEvent) => {
      try {
        const parsed: JobStreamEvent = JSON.parse(ev.data)
        setLatestEvent(parsed)

        // COMPLETED 이벤트 수신 시 SSE 연결 종료 (더 이상 업데이트 없음)
        if (parsed.type === 'COMPLETED') {
          eventSource.close()
          setIsConnected(false)
        }
      } catch {
        // JSON 파싱 실패 시 무시 (keep-alive ping 등)
      }
    }

    eventSource.onerror = () => {
      setError('실시간 연결이 끊어졌습니다. 페이지를 새로고침해주세요.')
      setIsConnected(false)
      eventSource.close()
    }

    // 컴포넌트 언마운트 시 EventSource 정리 (메모리 누수 방지)
    return () => {
      eventSource.close()
      eventSourceRef.current = null
      setIsConnected(false)
    }
  }, [jobId])

  return { latestEvent, isConnected, error }
}
