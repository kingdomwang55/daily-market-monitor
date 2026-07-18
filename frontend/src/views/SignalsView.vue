<script setup lang="ts">
import { ChevronLeft, ChevronRight, RefreshCw, Search } from 'lucide-vue-next'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { getMonitors, getSignals, getSignalTypes } from '../api/client'
import type { Monitor, SignalEvent, SignalType } from '../api/types'
import SignalTable from '../components/SignalTable.vue'

const pageSize = 20
const filters = reactive({ days: 7, monitor: '', type: '', level: 0 })
const monitors = ref<Monitor[]>([])
const signalTypes = ref<SignalType[]>([])
const signals = ref<SignalEvent[]>([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const error = ref('')

const visibleSignalTypes = computed(() =>
  filters.monitor
    ? signalTypes.value.filter((item) => item.monitor === filters.monitor)
    : signalTypes.value,
)
const rangeStart = computed(() => total.value === 0 ? 0 : offset.value + 1)
const rangeEnd = computed(() => Math.min(offset.value + pageSize, total.value))
const canGoBack = computed(() => offset.value > 0)
const canGoNext = computed(() => offset.value + pageSize < total.value)

watch(() => filters.monitor, () => {
  if (filters.type && !visibleSignalTypes.value.some((item) => item.signal_type === filters.type)) {
    filters.type = ''
  }
})

async function loadSignals(nextOffset = offset.value) {
  loading.value = true
  error.value = ''
  try {
    const result = await getSignals({
      ...filters,
      limit: pageSize,
      offset: nextOffset,
    })
    signals.value = result.items
    total.value = result.total
    offset.value = result.offset
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '无法读取信号'
  } finally {
    loading.value = false
  }
}

async function applyFilters() {
  await loadSignals(0)
}

onMounted(async () => {
  loading.value = true
  try {
    const [monitorResult, typeResult] = await Promise.all([getMonitors(), getSignalTypes()])
    monitors.value = monitorResult
    signalTypes.value = typeResult
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '无法读取筛选项'
  } finally {
    loading.value = false
  }
  await loadSignals(0)
})
</script>

<template>
  <section class="page page--wide">
    <header class="page-header">
      <div>
        <p class="eyebrow">SIGNAL LIBRARY</p>
        <h1>信号研究库</h1>
      </div>
      <span class="result-count">{{ total }} 条记录</span>
    </header>

    <form class="filter-bar filter-bar--signals" @submit.prevent="applyFilters">
      <label>
        <span>时间范围</span>
        <select v-model.number="filters.days">
          <option :value="1">今天</option>
          <option :value="7">最近 7 天</option>
          <option :value="30">最近 30 天</option>
          <option :value="90">最近 90 天</option>
        </select>
      </label>
      <label>
        <span>监控器</span>
        <select v-model="filters.monitor">
          <option value="">全部监控器</option>
          <option v-for="monitor in monitors" :key="monitor.name" :value="monitor.name">
            {{ monitor.display_name }}
          </option>
        </select>
      </label>
      <label>
        <span>信号类型</span>
        <select v-model="filters.type">
          <option value="">全部类型</option>
          <option v-for="item in visibleSignalTypes" :key="item.signal_type" :value="item.signal_type">
            {{ item.display_name }}
          </option>
        </select>
      </label>
      <label>
        <span>最低等级</span>
        <select v-model.number="filters.level">
          <option :value="0">全部等级</option>
          <option :value="1">L1 及以上</option>
          <option :value="2">L2 及以上</option>
          <option :value="3">仅 L3</option>
        </select>
      </label>
      <button class="primary-button" type="submit" :disabled="loading">
        <RefreshCw v-if="loading" class="spin" :size="17" />
        <Search v-else :size="17" />
        查询
      </button>
    </form>

    <div v-if="error" class="error-banner error-banner--action">
      <span>{{ error }}</span>
      <button type="button" @click="loadSignals(offset)">重试</button>
    </div>
    <div v-if="loading && !signals.length" class="loading-state">正在读取信号</div>
    <SignalTable v-else-if="signals.length" :signals="signals" />
    <div v-else-if="!error" class="empty-state">当前筛选条件下没有信号</div>

    <footer v-if="total > 0" class="pagination-bar">
      <span>{{ rangeStart }}–{{ rangeEnd }} / {{ total }}</span>
      <div>
        <button class="icon-button bordered" type="button" :disabled="!canGoBack || loading" aria-label="上一页" @click="loadSignals(offset - pageSize)">
          <ChevronLeft :size="18" />
        </button>
        <button class="icon-button bordered" type="button" :disabled="!canGoNext || loading" aria-label="下一页" @click="loadSignals(offset + pageSize)">
          <ChevronRight :size="18" />
        </button>
      </div>
    </footer>
  </section>
</template>
