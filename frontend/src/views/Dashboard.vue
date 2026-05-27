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

    <!-- 评测概览 -->
    <el-row :gutter="20" style="margin-top: 24px;">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>最近评测</span>
              <el-button size="small" type="primary" link @click="$router.push('/evaluation')">
                查看全部
              </el-button>
            </div>
          </template>
          <div v-if="evalHistory.length === 0" class="card-empty">
            <p>暂无评测数据</p>
            <el-button size="small" type="primary" @click="$router.push('/evaluation')">开始评测</el-button>
          </div>
          <div v-else>
            <div v-for="item in evalHistory.slice(0, 3)" :key="item.session_id" class="eval-mini-item">
              <span class="eval-mini-date">{{ formatShortDate(item.created_at) }}</span>
              <el-tag size="small" type="info">{{ item.sandtable_type || '未知' }}</el-tag>
              <el-progress
                :percentage="item.overall_score || 0"
                :color="item.overall_score >= 80 ? '#67C23A' : item.overall_score >= 60 ? '#E6A23C' : '#F56C6C'"
                :stroke-width="6"
                style="flex:1; min-width: 80px;"
              />
              <span class="eval-mini-score" :style="{ color: item.overall_score >= 80 ? '#67C23A' : item.overall_score >= 60 ? '#E6A23C' : '#F56C6C' }">
                {{ item.overall_score ?? '-' }}分
              </span>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span>评分概览</span></template>
          <div v-if="avgEvalScore === null" class="card-empty">
            <p>暂无评测数据</p>
          </div>
          <div v-else class="score-overview">
            <div class="overview-number">{{ avgEvalScore }}</div>
            <div class="overview-label">平均分 / 100</div>
            <div class="overview-trend" :style="{ color: scoreTrendIcon === 'up' ? '#67C23A' : '#F56C6C' }">
              {{ scoreTrendIcon === 'up' ? '↑ 呈上升趋势' : '↓ 有所下降' }}
            </div>
            <div class="overview-count">共 {{ evalHistory.filter(h => h.overall_score != null).length }} 次评测</div>
            <el-button size="small" type="primary" @click="$router.push('/evaluation')" style="margin-top: 12px;">
              开始评测
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 全域覆盖矩阵 -->
    <el-row :gutter="20" style="margin-top: 24px;">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>全域覆盖矩阵</span>
              <span style="font-size:12px;color:#909399;">
                已优化 {{ optimizedPlatformCount }}/7 平台
                <span v-if="currentSandtable" style="margin-left:8px;">| 当前沙盘: {{ currentSandtable }}</span>
              </span>
            </div>
          </template>
          <div class="coverage-matrix">
            <div class="matrix-header">
              <span class="matrix-label">平台</span>
              <span v-for="p in allPlatforms" :key="p.value" class="matrix-col-header" :class="{ configured: isPlatformConfigured(p.value) }">
                {{ p.label }}
              </span>
            </div>
            <div class="matrix-row">
              <span class="matrix-label">优化状态</span>
              <span v-for="p in allPlatforms" :key="p.value" class="matrix-cell">
                <el-tag v-if="isPlatformOptimized(p.value)" type="success" size="small" effect="dark">已优化</el-tag>
                <el-tag v-else-if="isPlatformConfigured(p.value)" type="warning" size="small">可优化</el-tag>
                <el-tag v-else type="info" size="small">未配置</el-tag>
              </span>
            </div>
            <div class="matrix-row">
              <span class="matrix-label">详情</span>
              <span v-for="p in allPlatforms" :key="p.value" class="matrix-cell">
                <template v-if="getPlatformResult(p.value)">
                  <span style="font-size:12px;color:#606266;">{{ getPlatformResult(p.value).word_count }}字</span>
                </template>
                <template v-else>
                  <span style="font-size:12px;color:#c0c4cc;">—</span>
                </template>
              </span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" style="margin-top: 24px;" v-if="recentProjects.length > 0">
      <template #header>
        <span>最近项目</span>
        <span style="font-size:12px;color:#909399;margin-left:8px;">点击行可跳转继续工作</span>
      </template>
      <el-table :data="recentProjects" style="width: 100%" size="small" @row-click="onProjectClick" :row-style="{ cursor: 'pointer' }">
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
import { useRouter } from 'vue-router'
import { useGeoStore } from '../stores/geo'
import { getLLMConfig, getEvalHistory } from '../api'

