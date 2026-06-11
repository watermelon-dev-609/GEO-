import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '/api',
  timeout: 300000,
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    // 仅在无服务端响应时（网络中断）全局提示；有服务端响应的错误由各页面自行处理，避免重复弹窗
    if (!err.response) {
      ElMessage.error(err.message || '网络连接失败，请检查网络')
    }
    return Promise.reject(err)
  }
)

// ── 文本清洗 ──
export const cleanText = (data) => api.post('/cleaning/clean', data)
export const extractInfo = (data) => api.post('/cleaning/extract', data)
export const getCleaningRules = () => api.get('/cleaning/rules')
export const updateCleaningRules = (data) => api.put('/cleaning/rules', data)

// ── GEO文案重构 ──
export const rewriteText = (data, options) => api.post('/geo/rewrite', data, options)
export const getSandtableProfile = (type) => api.get(`/geo/profiles/${type}`)
export const getPlatformRules = (platform) => api.get(`/geo/platform-rules/${platform}`)
export const getOptimizationRules = () => api.get('/geo/optimization-rules')
export const updateOptimizationRules = (data) => api.put('/geo/optimization-rules', data)

// ── JSON-LD ──
export const generateJSONLD = (data) => api.post('/jsonld/generate', data)
export const getJSONLDTemplates = () => api.get('/jsonld/templates')
export const validateJSONLD = (data) => api.post('/jsonld/validate', data)

// ── AI评测 ──
export const evaluateSemantic = (data) => api.post('/evaluate/semantic', data)
export const getEvalQuestions = () => api.get('/evaluate/questions')
export const quickBrandCheck = (data) => api.post('/evaluate/quick-brand-check', data)

// 新评测 API
export const generateEvalQuestions = (data) => api.post('/evaluate/generate-questions', data)
export const getEvalDimensions = () => api.get('/evaluate/dimensions')
export const getEvalSession = (id) => api.get(`/evaluate/session/${id}`)
export const cancelEval = (id) => api.post(`/evaluate/cancel/${id}`)
export const getEvalHistory = () => api.get('/evaluate/history')
export const getEvalHistoryDetail = (id) => api.get(`/evaluate/history/${id}`)
export const deleteEvalHistory = (id) => api.delete(`/evaluate/history/${id}`)
export const compareEvalHistory = (data) => api.post('/evaluate/history/compare', data)

/**
 * 创建 SSE 连接开始评测
 * @param {Object} data - 评测请求参数
 * @param {Function} onEvent - 事件回调 (eventType, payload) => void
 * @param {Function} onError - 错误回调 (error) => void
 * @returns {Object} { close, getSessionId }
 */
export function startEvalSSE(data, onEvent, onError) {
  const baseUrl = '/api'
  const url = `${baseUrl}/evaluate/start`

  const controller = new AbortController()
  let sessionId = null
  let sessionIdResolved = false
  let sessionIdPromiseResolve = null
  const sessionIdPromise = new Promise(resolve => { sessionIdPromiseResolve = resolve })

  const timeoutMs = data._timeout || 300000
  const timeoutSignal = AbortSignal.timeout(timeoutMs)
  const combinedSignal = AbortSignal.any([controller.signal, timeoutSignal])

  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    signal: combinedSignal,
  })
    .then(async (response) => {
      if (!response.ok) {
        let detail = response.statusText
        try {
          const errBody = await response.json()
          detail = errBody.detail || detail
        } catch { /* response body might not be JSON (e.g. SSE error stream) */ }
        onError(new Error(detail || '评测请求失败'))
        return
      }

      sessionId = response.headers.get('X-Session-Id')
      sessionIdResolved = true
      sessionIdPromiseResolve(sessionId)

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        let currentEvent = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            try {
              const payload = JSON.parse(line.slice(6))
              onEvent(currentEvent || payload.event, payload)
            } catch (e) {
              console.warn('[SSE] JSON parse failed for line:', line.slice(0, 80), e.message)
            }
            currentEvent = ''
          }
        }
      }

      if (buffer.trim() && buffer.startsWith('data: ')) {
        try {
          const payload = JSON.parse(buffer.slice(6))
          onEvent(payload.event || 'message', payload)
        } catch (e) {
          console.warn('[SSE] final buffer parse failed:', buffer.slice(0, 80), e.message)
        }
      }
    })
    .catch((err) => {
      if (err.name === 'TimeoutError' || err.name === 'AbortError' && timeoutSignal.aborted && !controller.signal.aborted) {
        onError(new Error('评测请求超时（300秒），请检查网络或减少评测文本量后重试'))
      } else if (err.name !== 'AbortError') {
        onError(err)
      }
    })

  return {
    close: () => controller.abort(),
    getSessionId: () => sessionId,
    waitForSessionId: () => sessionIdPromise,
  }
}

