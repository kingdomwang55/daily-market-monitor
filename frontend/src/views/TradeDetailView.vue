<script setup lang="ts">
import { ArrowLeft, RefreshCw } from 'lucide-vue-next'
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import { closeTrade, getTrade } from '../api/client'
import type { PaperTrade } from '../api/types'
import { formatDateTime, formatMoney, formatPercent } from '../utils/format'

const route = useRoute()
const trade = ref<PaperTrade | null>(null)
const loading = ref(false)
const error = ref('')
const closing = ref(false)
const closeForm = reactive({ close_price: null as number | null, close_reason: '' })

async function loadTrade() {
  loading.value = true
  error.value = ''
  try { trade.value = await getTrade(String(route.params.id)) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '无法读取交易详情' }
  finally { loading.value = false }
}

async function submitClose() {
  if (!trade.value || !closeForm.close_price) return
  closing.value = true
  error.value = ''
  try {
    trade.value = await closeTrade(trade.value.id, {
      close_price: closeForm.close_price,
      ...(closeForm.close_reason ? { close_reason: closeForm.close_reason } : {}),
    })
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '平仓失败' }
  finally { closing.value = false }
}

onMounted(loadTrade)
</script>

<template>
  <section class="page detail-page">
    <RouterLink class="back-link" to="/trades"><ArrowLeft :size="16" /> 返回纸面交易</RouterLink>
    <div v-if="error" class="error-banner error-banner--action"><span>{{ error }}</span><button type="button" @click="loadTrade">重试</button></div>
    <div v-if="loading && !trade" class="loading-state">正在读取交易</div>
    <template v-else-if="trade">
      <header class="detail-header">
        <div class="detail-kicker">PAPER TRADE #{{ trade.id }}</div>
        <h1>{{ trade.name || trade.symbol }}</h1>
        <div class="detail-meta"><span class="trade-status" :class="trade.status">{{ trade.status === 'open' ? '持仓' : '平仓' }}</span><span>{{ trade.symbol }}</span><span>{{ trade.strategy || 'manual' }}</span><span>{{ formatDateTime(trade.entry_at, { dateStyle: 'medium', timeStyle: 'short' }) }}</span></div>
      </header>
      <section class="detail-section trade-facts">
        <dl><div><dt>开仓价</dt><dd>{{ trade.entry_price }}</dd></div><div><dt>数量</dt><dd>{{ trade.qty }}</dd></div><div><dt>止损价</dt><dd>{{ trade.stop_loss ?? '-' }}</dd></div><div><dt>止盈价</dt><dd>{{ trade.take_profit ?? '-' }}</dd></div><div><dt>持仓天数</dt><dd>{{ trade.hold_days ?? '-' }}</dd></div><div><dt>盈亏</dt><dd :class="{ negative: (trade.pnl ?? 0) < 0 }">{{ formatMoney(trade.pnl) }} · {{ formatPercent(trade.pnl_pct) }}</dd></div></dl>
      </section>
      <section class="detail-section"><h2>交易理由</h2><p class="detail-copy">{{ trade.entry_reason || '未记录开仓理由' }}</p><p v-if="trade.notes" class="detail-note">{{ trade.notes }}</p></section>
      <section v-if="trade.signal_event_id" class="detail-section"><h2>关联信号</h2><RouterLink class="inline-link" :to="`/signals/${trade.signal_event_id}`">Signal #{{ trade.signal_event_id }}</RouterLink></section>
      <section v-if="trade.status === 'closed'" class="detail-section"><h2>平仓结果</h2><p class="detail-copy">{{ trade.close_reason || '未记录平仓理由' }}</p><p class="muted-copy">{{ formatDateTime(trade.close_at) }} · {{ trade.close_price }}</p></section>
      <form v-else class="detail-section close-form" @submit.prevent="submitClose"><h2>记录平仓</h2><div class="form-grid"><label><span>平仓价</span><input v-model.number="closeForm.close_price" required type="number" min="0.000001" step="any" /></label><label class="span-2"><span>平仓理由</span><textarea v-model.trim="closeForm.close_reason" maxlength="4000" rows="3" /></label></div><div class="form-actions"><button class="danger-button" type="submit" :disabled="closing"><RefreshCw v-if="closing" class="spin" :size="16" />确认平仓</button></div></form>
    </template>
  </section>
</template>
