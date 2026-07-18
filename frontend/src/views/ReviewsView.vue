<script setup lang="ts">
import { Download, RefreshCw } from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'

import { generateReview, getReview, getReviews, reviewMarkdownUrl } from '../api/client'
import type { ReviewDetail, ReviewSummary } from '../api/types'
import { formatDateTime, formatMoney, formatPercent } from '../utils/format'

const props = defineProps<{ periodType: 'week' | 'month' }>()
const reviews = ref<ReviewSummary[]>([])
const selected = ref<ReviewDetail | null>(null)
const loading = ref(false)
const generating = ref(false)
const error = ref('')
const title = computed(() => props.periodType === 'week' ? '周度复盘' : '月度复盘')

async function selectReview(item: ReviewSummary) {
  loading.value = true
  error.value = ''
  try { selected.value = await getReview(props.periodType, item.period_key) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '无法读取复盘' }
  finally { loading.value = false }
}

async function loadReviews() {
  loading.value = true
  error.value = ''
  selected.value = null
  try {
    reviews.value = await getReviews(props.periodType)
    if (reviews.value.length) selected.value = await getReview(props.periodType, reviews.value[0].period_key)
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '无法读取复盘列表' }
  finally { loading.value = false }
}

async function refreshCurrent() {
  generating.value = true
  error.value = ''
  try {
    selected.value = await generateReview(props.periodType)
    reviews.value = await getReviews(props.periodType)
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '生成复盘失败' }
  finally { generating.value = false }
}

watch(() => props.periodType, loadReviews)
onMounted(loadReviews)
</script>

<template>
  <section class="page page--wide">
    <header class="page-header">
      <div><p class="eyebrow">RESEARCH REVIEWS</p><h1>{{ title }}</h1></div>
      <button class="primary-button" type="button" :disabled="generating" @click="refreshCurrent"><RefreshCw :class="{ spin: generating }" :size="17" />生成当前{{ props.periodType === 'week' ? '周' : '月' }}</button>
    </header>
    <nav class="view-tabs"><RouterLink to="/reviews/weekly">周度</RouterLink><RouterLink to="/reviews/monthly">月度</RouterLink></nav>
    <div v-if="error" class="error-banner error-banner--action"><span>{{ error }}</span><button type="button" @click="loadReviews">重试</button></div>
    <div v-if="loading && !selected" class="loading-state">正在读取复盘</div>
    <div v-else class="review-layout">
      <aside class="review-index">
        <button v-for="item in reviews" :key="item.period_key" type="button" :class="{ active: selected?.period_key === item.period_key }" @click="selectReview(item)"><strong>{{ item.period_key }}</strong><span>{{ item.trade_count }} 笔 · {{ formatMoney(item.total_pnl) }}</span></button>
        <div v-if="!reviews.length" class="empty-state compact">尚未生成{{ title }}</div>
      </aside>
      <article v-if="selected" class="review-report">
        <header class="review-report-header"><div><span>{{ selected.period_key }}</span><h2>{{ title }}</h2></div><a class="secondary-button" :href="reviewMarkdownUrl(selected.period_type, selected.period_key)"><Download :size="16" />Markdown</a></header>
        <div class="review-metrics"><div><span>交易笔数</span><strong>{{ selected.trade_count }}</strong></div><div><span>交易胜率</span><strong>{{ formatPercent(selected.win_rate) }}</strong></div><div><span>总盈亏</span><strong :class="{ negative: (selected.total_pnl ?? 0) < 0 }">{{ formatMoney(selected.total_pnl) }}</strong></div><div><span>T+1 命中率</span><strong>{{ formatPercent(selected.outcomes.t1_hit_rate) }}</strong></div></div>
        <section class="review-section"><h3>信号频率</h3><div v-if="selected.signal_frequency.length" class="frequency-list"><div v-for="item in selected.signal_frequency" :key="item.signal_type"><span>{{ item.signal_type }}</span><strong>{{ item.count }}</strong></div></div><p v-else class="muted-copy">本期没有信号记录</p></section>
        <section class="review-section"><h3>判断分布</h3><div v-if="Object.keys(selected.decision_distribution).length" class="decision-summary"><div v-for="(count, decision) in selected.decision_distribution" :key="decision"><span>{{ decision }}</span><strong>{{ count }}</strong></div></div><p v-else class="muted-copy">本期没有人工判断</p></section>
        <section class="review-section"><h3>信号验证</h3><div class="review-inline-stats"><span>已验证 <strong>{{ selected.outcomes.verified }}</strong></span><span>待验证 <strong>{{ selected.outcomes.pending }}</strong></span><span>命中 / 未中 <strong>{{ selected.outcomes.t1_hits }} / {{ selected.outcomes.t1_misses }}</strong></span></div></section>
        <section v-if="selected.best_trade || selected.worst_trade" class="review-section review-extremes"><div v-if="selected.best_trade"><span>最佳交易</span><RouterLink :to="`/trades/${selected.best_trade.id}`">{{ selected.best_trade.name || selected.best_trade.symbol }}</RouterLink><strong>{{ formatMoney(selected.best_trade.pnl) }}</strong></div><div v-if="selected.worst_trade"><span>最差交易</span><RouterLink :to="`/trades/${selected.worst_trade.id}`">{{ selected.worst_trade.name || selected.worst_trade.symbol }}</RouterLink><strong class="negative">{{ formatMoney(selected.worst_trade.pnl) }}</strong></div></section>
        <footer class="report-time">生成于 {{ formatDateTime(selected.generated_at) }}</footer>
      </article>
      <div v-else-if="!loading" class="review-report empty-state">生成当前{{ props.periodType === 'week' ? '周' : '月' }}复盘后，报告会显示在这里</div>
    </div>
  </section>
</template>
