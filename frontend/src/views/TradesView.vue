<script setup lang="ts">
import { ChevronLeft, ChevronRight, Plus, RefreshCw, Search, X } from 'lucide-vue-next'
import { computed, onMounted, reactive, ref } from 'vue'

import { createTrade, getTrades } from '../api/client'
import type { PaperTrade, TradeCreatePayload } from '../api/types'
import { formatDateTime, formatMoney, formatPercent } from '../utils/format'

const pageSize = 20
const filters = reactive({ status: '' as '' | 'open' | 'closed', symbol: '', strategy: '' })
const trades = ref<PaperTrade[]>([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const error = ref('')
const formOpen = ref(false)
const saving = ref(false)
const formError = ref('')
const form = reactive({
  symbol: '', name: '', action: 'long' as 'long' | 'short', strategy: '', tag: '',
  entry_price: null as number | null, qty: null as number | null,
  entry_reason: '', stop_loss: null as number | null, take_profit: null as number | null,
  notes: '',
})

const rangeStart = computed(() => total.value ? offset.value + 1 : 0)
const rangeEnd = computed(() => Math.min(offset.value + pageSize, total.value))

async function loadTrades(nextOffset = offset.value) {
  loading.value = true
  error.value = ''
  try {
    const result = await getTrades({
      status: filters.status || undefined,
      symbol: filters.symbol || undefined,
      strategy: filters.strategy || undefined,
      limit: pageSize,
      offset: nextOffset,
    })
    trades.value = result.items
    total.value = result.total
    offset.value = result.offset
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '无法读取纸面交易'
  } finally {
    loading.value = false
  }
}

function resetForm() {
  Object.assign(form, {
    symbol: '', name: '', action: 'long', strategy: '', tag: '', entry_price: null,
    qty: null, entry_reason: '', stop_loss: null, take_profit: null, notes: '',
  })
  formError.value = ''
}

async function submitTrade() {
  if (!form.entry_price || !form.qty) {
    formError.value = '请填写有效的开仓价和数量'
    return
  }
  saving.value = true
  formError.value = ''
  const payload: TradeCreatePayload = {
    request_id: crypto.randomUUID(),
    symbol: form.symbol,
    action: form.action,
    entry_price: form.entry_price,
    qty: form.qty,
    ...(form.name ? { name: form.name } : {}),
    ...(form.strategy ? { strategy: form.strategy } : {}),
    ...(form.tag ? { tag: form.tag } : {}),
    ...(form.entry_reason ? { entry_reason: form.entry_reason } : {}),
    ...(form.stop_loss ? { stop_loss: form.stop_loss } : {}),
    ...(form.take_profit ? { take_profit: form.take_profit } : {}),
    ...(form.notes ? { notes: form.notes } : {}),
  }
  try {
    await createTrade(payload)
    formOpen.value = false
    resetForm()
    await loadTrades(0)
  } catch (cause) {
    formError.value = cause instanceof Error ? cause.message : '创建交易失败'
  } finally {
    saving.value = false
  }
}

onMounted(() => loadTrades(0))
</script>

<template>
  <section class="page page--wide">
    <header class="page-header">
      <div><p class="eyebrow">PAPER TRADES</p><h1>纸面交易</h1></div>
      <button class="primary-button" type="button" @click="formOpen = !formOpen">
        <X v-if="formOpen" :size="17" /><Plus v-else :size="17" />
        {{ formOpen ? '收起' : '新建交易' }}
      </button>
    </header>

    <form v-if="formOpen" class="write-panel trade-create-form" @submit.prevent="submitTrade">
      <div class="write-panel-header"><div><h2>新建纸面交易</h2><span>只记录研究决策，不连接券商或实盘账户</span></div></div>
      <div class="form-grid">
        <label><span>标的代码</span><input v-model.trim="form.symbol" required maxlength="64" placeholder="sh510300" /></label>
        <label><span>名称</span><input v-model.trim="form.name" maxlength="128" placeholder="沪深300ETF" /></label>
        <label><span>方向</span><select v-model="form.action"><option value="long">做多</option><option value="short">做空</option></select></label>
        <label><span>策略</span><input v-model.trim="form.strategy" maxlength="64" placeholder="manual" /></label>
        <label><span>开仓价</span><input v-model.number="form.entry_price" required type="number" min="0.000001" step="any" /></label>
        <label><span>数量</span><input v-model.number="form.qty" required type="number" min="0.000001" step="any" /></label>
        <label><span>止损价</span><input v-model.number="form.stop_loss" type="number" min="0.000001" step="any" /></label>
        <label><span>止盈价</span><input v-model.number="form.take_profit" type="number" min="0.000001" step="any" /></label>
        <label class="span-2"><span>开仓理由</span><textarea v-model.trim="form.entry_reason" maxlength="4000" rows="3" /></label>
        <label class="span-2"><span>备注</span><textarea v-model.trim="form.notes" maxlength="4000" rows="2" /></label>
      </div>
      <div v-if="formError" class="form-error">{{ formError }}</div>
      <div class="form-actions"><button class="secondary-button" type="button" @click="formOpen = false">取消</button><button class="primary-button" type="submit" :disabled="saving"><RefreshCw v-if="saving" class="spin" :size="16" />创建</button></div>
    </form>

    <form class="filter-bar trade-filter-bar" @submit.prevent="loadTrades(0)">
      <label><span>状态</span><select v-model="filters.status"><option value="">全部状态</option><option value="open">持仓中</option><option value="closed">已平仓</option></select></label>
      <label><span>标的</span><input v-model.trim="filters.symbol" placeholder="全部标的" /></label>
      <label><span>策略</span><input v-model.trim="filters.strategy" placeholder="全部策略" /></label>
      <button class="primary-button" type="submit" :disabled="loading"><Search :size="17" />查询</button>
    </form>

    <div v-if="error" class="error-banner error-banner--action"><span>{{ error }}</span><button type="button" @click="loadTrades(offset)">重试</button></div>
    <div v-if="loading && !trades.length" class="loading-state">正在读取交易</div>
    <div v-else-if="trades.length" class="table-wrap">
      <table class="signal-table trades-table">
        <thead><tr><th>状态</th><th>标的</th><th>开仓</th><th>策略</th><th>盈亏</th><th>时间</th></tr></thead>
        <tbody>
          <tr v-for="trade in trades" :key="trade.id">
            <td><span class="trade-status" :class="trade.status">{{ trade.status === 'open' ? '持仓' : '平仓' }}</span></td>
            <td><RouterLink class="signal-title" :to="`/trades/${trade.id}`">{{ trade.name || trade.symbol }}</RouterLink><span class="signal-type">{{ trade.symbol }}</span></td>
            <td>{{ trade.entry_price.toFixed(3) }} × {{ trade.qty }}</td>
            <td>{{ trade.strategy || 'manual' }}</td>
            <td><strong :class="{ negative: (trade.pnl ?? 0) < 0 }">{{ formatMoney(trade.pnl) }}</strong><span class="signal-type">{{ formatPercent(trade.pnl_pct) }}</span></td>
            <td>{{ formatDateTime(trade.entry_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else-if="!error" class="empty-state">还没有符合条件的纸面交易</div>

    <footer v-if="total" class="pagination-bar"><span>{{ rangeStart }}–{{ rangeEnd }} / {{ total }}</span><div><button class="icon-button bordered" :disabled="offset === 0 || loading" aria-label="上一页" @click="loadTrades(Math.max(0, offset - pageSize))"><ChevronLeft :size="18" /></button><button class="icon-button bordered" :disabled="offset + pageSize >= total || loading" aria-label="下一页" @click="loadTrades(offset + pageSize)"><ChevronRight :size="18" /></button></div></footer>
  </section>
</template>
