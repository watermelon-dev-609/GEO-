<template>
  <div class="dashboard">
    <div class="welcome">
      <h1>GEO生成式搜索优化系统</h1>
      <p>武汉微艺达智能科技有限公司 · 全平台AI品牌优先曝光 · 纯白帽合规优化</p>
    </div>

    <el-row :gutter="20" class="quick-actions">
      <el-col :span="6" v-for="action in quickActions" :key="action.path">
        <el-card shadow="hover" class="action-card" @click="$router.push(action.path)">
          <div class="action-icon" :style="{ background: action.color }">
            <el-icon :size="28"><component :is="action.icon" /></el-icon>
          </div>
          <div class="action-info">
            <h3>{{ action.title }}</h3>
            <p>{{ action.desc }}</p>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 24px;">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>AI平台配置状态</span>
              <el-button size="small" type="primary" link @click="refreshConfig">刷新</el-button>
            </div>
          </template>
          <div class="platform-grid">
            <div v-for="plat in llmConfigs" :key="plat.platform" class="platform-item">
              <el-tag :type="plat.configured ? 'success' : 'info'" size="default" effect="plain">
                {{ plat.platform }}
              </el-tag>
              <span class="plat-status">{{ plat.configured ? '✓ 已配置' : '✗ 待配置' }}</span>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <span>操作指引</span>
          </template>
          <el-steps direction="vertical" :active="activeGuideStep" finish-status="success">
            <el-step title="第一步：配置API Key" description="编辑 config/api_keys.yaml 填入至少一个AI平台的API Key" />
            <el-step title="第二步：导入文案" description="粘贴或上传需要优化的企业文案" />
            <el-step title="第三步：GEO智能优化" description="选择沙盘业务类型和目标AI平台，一键生成优化文案" />
            <el-step title="第四步：效果评测" description="模拟真实用户提问，检测AI曝光和品牌采信效果" />
            <el-step title="第五步：成果导出" description="下载优化文案、JSON-LD代码和评测报告" />
          </el-steps>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" style="margin-top: 24px;" v-if="recentProjects.length > 0">
      <template #header><span>最近项目</span></template>
      <el-table :data="recentProjects" style="width: 100%" size="small">
        <el-table-column prop="name" label="项目名称" />
        <el-table-column prop="sandtableType" label="沙盘类型" width="150" />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column prop="time" label="时间" width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useGeoStore } from '../stores/geo'
import { getLLMConfig } from '../api'

const store = useGeoStore()

const quickActions = [
  { path: '/import', title: '文案导入', desc: '导入、清洗标准化文案', icon: 'DocumentAdd', color: '#409EFF' },
  { path: '/workshop', title: 'GEO优化工坊', desc: '八大沙盘×七大平台专项优化', icon: 'EditPen', color: '#67C23A' },
  { path: '/evaluation', title: 'AI评测中心', desc: '模拟评测·品牌采信分析', icon: 'DataAnalysis', color: '#E6A23C' },
  { path: '/export', title: '成果导出', desc: '文案·代码·报表一键导出', icon: 'Download', color: '#B37FEB' },
]

const llmConfigs = computed(() => store.llmConfigs)
const recentProjects = computed(() => store.projectHistory.slice(0, 5))
const activeGuideStep = computed(() => {
  if (store.hasEvaluation) return 5
  if (store.hasResults) return 4
  if (store.hasCleanedText) return 3
  if (store.originalText) return 2
  return 1
})

async function refreshConfig() {
  try {
    const res = await getLLMConfig()
    store.setLLMConfigs(res.data.llm_platforms || [])
  } catch { /* ignore */ }
}
</script>

<style scoped>
.dashboard { max-width: 1200px; }
.welcome { margin-bottom: 28px; }
.welcome h1 { font-size: 24px; color: #303133; margin-bottom: 8px; }
.welcome p { font-size: 14px; color: #909399; }
.quick-actions { margin-bottom: 0; }
.action-card { cursor: pointer; transition: transform .2s; }
.action-card:hover { transform: translateY(-2px); }
.action-card .el-card__body { display: flex; align-items: center; gap: 16px; padding: 20px; }
.action-icon { width: 52px; height: 52px; border-radius: 12px; display: flex; align-items: center; justify-content: center; color: #fff; }
.action-info h3 { font-size: 16px; margin-bottom: 4px; color: #303133; }
.action-info p { font-size: 12px; color: #909399; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.platform-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.platform-item { display: flex; align-items: center; gap: 8px; }
.plat-status { font-size: 13px; color: #606266; }
</style>
