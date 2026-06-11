// api/index.test.js — Tests for the frontend API layer
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Use vi.hoisted() so the factory can access these before initialization
const { mockGet, mockPost, mockDelete, mockPut } = vi.hoisted(() => ({
  mockGet: vi.fn(() => Promise.resolve({ data: {} })),
  mockPost: vi.fn(() => Promise.resolve({ data: {} })),
  mockDelete: vi.fn(() => Promise.resolve({ data: {} })),
  mockPut: vi.fn(() => Promise.resolve({ data: {} })),
}))

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      get: mockGet,
      post: mockPost,
      put: mockPut,
      delete: mockDelete,
      interceptors: {
        response: { use: vi.fn() },
        request: { use: vi.fn() },
      },
    })),
  },
}))

vi.mock('element-plus', async () => {
  const actual = await vi.importActual('element-plus')
  return { ...actual, ElMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() } }
})

import {
  cleanText, rewriteText, generateJSONLD,
  evaluateSemantic, getEvalHistory, deleteEvalHistory,
  getAnalyticsOverview, quickDiagnosis,
  listPlatforms, generateLLMSummary,
  getEvalDimensions, getSandtableProfile, getPlatformRules,
} from '../../api/index.js'


describe('API Layer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Text Cleaning', () => {
    it('cleanText POST /cleaning/clean', async () => {
      await cleanText({ content: 'test', sandtable_type: 'smart_city' })
      expect(mockPost).toHaveBeenCalledWith('/cleaning/clean', { content: 'test', sandtable_type: 'smart_city' })
    })
  })

  describe('GEO Rewrite', () => {
    it('rewriteText POST /geo/rewrite', async () => {
      await rewriteText({ content: 'test', platform: 'deepseek' }, { timeout: 60000 })
      expect(mockPost).toHaveBeenCalledWith('/geo/rewrite', { content: 'test', platform: 'deepseek' }, { timeout: 60000 })
    })

    it('getSandtableProfile GET with type', async () => {
      await getSandtableProfile('smart_city')
      expect(mockGet).toHaveBeenCalledWith('/geo/profiles/smart_city')
    })

    it('getPlatformRules GET with platform', async () => {
      await getPlatformRules('deepseek')
      expect(mockGet).toHaveBeenCalledWith('/geo/platform-rules/deepseek')
    })
  })

  describe('JSON-LD', () => {
    it('generateJSONLD POST /jsonld/generate', async () => {
      await generateJSONLD({ sandtable_type: 'smart_city' })
      expect(mockPost).toHaveBeenCalledWith('/jsonld/generate', { sandtable_type: 'smart_city' })
    })
  })

  describe('Evaluation', () => {
    it('evaluateSemantic POST', async () => {
      await evaluateSemantic({ text: 'test' })
      expect(mockPost).toHaveBeenCalledWith('/evaluate/semantic', { text: 'test' })
    })

    it('getEvalHistory GET and returns data', async () => {
      mockGet.mockResolvedValueOnce({ data: { items: [{ id: 1 }] } })
      const result = await getEvalHistory()
      expect(mockGet).toHaveBeenCalledWith('/evaluate/history')
      expect(result.data.items).toEqual([{ id: 1 }])
    })

    it('deleteEvalHistory DELETE with id', async () => {
      await deleteEvalHistory('sess_abc')
      expect(mockDelete).toHaveBeenCalledWith('/evaluate/history/sess_abc')
    })

    it('getEvalDimensions GET', async () => {
      await getEvalDimensions()
      expect(mockGet).toHaveBeenCalledWith('/evaluate/dimensions')
    })
  })

  describe('Other endpoints', () => {
    it('getAnalyticsOverview GET', async () => {
      await getAnalyticsOverview()
      expect(mockGet).toHaveBeenCalledWith('/analytics/overview')
    })

    it('quickDiagnosis POST', async () => {
      await quickDiagnosis({ text: 'test' })
      expect(mockPost).toHaveBeenCalledWith('/diagnosis/quick', { text: 'test' })
    })

    it('listPlatforms GET', async () => {
      await listPlatforms()
      expect(mockGet).toHaveBeenCalledWith('/platform-monitor/platforms')
    })

    it('generateLLMSummary POST with id', async () => {
      await generateLLMSummary('doubao')
      expect(mockPost).toHaveBeenCalledWith('/platform-monitor/platforms/doubao/llm-summary')
    })
  })

  describe('Error handling', () => {
    it('propagates network errors', async () => {
      mockGet.mockRejectedValueOnce(new Error('Network Error'))
      await expect(getEvalHistory()).rejects.toThrow('Network Error')
    })
  })

  describe('URL path correctness', () => {
    it('all endpoints use correct paths', async () => {
      const calls = []
      mockPost.mockImplementation((url) => { calls.push(['POST', url]); return Promise.resolve({ data: {} }) })
      mockGet.mockImplementation((url) => { calls.push(['GET', url]); return Promise.resolve({ data: {} }) })
      mockDelete.mockImplementation((url) => { calls.push(['DELETE', url]); return Promise.resolve({ data: {} }) })

      await cleanText({ content: 'x' })
      await generateJSONLD({})
      await getEvalHistory()
      await deleteEvalHistory('id')
      await listPlatforms()

      expect(calls).toContainEqual(['POST', '/cleaning/clean'])
      expect(calls).toContainEqual(['POST', '/jsonld/generate'])
      expect(calls).toContainEqual(['GET', '/evaluate/history'])
      expect(calls).toContainEqual(['DELETE', '/evaluate/history/id'])
      expect(calls).toContainEqual(['GET', '/platform-monitor/platforms'])
    })
  })
})
