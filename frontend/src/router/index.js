import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('../components/LayoutShell.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../views/Dashboard.vue'),
        meta: { title: '工作台' },
      },
      {
        path: 'import',
        name: 'Import',
        component: () => import('../views/ImportView.vue'),
        meta: { title: '文案导入' },
      },
      {
        path: 'workshop',
        name: 'Workshop',
        component: () => import('../views/GEOWorkshop.vue'),
        meta: { title: 'GEO优化工坊' },
      },
      {
        path: 'evaluation',
        name: 'Evaluation',
        component: () => import('../views/EvaluationCenter.vue'),
        meta: { title: 'AI评测中心' },
      },
      {
        path: 'export',
        name: 'Export',
        component: () => import('../views/ExportView.vue'),
        meta: { title: '成果导出' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
