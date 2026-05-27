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
        background-color="#1d1e2c"
        text-color="#a0a4b8"
        active-text-color="#409EFF"
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
      </el-menu>

      <div class="sidebar-footer">
        <div class="config-status">
          <el-tag :type="hasConfiguredLLM ? 'success' : 'warning'" size="small" effect="dark">
            {{ hasConfiguredLLM ? 'LLM已配置' : '待配置LLM' }}
          </el-tag>
        </div>
        <div class="version">v1.0.0 Personal</div>
      </div>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <div class="topbar-left">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/dashboard' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item>{{ currentPageTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
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
import { useRoute } from 'vue-router'
import { useGeoStore } from '../stores/geo'
import { getLLMConfig, healthCheck } from '../api'
import { ElMessage } from 'element-plus'

const route = useRoute()
const store = useGeoStore()

const activeMenu = computed(() => route.path)
const currentPageTitle = computed(() => route.meta?.title || '')
const hasConfiguredLLM = computed(() => store.configuredPlatforms.length > 0)

onMounted(async () => {
  try {
    const res = await getLLMConfig()
    store.setLLMConfigs(res.data.llm_platforms || [])
  } catch { /* ignore */ }
})

async function checkHealth() {
  try {
    const res = await healthCheck()
    ElMessage.success(`服务正常 v${res.data.version}`)
  } catch {
    ElMessage.error('后端服务未启动')
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
  } catch {
    ElMessage.error('无法获取配置')
  }
}
</script>

<style scoped>
.layout { height: 100vh; }
.sidebar { background: #1d1e2c; overflow-y: auto; display: flex; flex-direction: column; }
.logo { padding: 20px 16px; display: flex; align-items: center; gap: 10px; border-bottom: 1px solid #2d2e3c; }
.logo-icon { font-size: 28px; }
.logo-title { font-size: 15px; font-weight: bold; color: #fff; }
.logo-sub { font-size: 11px; color: #909399; margin-top: 2px; }
.sidebar .el-menu { border-right: none; flex: 1; }
.sidebar-footer { padding: 12px 16px; border-top: 1px solid #2d2e3c; text-align: center; }
.config-status { margin-bottom: 6px; }
.version { font-size: 11px; color: #606266; }
.topbar { background: #fff; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #ebeef5; padding: 0 24px; height: 56px; }
.topbar-right { display: flex; gap: 8px; }
.main-content { background: #f5f7fa; padding: 24px; overflow-y: auto; }
</style>
