<template>
  <div class="dashboard">
    <div class="welcome">
      <h1>GEO生成式搜索优化系统</h1>
      <p>{{ store.enterpriseName || 'GEO生成式搜索优化平台' }} · 全平台AI品牌优先曝光 · 纯白帽合规优化</p>
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

    <!-- 数据看板 -->
    <div v-loading="analyticsLoading" style="min-height:100px;">
      <el-result
        v-if="analyticsError"
        icon="error"
        title="数据加载失败"
        sub-title="无法获取看板数据，请检查后端服务"
      >
        <template #extra>
          <el-button type="primary" @click="loadAnalytics">重试</el-button>
        </template>
      </el-result>
      <el-empty
        v-else-if="!analyticsLoading && (!analytics || !analytics.overview || analytics.overview.scored_evaluations === 0)"
        description="暂无评测数据，请先完成AI评测"
      >
        <el-button type="primary" @click="$router.push('/evaluation')">开始评测</el-button>
      </el-empty>
      <el-row v-else :gutter="20" style="margin-top:24px;">
        <el-col :span="6">
          <el-card shadow="never" class="stat-card">
            <div class="stat-number" style="color:#C8963E;">{{ analytics.overview.scored_evaluations ?? 0 }}</div>
            <div class="stat-label">累计评测</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="stat-card">
            <div class="stat-number" style="color:#5B8C5A;">{{ analytics.overview.average_score ?? '-' }}</div>
            <div class="stat-label">平均评分</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="stat-card">
            <div class="stat-number" style="color:#D4956A;">{{ analytics.overview.improvement_rate ?? 0 }}%</div>
            <div class="stat-label">优化改进率</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="stat-card">
            <div class="stat-number" style="color:#8065E6;">{{ Object.keys(analytics.dimension_averages || {}).length }}</div>
            <div class="stat-label">监测维度</div>
          </el-card>
        </el-col>
      </el-row>
    </div>

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
          <div v-if="evalHistoryLoading" class="card-empty">
            <p>加载中...</p>
          </div>
          <div v-else-if="evalHistory.length === 0" class="card-empty">
            <p>暂无评测数据</p>
            <el-button size="small" type="primary" @click="$router.push('/evaluation')">开始评测</el-button>
          </div>
          <div v-else>
            <div v-for="item in evalHistory.slice(0, 3)" :key="item.session_id" class="eval-mini-item">
              <span class="eval-mini-date">{{ formatShortDate(item.created_at) }}</span>
              <el-tag size="small" type="info">{{ item.sandtable_type || '未知' }}</el-tag>
              <el-progress
                :percentage="item.overall_score || 0"
                :color="scoreColor(item.overall_score || 0)"
                :stroke-width="6"
                style="flex:1; min-width: 80px;"
              />
              <span class="eval-mini-score" :style="{ color: scoreColor(item.overall_score || 0) }">
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
            <div v-if="scoreTrendIcon === null" class="overview-trend" style="color:#9B9EAA;">
              数据不足，无法分析趋势
            </div>
            <div v-else class="overview-trend" :style="{ color: scoreTrendIcon === 'up' ? '#5B8C5A' : '#C5554A' }">
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
              <span style="font-size:12px;color:#9B9EAA;">
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
                  <span style="font-size:12px;color:#6B6E7B;">{{ getPlatformResult(p.value).word_count }}字</span>
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
        <span style="font-size:12px;color:#9B9EAA;margin-left:8px;">点击行可跳转继续工作</span>
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
import { getLLMConfig, getEvalHistory, getAnalyticsOverview } from '../api'
import { ElMessage } from 'element-plus'
import { SANDTABLE_LABELS, AI_PLATFORMS, scoreColor } from '../constants'

const router = useRouter()
const store = useGeoStore()

const evalHistory = ref([])
const evalHistoryLoading = ref(false)
const analytics = ref(null)
const analyticsLoading = ref(false)
const analyticsError = ref(false)

