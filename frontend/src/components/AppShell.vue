<script setup lang="ts">
import { Activity, BookOpen, Menu, Radio, Settings, WalletCards, X } from 'lucide-vue-next'
import { ref } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const menuOpen = ref(false)
</script>

<template>
  <div class="app-shell">
    <header class="mobile-header">
      <RouterLink class="mobile-brand" to="/">DMM</RouterLink>
      <button class="icon-button" type="button" aria-label="切换导航" @click="menuOpen = !menuOpen">
        <X v-if="menuOpen" :size="20" />
        <Menu v-else :size="20" />
      </button>
    </header>

    <aside class="sidebar" :class="{ 'sidebar--open': menuOpen }">
      <div class="brand-block">
        <span class="brand-mark">DMM</span>
        <span class="brand-name">Market Monitor</span>
      </div>
      <nav class="nav-list" aria-label="主导航">
        <RouterLink :class="{ active: route.name === 'today' }" to="/" @click="menuOpen = false">
          <Activity :size="18" />
          今日
        </RouterLink>
        <RouterLink :class="{ active: String(route.name).startsWith('signal') }" to="/signals" @click="menuOpen = false">
          <Radio :size="18" />
          信号
        </RouterLink>
        <RouterLink :class="{ active: String(route.name).startsWith('trade') }" to="/trades" @click="menuOpen = false">
          <WalletCards :size="18" />
          纸面交易
        </RouterLink>
        <RouterLink :class="{ active: String(route.name).startsWith('reviews') }" to="/reviews/weekly" @click="menuOpen = false">
          <BookOpen :size="18" />
          复盘
        </RouterLink>
        <RouterLink :class="{ active: route.name === 'system' }" to="/system" @click="menuOpen = false">
          <Settings :size="18" />
          系统
        </RouterLink>
      </nav>
      <div class="sidebar-foot">
        <span class="status-dot" />
        本地研究库
      </div>
    </aside>

    <main class="workspace">
      <slot />
    </main>
  </div>
</template>
