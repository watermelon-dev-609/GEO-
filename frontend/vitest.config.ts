import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  test: {
    // jsdom environment for DOM-dependent component tests
    environment: 'jsdom',

    // Global test setup file
    setupFiles: ['./src/__tests__/setup.ts'],

    // Look for test files anywhere in src/
    include: ['src/**/*.{test,spec}.{js,ts,jsx,tsx}'],

    // Globals like describe, it, expect (no imports needed)
    globals: true,

    // CSS handling
    css: {
      modules: {
        classNameStrategy: 'non-scoped',
      },
    },

    // Inline Element Plus for proper ESM handling in jsdom
    server: {
      deps: {
        inline: ['element-plus'],
      },
    },
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
})
