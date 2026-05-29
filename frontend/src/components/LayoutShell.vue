<template>
  <el-container class="layout">
    <el-aside width="220px" class="sidebar">
      <div class="logo">
        <span class="logo-icon">🎯</span>
        <div class="logo-text">
          <div class="logo-title">GEO优化系统</div>
          <div class="logo-sub">武汉微艺达智能科技</div>
        </div>
      </div>

      <el-menu
        :default-active="activeMenu"
        router
        background-color="#1E2030"
        text-color="#B8BAC8"
        active-text-color="#D4A855"
      >
        <el-menu-item index="/dashboard">
          <el-icon><HomeFilled /></el-icon>
          <span>工作台</span>
        </el-menu-item>
        <el-menu-item index="/import">
          <el-icon><DocumentAdd /></el-icon>
          <span>文案导入</span>
        </el-menu-item>
        <el-menu-item index="/workshop">
          <el-icon><EditPen /></el-icon>
          <span>GEO优化工坊</span>
        </el-menu-item>
        <el-menu-item index="/evaluation">
          <el-icon><DataAnalysis /></el-icon>
          <span>AI评测中心</span>
        </el-menu-item>
        <el-menu-item index="/export">
          <el-icon><Download /></el-icon>
          <span>成果导出</span>
        </el-menu-item>
        <div class="menu-divider">策略中心</div>
        <el-menu-item index="/strategy">
          <el-icon><TrendCharts /></el-icon>
          <span>策略中心</span>
        </el-menu-item>
        <el-menu-item index="/templates">
          <el-icon><Document /></el-icon>
          <span>内容规范</span>
        </el-menu-item>
      </el-menu>

      <div class="sidebar-footer">
        <div class="config-status">
          <el-tag :type="hasConfiguredLLM ? 'success' : 'warning'" size="small" effect="dark">
            {{ hasConfiguredLLM ? 'LLM已配置' : '待配置LLM' }}
          </el-tag>
        </div>
        <el-button size="small" text type="primary" @click="showConfigDialog = true" style="width:100%;margin-top:6px;">
          配置API Key
        </el-button>
        <div class="version">v1.0.0 Personal</div>
      </div>
    </el-aside>

    <!-- API Key 配置弹窗 -->
    <el-dialog v-model="showConfigDialog" title="API Key 配置" width="600px" :destroy-on-close="true" @open="loadConfigForDialog">
      <el-form label-position="top">
        <div v-for="plat in configPlatforms" :key="plat.platform" class="config-plat-row">
          <div class="config-plat-header">
            <span class="config-plat-name">{{ plat.platform }}</span>
            <el-tag :type="plat.configured ? 'success' : 'danger'" size="small">{{ plat.configured ? '已配置' : '未配置' }}</el-tag>
          </div>
          <el-input
            v-model="plat.apiKey"
            type="password"
            show-password
            placeholder="输入 API Key"
            size="small"
          />
          <el-button size="small" type="primary" @click="saveApiKey(plat)" style="margin-top:4px;" :loading="plat._saving">
            保存
          </el-button>
        </div>
      </el-form>
    </el-dialog>

    <el-container>
      <el-header class="topbar">
        <div class="topbar-left">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/dashboard' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item>{{ currentPageTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
          <div class="pipeline-steps">
            <div
              v-for="(step, i) in pipelineSteps"
              :key="step.path"
              class="pipeline-step"
              :class="{ active: i === activePipelineStep, done: i < activePipelineStep }"
              @click="navigateToStep(step.path)"
            >
              <span class="step-dot">{{ i < activePipelineStep ? '✓' : i + 1 }}</span>
              <span class="step-label">{{ step.label }}</span>
              <span v-if="i < pipelineSteps.length - 1" class="step-line" />
            </div>
          </div>
        </div>
        <div class="topbar-right">
          <el-button size="small" @click="checkConfig" :icon="Setting">配置检查</el-button>
          <el-button size="small" type="primary" @click="checkHealth" :icon="Connection">服务状态</el-button>
        </div>
      </el-header>

      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useGeoStore } from '../stores/geo'
