export interface SignalEvent {
  id: number
  ts: string
  trade_date: string
  monitor: string
  signal_type: string
  symbol: string | null
  symbols: string[]
  direction: number | null
  level: number | null
  title: string
  status: 'detected' | 'pushed'
  metrics: Record<string, unknown>
  push_log_id: number | null
  outcome: unknown | null
}

export interface SignalDetail extends SignalEvent {
  push: PushLog | null
  actions: TradeAction[]
  notes: SignalNote[]
  trades: PaperTrade[]
}

export interface PageResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export type SignalPage = PageResponse<SignalEvent>

export interface Monitor {
  name: string
  display_name: string
  category: string
  enabled: boolean
  description: string | null
}

export interface SignalType {
  signal_type: string
  monitor: string
  display_name: string
  direction: number | null
  description: string | null
}

export interface PushSignal {
  id: number
  signal_type: string
  symbol: string | null
  level: number | null
}

export interface PushLog {
  id: number
  ts: string
  trade_date: string
  monitor: string
  scenario: string | null
  max_level: number
  title: string | null
  sent_ok: boolean | null
  error: string | null
  signal_ids: number[]
  signal_types: string[]
  signals: PushSignal[]
  message: string
  context: Record<string, unknown>
}

export interface PaperTrade {
  id: number
  request_id: string | null
  symbol: string
  name: string | null
  action: string
  strategy: string | null
  tag: string | null
  status: 'open' | 'closed'
  entry_at: string
  entry_price: number
  qty: number
  entry_reason: string | null
  close_at: string | null
  close_price: number | null
  close_reason: string | null
  stop_loss: number | null
  take_profit: number | null
  pnl: number | null
  pnl_pct: number | null
  hold_days: number | null
  signal_event_id: number | null
  notes: string | null
}

export interface TradeAction {
  id: number
  signal_event_id: number
  paper_trade_id: number | null
  decision: string
  reason: string | null
  created_at: string
}

export interface SignalNote {
  id: number
  signal_event_id: number
  body: string
  created_at: string
  updated_at: string
}

export interface ReviewSummary {
  period_type: 'week' | 'month'
  period_key: string
  trade_count: number
  win_count: number
  loss_count: number
  win_rate: number | null
  total_pnl: number | null
  avg_win: number | null
  avg_loss: number | null
  max_drawdown: number | null
  best_trade_id: number | null
  worst_trade_id: number | null
  notes: string | null
  generated_at: string
}

export interface ReviewDetail extends ReviewSummary {
  signal_frequency: Array<{ signal_type: string; count: number }>
  decision_distribution: Record<string, number>
  outcomes: {
    verified: number
    pending: number
    t1_hits: number
    t1_misses: number
    t1_hit_rate: number | null
  }
  best_trade: PaperTrade | null
  worst_trade: PaperTrade | null
}

export interface SystemStatus {
  database: { engine: string; path: string | null }
  monitors: Array<Monitor & { last_push_at: string | null; push_count: number }>
  tables: Array<{ table: string; rows: number }>
  checks: Array<{ name: string; ok: boolean; message: string }>
  healthy: boolean
}

export interface StatsSummary {
  days: number
  signals: number
  pushes: number
  trades: number
  max_signal_level: number
  open_trades: number
  pending_outcomes: number
}

export interface HealthResponse {
  status: 'ok' | 'degraded'
  database: {
    status: 'ok' | 'error'
    engine: string
  }
}

export interface SignalFilters {
  days?: number
  monitor?: string
  type?: string
  level?: number
  limit?: number
  offset?: number
}

export interface PushFilters {
  days?: number
  monitor?: string
  level?: number
  limit?: number
  offset?: number
}

export interface TradeFilters {
  status?: 'open' | 'closed'
  symbol?: string
  strategy?: string
  days?: number
  limit?: number
  offset?: number
}

export interface TradeCreatePayload {
  request_id: string
  symbol: string
  name?: string
  action: 'long' | 'short'
  strategy?: string
  tag?: string
  entry_price: number
  qty: number
  entry_reason?: string
  stop_loss?: number
  take_profit?: number
  signal_event_id?: number
  notes?: string
}