const quickActions = [
  { path: '/import', title: '文案导入', desc: '导入、清洗标准化文案', icon: 'DocumentAdd', color: '#C8963E' },
  { path: '/workshop', title: 'GEO优化工坊', desc: '八大沙盘×七大平台专项优化', icon: 'EditPen', color: '#5B8C5A' },
  { path: '/evaluation', title: 'AI评测中心', desc: '模拟评测·品牌采信分析', icon: 'DataAnalysis', color: '#5B8AAC' },
  { path: '/export', title: '成果导出', desc: '文案·代码·报表一键导出', icon: 'Download', color: '#8065E6' },
  { path: '/full-funnel', title: '全域转化漏斗', desc: '追踪AI引用→流量→转化全链路ROI', icon: 'TrendCharts', color: '#D4956A' },
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

const allPlatforms = AI_PLATFORMS

const optimizedPlatformCount = computed(() => {
  const optimized = new Set(store.rewriteResults.map(r => r.platform))
  return optimized.size
})

const currentSandtable = computed(() => {
  return SANDTABLE_LABELS[store.currentSandtableType] || ''
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
    ElMessage.success('配置已刷新')
  } catch (e) { ElMessage.error('配置刷新失败: ' + (e.response?.data?.detail || e.message)) }
}

async function loadEvalHistory() {
  evalHistoryLoading.value = true
  try {
    const res = await getEvalHistory()
    evalHistory.value = res.data.items || []
  } catch (e) { ElMessage.error('评测历史加载失败: ' + (e.response?.data?.detail || e.message)) }
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
  if (isNaN(d.getTime())) return ''
  return `${d.getMonth() + 1}/${d.getDate()}`
}

async function loadAnalytics() {
  analyticsLoading.value = true
  analyticsError.value = false
  try {
    const res = await getAnalyticsOverview()
    analytics.value = res.data
  } catch (e) {
    analyticsError.value = true
    if (e.response?.status !== 404) {
      ElMessage.warning('数据看板加载失败: ' + (e.response?.data?.detail || e.message))
    }
  } finally {
    analyticsLoading.value = false
  }
}

onMounted(async () => {
  try {
    const res = await getLLMConfig()
    store.setLLMConfigs(res.data.llm_platforms || [])
  } catch (e) { ElMessage.warning('LLM配置加载失败，请检查后端服务: ' + (e.response?.data?.detail || e.message)) }
  loadEvalHistory()
  loadAnalytics()
})
</script>

<style scoped>
.dashboard { max-width: 1240px; }

/* ── Welcome ── */
.welcome { margin-bottom: 32px; }
.welcome h1 {
  font-size: 26px;
  font-weight: 700;
  color: var(--geo-text);
  margin-bottom: 6px;
  letter-spacing: 0.3px;
}
.welcome p { font-size: 14px; color: var(--geo-text-secondary); }

/* ── Quick Actions ── */
.quick-actions { margin-bottom: 0; }
.action-card {
  cursor: pointer;
  transition: all var(--geo-transition);
  border: 1px solid var(--geo-border);
}
.action-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--geo-shadow-lg) !important;
  border-color: var(--geo-primary-border);
}
.action-card :deep(.el-card__body) {
  display: flex; align-items: center; gap: 18px; padding: 22px 20px;
}
.action-icon {
  width: 52px; height: 52px;
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  color: #fff;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}
.action-info h3 { font-size: 15px; font-weight: 600; margin-bottom: 4px; color: var(--geo-text); }
.action-info p { font-size: 12px; color: var(--geo-text-secondary); }

/* ── Card Header ── */
.card-header { display: flex; justify-content: space-between; align-items: center; }

/* ── Platform Grid ── */
.platform-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.platform-item { display: flex; align-items: center; gap: 10px; }
.plat-status { font-size: 13px; color: var(--geo-text-secondary); }

/* ── Empty ── */
.card-empty { text-align: center; padding: 40px 0; color: var(--geo-text-muted); }

/* ── Evaluation Mini ── */
.eval-mini-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--geo-border-light);
  transition: background var(--geo-transition-fast);
}
.eval-mini-item:last-child { border-bottom: none; }
.eval-mini-item:hover { background: var(--geo-surface-hover); margin: 0 -12px; padding: 10px 12px; border-radius: 6px; }
.eval-mini-date { font-size: 12px; color: var(--geo-text-muted); min-width: 42px; }
.eval-mini-score { font-size: 16px; font-weight: 700; min-width: 52px; text-align: right; }

/* ── Score Overview ── */
.score-overview { text-align: center; padding: 20px 0; }
.overview-number {
  font-size: 64px; font-weight: 800;
  color: var(--geo-primary);
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.overview-label { font-size: 14px; color: var(--geo-text-muted); margin-top: 6px; }
.overview-trend { font-size: 14px; font-weight: 600; margin-top: 10px; }
.overview-count { font-size: 13px; color: var(--geo-text-muted); margin-top: 6px; }

/* ── Coverage Matrix ── */
.coverage-matrix { overflow-x: auto; padding: 4px 0; }
.matrix-header, .matrix-row { display: flex; align-items: center; padding: 8px 0; }
.matrix-header {
  font-weight: 600;
  border-bottom: 2px solid var(--geo-border);
  padding-bottom: 12px;
}
.matrix-label { width: 80px; font-size: 13px; color: var(--geo-text-secondary); flex-shrink: 0; }
.matrix-col-header { flex: 1; min-width: 70px; text-align: center; font-size: 13px; color: var(--geo-text-muted); }
.matrix-col-header.configured { color: var(--geo-primary); font-weight: 600; }
.matrix-cell { flex: 1; min-width: 70px; text-align: center; }

/* ── Stat Cards ── */
.stat-card {
  text-align: center;
  border: 1px solid var(--geo-border);
  transition: box-shadow var(--geo-transition);
}
.stat-card:hover { box-shadow: var(--geo-shadow) !important; }
.stat-card :deep(.el-card__body) { padding: 24px 16px; }
.stat-number { font-size: 34px; font-weight: 700; letter-spacing: -0.5px; }
.stat-label { font-size: 13px; color: var(--geo-text-muted); margin-top: 6px; font-weight: 500; }
</style>
