// smoke.test.js — Verify test infrastructure is working
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import { createPinia, setActivePinia, defineStore } from 'pinia'

describe('Test Infrastructure Smoke', () => {

  it('mounts a simple Vue component', () => {
    const Comp = defineComponent({
      template: '<div class="hello">{{ msg }}</div>',
      props: { msg: { type: String, default: 'Hello' } },
    })
    const wrapper = mount(Comp, { props: { msg: 'World' } })
    expect(wrapper.text()).toBe('World')
    expect(wrapper.classes()).toContain('hello')
  })

  it('ResizeObserver is mocked globally', () => {
    expect(global.ResizeObserver).toBeDefined()
    const obs = new ResizeObserver(() => {})
    expect(obs.observe).toBeDefined()
  })

  it('IntersectionObserver is mocked globally', () => {
    expect(global.IntersectionObserver).toBeDefined()
  })

  it('matchMedia is mocked globally', () => {
    expect(global.matchMedia).toBeDefined()
    const mq = global.matchMedia('(min-width: 768px)')
    expect(mq.matches).toBe(false)
  })

  it('Element Plus icons resolve correctly', async () => {
    const { Edit, Search, Setting } = await import('@element-plus/icons-vue')
    expect(Edit).toBeDefined()
    expect(Search).toBeDefined()
    expect(Setting).toBeDefined()
  })

  it('ECharts is mocked', async () => {
    const echarts = await import('echarts')
    expect(echarts.init).toBeDefined()
    const instance = echarts.init(document.createElement('div'))
    expect(instance.setOption).toBeDefined()
  })

  it('Pinia store can be created', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const useTestStore = defineStore('test', {
      state: () => ({ count: 0 }),
      actions: { increment() { this.count++ } },
    })
    const store = useTestStore()
    expect(store.count).toBe(0)
    store.increment()
    expect(store.count).toBe(1)
  })

  it('vue-router can be created', () => {
    const router = createRouter({
      history: createWebHistory(),
      routes: [{ path: '/', component: { template: '<div>Home</div>' } }],
    })
    expect(router).toBeDefined()
    expect(router.currentRoute.value.path).toBe('/')
  })
})
