// setup.ts — Global test setup for Vue 3 + Element Plus component tests
//
// This file runs before every test file. It handles:
// - Global component stubs (Element Plus icons, ECharts)
// - Browser API mocks (ResizeObserver, IntersectionObserver)
// - Console warning/error suppression (optional)
// - Mock Service Worker (MSW) lifecycle for API tests

import { config } from '@vue/test-utils'
import { vi } from 'vitest'

// =============================================================================
// Note: Element Plus icons are NOT mocked — they work fine in jsdom.
// Only ECharts (heavy canvas library) is mocked below.
// If individual icons cause issues, mock them per test file via vi.mock.
// =============================================================================

// =============================================================================
// Mock ECharts — avoids loading the full chart library in jsdom
// =============================================================================
vi.mock('echarts', () => {
  const echarts = {
    init: vi.fn(() => ({
      setOption: vi.fn(),
      getOption: vi.fn(() => ({})),
      resize: vi.fn(),
      dispose: vi.fn(),
      on: vi.fn(),
      off: vi.fn(),
      clear: vi.fn(),
      showLoading: vi.fn(),
      hideLoading: vi.fn(),
    })),
    getInstanceByDom: vi.fn(),
    dispose: vi.fn(),
    registerTheme: vi.fn(),
  }
  return {
    default: echarts,
    ...echarts,
  }
})

// =============================================================================
// Mock vue-echarts — thin wrapper around ECharts
// =============================================================================
vi.mock('vue-echarts', () => ({
  default: {
    name: 'VChart',
    template: '<div class="mock-vchart" :style="{width: width, height: height}"></div>',
    props: ['option', 'width', 'height', 'theme', 'loading', 'autoresize'],
    inheritAttrs: false,
  },
}))

// =============================================================================
// Mock browser APIs absent in jsdom
// =============================================================================

// ResizeObserver — used by Element Plus for responsive components
if (typeof global.ResizeObserver === 'undefined') {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

// IntersectionObserver — used for lazy loading and visibility
if (typeof global.IntersectionObserver === 'undefined') {
  global.IntersectionObserver = class IntersectionObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() { return [] }
    root = null
    rootMargin = ''
    thresholds = []
  }
}

// matchMedia — used by Element Plus for responsive breakpoints
if (typeof global.matchMedia === 'undefined') {
  global.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}

// ScrollTo — used by Element Plus for scroll behaviors
if (typeof global.scrollTo === 'undefined') {
  global.scrollTo = vi.fn() as unknown as typeof global.scrollTo
}

// localStorage — jsdom may not provide it; polyfill with a simple in-memory store
if (typeof global.localStorage === 'undefined') {
  const _store = new Map<string, string>()
  global.localStorage = {
    getItem: (key: string) => _store.get(key) ?? null,
    setItem: (key: string, value: string) => { _store.set(key, value) },
    removeItem: (key: string) => { _store.delete(key) },
    clear: () => { _store.clear() },
    get length() { return _store.size },
    key: (index: number) => [..._store.keys()][index] ?? null,
  } as typeof localStorage
}

// =============================================================================
// Mock Element Plus message/message-box/notification — avoid actual DOM popups
// =============================================================================
vi.mock('element-plus', async () => {
  const actual = await vi.importActual('element-plus')
  return {
    ...actual,
    ElMessage: {
      success: vi.fn(),
      warning: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
    },
    ElMessageBox: {
      confirm: vi.fn(() => Promise.resolve('confirm')),
      alert: vi.fn(() => Promise.resolve()),
      prompt: vi.fn(() => Promise.resolve({ value: '' })),
    },
    ElNotification: {
      success: vi.fn(),
      warning: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
    },
  }
})

// =============================================================================
// Suppress noisy console output during tests (optional — toggle as needed)
// =============================================================================
const originalWarn = console.warn
const originalError = console.error

// Uncomment to suppress specific warnings:
// console.warn = (...args: unknown[]) => {
//   const msg = String(args[0])
//   // Suppress Vue/Element Plus known warnings in jsdom
//   if (msg.includes('[Vue warn]') && msg.includes('non-standard')) return
//   if (msg.includes('Failed to resolve component')) return
//   originalWarn.call(console, ...args)
// }

// =============================================================================
// Restore globals after each test suite
// =============================================================================
// Note: vitest handles module mock cleanup automatically with vi.mock()
// Only restore manually-patched globals if needed
