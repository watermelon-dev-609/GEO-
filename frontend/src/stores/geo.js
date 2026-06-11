import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'

const STORAGE_KEY = 'geo_pipeline_state'

function loadFromStorage() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch (e) { console.error('sessionStorage load failed:', e); return {} }
}

export const useGeoStore = defineStore('geo', () => {
  // ── 从 sessionStorage 恢复状态 ──
  const saved = loadFromStorage()

  // ── 当前项目状态 ──
  const currentStep = ref(saved.currentStep || 'import')
  const originalText = ref(saved.originalText || '')
  const cleanedText = ref(saved.cleanedText || '')
  const currentSandtableType = ref(saved.currentSandtableType || '')
  const dimensions = ref(saved.dimensions || null)
  const rewriteResults = ref(saved.rewriteResults || [])
  const evaluationResult = ref(saved.evaluationResult || null)
  const selectedPlatforms = ref(saved.selectedPlatforms || [])
  const projectHistory = ref(saved.projectHistory || [])

  // ── 加载状态 ──
  const isProcessing = ref(false)
  const processingMessage = ref('')

  // ── 系统配置 ──
  const llmConfigs = ref([])
  const enterpriseName = ref('')
  const enterpriseLocation = ref('')
  const enterpriseWebsite = ref('')

  // ── 评测历史 ──
  const evalHistory = ref([])
  const evalHistoryLoading = ref(false)

  // ── Computed ──
  const hasCleanedText = computed(() => !!cleanedText.value)
  const hasResults = computed(() => rewriteResults.value.length > 0)
  const hasEvaluation = computed(() => !!evaluationResult.value)
  const configuredPlatforms = computed(() => llmConfigs.value.filter(c => c.configured))

  const recentEvaluations = computed(() => {
    return evalHistory.value
      .filter(h => h.overall_score !== null)
      .slice(0, 3)
  })

  const averageEvalScore = computed(() => {
    const scored = evalHistory.value.filter(h => h.overall_score !== null)
    if (scored.length === 0) return null
    return (scored.reduce((sum, h) => sum + h.overall_score, 0) / scored.length).toFixed(1)
  })

  const scoreTrend = computed(() => {
    const scored = evalHistory.value.filter(h => h.overall_score !== null)
    if (scored.length < 2) return null
    // 限定同沙盘类型对比，否则无意义
    const currentType = currentSandtableType.value || scored[0]?.sandtable_type
    const same = scored.filter(h => h.sandtable_type === currentType)
    if (same.length >= 2) {
      const latest = same[0].overall_score
      const previous = same[1].overall_score
      if (latest > previous) return 'up'
      if (latest < previous) return 'down'
      return 'stable'
    }
    return null
  })

  // ── 重优化上下文 ──
  const reoptimizeContext = ref(null)

  // ── Actions ──
  function setOriginalText(text) { originalText.value = text }
  function setCleanedText(text) { cleanedText.value = text }
  function setSandtableType(type) { currentSandtableType.value = type }
  function setDimensions(dims) { dimensions.value = dims }
  function setRewriteResults(results) { rewriteResults.value = results }
  function setEvaluationResult(result) { evaluationResult.value = result }
  function setSelectedPlatforms(platforms) { selectedPlatforms.value = platforms }
  function setLLMConfigs(configs, enterprise_name = '', enterprise_location = '', enterprise_website = '') {
    llmConfigs.value = configs
    if (enterprise_name) enterpriseName.value = enterprise_name
    if (enterprise_location) enterpriseLocation.value = enterprise_location
    if (enterprise_website) enterpriseWebsite.value = enterprise_website
  }
  function setProcessing(val, msg = '') {
    isProcessing.value = val
    processingMessage.value = msg
  }

  function addToHistory(project) {
    projectHistory.value.unshift({
      ...project,
      id: Date.now().toString(36),
      time: new Date().toISOString(),
    })
    if (projectHistory.value.length > 50) {
      projectHistory.value = projectHistory.value.slice(0, 50)
    }
  }

  async function fetchEvalHistory() {
    evalHistoryLoading.value = true
    try {
      const { getEvalHistory } = await import('../api/index.js')
      const res = await getEvalHistory()
      evalHistory.value = res.data.items || []
    } catch (e) {
      if (e.response?.status !== 404) {
        ElMessage.error('加载评测历史失败: ' + (e.response?.data?.detail || e.message))
      }
    } finally {
      evalHistoryLoading.value = false
    }
  }

  function pushToHistory(sessionData) {
    evalHistory.value.unshift({
      session_id: sessionData.session_id || '',
      status: sessionData.status || 'completed',
      overall_score: sessionData.overall_score ?? null,
      sandtable_type: sessionData.sandtable_type || '',
      mode: sessionData.mode || 'pipeline',
      created_at: sessionData.created_at || new Date().toISOString(),
      _detail: sessionData,
    })
    if (evalHistory.value.length > 100) {
      evalHistory.value = evalHistory.value.slice(0, 100)
    }
  }

  async function deleteEvalHistoryItem(id) {
    try {
      const { deleteEvalHistory } = await import('../api/index.js')
      await deleteEvalHistory(id)
      evalHistory.value = evalHistory.value.filter(h => h.session_id !== id)
    } catch (e) {
      if (e.response?.status !== 404) {
        ElMessage.error('删除评测记录失败: ' + (e.response?.data?.detail || e.message))
      }
      throw e
    }
  }

  function setReoptimizeContext(ctx) {
    reoptimizeContext.value = ctx
  }

  function clearReoptimizeContext() {
    reoptimizeContext.value = null
  }

  // ── 流量与转化追踪 (Phase 5) ──
  const trafficConfig = ref(null)
  const trafficSummary = ref(null)
  const trafficTrend = ref([])
  const trafficLoading = ref(false)
  const conversionSummary = ref(null)
  const conversionTrend = ref([])
  const funnelData = ref(null)
  const conversionsByPlatform = ref([])
  const conversionLoading = ref(false)
  const utmCampaigns = ref([])
  const utmLoading = ref(false)

  async function fetchTrafficConfig() {
    try {
      const { getTrafficConfig } = await import('../api/index.js')
      const res = await getTrafficConfig()
      trafficConfig.value = res.data?.sources || null
    } catch (e) {
      ElMessage.error('加载流量配置失败: ' + (e.response?.data?.detail || e.message))
    }
  }

  async function fetchTrafficSummary(params) {
    trafficLoading.value = true
    try {
      const { getTrafficSummary } = await import('../api/index.js')
      const res = await getTrafficSummary(params)
      trafficSummary.value = res.data || null
    } catch (e) {
      ElMessage.error('加载流量数据失败: ' + (e.response?.data?.detail || e.message))
    } finally {
      trafficLoading.value = false
    }
  }

  async function fetchTrafficTrend(params) {
    try {
      const { getTrafficTrend } = await import('../api/index.js')
      const res = await getTrafficTrend(params)
      trafficTrend.value = res.data?.trend || []
    } catch (e) {
      ElMessage.error('加载流量趋势失败: ' + (e.response?.data?.detail || e.message))
    }
  }

  async function fetchFunnelData(params) {
    try {
      const { getFunnelData } = await import('../api/index.js')
      const res = await getFunnelData(params)
      funnelData.value = res.data || null
    } catch (e) {
      ElMessage.error('加载漏斗数据失败: ' + (e.response?.data?.detail || e.message))
    }
  }

  async function fetchConversionSummary(params) {
    conversionLoading.value = true
    try {
      const { getAttribution } = await import('../api/index.js')
      const res = await getAttribution(params)
      conversionSummary.value = res.data || null
    } catch (e) {
      ElMessage.error('加载转化数据失败: ' + (e.response?.data?.detail || e.message))
    } finally {
      conversionLoading.value = false
    }
  }

  async function fetchConversionsByPlatform(params) {
    try {
      const { getConversionsByPlatform } = await import('../api/index.js')
      const res = await getConversionsByPlatform(params)
      conversionsByPlatform.value = res.data?.platforms || []
    } catch (e) {
      ElMessage.error('加载平台转化数据失败: ' + (e.response?.data?.detail || e.message))
    }
  }

  async function fetchConversionTrend(params) {
    try {
      const { getConversionTrend } = await import('../api/index.js')
      const res = await getConversionTrend(params)
      conversionTrend.value = res.data?.trend || []
    } catch (e) {
      ElMessage.error('加载转化趋势失败: ' + (e.response?.data?.detail || e.message))
    }
  }

  async function fetchUTMCampaigns() {
    utmLoading.value = true
    try {
      const { listCampaigns } = await import('../api/index.js')
      const res = await listCampaigns()
      utmCampaigns.value = res.data?.campaigns || []
    } catch (e) {
      ElMessage.error('加载UTM计划失败: ' + (e.response?.data?.detail || e.message))
    } finally {
      utmLoading.value = false
    }
  }

  function reset() {
    currentStep.value = 'import'
    originalText.value = ''
    cleanedText.value = ''
    currentSandtableType.value = ''
    dimensions.value = null
    rewriteResults.value = []
    evaluationResult.value = null
    selectedPlatforms.value = []
  }

  // ── 自动保存到 sessionStorage（防抖 + 容量保护）──
  const SESSION_STORAGE_MAX = 4 * 1024 * 1024  // 4MB 安全上限
  let _saveTimer = null
  function _scheduleSave() {
    clearTimeout(_saveTimer)
    _saveTimer = setTimeout(() => {
      try {
        const payload = {
          currentStep: currentStep.value,
          originalText: originalText.value,
          cleanedText: cleanedText.value,
          currentSandtableType: currentSandtableType.value,
          dimensions: dimensions.value,
          rewriteResults: rewriteResults.value,
          evaluationResult: evaluationResult.value,
          selectedPlatforms: selectedPlatforms.value,
          projectHistory: projectHistory.value.slice(0, 20),
        }
        const serialized = JSON.stringify(payload)
        if (serialized.length > SESSION_STORAGE_MAX) {
          payload.rewriteResults = (payload.rewriteResults || []).map(r => ({
            platform: r.platform,
            optimized_text: (r.optimized_text || '').slice(0, 1000),
            word_count: r.word_count,
          }))
          payload.evaluationResult = null
          payload.projectHistory = (payload.projectHistory || []).slice(0, 5)
        }
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
      } catch (e) {
        console.error('sessionStorage save failed:', e)
        try { sessionStorage.removeItem(STORAGE_KEY) } catch { /* full clear */ }
      }
    }, 300)
  }

  const _watchTargets = [originalText, cleanedText, currentSandtableType,
    dimensions, rewriteResults, evaluationResult, selectedPlatforms]
  _watchTargets.forEach(t => watch(t, _scheduleSave, { deep: false }))

  return {
    currentStep, originalText, cleanedText, currentSandtableType,
    dimensions, rewriteResults, evaluationResult, selectedPlatforms,
    projectHistory, isProcessing, processingMessage, llmConfigs, enterpriseName, enterpriseLocation, enterpriseWebsite,
    hasCleanedText, hasResults, hasEvaluation, configuredPlatforms,
    setOriginalText, setCleanedText, setSandtableType, setDimensions,
    setRewriteResults, setEvaluationResult, setSelectedPlatforms,
    setLLMConfigs, setProcessing, addToHistory, reset,
    evalHistory, evalHistoryLoading, fetchEvalHistory, pushToHistory, deleteEvalHistoryItem,
    recentEvaluations, averageEvalScore, scoreTrend,
    reoptimizeContext, setReoptimizeContext, clearReoptimizeContext,
    // Traffic, conversion, UTM
    trafficConfig, trafficSummary, trafficTrend, trafficLoading,
    conversionSummary, conversionTrend, funnelData, conversionsByPlatform, conversionLoading,
    utmCampaigns, utmLoading,
    fetchTrafficConfig, fetchTrafficSummary, fetchTrafficTrend,
    fetchFunnelData, fetchConversionSummary, fetchConversionsByPlatform,
    fetchConversionTrend, fetchUTMCampaigns,
  }
})
