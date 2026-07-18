<script setup lang="ts">
defineProps<{ level: number | null }>()
</script>

<template>
  <span class="level-badge" :class="`level-${level ?? 0}`">L{{ level ?? '-' }}</span>
</template>
