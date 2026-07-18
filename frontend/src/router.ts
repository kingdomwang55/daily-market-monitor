import { createRouter, createWebHistory } from 'vue-router'

import SignalDetailView from './views/SignalDetailView.vue'
import SignalsView from './views/SignalsView.vue'
import SystemView from './views/SystemView.vue'
import TodayView from './views/TodayView.vue'
import TradeDetailView from './views/TradeDetailView.vue'
import TradesView from './views/TradesView.vue'
import ReviewsView from './views/ReviewsView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'today', component: TodayView },
    { path: '/signals', name: 'signals', component: SignalsView },
    { path: '/signals/:id', name: 'signal-detail', component: SignalDetailView },
    { path: '/trades', name: 'trades', component: TradesView },
    { path: '/trades/:id', name: 'trade-detail', component: TradeDetailView },
    {
      path: '/reviews/weekly',
      name: 'reviews-weekly',
      component: ReviewsView,
      props: { periodType: 'week' },
    },
    {
      path: '/reviews/monthly',
      name: 'reviews-monthly',
      component: ReviewsView,
      props: { periodType: 'month' },
    },
    { path: '/reviews', redirect: '/reviews/weekly' },
    { path: '/system', name: 'system', component: SystemView },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
