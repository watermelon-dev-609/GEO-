// geo.test.js — Pinia store unit tests
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// Mock the API module used by dynamic imports in fetchEvalHistory/deleteEvalHistoryItem
vi.mock('../../api/index.js', () => ({
  getEvalHistory: vi.fn(() => Promise.resolve({ data: { items: [] } })),
  deleteEvalHistory: vi.fn(() => Promise.resolve({ data: { success: true } })),
}))

// Mock ElMessage (should also be handled by setup.ts)
vi.mock('element-plus', async () => {
  const actual = await vi.importActual('element-plus')
  return { ...actual, ElMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() } }
})

import { useGeoStore } from '../../stores/geo.js'


describe('Geo Store', () => {
  let store

  beforeEach(() => {
    // Fresh Pinia for each test
    setActivePinia(createPinia())
    // Clear sessionStorage
    sessionStorage.clear()
    store = useGeoStore()
  })

  describe('Initial state', () => {
    it('has default currentStep', () => {
      expect(store.currentStep).toBe('import')
    })

    it('has empty originalText', () => {
      expect(store.originalText).toBe('')
    })

    it('has empty cleanedText', () => {
      expect(store.cleanedText).toBe('')
    })

    it('has empty currentSandtableType', () => {
      expect(store.currentSandtableType).toBe('')
    })

    it('has null dimensions', () => {
      expect(store.dimensions).toBeNull()
    })

    it('has empty rewriteResults array', () => {
      expect(store.rewriteResults).toEqual([])
    })

    it('has null evaluationResult', () => {
      expect(store.evaluationResult).toBeNull()
    })

    it('has empty selectedPlatforms', () => {
      expect(store.selectedPlatforms).toEqual([])
    })

    it('has isProcessing false', () => {
      expect(store.isProcessing).toBe(false)
    })

    it('has null reoptimizeContext', () => {
      expect(store.reoptimizeContext).toBeNull()
    })
  })

  describe('Setters', () => {
    it('setOriginalText updates value', () => {
      store.setOriginalText('测试文本')
      expect(store.originalText).toBe('测试文本')
    })

    it('setCleanedText updates value', () => {
      store.setCleanedText('清洗后的文本')
      expect(store.cleanedText).toBe('清洗后的文本')
    })

    it('setSandtableType updates value', () => {
      store.setSandtableType('smart_city')
      expect(store.currentSandtableType).toBe('smart_city')
    })

    it('setDimensions updates value', () => {
      const dims = { core_advantages: ['优势A'] }
      store.setDimensions(dims)
      expect(store.dimensions).toEqual(dims)
    })

    it('setRewriteResults updates value', () => {
      const results = [{ platform: 'deepseek', optimized_text: 'test' }]
      store.setRewriteResults(results)
      expect(store.rewriteResults).toEqual(results)
    })

    it('setEvaluationResult updates value', () => {
      const result = { overall_score: 85.5 }
      store.setEvaluationResult(result)
      expect(store.evaluationResult).toEqual(result)
    })

    it('setSelectedPlatforms updates value', () => {
      store.setSelectedPlatforms(['deepseek', 'kimi'])
      expect(store.selectedPlatforms).toEqual(['deepseek', 'kimi'])
    })

    it('setLLMConfigs updates configs and enterprise info', () => {
      store.setLLMConfigs(
        [{ platform: 'deepseek', configured: true }],
        '测试企业',
        '武汉'
      )
      expect(store.llmConfigs).toHaveLength(1)
      expect(store.enterpriseName).toBe('测试企业')
      expect(store.enterpriseLocation).toBe('武汉')
    })

    it('setProcessing toggles processing state', () => {
      store.setProcessing(true, '正在处理...')
      expect(store.isProcessing).toBe(true)
      expect(store.processingMessage).toBe('正在处理...')
      store.setProcessing(false)
      expect(store.isProcessing).toBe(false)
    })
  })

  describe('Computed', () => {
    it('hasCleanedText returns false when empty', () => {
      expect(store.hasCleanedText).toBe(false)
    })

    it('hasCleanedText returns true when text set', () => {
      store.setCleanedText('清洗文本')
      expect(store.hasCleanedText).toBe(true)
    })

    it('hasResults returns false when empty', () => {
      expect(store.hasResults).toBe(false)
    })

    it('hasResults returns true with results', () => {
      store.setRewriteResults([{ platform: 'test' }])
      expect(store.hasResults).toBe(true)
    })

    it('hasEvaluation returns false when null', () => {
      expect(store.hasEvaluation).toBe(false)
    })

    it('hasEvaluation returns true with result', () => {
      store.setEvaluationResult({ overall_score: 80 })
      expect(store.hasEvaluation).toBe(true)
    })

    it('configuredPlatforms filters configured ones', () => {
      store.llmConfigs = [
        { platform: 'a', configured: true },
        { platform: 'b', configured: false },
        { platform: 'c', configured: true },
      ]
      expect(store.configuredPlatforms).toHaveLength(2)
    })

    it('averageEvalScore calculates correctly', () => {
      store.evalHistory = [
        { overall_score: 80, session_id: '1' },
        { overall_score: 90, session_id: '2' },
      ]
      expect(store.averageEvalScore).toBe('85.0')
    })

    it('averageEvalScore returns null with no data', () => {
      store.evalHistory = []
      expect(store.averageEvalScore).toBeNull()
    })

    it('averageEvalScore skips null scores', () => {
      store.evalHistory = [
        { overall_score: 80, session_id: '1' },
        { overall_score: null, session_id: '2' },
      ]
      expect(store.averageEvalScore).toBe('80.0')
    })

    it('scoreTrend returns null with < 2 entries', () => {
      store.evalHistory = [{ overall_score: 80 }]
      expect(store.scoreTrend).toBeNull()
    })

    it('scoreTrend detects up trend', () => {
      store.evalHistory = [
        { overall_score: 90, sandtable_type: 'smart_city', session_id: '2' },
        { overall_score: 80, sandtable_type: 'smart_city', session_id: '1' },
      ]
      store.currentSandtableType = 'smart_city'
      expect(store.scoreTrend).toBe('up')
    })

    it('scoreTrend detects down trend', () => {
      store.evalHistory = [
        { overall_score: 70, sandtable_type: 'smart_city', session_id: '2' },
        { overall_score: 80, sandtable_type: 'smart_city', session_id: '1' },
      ]
      store.currentSandtableType = 'smart_city'
      expect(store.scoreTrend).toBe('down')
    })

    it('scoreTrend detects stable', () => {
      store.evalHistory = [
        { overall_score: 85, sandtable_type: 'smart_city', session_id: '2' },
        { overall_score: 85, sandtable_type: 'smart_city', session_id: '1' },
      ]
      store.currentSandtableType = 'smart_city'
      expect(store.scoreTrend).toBe('stable')
    })

    it('recentEvaluations returns max 3', () => {
      store.evalHistory = [
        { overall_score: 1, session_id: '1' },
        { overall_score: 2, session_id: '2' },
        { overall_score: 3, session_id: '3' },
        { overall_score: 4, session_id: '4' },
      ]
      expect(store.recentEvaluations).toHaveLength(3)
    })
  })

  describe('History actions', () => {
    it('addToHistory prepends project', () => {
      store.addToHistory({ name: 'test project' })
      expect(store.projectHistory).toHaveLength(1)
      expect(store.projectHistory[0].name).toBe('test project')
      expect(store.projectHistory[0].id).toBeDefined()
      expect(store.projectHistory[0].time).toBeDefined()
    })

    it('addToHistory caps at 50', () => {
      for (let i = 0; i < 60; i++) {
        store.addToHistory({ name: `project ${i}` })
      }
      expect(store.projectHistory).toHaveLength(50)
    })

    it('pushToHistory prepends eval entry', () => {
      store.pushToHistory({ session_id: 'abc', overall_score: 85, sandtable_type: 'smart_city' })
      expect(store.evalHistory).toHaveLength(1)
      expect(store.evalHistory[0].session_id).toBe('abc')
      expect(store.evalHistory[0].overall_score).toBe(85)
    })

    it('pushToHistory caps at 100', () => {
      for (let i = 0; i < 120; i++) {
        store.pushToHistory({ session_id: `s${i}` })
      }
      expect(store.evalHistory).toHaveLength(100)
    })
  })

  describe('Reset', () => {
    it('reset clears all state', () => {
      store.setOriginalText('text')
      store.setCleanedText('clean')
      store.setSandtableType('smart_city')
      store.setDimensions({ test: true })
      store.setRewriteResults([{ platform: 'test' }])
      store.setEvaluationResult({ score: 90 })
      store.setSelectedPlatforms(['deepseek'])

      store.reset()

      expect(store.originalText).toBe('')
      expect(store.cleanedText).toBe('')
      expect(store.currentSandtableType).toBe('')
      expect(store.dimensions).toBeNull()
      expect(store.rewriteResults).toEqual([])
      expect(store.evaluationResult).toBeNull()
      expect(store.selectedPlatforms).toEqual([])
      expect(store.currentStep).toBe('import')
    })
  })

  describe('Reoptimize context', () => {
    it('setReoptimizeContext sets value', () => {
      const ctx = { from: 'evaluation', hints: ['hint1'] }
      store.setReoptimizeContext(ctx)
      expect(store.reoptimizeContext).toEqual(ctx)
    })

    it('clearReoptimizeContext sets null', () => {
      store.setReoptimizeContext({ test: true })
      store.clearReoptimizeContext()
      expect(store.reoptimizeContext).toBeNull()
    })
  })

  describe('localStorage persistence', () => {
    it('loads saved state from localStorage', () => {
      localStorage.setItem('geo_pipeline_state', JSON.stringify({
        _ts: Date.now(),
        currentStep: 'geo_workshop',
        originalText: 'saved text',
        currentSandtableType: 'smart_city',
      }))
      // Need a fresh Pinia instance to trigger store re-creation
      const freshPinia = createPinia()
      setActivePinia(freshPinia)
      const newStore = useGeoStore()
      expect(newStore.currentStep).toBe('geo_workshop')
      expect(newStore.originalText).toBe('saved text')
      expect(newStore.currentSandtableType).toBe('smart_city')
      // cleanup
      localStorage.removeItem('geo_pipeline_state')
    })

    it('handles corrupted localStorage gracefully', () => {
      localStorage.setItem('geo_pipeline_state', 'not valid json{{{')
      // Should not throw when loading
      expect(() => useGeoStore()).not.toThrow()
      localStorage.removeItem('geo_pipeline_state')
    })

    it('handles missing localStorage gracefully', () => {
      localStorage.removeItem('geo_pipeline_state')
      expect(() => useGeoStore()).not.toThrow()
    })

    it('handles expired (7d+) localStorage gracefully', () => {
      localStorage.setItem('geo_pipeline_state', JSON.stringify({
        _ts: Date.now() - 8 * 24 * 60 * 60 * 1000,  // 8 days ago
        currentStep: 'expired_state',
        originalText: 'should be cleared',
      }))
      const freshPinia = createPinia()
      setActivePinia(freshPinia)
      const newStore = useGeoStore()
      // Expired state should be treated as empty
      expect(newStore.currentStep).toBe('import')
      expect(newStore.originalText).toBe('')
      localStorage.removeItem('geo_pipeline_state')
    })
  })
})
