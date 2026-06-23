import { createRouter, createWebHistory } from 'vue-router'
import { useGeoStore } from '../stores/geo'

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
      {
        path: 'strategy',
        name: 'StrategyCenter',
        component: () => import('../views/StrategyCenter.vue'),
        meta: { title: '策略中心' },
      },
      {
        path: 'templates',
        name: 'ContentTemplates',
        component: () => import('../views/ContentTemplates.vue'),
        meta: { title: '内容规范' },
      },
      {
        path: 'brand-monitor',
        name: 'BrandMonitor',
        component: () => import('../views/BrandMonitor.vue'),
        meta: { title: 'AI收录监测' },
      },
      {
        path: 'batch',
        name: 'Batch',
        component: () => import('../views/BatchView.vue'),
        meta: { title: '批量处理' },
      },
      {
        path: 'logs',
        name: 'LogViewer',
        component: () => import('../views/LogViewer.vue'),
        meta: { title: '系统日志' },
      },
      {
        path: 'audit',
        name: 'AuditLogViewer',
        component: () => import('../views/AuditLogViewer.vue'),
        meta: { title: '审计日志' },
      },
      {
        path: 'scheduler',
        name: 'Scheduler',
        component: () => import('../views/SchedulerView.vue'),
        meta: { title: '定时任务' },
      },
      {
        path: 'seo',
        name: 'SEOIntegration',
        component: () => import('../views/SEOIntegration.vue'),
        meta: { title: 'SEO集成' },
      },
      {
        path: 'template-engine',
        name: 'TemplateEngine',
        component: () => import('../views/TemplateEngine.vue'),
        meta: { title: '模板引擎' },
      },
      {
        path: 'adaptation',
        name: 'AdaptationPipeline',
        component: () => import('../views/AdaptationPipeline.vue'),
        meta: { title: '适配流水线' },
      },
      {
        path: 'feedback',
        name: 'FeedbackDashboard',
        component: () => import('../views/FeedbackDashboard.vue'),
        meta: { title: '数据闭环' },
      },
      {
        path: 'full-funnel',
        name: 'FullFunnelDashboard',
        component: () => import('../views/FullFunnelDashboard.vue'),
        meta: { title: '全域转化漏斗' },
      },
      {
        path: 'conversion-attribution',
        name: 'ConversionAttribution',
        component: () => import('../views/ConversionAttribution.vue'),
        meta: { title: '转化归因' },
      },
      {
        path: 'utm-campaigns',
        name: 'UTMCampaignManager',
        component: () => import('../views/UTMCampaignManager.vue'),
        meta: { title: 'UTM追踪' },
      },
      {
        path: 'reputation',
        name: 'ReputationManager',
        component: () => import('../views/ReputationManager.vue'),
        meta: { title: '品牌舆情管理' },
      },
    ],
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { title: '登录' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('../views/NotFound.vue'),
    meta: { title: '页面未找到' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    return { top: 0, behavior: 'smooth' }
  },
})

// ══════════════════════════════════════════════════════════════
// 路由守卫：登录保护 + 会话超时检测
// ══════════════════════════════════════════════════════════════

router.beforeEach(async (to, from, next) => {
  // 等待 Pinia 初始化
  const store = useGeoStore()

  // 首次访问时检查服务端鉴权状态
  if (!store.authChecked) {
    try {
      const { authStatus } = await import('../api/index.js')
      const res = await authStatus()
      store.setAuthEnabled(res.data?.auth_enabled ?? false)
    } catch {
      // API 不可用，假设鉴权已启用（安全优先）
      store.setAuthEnabled(true)
    }
    store.setAuthChecked()
  }

  // 登录页：如果已认证则直接跳转工作台
  if (to.path === '/login') {
    if (store.isAuthenticated) {
      return next('/dashboard')
    }
    return next()
  }

  // 其他页面：未认证则跳转登录页
  if (!store.isAuthenticated) {
    // 保存目标路径，登录后跳回
    return next({ path: '/login', query: { redirect: to.fullPath } })
  }

  // 已认证：记录活动时间
  store.recordActivity()
  next()
})

export default router
