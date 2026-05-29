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

// ── GEO文案重构 ──
export const rewriteText = (data, options) => api.post('/geo/rewrite', data, options)
export const getSandtableProfile = (type) => api.get(`/geo/profiles/${type}`)
export const getPlatformRules = (platform) => api.get(`/geo/platform-rules/${platform}`)

// ── JSON-LD ──
export const generateJSONLD = (data) => api.post('/jsonld/generate', data)
export const getJSONLDTemplates = () => api.get('/jsonld/templates')
export const validateJSONLD = (data) => api.post('/jsonld/validate', data)

// ── AI评测 ──
export const evaluateSemantic = (data) => api.post('/evaluate/semantic', data)
export const getEvalQuestions = () => api.get('/evaluate/questions')
export const quickBrandCheck = (data) => api.post('/evaluate/quick-brand-check', data)

// 新评测 API
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
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
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

export default api
