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

export default router
