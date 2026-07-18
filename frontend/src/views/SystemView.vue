<script setup lang="ts">
import { CheckCircle2, CircleAlert, Database, KeyRound, RefreshCw, Trash2 } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'

import { getSystemStatus } from '../api/client'
import type { SystemStatus } from '../api/types'
import { formatDateTime } from '../utils/format'

const system = ref<SystemStatus | null>(null)
const loading = ref(false)
const error = ref('')
const writeToken = ref(sessionStorage.getItem('market-write-token') || '')
const tokenSaved = ref(false)

function saveWriteToken() {
  const value = writeToken.value.trim()
  if (value) sessionStorage.setItem('market-write-token', value)
  else sessionStorage.removeItem('market-write-token')
  tokenSaved.value = true
}

function clearWriteToken() {
  writeToken.value = ''
  sessionStorage.removeItem('market-write-token')
  tokenSaved.value = false
}

async function loadSystem() {
  loading.value = true
  error.value = ''
  try { system.value = await getSystemStatus() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '无法读取系统状态' }
  finally { loading.value = false }
}
onMounted(loadSystem)
</script>

<template>
  <section class="page page--wide">
    <header class="page-header"><div><p class="eyebrow">SYSTEM</p><h1>系统状态</h1></div><button class="icon-button bordered" type="button" :disabled="loading" aria-label="刷新系统状态" @click="loadSystem"><RefreshCw :class="{ spin: loading }" :size="18" /></button></header>
    <div v-if="error" class="error-banner error-banner--action"><span>{{ error }}</span><button type="button" @click="loadSystem">重试</button></div>
    <div v-if="loading && !system" class="loading-state">正在检查系统</div>
    <template v-else-if="system">
      <div class="system-summary"><div :class="{ healthy: system.healthy }"><CheckCircle2 v-if="system.healthy" :size="22" /><CircleAlert v-else :size="22" /><span>运行检查</span><strong>{{ system.healthy ? '正常' : '需要关注' }}</strong></div><div><Database :size="22" /><span>数据库</span><strong>{{ system.database.engine }}</strong><small>{{ system.database.path || '外部数据库' }}</small></div><div><span>监控器</span><strong>{{ system.monitors.filter(item => item.enabled).length }} / {{ system.monitors.length }}</strong><small>启用 / 总数</small></div><div><span>数据表</span><strong>{{ system.tables.reduce((sum, item) => sum + item.rows, 0) }}</strong><small>记录总数</small></div></div>
      <section class="system-section"><h2>写入令牌</h2><form class="token-form" @submit.prevent="saveWriteToken"><label><span class="sr-only">写入令牌</span><KeyRound :size="17" /><input v-model="writeToken" type="password" autocomplete="off" placeholder="未配置时留空" /></label><button class="primary-button" type="submit">保存到当前会话</button><button class="icon-button bordered" type="button" aria-label="清除写入令牌" @click="clearWriteToken"><Trash2 :size="17" /></button><span v-if="tokenSaved" class="token-saved">已保存</span></form></section>
      <section class="system-section"><h2>运行检查</h2><div class="check-list"><article v-for="check in system.checks" :key="check.name"><CheckCircle2 v-if="check.ok" :size="18" /><CircleAlert v-else :size="18" /><strong>{{ check.name }}</strong><span>{{ check.message }}</span></article></div></section>
      <section class="system-section"><h2>监控器</h2><div class="table-wrap"><table class="signal-table system-table"><thead><tr><th>状态</th><th>监控器</th><th>类别</th><th>推送次数</th><th>最近推送</th></tr></thead><tbody><tr v-for="monitor in system.monitors" :key="monitor.name"><td><span class="enabled-dot" :class="{ off: !monitor.enabled }" />{{ monitor.enabled ? '启用' : '停用' }}</td><td><strong>{{ monitor.display_name }}</strong><span class="signal-type">{{ monitor.name }}</span></td><td>{{ monitor.category }}</td><td>{{ monitor.push_count }}</td><td>{{ formatDateTime(monitor.last_push_at) }}</td></tr></tbody></table></div></section>
      <section class="system-section"><h2>数据表</h2><div class="table-count-grid"><div v-for="table in system.tables" :key="table.table"><span>{{ table.table }}</span><strong>{{ table.rows }}</strong></div></div></section>
    </template>
  </section>
</template>