import { getLLMConfig, healthCheck } from '../api'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const route = useRoute()
const router = useRouter()
const store = useGeoStore()

const activeMenu = computed(() => route.path)
const currentPageTitle = computed(() => route.meta?.title || '')
const hasConfiguredLLM = computed(() => store.configuredPlatforms.length > 0)

function navigateToStep(path) {
  if (route.path !== path) {
    router.push(path)
  }
}

// ── 流水线步骤指示器 ──
const pipelineSteps = [
  { path: '/import', label: '文案导入', order: 0 },
  { path: '/workshop', label: 'GEO优化', order: 1 },
  { path: '/evaluation', label: 'AI评测', order: 2 },
  { path: '/export', label: '成果导出', order: 3 },
]

const activePipelineStep = computed(() => {
  // 根据 store 状态判断当前处于第几步
  if (store.hasEvaluation) return 3  // 评测完成，进入导出
  if (store.hasResults) return 2     // 优化完成，进入评测
  if (store.hasCleanedText) return 1 // 清洗完成，进入优化
  return 0                            // 导入
})

// ── API Key 配置弹窗 ──
const showConfigDialog = ref(false)
const configPlatforms = ref([])

async function loadConfigForDialog() {
  try {
    const res = await getLLMConfig()
    configPlatforms.value = (res.data.llm_platforms || []).map(p => ({
      ...p,
      apiKey: '',
      _saving: false,
    }))
  } catch (e) {
    ElMessage.error('加载配置失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function saveApiKey(plat) {
  if (!plat.apiKey.trim()) {
    ElMessage.warning('请输入 API Key')
    return
  }
  plat._saving = true
  try {
    await axios.post('/api/config/llm/update', {
      platform: plat.platform,
      api_key: plat.apiKey.trim(),
    })
    plat.configured = true
    // 刷新全局 LLM 配置状态
    const res = await getLLMConfig()
    store.setLLMConfigs(res.data.llm_platforms || [])
    ElMessage.success(`${plat.platform} 已保存并立即生效`)
    plat.apiKey = ''
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    plat._saving = false
  }
}

onMounted(async () => {
  try {
    const res = await getLLMConfig()
    store.setLLMConfigs(res.data.llm_platforms || [])
  } catch (e) {
    ElMessage.warning('LLM配置加载失败，请检查后端服务是否启动')
  }
})

async function checkHealth() {
  try {
    const res = await healthCheck()
    ElMessage.success(`服务正常 v${res.data.version}`)
  } catch (e) { console.error('checkHealth failed:', e); ElMessage.error('后端服务未启动')
  }
}

async function checkConfig() {
  try {
    const res = await getLLMConfig()
    store.setLLMConfigs(res.data.llm_platforms || [])
    const configured = res.data.llm_platforms?.filter(p => p.configured) || []
    if (configured.length === 0) {
      ElMessage.warning('暂未配置任何LLM平台，请编辑 config/api_keys.yaml 填入API Key')
    } else {
      ElMessage.success(`已配置 ${configured.length} 个AI平台: ${configured.map(c => c.platform).join(', ')}`)
    }
  } catch (e) { console.error('checkConfig failed:', e); ElMessage.error('无法获取配置')
  }
}
</script>

<style scoped>
.layout { height: 100vh; }
.sidebar {
  background: var(--geo-sidebar);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--geo-border-sidebar);
}

/* ── Logo ── */
.logo {
  padding: 22px 18px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid var(--geo-border-sidebar);
}
.logo-icon {
  width: 38px; height: 38px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--geo-primary), var(--geo-primary-dark));
  display: flex; align-items: center; justify-content: center;
  font-size: 18px;
  box-shadow: 0 2px 8px rgba(200, 150, 62, 0.25);
}
.logo-title { font-size: 15px; font-weight: 700; color: var(--geo-text-inverse); letter-spacing: 0.3px; }
.logo-sub { font-size: 11px; color: var(--geo-text-sidebar); margin-top: 2px; }

