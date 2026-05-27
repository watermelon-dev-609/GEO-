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

  // ── Computed ──
  const hasCleanedText = computed(() => !!cleanedText.value)
  const hasResults = computed(() => rewriteResults.value.length > 0)
  const hasEvaluation = computed(() => !!evaluationResult.value)
  const configuredPlatforms = computed(() => llmConfigs.value.filter(c => c.configured))

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
  }
})
