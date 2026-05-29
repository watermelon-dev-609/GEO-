<template>
  <router-view v-slot="{ Component }">
    <transition name="fade" mode="out-in">
      <component :is="Component" />
    </transition>
  </router-view>
</template>

<script setup>
import { onErrorCaptured } from 'vue'

onErrorCaptured((err, instance, info) => {
  console.error('[GEO] Render error:', err, info)
  return false
})
</script>

<style>
:root {
  /* ── Brand ── */
  --geo-primary: #C8963E;
  --geo-primary-light: #D4A855;
  --geo-primary-dark: #A07830;
  --geo-primary-bg: rgba(200, 150, 62, 0.08);
  --geo-primary-border: rgba(200, 150, 62, 0.18);

  /* ── Surface ── */
  --geo-bg: #F5F3EE;
  --geo-surface: #FFFFFF;
  --geo-surface-hover: #FAF8F5;
  --geo-surface-elevated: #FFFFFF;
  --geo-sidebar: #1E2030;
  --geo-sidebar-hover: #282B3D;
  --geo-sidebar-active: rgba(200, 150, 62, 0.12);
  --geo-terminal: #151721;

  /* ── Text ── */
  --geo-text: #2D3142;
  --geo-text-secondary: #6B6E7B;
  --geo-text-muted: #9B9EAA;
  --geo-text-inverse: #EDEBE8;
  --geo-text-sidebar: #B8BAC8;
  --geo-text-sidebar-active: #D4A855;

  /* ── Border ── */
  --geo-border: #E8E5DF;
  --geo-border-light: #F0EDE8;
  --geo-border-sidebar: #2A2D3E;

  /* ── Status ── */
  --geo-success: #5B8C5A;
  --geo-success-bg: rgba(91, 140, 90, 0.08);
  --geo-success-border: rgba(91, 140, 90, 0.18);
  --geo-warning: #D4956A;
  --geo-warning-bg: rgba(212, 149, 106, 0.08);
  --geo-warning-border: rgba(212, 149, 106, 0.18);
  --geo-danger: #C5554A;
  --geo-danger-bg: rgba(197, 85, 74, 0.08);
  --geo-danger-border: rgba(197, 85, 74, 0.18);
  --geo-info: #5B8AAC;
  --geo-info-bg: rgba(91, 138, 172, 0.08);
  --geo-info-border: rgba(91, 138, 172, 0.18);

  /* ── Radius ── */
  --geo-radius-sm: 6px;
  --geo-radius: 10px;
  --geo-radius-lg: 14px;
  --geo-radius-xl: 18px;

  /* ── Shadow ── */
  --geo-shadow-sm: 0 1px 2px rgba(45, 49, 66, 0.04);
  --geo-shadow: 0 2px 8px rgba(45, 49, 66, 0.06), 0 1px 3px rgba(45, 49, 66, 0.04);
  --geo-shadow-lg: 0 8px 24px rgba(45, 49, 66, 0.08), 0 2px 6px rgba(45, 49, 66, 0.04);
  --geo-shadow-xl: 0 16px 48px rgba(45, 49, 66, 0.1), 0 4px 12px rgba(45, 49, 66, 0.05);

  /* ── Transition ── */
  --geo-transition: 0.22s cubic-bezier(0.4, 0, 0.2, 1);
  --geo-transition-fast: 0.15s cubic-bezier(0.4, 0, 0.2, 1);
  --geo-transition-slow: 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

/* ── Element Plus Overrides ── */
:root {
  --el-color-primary: #C8963E;
  --el-color-primary-light-3: #D4A855;
  --el-color-primary-light-5: #DDB970;
  --el-color-primary-light-7: #E8CF9A;
  --el-color-primary-light-8: #EFDDB8;
  --el-color-primary-light-9: #F7EEDA;
  --el-color-primary-dark-2: #A07830;
  --el-color-success: #5B8C5A;
  --el-color-warning: #D4956A;
  --el-color-danger: #C5554A;
  --el-color-info: #5B8AAC;
  --el-border-color-base: #E8E5DF;
  --el-border-color-light: #F0EDE8;
  --el-border-color-lighter: #F5F3EE;
  --el-border-radius-base: 6px;
  --el-border-radius-small: 4px;
  --el-border-radius-round: 20px;
  --el-bg-color: #FFFFFF;
  --el-bg-color-page: #F5F3EE;
  --el-text-color-primary: #2D3142;
  --el-text-color-regular: #4A4D5A;
  --el-text-color-secondary: #6B6E7B;
  --el-text-color-placeholder: #9B9EAA;
  --el-box-shadow-light: 0 2px 8px rgba(45, 49, 66, 0.06);
  --el-box-shadow: 0 4px 16px rgba(45, 49, 66, 0.08);
}

* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', sans-serif;
  background: var(--geo-bg);
  color: var(--geo-text);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
#app { min-height: 100vh; }

/* ── Route transitions ── */
.fade-enter-active, .fade-leave-active { transition: opacity 0.25s ease, transform 0.25s ease; }
.fade-enter-from { opacity: 0; transform: translateY(6px); }
.fade-leave-to { opacity: 0; transform: translateY(-4px); }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #D0CDC6; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #B0ADA6; }

/* ── Global card refinement ── */
.el-card {
  border-radius: var(--geo-radius) !important;
  border-color: var(--geo-border) !important;
  box-shadow: var(--geo-shadow-sm) !important;
  transition: box-shadow var(--geo-transition);
}
.el-card:hover { box-shadow: var(--geo-shadow) !important; }

/* ── Button refinement ── */
.el-button {
  border-radius: var(--geo-radius-sm);
  font-weight: 500;
  transition: all var(--geo-transition-fast);
}
.el-button--primary {
  background: var(--geo-primary);
  border-color: var(--geo-primary);
}
.el-button--primary:hover {
  background: var(--geo-primary-light);
  border-color: var(--geo-primary-light);
}

/* ── Tag refinement ── */
.el-tag {
  border-radius: 4px;
  font-weight: 500;
}

/* ── Dialog refinement ── */
.el-dialog {
  border-radius: var(--geo-radius-lg);
}
.el-dialog__header {
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--geo-border);
}
.el-dialog__body { padding: 20px 24px; }

