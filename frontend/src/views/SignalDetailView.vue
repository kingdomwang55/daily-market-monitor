<script setup lang="ts">
import { ArrowLeft, BellRing, MessageSquarePlus, Plus, Radio, RefreshCw, WalletCards } from 'lucide-vue-next'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import { createSignalAction, createSignalNote, createTrade, getSignal, getTrades } from '../api/client'
import type { PaperTrade, SignalDetail, TradeCreatePayload } from '../api/types'
import LevelBadge from '../components/LevelBadge.vue'
import { formatDateTime, formatMoney, formatPercent } from '../utils/format'

const route = useRoute()
const signal = ref<SignalDetail | null>(null)
const loading = ref(false)
const error = ref('')
const writeError = ref('')
const writeNotice = ref('')
const saving = ref(false)
const availableTrades = ref<PaperTrade[]>([])
const tradeFormOpen = ref(false)
const actionForm = reactive({ decision: 'watch' as 'act' | 'skip' | 'watch' | 'noise', reason: '', paper_trade_id: null as number | null })
const noteBody = ref('')
const tradeForm = reactive({ symbol: '', name: '', strategy: '', entry_price: null as number | null, qty: null as number | null, entry_reason: '', stop_loss: null as number | null, take_profit: null as number | null })

const metricEntries = computed(() => Object.entries(signal.value?.metrics ?? {}))

function metricValue(value: unknown): string {
  if (typeof value === 'string') return value
  if (value === null || value === undefined) return '-'
  return JSON.stringify(value, null, 2)
}

async function loadSignal() {
  loading.value = true
  error.value = ''
  try {
    const [signalResult, tradeResult] = await Promise.all([
      getSignal(String(route.params.id)),
      getTrades({ limit: 200 }),
    ])
    signal.value = signalResult
    availableTrades.value = tradeResult.items
    if (!tradeForm.symbol) tradeForm.symbol = signalResult.symbol || ''
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '无法读取信号详情'
  } finally {
    loading.value = false
  }
}

async function saveAction() {
  if (!signal.value) return
  saving.value = true
  writeError.value = ''
  writeNotice.value = ''
  try {
    const result = await createSignalAction(signal.value.id, {
      decision: actionForm.decision,
      ...(actionForm.reason ? { reason: actionForm.reason } : {}),
      ...(actionForm.paper_trade_id ? { paper_trade_id: actionForm.paper_trade_id } : {}),
    })
    writeNotice.value = result.created ? '判断已记录' : '相同判断已存在'
    actionForm.reason = ''
    actionForm.paper_trade_id = null
    await loadSignal()
  } catch (cause) { writeError.value = cause instanceof Error ? cause.message : '记录判断失败' }
  finally { saving.value = false }
}

async function saveNote() {
  if (!signal.value || !noteBody.value.trim()) return
  saving.value = true
  writeError.value = ''
  writeNotice.value = ''
  try {
    const result = await createSignalNote(signal.value.id, noteBody.value)
    writeNotice.value = result.created ? '批注已添加' : '相同批注已存在'
    noteBody.value = ''
    await loadSignal()
  } catch (cause) { writeError.value = cause instanceof Error ? cause.message : '添加批注失败' }
  finally { saving.value = false }
}

async function createLinkedTrade() {
  if (!signal.value || !tradeForm.entry_price || !tradeForm.qty) return
  saving.value = true
  writeError.value = ''
  writeNotice.value = ''
  const payload: TradeCreatePayload = {
    request_id: crypto.randomUUID(),
    symbol: tradeForm.symbol,
    action: 'long',
    entry_price: tradeForm.entry_price,
    qty: tradeForm.qty,
    signal_event_id: signal.value.id,
    ...(tradeForm.name ? { name: tradeForm.name } : {}),
    ...(tradeForm.strategy ? { strategy: tradeForm.strategy } : {}),
    ...(tradeForm.entry_reason ? { entry_reason: tradeForm.entry_reason } : {}),
    ...(tradeForm.stop_loss ? { stop_loss: tradeForm.stop_loss } : {}),
    ...(tradeForm.take_profit ? { take_profit: tradeForm.take_profit } : {}),
  }
  try {
    await createTrade(payload)
    writeNotice.value = '纸面交易已创建并关联'
    tradeFormOpen.value = false
    Object.assign(tradeForm, { name: '', strategy: '', entry_price: null, qty: null, entry_reason: '', stop_loss: null, take_profit: null })
    await loadSignal()
  } catch (cause) { writeError.value = cause instanceof Error ? cause.message : '创建交易失败' }
  finally { saving.value = false }
}