const router = useRouter()
const store = useGeoStore()

const evalHistory = ref([])
const evalHistoryLoading = ref(false)

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

const avgEvalScore = computed(() => {
  const scored = evalHistory.value.filter(h => h.overall_score != null)
  if (scored.length === 0) return null
  return (scored.reduce((s, h) => s + h.overall_score, 0) / scored.length).toFixed(1)
})
const scoreTrendIcon = computed(() => {
  const scored = evalHistory.value.filter(h => h.overall_score != null)
  if (scored.length < 2) return null
  return scored[0].overall_score >= scored[1].overall_score ? 'up' : 'down'
})

const allPlatforms = [
  { value: 'wenxin', label: '文心' },
  { value: 'tongyi', label: '通义' },
  { value: 'gpt', label: 'GPT' },
  { value: 'claude', label: 'Claude' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'doubao', label: '豆包' },
  { value: 'yuanbao', label: '元宝' },
]

const optimizedPlatformCount = computed(() => {
  const optimized = new Set(store.rewriteResults.map(r => r.platform))
  return optimized.size
})

const currentSandtable = computed(() => {
  const type = store.currentSandtableType
  const map = {
    smart_traffic: '智慧交通', smart_city: '智慧城市', smart_industry: '智慧工业',
    smart_agriculture: '智慧农业', smart_logistics: '智慧物流', military_terrain: '军事地形',
    digital_multimedia: '数字多媒体', real_estate: '地产/规划/展厅',
  }
  return map[type] || ''
})

function isPlatformConfigured(platform) {
  return store.llmConfigs.some(c => c.platform === platform && c.configured)
}

function isPlatformOptimized(platform) {
  return store.rewriteResults.some(r => r.platform === platform)
}

function getPlatformResult(platform) {
  return store.rewriteResults.find(r => r.platform === platform)
}

async function refreshConfig() {
  try {
    const res = await getLLMConfig()
    store.setLLMConfigs(res.data.llm_platforms || [])
  } catch { /* ignore */ }
}

async function loadEvalHistory() {
  evalHistoryLoading.value = true
  try {
    const res = await getEvalHistory()
    evalHistory.value = res.data.items || []
  } catch { /* ignore */ }
  finally { evalHistoryLoading.value = false }
}

function onProjectClick(row) {
  const pageMap = {
    '文案清洗': '/import',
    'GEO优化': '/workshop',
    'AI评测': '/evaluation',
  }
  const target = pageMap[row.name] || '/dashboard'
  router.push(target)
}

function formatShortDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

onMounted(async () => {
  try {
    const res = await getLLMConfig()
    store.setLLMConfigs(res.data.llm_platforms || [])
  } catch { /* ignore */ }
  loadEvalHistory()
})
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
.card-empty { text-align: center; padding: 32px 0; color: #909399; }
.eval-mini-item { display: flex; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid #f5f5f5; }
.eval-mini-item:last-child { border-bottom: none; }
.eval-mini-date { font-size: 12px; color: #909399; min-width: 42px; }
.eval-mini-score { font-size: 16px; font-weight: bold; min-width: 52px; text-align: right; }
.score-overview { text-align: center; padding: 16px 0; }
.overview-number { font-size: 56px; font-weight: bold; color: #409EFF; }
.overview-label { font-size: 14px; color: #909399; margin-top: 4px; }
.overview-trend { font-size: 14px; font-weight: bold; margin-top: 8px; }
.overview-count { font-size: 13px; color: #909399; margin-top: 4px; }
.coverage-matrix { overflow-x: auto; }
.matrix-header, .matrix-row { display: flex; align-items: center; gap: 0; padding: 6px 0; }
.matrix-header { font-weight: bold; border-bottom: 2px solid #ebeef5; padding-bottom: 10px; }
.matrix-label { width: 80px; font-size: 13px; color: #606266; flex-shrink: 0; }
.matrix-col-header { flex: 1; min-width: 70px; text-align: center; font-size: 13px; color: #909399; }
.matrix-col-header.configured { color: #409EFF; }
.matrix-cell { flex: 1; min-width: 70px; text-align: center; }
</style>
