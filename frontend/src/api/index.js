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

  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: response.statusText }))
        onError(new Error(err.detail || '评测请求失败'))
        return
      }

      sessionId = response.headers.get('X-Session-Id')

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
            } catch { /* skip bad JSON */ }
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
  }
}

// ── 报表 ──
export const previewReport = (data) => api.post('/reports/preview', data)
export const generateReport = (data) => api.post('/reports/generate-from-data', data)
export const exportReport = (id, format) => api.get(`/reports/export/${id}`, { params: { format }, responseType: 'blob' })
export const listReports = () => api.get('/reports/history')

// ── 系统 ──
export const getLLMConfig = () => api.get('/config/llm')
export const healthCheck = () => api.get('/health')

export default api
