import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useGeoStore = defineStore('geo', () => {
  // ── 当前项目状态 ──
  const currentStep = ref('import') // import | cleaning | rewrite | evaluate | export
  const originalText = ref('')
  const cleanedText = ref('')
  const currentSandtableType = ref('')
  const dimensions = ref(null)
  const rewriteResults = ref([])
  const evaluationResult = ref(null)
  const selectedPlatforms = ref([])
  const projectHistory = ref([])

  // ── 加载状态 ──
  const isProcessing = ref(false)
  const processingMessage = ref('')

  // ── 系统配置 ──
  const llmConfigs = ref([])

  // ── 评测会话状态 ──
  const evalSessionId = ref(null)
  const evalStatus = ref('idle') // idle | running | completed | cancelled | failed
  const evalPhases = ref({})
  const evalOverallProgress = ref(0)
  const evalOverallScore = ref(null)
  const evalMode = ref('pipeline')
  const evalDimensionConfigs = ref([])

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
    const latest = scored[0].overall_score
    const previous = scored[1].overall_score
    if (latest > previous) return 'up'
    if (latest < previous) return 'down'
    return 'stable'
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
  function setLLMConfigs(configs) { llmConfigs.value = configs }
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

  function setEvalSessionId(id) { evalSessionId.value = id }
  function setEvalStatus(status) { evalStatus.value = status }
  function setEvalPhase(phaseKey, data) {
    evalPhases.value = { ...evalPhases.value, [phaseKey]: data }
  }
  function setEvalProgress(progress) { evalOverallProgress.value = progress }
  function setEvalScore(score) { evalOverallScore.value = score }
  function setEvalMode(mode) { evalMode.value = mode }
  function setEvalDimensionConfigs(configs) { evalDimensionConfigs.value = configs }

  function resetEvalSession() {
    evalSessionId.value = null
    evalStatus.value = 'idle'
    evalPhases.value = {}
    evalOverallProgress.value = 0
    evalOverallScore.value = null
  }

  async function fetchEvalHistory() {
    evalHistoryLoading.value = true
    try {
      const { getEvalHistory } = await import('../api/index.js')
      const res = await getEvalHistory()
      evalHistory.value = res.data.items || []
    } catch {
      // 静默失败
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
    } catch {
      // 静默失败
    }
  }

  function setReoptimizeContext(ctx) {
    reoptimizeContext.value = ctx
  }

  function clearReoptimizeContext() {
    reoptimizeContext.value = null
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

  return {
    currentStep, originalText, cleanedText, currentSandtableType,
    dimensions, rewriteResults, evaluationResult, selectedPlatforms,
    projectHistory, isProcessing, processingMessage, llmConfigs,
    hasCleanedText, hasResults, hasEvaluation, configuredPlatforms,
    setOriginalText, setCleanedText, setSandtableType, setDimensions,
    setRewriteResults, setEvaluationResult, setSelectedPlatforms,
    setLLMConfigs, setProcessing, addToHistory, reset,
    evalSessionId, evalStatus, evalPhases, evalOverallProgress,
    evalOverallScore, evalMode, evalDimensionConfigs,
    setEvalSessionId, setEvalStatus, setEvalPhase, setEvalProgress,
    setEvalScore, setEvalMode, setEvalDimensionConfigs, resetEvalSession,
    evalHistory, evalHistoryLoading, fetchEvalHistory, pushToHistory, deleteEvalHistoryItem,
    recentEvaluations, averageEvalScore, scoreTrend,
    reoptimizeContext, setReoptimizeContext, clearReoptimizeContext,
  }
})