// ── 数据看板 ──
export const getAnalyticsOverview = () => api.get('/analytics/overview')
export const getAnalyticsTrend = (days) => api.get('/analytics/trend', { params: { days } })

// ── 内容诊断 ──
export const quickDiagnosis = (data) => api.post('/diagnosis/quick', data)
export const deepDiagnosis = (data) => api.post('/diagnosis/deep', data)
export const batchDiagnosis = (data) => api.post('/diagnosis/batch', data)

// ── 平台监测 ──
export const listPlatforms = () => api.get('/platform-monitor/platforms')
export const getPlatformDetail = (id) => api.get(`/platform-monitor/platforms/${id}`)
export const updatePlatformRules = (id, data) => api.post(`/platform-monitor/platforms/${id}`, data)
export const generateLLMSummary = (id) => api.post(`/platform-monitor/platforms/${id}/llm-summary`)
export const checkAllPlatforms = () => api.post('/platform-monitor/check-all')
export const checkSinglePlatform = (id) => api.post(`/platform-monitor/check/${id}`)
export const getSchedulerStatus = () => api.get('/platform-monitor/scheduler/status')
export const startScheduler = (intervalMinutes) => api.post(`/platform-monitor/scheduler/start?interval_minutes=${intervalMinutes || 30}`)
export const stopScheduler = () => api.post('/platform-monitor/scheduler/stop')

// ── 关键词库 ──
export const listSandtableTypes = () => api.get('/keywords/types')
export const getKeywords = (type) => api.get(`/keywords/${type}`)
export const addKeyword = (type, data) => api.post(`/keywords/${type}`, data)
export const deleteKeyword = (type, cat, word) => api.delete(`/keywords/${type}/${cat}/${encodeURIComponent(word)}`)
export const updateKeyword = (type, cat, word, data) => api.put(`/keywords/${type}/${cat}/${encodeURIComponent(word)}`, data)
export const expandKeywords = (type, data) => api.post(`/keywords/${type}/expand`, data)
export const exportKeywordsCSV = (type) => api.get(`/keywords/${type}/export`)

// ── 竞品调研 ──
export const listCompetitors = () => api.get('/competitors')
export const getCompetitor = (id) => api.get(`/competitors/${id}`)
export const createCompetitor = (data) => api.post('/competitors', data)
export const updateCompetitor = (id, data) => api.put(`/competitors/${id}`, data)
export const deleteCompetitor = (id) => api.delete(`/competitors/${id}`)
export const addSnapshot = (id, data) => api.post(`/competitors/${id}/snapshot`, data)
export const compareCompetitors = (data) => api.post('/competitors/compare', data)
export const generateCompetitorReport = (data) => api.post('/competitors/report', data)
export const triggerCompetitorMonitor = () => api.post('/competitors/monitor/trigger')
export const getCompetitorMonitorHistory = (days) => api.get('/competitors/monitor/history', { params: { days } })
export const compareCompetitorMonitorCycles = (cycle1, cycle2) => api.get('/competitors/monitor/compare', { params: { cycle1, cycle2 } })

// ── 报表 ──
export const previewReport = (data) => api.post('/reports/preview', data)
export const generateReport = (data) => api.post('/reports/generate-from-data', data)
export const exportReport = (id, format) => api.get(`/reports/export/${id}`, { params: { format }, responseType: 'blob' })
export const listReports = () => api.get('/reports/history')

// ── 内容模板 ──
export const listTemplates = () => api.get('/templates/list')
export const getTemplate = (id) => api.get(`/templates/${id}`)
export const saveTemplate = (data) => api.post('/templates/save', data)
export const deleteTemplate = (id) => api.delete(`/templates/${id}`)
export const getStandards = () => api.get('/templates/standards/list')
export const saveStandards = (data) => api.post('/templates/standards/save', data)
export const exportTemplatesAll = () => api.get('/templates/export/all')