/* ── Menu (sidebar) ── */
.el-menu {
  border-right: none !important;
}

/* ── Input / Textarea ── */
.el-input__wrapper, .el-textarea__inner {
  border-radius: var(--geo-radius-sm);
  box-shadow: none !important;
  transition: border-color var(--geo-transition-fast), box-shadow var(--geo-transition-fast);
}
.el-input__wrapper:hover, .el-textarea__inner:hover { border-color: var(--geo-primary-light); }
.el-input.is-focus .el-input__wrapper,
.el-textarea__inner:focus {
  border-color: var(--geo-primary);
  box-shadow: 0 0 0 2px var(--geo-primary-bg) !important;
}

/* ── Select ── */
.el-select .el-input.is-focus .el-input__wrapper {
  box-shadow: 0 0 0 2px var(--geo-primary-bg) !important;
}

/* ── Tabs ── */
.el-tabs__item.is-active { color: var(--geo-primary); }
.el-tabs__active-bar { background-color: var(--geo-primary); }
.el-tabs__item:hover { color: var(--geo-primary-light); }

/* ── Table ── */
.el-table th.el-table__cell {
  background: var(--geo-surface-hover);
  color: var(--geo-text-secondary);
  font-weight: 600;
  font-size: 13px;
}
.el-table tr { transition: background var(--geo-transition-fast); }

/* ── Switch ── */
.el-switch.is-checked .el-switch__core {
  background: var(--geo-success);
  border-color: var(--geo-success);
}

/* ── Progress ── */
.el-progress-bar__outer { border-radius: 4px; background: var(--geo-border-light); }
.el-progress-bar__inner { border-radius: 4px; }

/* ── Empty ── */
.el-empty__description { color: var(--geo-text-muted); }

/* ── Alert ── */
.el-alert { border-radius: var(--geo-radius); }

/* ── Slider ── */
.el-slider__bar { background: var(--geo-primary); }
.el-slider__button { border-color: var(--geo-primary); }
</style>
