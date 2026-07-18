<script setup lang="ts">
import { ArrowUpRight } from 'lucide-vue-next'

import type { SignalEvent } from '../api/types'
import { formatDateTime } from '../utils/format'
import LevelBadge from './LevelBadge.vue'

defineProps<{ signals: SignalEvent[] }>()

</script>

<template>
  <div class="table-wrap">
    <table class="signal-table">
      <thead>
        <tr>
          <th>等级</th>
          <th>信号</th>
          <th>监控器</th>
          <th>标的</th>
          <th>时间</th>
          <th><span class="sr-only">查看</span></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="signal in signals" :key="signal.id">
          <td><LevelBadge :level="signal.level" /></td>
          <td>
            <RouterLink class="signal-title" :to="`/signals/${signal.id}`">{{ signal.title }}</RouterLink>
            <span class="signal-type">{{ signal.signal_type }}</span>
          </td>
          <td>{{ signal.monitor }}</td>
          <td>{{ signal.symbol || '全市场' }}</td>
          <td>{{ formatDateTime(signal.ts) }}</td>
          <td>
            <RouterLink class="row-link" :to="`/signals/${signal.id}`" :aria-label="`查看信号 ${signal.title}`">
              <ArrowUpRight :size="17" />
            </RouterLink>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
