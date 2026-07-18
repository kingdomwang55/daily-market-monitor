import type {
  HealthResponse,
  Monitor,
  PageResponse,
  PaperTrade,
  PushFilters,
  PushLog,
  SignalDetail,
  SignalFilters,
  SignalPage,
  SignalType,
  StatsSummary,
  ReviewDetail,
  ReviewSummary,
  SignalNote,
  SystemStatus,
  TradeAction,
  TradeCreatePayload,
  TradeFilters,
} from './types'

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message)
  }
}

function queryString<T extends object>(filters: T): string {
  const query = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== '' && value !== null) {
      query.set(key, String(value))
    }
  })
  return query.size ? `?${query.toString()}` : ''
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = sessionStorage.getItem('market-write-token')
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { 'X-Market-Token': token } : {}),
      ...init.headers,
    },
  })
  if (!response.ok) {
    let message = `请求失败 (${response.status})`
    try {
      const body = (await response.json()) as { detail?: string }
      message = body.detail || message
    } catch {
      // Keep the status-based message when the response is not JSON.
    }
    throw new ApiError(message, response.status)
  }
  return response.json() as Promise<T>
}

export function getHealth(): Promise<HealthResponse> {
  return request('/api/health')
}

export function getSignals(filters: SignalFilters = {}): Promise<SignalPage> {
  return request(`/api/signals${queryString(filters)}`)
}

export function getSignal(id: string | number): Promise<SignalDetail> {
  return request(`/api/signals/${id}`)
}

export async function getMonitors(): Promise<Monitor[]> {
  const response = await request<{ items: Monitor[] }>('/api/monitors')
  return response.items
}

export async function getSignalTypes(monitor?: string): Promise<SignalType[]> {
  const response = await request<{ items: SignalType[] }>(
    `/api/signal-types${queryString({ monitor })}`,
  )
  return response.items
}

export function getPushes(filters: PushFilters = {}): Promise<PageResponse<PushLog>> {
  return request(`/api/pushes${queryString(filters)}`)
}

export function getTrades(filters: TradeFilters = {}): Promise<PageResponse<PaperTrade>> {
  return request(`/api/trades${queryString(filters)}`)
}

export function getTrade(id: string | number): Promise<PaperTrade> {
  return request(`/api/trades/${id}`)
}

export function createTrade(payload: TradeCreatePayload): Promise<PaperTrade & { created: boolean }> {
  return request('/api/trades', { method: 'POST', body: JSON.stringify(payload) })
}

export function closeTrade(
  id: string | number,
  payload: { close_price: number; close_reason?: string },
): Promise<PaperTrade> {
  return request(`/api/trades/${id}/close`, { method: 'PATCH', body: JSON.stringify(payload) })
}

export function createSignalAction(
  signalId: string | number,
  payload: { decision: 'act' | 'skip' | 'watch' | 'noise'; reason?: string; paper_trade_id?: number },
): Promise<TradeAction & { created: boolean }> {
  return request(`/api/signals/${signalId}/actions`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function createSignalNote(
  signalId: string | number,
  body: string,
): Promise<SignalNote & { created: boolean }> {
  return request(`/api/signals/${signalId}/notes`, {
    method: 'POST',
    body: JSON.stringify({ body }),
  })
}

export async function getReviews(periodType: 'week' | 'month'): Promise<ReviewSummary[]> {
  const response = await request<{ items: ReviewSummary[] }>(
    `/api/reviews${queryString({ period_type: periodType })}`,
  )
  return response.items
}

export function getReview(periodType: 'week' | 'month', periodKey: string): Promise<ReviewDetail> {
  return request(`/api/reviews/${periodType}/${encodeURIComponent(periodKey)}`)
}

export function generateReview(
  periodType: 'week' | 'month',
  periodKey?: string,
): Promise<ReviewDetail> {
  return request('/api/reviews/generate', {
    method: 'POST',
    body: JSON.stringify({ period_type: periodType, period_key: periodKey || null }),
  })
}

export function reviewMarkdownUrl(periodType: 'week' | 'month', periodKey: string): string {
  return `/api/reviews/${periodType}/${encodeURIComponent(periodKey)}/markdown`
}

export function getSystemStatus(): Promise<SystemStatus> {
  return request('/api/system/status')
}

export function getStats(days = 7): Promise<StatsSummary> {
  return request(`/api/stats/summary${queryString({ days })}`)
}