/* ── Menu ── */
.sidebar .el-menu {
  border-right: none;
  flex: 1;
  padding: 8px 0;
}
.sidebar :deep(.el-menu-item) {
  margin: 2px 10px;
  border-radius: 8px;
  height: 42px;
  line-height: 42px;
  font-size: 14px;
  transition: all var(--geo-transition-fast);
}
.sidebar :deep(.el-menu-item:hover) {
  background: var(--geo-sidebar-hover) !important;
}
.sidebar :deep(.el-menu-item.is-active) {
  background: var(--geo-sidebar-active) !important;
  color: var(--geo-text-sidebar-active) !important;
  font-weight: 600;
}
.sidebar :deep(.el-menu-item .el-icon) { font-size: 17px; }

/* divider label */
.sidebar :deep(.menu-divider) {
  padding: 8px 20px;
  font-size: 10px;
  color: var(--geo-text-muted);
  text-transform: uppercase;
  letter-spacing: 1.5px;
  font-weight: 600;
}

/* ── Footer ── */
.sidebar-footer {
  padding: 14px 16px;
  border-top: 1px solid var(--geo-border-sidebar);
  text-align: center;
}
.config-status { margin-bottom: 8px; }
.version { font-size: 10px; color: var(--geo-text-muted); margin-top: 8px; letter-spacing: 0.5px; }

/* ── Topbar ── */
.topbar {
  background: var(--geo-surface);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  height: 58px;
  border-bottom: 1px solid var(--geo-border);
  box-shadow: 0 1px 3px rgba(45, 49, 66, 0.03);
  position: relative;
  z-index: 10;
}
.topbar-left { display: flex; align-items: center; gap: 36px; }
.topbar-right { display: flex; gap: 8px; }

/* ── Pipeline ── */
.pipeline-steps { display: flex; align-items: center; }
.pipeline-step {
  display: flex; align-items: center;
  cursor: pointer;
  font-size: 12px;
  color: var(--geo-text-muted);
  white-space: nowrap;
  transition: all var(--geo-transition);
  font-weight: 500;
}
.pipeline-step.active { color: var(--geo-primary); font-weight: 700; }
.pipeline-step.done { color: var(--geo-success); }
.step-dot {
  display: inline-flex; align-items: center; justify-content: center;
  width: 20px; height: 20px;
  border-radius: 50%;
  font-size: 10px;
  margin-right: 5px;
  border: 1.5px solid currentColor;
  transition: all var(--geo-transition);
}
.pipeline-step.active .step-dot {
  background: var(--geo-primary);
  color: #fff;
  border-color: var(--geo-primary);
  box-shadow: 0 2px 6px rgba(200, 150, 62, 0.3);
}
.pipeline-step.done .step-dot {
  background: var(--geo-success);
  color: #fff;
  border-color: var(--geo-success);
}
.step-line {
  display: inline-block;
  width: 22px;
  height: 1.5px;
  background: #d5d2cc;
  margin: 0 7px;
  transition: background var(--geo-transition);
}
.pipeline-step.done ~ .pipeline-step .step-line,
.pipeline-step.done .step-line { background: var(--geo-success); }

/* ── Main Content ── */
.main-content {
  background: var(--geo-bg);
  padding: 28px 28px 40px;
  overflow-y: auto;
}

/* ── Config Dialog ── */
.config-plat-row {
  margin-bottom: 16px;
  padding: 14px;
  background: var(--geo-surface-hover);
  border-radius: var(--geo-radius);
  border: 1px solid var(--geo-border);
  transition: border-color var(--geo-transition-fast);
}
.config-plat-row:hover { border-color: var(--geo-primary-border); }
.config-plat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.config-plat-name { font-weight: 600; font-size: 14px; color: var(--geo-text); }
</style>