// ── 系统 ──
export const getLLMConfig = () => api.get('/config/llm')
export const healthCheck = () => api.get('/health')

// ── 品牌收录监测 ──
export const getMonitorOverview = () => api.get('/brand-monitor/overview')
export const getMonitorHistory = (params) => api.get('/brand-monitor/history', { params })
export const getMonitorSession = (id) => api.get(`/brand-monitor/history/${id}`)
export const runMonitorCheck = (data) => api.post('/brand-monitor/check', data)
export const runMonitorCheckAll = (data) => api.post('/brand-monitor/check-all', data)
export const getMonitorTrend = (days) => api.get('/brand-monitor/trend', { params: { days } })
export const getMonitorQueries = () => api.get('/brand-monitor/queries')
export const addMonitorQuery = (data) => api.post('/brand-monitor/queries', data)
export const deleteMonitorQuery = (id) => api.delete(`/brand-monitor/queries/${id}`)

// ── 批量处理 ──
export const batchClean = (data) => api.post('/batch/clean', data)
export const batchDiagnose = (data) => api.post('/batch/diagnose', data)
export const batchExport = (data) => api.post('/batch/export', data, { responseType: 'blob' })
export const getBatchProgress = (taskId) => api.get(`/batch/progress/${taskId}`)
export const cancelBatchTask = (taskId) => api.post('/batch/cancel', { task_id: taskId })
export const listBatchTasks = () => api.get('/batch/tasks')

export function startBatchOptimizeSSE(data, onEvent, onError) {
  return createBatchSSE('/batch/optimize/stream', data, onEvent, onError)
}

export function startBatchEvaluateSSE(data, onEvent, onError) {
  return createBatchSSE('/batch/evaluate/stream', data, onEvent, onError)
}

function createBatchSSE(url, data, onEvent, onError) {
  const baseUrl = '/api'
  const fullUrl = `${baseUrl}${url}`
  const controller = new AbortController()
  const timeoutMs = data._timeout || 600000
  const timeoutSignal = AbortSignal.timeout(timeoutMs)
  const combinedSignal = AbortSignal.any([controller.signal, timeoutSignal])

  fetch(fullUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    signal: combinedSignal,
  })
    .then(async (response) => {
      if (!response.ok) {
        let detail = response.statusText
        try { const errBody = await response.json(); detail = errBody.detail || detail } catch {}
        onError(new Error(detail || '请求失败'))
        return
      }
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const content = line.slice(6)
            if (content === '[DONE]') { onEvent('done', {}); return }
            try { onEvent('message', JSON.parse(content)) } catch (e) { console.warn('[BatchSSE] parse failed:', content.slice(0, 80)) }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name === 'TimeoutError' || (err.name === 'AbortError' && timeoutSignal.aborted && !controller.signal.aborted)) {
        onError(new Error('批量处理请求超时（600秒），请减少批量数量后重试'))
      } else if (err.name !== 'AbortError') {
        onError(err)
      }
    })

  return { close: () => controller.abort() }
}

// ── 合规检测 ──
export const checkCompliance = (data) => api.post('/compliance/check', data)

// ── 用量监控 ──
export const getUsageSummary = (date) => api.get('/usage/summary', { params: { date } })
export const getUsageHistory = (days) => api.get('/usage/history', { params: { days } })
export const getUsageAlerts = () => api.get('/usage/alerts')

// ── 鉴权 ──
export const authLogin = (data) => api.post('/auth/login', data)
export const authLogout = () => api.post('/auth/logout')
export const authStatus = () => api.get('/auth/status')

// ── 系统日志 ──
export const getRecentLogs = (params) => api.get('/logs/recent', { params })
export const downloadLogs = () => api.get('/logs/download', { responseType: 'blob' })

// ── 审计日志 ──
export const getAuditLogs = (params) => api.get('/audit/logs', { params })
export const exportAuditLogs = (date) => api.get('/audit/export', { params: { date }, responseType: 'blob' })

