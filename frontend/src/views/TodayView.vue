<script setup lang="ts">
import { ArrowRight, BellRing, Database, Radio, WalletCards } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'

import { getHealth, getPushes, getSignals, getStats, getTrades } from '../api/client'
import type { HealthResponse, PaperTrade, PushLog, SignalEvent, StatsSummary } from '../api/types'
import LevelBadge from '../components/LevelBadge.vue'
import { formatDateTime, formatMoney } from '../utils/format'

const health = ref<HealthResponse | null>(null)
const summary = ref<StatsSummary | null>(null)
const signals = ref<SignalEvent[]>([])
const pushes = ref<PushLog[]>([])
const trades = ref<PaperTrade[]>([])
const loading = ref(false)
const error = ref('')

async function loadToday() {
  loading.value = true
  error.value = ''
  try {
    const [healthResult, summaryResult, signalResult, pushResult, tradeResult] = await Promise.all([
      getHealth(),
      getStats(1),
      getSignals({ days: 1, limit: 6 }),
      getPushes({ days: 1, limit: 5 }),
      getTrades({ limit: 5 }),
    ])
    health.value = healthResult
    summary.value = summaryResult
    signals.value = signalResult.items
    pushes.value = pushResult.items
    trades.value = tradeResult.items
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '无法读取今日数据'
  } finally {
    loading.value = false
  }
}

onMounted(loadToday)
</script>

<template>
  <section class="page page--wide">
    <header class="page-header">
      <div>
        <p class="eyebrow">TODAY</p>
        <h1>今日市场脉冲</h1>
      </div>
      <span class="date-label">{{ new Intl.DateTimeFormat('zh-CN', { dateStyle: 'long' }).format(new Date()) }}</span>
    </header>

    <div v-if="error" class="error-banner error-banner--action">
      <span>{{ error }}</span>
      <button type="button" @click="loadToday">重试</button>
    </div>
    <div v-if="loading && !summary" class="loading-state">正在汇总今日研究记录</div>

    <template v-else>
      <div class="metric-strip metric-strip--four">
        <div class="metric-cell">
          <span>今日信号</span>
          <strong>{{ summary?.signals ?? 0 }}</strong>
        </div>
        <div class="metric-cell">
          <span>最高等级</span>
          <LevelBadge :level="summary?.max_signal_level ?? 0" />
        </div>
        <div class="metric-cell">
          <span>待验证</span>
          <strong>{{ summary?.pending_outcomes ?? 0 }}</strong>
        </div>
        <div class="metric-cell">
          <span>数据连接</span>
          <strong class="health-value" :class="{ healthy: health?.status === 'ok' }">
            <Database :size="18" />
            {{ health?.status === 'ok' ? '正常' : '异常' }}
          </strong>
        </div>
      </div>

      <div class="research-grid">
        <section class="research-column">
          <div class="section-heading">
            <div><Radio :size="19" /><h2>最近信号</h2></div>
            <RouterLink to="/signals">查看全部 <ArrowRight :size="16" /></RouterLink>
          </div>
          <div v-if="signals.length" class="pulse-list">
            <RouterLink v-for="signal in signals" :key="signal.id" :to="`/signals/${signal.id}`" class="pulse-row">
              <LevelBadge :level="signal.level" />
              <div>
                <strong>{{ signal.title }}</strong>
                <span>{{ signal.monitor }} · {{ signal.symbol || '全市场' }}</span>
              </div>
              <time>{{ formatDateTime(signal.ts, { hour: '2-digit', minute: '2-digit', hour12: false }) }}</time>
            </RouterLink>
          </div>
          <div v-else class="empty-state compact">今天还没有记录到信号</div>
        </section>

        <section class="research-column">
          <div class="section-heading">
            <div><BellRing :size="18" /><h2>最近推送</h2></div>
            <span>{{ summary?.pushes ?? 0 }} 条</span>
          </div>
          <div v-if="pushes.length" class="timeline-list">
            <article v-for="push in pushes" :key="push.id" class="timeline-row">
              <LevelBadge :level="push.max_level" />
              <div>
                <strong>{{ push.title || push.monitor }}</strong>
                <span>{{ push.monitor }} · {{ formatDateTime(push.ts) }}</span>
              </div>
            </article>
          </div>
          <div v-else class="empty-state compact">今天还没有推送记录</div>
        </section>
      </div>

      <section class="trade-band">
        <div class="section-heading">
          <div><WalletCards :size="19" /><h2>最近纸面交易</h2></div>
          <span>{{ summary?.open_trades ?? 0 }} 笔持仓中</span>
        </div>
        <div v-if="trades.length" class="trade-list">
          <article v-for="trade in trades" :key="trade.id" class="trade-row">
            <span class="trade-status" :class="trade.status">{{ trade.status === 'open' ? '持仓' : '平仓' }}</span>
            <div>
              <strong>{{ trade.name || trade.symbol }}</strong>
              <span>{{ trade.strategy || 'manual' }} · {{ formatDateTime(trade.entry_at) }}</span>
            </div>
            <span class="trade-price">{{ trade.entry_price.toFixed(3) }} × {{ trade.qty }}</span>
            <strong class="trade-pnl" :class="{ negative: (trade.pnl ?? 0) < 0 }">{{ formatMoney(trade.pnl) }}</strong>
          </article>
        </div>
        <div v-else class="empty-state compact">还没有纸面交易记录</div>
      </section>
    </template>
  </section>
</template>