onMounted(loadSignal)
</script>

<template>
  <section class="page detail-page">
    <RouterLink class="back-link" to="/signals"><ArrowLeft :size="16" /> 返回信号库</RouterLink>
    <div v-if="error" class="error-banner error-banner--action">
      <span>{{ error }}</span>
      <button type="button" @click="loadSignal">重试</button>
    </div>
    <div v-if="loading && !signal" class="loading-state">正在读取信号</div>

    <template v-else-if="signal">
      <header class="detail-header">
        <div class="detail-kicker"><Radio :size="17" /> {{ signal.monitor }}</div>
        <h1>{{ signal.title }}</h1>
        <div class="detail-meta">
          <LevelBadge :level="signal.level" />
          <span>{{ signal.signal_type }}</span>
          <span>{{ formatDateTime(signal.ts, { dateStyle: 'medium', timeStyle: 'short' }) }}</span>
          <span>{{ signal.status === 'pushed' ? '已推送' : '已识别' }}</span>
        </div>
      </header>

      <section class="detail-section">
        <h2>关联标的</h2>
        <div class="symbol-list">
          <span v-for="symbol in signal.symbols" :key="symbol">{{ symbol }}</span>
          <span v-if="!signal.symbols.length">全市场</span>
        </div>
      </section>

      <section class="detail-section research-actions">
        <div class="section-heading detail-section-heading"><div><MessageSquarePlus :size="18" /><h2>研究动作</h2></div><span>不会修改原始信号</span></div>
        <div v-if="writeError" class="form-error">{{ writeError }}</div>
        <div v-if="writeNotice" class="success-banner">{{ writeNotice }}</div>
        <form class="action-compose" @submit.prevent="saveAction">
          <div class="segmented-control" aria-label="判断类型"><button v-for="decision in (['act', 'skip', 'watch', 'noise'] as const)" :key="decision" type="button" :class="{ active: actionForm.decision === decision }" @click="actionForm.decision = decision">{{ decision }}</button></div>
          <input v-model.trim="actionForm.reason" maxlength="2000" placeholder="判断理由（可选）" />
          <select v-model.number="actionForm.paper_trade_id"><option :value="null">不关联已有交易</option><option v-for="trade in availableTrades" :key="trade.id" :value="trade.id">#{{ trade.id }} {{ trade.name || trade.symbol }} · {{ trade.status }}</option></select>
          <button class="primary-button" type="submit" :disabled="saving"><RefreshCw v-if="saving" class="spin" :size="16" />记录判断</button>
        </form>
        <form class="note-compose" @submit.prevent="saveNote"><textarea v-model.trim="noteBody" required maxlength="4000" rows="3" placeholder="添加研究批注" /><button class="secondary-button" type="submit" :disabled="saving">添加批注</button></form>
        <button class="text-command" type="button" @click="tradeFormOpen = !tradeFormOpen"><Plus :size="16" />{{ tradeFormOpen ? '收起交易表单' : '从该信号创建纸面交易' }}</button>
        <form v-if="tradeFormOpen" class="linked-trade-form form-grid" @submit.prevent="createLinkedTrade">
          <label><span>标的</span><input v-model.trim="tradeForm.symbol" required maxlength="64" /></label><label><span>名称</span><input v-model.trim="tradeForm.name" maxlength="128" /></label><label><span>开仓价</span><input v-model.number="tradeForm.entry_price" required type="number" min="0.000001" step="any" /></label><label><span>数量</span><input v-model.number="tradeForm.qty" required type="number" min="0.000001" step="any" /></label><label><span>策略</span><input v-model.trim="tradeForm.strategy" maxlength="64" /></label><label><span>止损价</span><input v-model.number="tradeForm.stop_loss" type="number" min="0.000001" step="any" /></label><label><span>止盈价</span><input v-model.number="tradeForm.take_profit" type="number" min="0.000001" step="any" /></label><label class="span-2"><span>开仓理由</span><textarea v-model.trim="tradeForm.entry_reason" maxlength="4000" rows="2" /></label><div class="form-actions span-2"><button class="primary-button" type="submit" :disabled="saving">创建并关联</button></div>
        </form>
      </section>

      <section class="detail-section">
        <h2>信号指标</h2>
        <dl v-if="metricEntries.length" class="metric-list">
          <div v-for="([key, value]) in metricEntries" :key="key">
            <dt>{{ key }}</dt>
            <dd><pre>{{ metricValue(value) }}</pre></dd>
          </div>
        </dl>
        <p v-else class="muted-copy">没有附加指标</p>
      </section>

      <section class="detail-section">
        <div class="section-heading detail-section-heading">
          <div><BellRing :size="18" /><h2>关联推送</h2></div>
          <span v-if="signal.push">#{{ signal.push.id }}</span>
        </div>
        <article v-if="signal.push" class="push-detail">
          <header>
            <LevelBadge :level="signal.push.max_level" />
            <div>
              <strong>{{ signal.push.title || signal.push.monitor }}</strong>
              <span>{{ signal.push.monitor }} · {{ formatDateTime(signal.push.ts) }}</span>
            </div>
          </header>
          <p>{{ signal.push.message }}</p>
          <span v-if="signal.push.error" class="push-error">{{ signal.push.error }}</span>
        </article>
        <p v-else class="muted-copy">该信号未关联推送记录</p>
      </section>

      <section class="detail-section">
        <div class="section-heading detail-section-heading">
          <div><WalletCards :size="18" /><h2>关联交易与判断</h2></div>
          <span>{{ signal.trades.length }} 笔交易 · {{ signal.actions.length }} 条判断</span>
        </div>
        <div v-if="signal.actions.length" class="action-list">
          <article v-for="action in signal.actions" :key="action.id">
            <span class="decision-label">{{ action.decision }}</span>
            <p>{{ action.reason || '未记录理由' }}</p>
            <time>{{ formatDateTime(action.created_at) }}</time>
          </article>
        </div>
        <div v-if="signal.notes.length" class="note-history">
          <article v-for="note in signal.notes" :key="note.id"><p>{{ note.body }}</p><time>{{ formatDateTime(note.created_at) }}</time></article>
        </div>
        <div v-if="signal.trades.length" class="linked-trades">
          <article v-for="trade in signal.trades" :key="trade.id" class="linked-trade-row">
            <span class="trade-status" :class="trade.status">{{ trade.status === 'open' ? '持仓' : '平仓' }}</span>
            <div>
              <strong>{{ trade.name || trade.symbol }}</strong>
              <span>{{ trade.entry_price.toFixed(3) }} × {{ trade.qty }} · {{ trade.strategy || 'manual' }}</span>
            </div>
            <div class="linked-trade-result">
              <strong :class="{ negative: (trade.pnl ?? 0) < 0 }">{{ formatMoney(trade.pnl) }}</strong>
              <span>{{ formatPercent(trade.pnl_pct) }}</span>
            </div>
          </article>
        </div>
        <p v-if="!signal.actions.length && !signal.notes.length && !signal.trades.length" class="muted-copy">该信号还没有关联判断、批注或纸面交易</p>
      </section>
    </template>
  </section>
</template>