// ── 模板引擎 (Phase 2) ──
export const getEnginePlatforms = () => api.get('/templates/engine/platforms')
export const getEnginePlatform = (id) => api.get(`/templates/engine/${id}`)
export const updateEnginePlatform = (id, data) => api.put(`/templates/engine/${id}`, data)
export const validateTemplate = (id) => api.post(`/templates/engine/${id}/validate`)
export const getTemplateHistory = (id) => api.get(`/templates/engine/${id}/history`)
export const diffTemplates = (id, v1, v2) => api.get(`/templates/engine/${id}/diff/${v1}/${v2}`)
export const previewTemplate = (data) => api.post(`/templates/engine/${data.platform_id}/preview`, data)
export const rollbackTemplate = (id, versionId) => api.post(`/templates/engine/${id}/rollback/${versionId}`)
export const reloadTemplates = () => api.post('/templates/engine/reload')
export const getWatchdogStatus = () => api.get('/templates/engine/watchdog-status')

// ── 适配流水线 (Phase 3) ──
export const getAdaptationRuns = (params) => api.get('/adaptation/runs', { params })
export const createAdaptationRun = (params) => api.post('/adaptation/runs', null, { params })
export const getAdaptationRun = (id) => api.get(`/adaptation/runs/${id}`)
export const advanceAdaptationRun = (id, target_stage) => api.post(`/adaptation/runs/${id}/advance`, null, { params: { target_stage } })
export const scanInventory = (id) => api.post(`/adaptation/runs/${id}/scan`)
export const validateContent = (id, text) => api.post(`/adaptation/runs/${id}/validate`, null, { params: { text } })
export const publishRun = (id, strategy) => api.post(`/adaptation/runs/${id}/publish`, null, { params: { strategy } })
export const rollbackRun = (id) => api.post(`/adaptation/runs/${id}/rollback`)
export const postTestRun = (id, days) => api.post(`/adaptation/runs/${id}/post-test`, null, { params: { days } })

// ── 数据闭环 (Phase 4) ──
export const getCurrentMetrics = (platform_id) => api.get('/feedback/metrics/current', { params: { platform_id } })
export const getPlatformMetrics = (id) => api.get(`/feedback/metrics/${id}`)
export const getMetricsTrend = (id, weeks) => api.get(`/feedback/metrics/${id}/trend`, { params: { weeks } })
export const checkCitationDrop = (id) => api.get(`/feedback/citation-drop/${id}`)
export const diagnosePlatform = (id) => api.post(`/feedback/diagnose/${id}`)
export const getIterationHistory = (limit) => api.get('/feedback/iteration-history', { params: { limit } })

// ── 流量与转化追踪 (Phase 5) ──
// Traffic
export const getTrafficConfig = () => api.get('/traffic/config')
export const saveTrafficConfig = (data) => api.post('/traffic/config', data)
export const fetchTrafficData = (source, date) => api.post(`/traffic/fetch/${source}`, null, { params: { date } })
export const getTrafficSummary = (params) => api.get('/traffic/summary', { params })
export const getDailyTraffic = (date) => api.get(`/traffic/daily/${date}`)
export const getTrafficTrend = (params) => api.get('/traffic/trend', { params })
export const getTrafficSources = (params) => api.get('/traffic/sources', { params })
// Conversions
export const recordConversionEvent = (data) => api.post('/conversions/event', data)
export const getConversionEvents = (params) => api.get('/conversions/events', { params })
export const deleteConversionEvent = (id) => api.delete(`/conversions/event/${id}`)
export const getAttribution = (params) => api.get('/conversions/attribution', { params })
export const getFunnelData = (params) => api.get('/conversions/funnel', { params })
export const getConversionTrend = (params) => api.get('/conversions/trend', { params })
export const getConversionsByPlatform = (params) => api.get('/conversions/by-ai-platform', { params })
// UTM Campaigns
export const createCampaign = (data) => api.post('/utm/campaigns', data)
export const listCampaigns = (params) => api.get('/utm/campaigns', { params })
export const getCampaign = (id) => api.get(`/utm/campaigns/${id}`)
export const updateCampaign = (id, data) => api.put(`/utm/campaigns/${id}`, data)
export const deleteCampaign = (id) => api.delete(`/utm/campaigns/${id}`)
export const generateUTMLink = (id, platformId) => api.post(`/utm/campaigns/${id}/generate`, null, { params: { platform_id: platformId || '' } })
export const batchGenerateUTM = (data) => api.post('/utm/batch-generate', data)
// Full funnel analytics
export const getFullFunnelAnalytics = (params) => api.get('/analytics/full-funnel', { params })

export default api
