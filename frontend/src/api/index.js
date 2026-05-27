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
export const rewriteText = (data) => api.post('/geo/rewrite', data)
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

// ── 报表 ──
export const generateReport = (data) => api.post('/reports/generate-from-data', data)
export const exportReport = (id, format) => api.get(`/reports/export/${id}`, { params: { format }, responseType: 'blob' })
export const listReports = () => api.get('/reports/history')

// ── 系统 ──
export const getLLMConfig = () => api.get('/config/llm')
export const healthCheck = () => api.get('/health')

export default api
