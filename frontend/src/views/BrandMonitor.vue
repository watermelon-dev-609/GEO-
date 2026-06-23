<template>
  <div class="brand-monitor">
    <div class="page-header">
      <h2 class="page-title">AI收录监测</h2>
      <p class="page-desc">实时追踪品牌在10大AI平台中被收录和引用的情况，掌握真实的AI搜索曝光状态</p>
    </div>

    <!-- 使用指引 -->
    <el-alert type="info" :closable="false" style="margin-bottom: 16px;">
      <template #title>
        <strong>📋 如何用AI收录监测提升品牌收录率</strong>
      </template>
      <div style="font-size:13px;line-height:1.8;color:#6B6E7B;">
        1. 选择沙盘类型和查询分类 → 点击<strong>"全量检测"</strong> → 系统在10大AI平台搜索您的品牌<br/>
        2. 查看<strong>收录矩阵</strong>和<strong>检测详情</strong> → 找出哪些平台、哪些查询没有收录您的品牌<br/>
        3. 在检测详情中点击<strong>"优化未被收录的平台"</strong> → 自动跳转GEO工坊并带入优化指令<br/>
        4. 在工坊中<strong>导入文案→开始优化</strong> → 系统会针对未收录的查询针对性改写内容<br/>
        5. 优化完成后<strong>再次全量检测</strong> → 对比收录率变化，验证优化效果
      </div>
    </el-alert>

    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :span="4" v-for="s in statCards" :key="s.label">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value" :style="{ color: s.color }">{{ s.value }}</div>
          <div class="stat-label">{{ s.label }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 操作栏 -->
    <el-card shadow="never" style="margin-bottom: 20px;">
      <div class="action-bar">
        <div class="action-left">
          <span class="action-label">沙盘类型</span>
          <el-select v-model="sandtableType" size="default" style="width: 160px;">
            <el-option v-for="t in SANDBTABLE_TYPES" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
          <span class="action-label">查询分类</span>
          <el-checkbox-group v-model="queryCategories">
            <el-checkbox v-for="c in QUERY_CATEGORIES" :key="c.key" :value="c.key" :label="c.key">{{ c.label }}</el-checkbox>
          </el-checkbox-group>
        </div>
        <div class="action-right">
          <el-button type="primary" :icon="Search" :loading="isChecking" @click="startCheckAll" size="large">
            {{ isChecking ? '检测中...' : '全量检测' }}
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 主内容区 -->
    <el-row :gutter="20">
      <!-- 左：平台收录矩阵 -->
      <el-col :span="14">
        <el-card shadow="never" v-loading="loading">
          <template #header>
            <div class="card-header">
              <span>平台收录矩阵</span>
              <el-tag size="small" type="info">{{ platformMatrix.length }} 个平台</el-tag>
            </div>
          </template>
          <div v-if="platformMatrix.length === 0 && !loading" class="empty-state">
            <el-empty description="暂无检测数据" :image-size="80">
              <el-button type="primary" @click="startCheckAll">开始首次检测</el-button>
            </el-empty>
          </div>
          <div v-else>
            <div v-for="p in platformMatrix" :key="p.platform" class="platform-row">
              <div class="platform-info">
                <span class="platform-name">{{ p.label }}</span>
                <el-tag :type="p.configured ? 'success' : 'info'" size="small" effect="plain">
                  {{ p.configured ? '已配置' : '未配置' }}
                </el-tag>
              </div>
              <div class="platform-metrics">
                <span class="metric">检测 <strong>{{ p.checked }}</strong> 次</span>
                <span class="metric-sep">|</span>
                <span class="metric">收录 <strong>{{ p.mentioned }}</strong> 次</span>
              </div>
              <div class="platform-bar-wrap">
                <div class="platform-bar" :style="{ width: p.rate + '%', background: p.rate >= 50 ? '#5B8C5A' : p.rate >= 20 ? '#D4956A' : '#C5554A' }"></div>
              </div>
              <span class="platform-rate" :style="{ color: scoreColor(p.rate) }">{{ p.rate }}%</span>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 右：趋势 + 最近记录 -->
      <el-col :span="10">
        <el-card shadow="never" style="margin-bottom: 16px;" v-loading="trendLoading">
          <template #header><span>收录率趋势</span></template>
          <div v-if="trendData.length === 0" class="empty-state" style="padding: 24px 0;">
            <span style="color: #9B9EAA;">暂无趋势数据</span>
          </div>
          <div v-else class="trend-bars">
            <div v-for="t in trendData.slice(-14)" :key="t.date" class="trend-bar-item">
              <div class="trend-bar-fill" :style="{ height: Math.max(t.mention_rate, 4) + '%' }" :title="t.date + ': ' + t.mention_rate + '%'"></div>
              <span class="trend-date">{{ t.date.slice(5) }}</span>
            </div>
          </div>
        </el-card>

        <el-card shadow="never" v-loading="historyLoading">
          <template #header>
            <div class="card-header">
              <span>最近检测</span>
              <el-button size="small" type="primary" link @click="loadHistory">刷新</el-button>
            </div>
          </template>
          <div v-if="recentSessions.length === 0" class="empty-state">
            <span style="color: #9B9EAA;">暂无检测记录</span>
          </div>
          <div v-else>
            <div v-for="s in recentSessions.slice(0, 6)" :key="s.session_id" class="session-mini"
                 @click="showSessionDetail(s.session_id)">
              <div class="session-mini-left">
                <span class="session-mini-date">{{ formatDate(s.created_at) }}</span>
                <span class="session-mini-plats">{{ (s.platforms_checked || []).length }} 平台</span>
              </div>
              <div class="session-mini-right">
                <span class="session-mini-count">{{ s.mentioned_count }}/{{ s.total_queries }}</span>
                <span class="session-mini-rate" :style="{ color: scoreColor(s.mention_rate) }">{{ s.mention_rate }}%</span>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 检测历史表格 -->
    <el-card shadow="never" style="margin-top: 20px;" v-loading="historyLoading">
      <template #header><span>检测历史</span></template>
      <el-table :data="historyItems" size="small" stripe v-if="historyItems.length > 0">
        <el-table-column prop="created_at" label="时间" width="170">
          <template #default="scope">{{ formatDateTime(scope.row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="平台" width="200">
          <template #default="scope">{{ (scope.row.platforms_checked || []).join(', ') }}</template>
        </el-table-column>
        <el-table-column prop="total_queries" label="查询数" width="80" align="center" />
        <el-table-column prop="mentioned_count" label="收录次数" width="100" align="center" />
        <el-table-column label="收录率" width="120" align="center">
          <template #default="scope">
            <el-progress :percentage="scope.row.mention_rate || 0" :stroke-width="8"
              :color="scoreColor(scope.row.mention_rate || 0)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center">
          <template #default="scope">
            <el-button size="small" type="primary" link @click="showSessionDetail(scope.row.session_id)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-else class="empty-state" style="padding: 32px 0;">
        <span style="color: #9B9EAA;">暂无检测记录，点击"全量检测"开始</span>
      </div>
    </el-card>

    <!-- 会话详情弹窗 -->
    <el-dialog v-model="detailVisible" title="检测详情" width="800px" :destroy-on-close="true">
      <div v-loading="detailLoading">
        <div v-if="sessionDetail" class="session-detail">
          <div class="detail-summary">
            <span>平台: <strong>{{ (sessionDetail.platforms_checked || []).join(', ') }}</strong></span>
            <span>收录率: <strong :style="{ color: scoreColor(sessionDetail.mention_rate) }">{{ sessionDetail.mention_rate }}%</strong></span>
            <span>{{ sessionDetail.mentioned_count }}/{{ sessionDetail.total_queries }} 次被收录</span>
            <el-button type="warning" size="small" @click="goOptimizeFromMonitor" :disabled="!unmentionedQueries.length" style="margin-left:auto;">
              优化未被收录的平台 ({{ unmentionedQueries.length }})
            </el-button>
          </div>
          <el-table :data="sessionDetail.results || []" size="small" max-height="400">
            <el-table-column prop="platform" label="平台" width="80" />
            <el-table-column prop="query" label="查询" min-width="200" show-overflow-tooltip />
            <el-table-column label="收录" width="80" align="center">
              <template #default="scope">
                <el-tag :type="scope.row.brand_mentioned ? 'success' : 'danger'" size="small" effect="dark">
                  {{ scope.row.brand_mentioned ? '是' : '否' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="情感" width="70" align="center">
              <template #default="scope">
                <el-tag v-if="scope.row.sentiment" size="small"
                  :type="scope.row.sentiment.polarity === 'positive' ? 'success' : scope.row.sentiment.polarity === 'negative' ? 'danger' : 'info'">
                  {{ scope.row.sentiment.polarity === 'positive' ? '正面' : scope.row.sentiment.polarity === 'negative' ? '负面' : '中性' }}
                </el-tag>
                <span v-else style="color:#c0c4cc;">—</span>
              </template>
            </el-table-column>
            <el-table-column prop="mention_score" label="评分" width="60" align="center" />
            <el-table-column label="引用片段" min-width="180">
              <template #default="scope">
                <span v-if="scope.row.mention_context" class="mention-ctx">{{ scope.row.mention_context }}</span>
                <span v-else style="color: #c0c4cc;">—</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" align="center">
              <template #default="scope">
                <el-button v-if="scope.row.sentiment?.polarity === 'negative' || scope.row.sentiment?.factual_accuracy === 'inaccurate'"
                  link type="danger" size="small" @click="flagToReputation(scope.row)">
                  标记舆情
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div v-else class="empty-state" style="padding: 40px;">
          <span style="color: #9B9EAA;">加载失败</span>
        </div>
      </div>
    </el-dialog>

    <!-- ═══ 真实AI收录搜索 ═══ -->
    <el-card shadow="never" style="margin-top: 20px;">
      <template #header>
        <div style="display:flex;align-items:center;justify-content:space-between;">
          <span>🔍 真实AI收录搜索 — 实际调用AI平台API检索品牌</span>
          <el-tag size="small" type="success" effect="plain">实际API调用</el-tag>
        </div>
      </template>

      <el-alert type="info" :closable="false" style="margin-bottom:16px;">
        <strong>与上方「全量检测」的区别</strong>：上方检测使用LLM模拟评估，本功能实际调用各AI平台的Chat API发送真实搜索查询，解析返回结果中是否包含你的品牌。结果更接近真实AI收录数据。
      </el-alert>

      <el-row :gutter="12">
        <el-col :span="6">
          <el-select v-model="realSearchSandtable" style="width:100%" placeholder="沙盘类型">
            <el-option v-for="t in SANDBTABLE_TYPES" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-col>
        <el-col :span="12">
          <el-checkbox-group v-model="realSearchPlatforms">
            <el-checkbox v-for="p in availablePlatforms" :key="p.value" :value="p.value" :label="p.label" />
          </el-checkbox-group>
        </el-col>
        <el-col :span="6">
          <el-button type="primary" :loading="realSearchLoading" @click="runRealSearch" style="width:100%">
            {{ realSearchLoading ? '搜索中...' : '开始真实搜索' }}
          </el-button>
        </el-col>
      </el-row>

      <!-- 搜索结果 -->
      <div v-if="realSearchResult" style="margin-top:16px;">
        <el-divider />
        <el-alert :title="realSearchResult.summary" :type="realSearchResult.mention_rate >= 50 ? 'success' : realSearchResult.mention_rate >= 20 ? 'warning' : 'danger'" :closable="false" />

        <el-table :data="realSearchPlatformRows" size="small" style="margin-top:12px;">
          <el-table-column prop="platform" label="AI平台" width="120" />
          <el-table-column label="提及次数" width="100" align="center">
            <template #default="scope">{{ scope.row.mentions }}/{{ scope.row.total }}</template>
          </el-table-column>
          <el-table-column label="提及率" width="100" align="center">
            <template #default="scope">
              <el-tag :type="scope.row.mention_rate >= 50 ? 'success' : scope.row.mention_rate >= 20 ? 'warning' : 'danger'" size="small">
                {{ scope.row.mention_rate }}%
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="引用率" width="100" align="center">
            <template #default="scope">
              {{ scope.row.citation_rate }}%
            </template>
          </el-table-column>
          <el-table-column label="状态" min-width="120">
            <template #default="scope">
              <el-tag v-if="scope.row.errors > 0" type="danger" size="small">{{ scope.row.errors }}个错误</el-tag>
              <el-tag v-else-if="scope.row.mentions === 0" type="warning" size="small">未被提及</el-tag>
              <el-tag v-else type="success" size="small">已收录</el-tag>
            </template>
          </el-table-column>
        </el-table>

        <!-- 搜索详情 -->
        <el-collapse style="margin-top:12px;">
          <el-collapse-item title="查看搜索详情">
            <div v-for="pq in (realSearchResult.per_query || [])" :key="pq.query" style="margin-bottom:12px;">
              <div style="font-weight:600;font-size:13px;margin-bottom:4px;">🔎 {{ pq.query }}</div>
              <div v-for="(item, plat) in (pq.platforms || {})" :key="plat" style="margin-left:16px;margin-bottom:4px;font-size:12px;">
                <el-tag :type="item.mentioned ? 'success' : 'danger'" size="small" effect="plain">{{ plat }}</el-tag>
                <span v-if="item.error" style="color:#C5554A;">⚠️ {{ item.error }}</span>
                <span v-else-if="item.answer_snippet" style="color:#6B6E7B;margin-left:4px;">{{ item.answer_snippet.slice(0, 120) }}{{ item.answer_snippet.length > 120 ? '...' : '' }}</span>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useGeoStore } from '../stores/geo'
import { Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { SANDTABLE_TYPES, AI_PLATFORMS, QUERY_CATEGORIES, scoreColor } from '../constants'
import { realSearch, realSearchHistory, getMonitorQueries } from '../api'
import {
  getMonitorOverview, getMonitorHistory, getMonitorSession,
  runMonitorCheckAll, getMonitorTrend, getLLMConfig,
} from '../api'

const router = useRouter()
const store = useGeoStore()

const loading = ref(false)
const isChecking = ref(false)
const trendLoading = ref(false)
const historyLoading = ref(false)
const detailVisible = ref(false)
const detailLoading = ref(false)

const sandtableType = ref('smart_traffic')
const queryCategories = ref(['brand_direct', 'scenario'])
const overview = ref(null)
const trendData = ref([])
const recentSessions = ref([])
const historyItems = ref([])
const sessionDetail = ref(null)
const configuredPlatforms = ref([])

// ── 真实AI收录搜索 ──
const realSearchSandtable = ref('smart_traffic')
const realSearchPlatforms = ref(['deepseek', 'kimi', 'doubao'])
const realSearchLoading = ref(false)
const realSearchResult = ref(null)
const realSearchPlatformRows = ref([])
const availablePlatforms = AI_PLATFORMS.filter(p => !['ollama', 'lmstudio'].includes(p.value))

async function runRealSearch() {
  if (realSearchPlatforms.value.length === 0) {
    ElMessage.warning('请至少选择一个AI平台')
    return
  }
  realSearchLoading.value = true
  realSearchResult.value = null
  try {
    const res = await realSearch({
      sandtable_type: realSearchSandtable.value,
      platforms: realSearchPlatforms.value,
    })
    const data = res.data
    realSearchResult.value = data
    // 构建平台行
    const rows = []
    for (const [plat, info] of Object.entries(data.per_platform || {})) {
      rows.push({
        platform: plat,
        mentions: info.mentions || 0,
        total: info.total || 0,
        mention_rate: info.mention_rate || 0,
        citation_rate: info.citation_rate || 0,
        errors: info.errors || 0,
      })
    }
    realSearchPlatformRows.value = rows
    ElMessage.success(`真实搜索完成：提及率 ${data.mention_rate}%`)
  } catch (e) {
    ElMessage.error('真实搜索失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    realSearchLoading.value = false
  }
}

const SANDBTABLE_TYPES = SANDTABLE_TYPES

const statCards = computed(() => {
  const o = overview.value || {}
  return [
    { label: '最近检测', value: o.last_check_at ? formatDate(o.last_check_at) : '未检测', color: '#C8963E' },
    { label: '总检测次数', value: o.total_checks || 0, color: '#6B6E7B' },
    { label: '品牌收录', value: o.total_mentioned || 0, color: '#5B8C5A' },
    { label: '收录率', value: (o.overall_mention_rate || 0) + '%', color: '#8065E6' },
    { label: '覆盖平台', value: Object.keys(o.by_platform || {}).length, color: '#D4956A' },
  ]
})

const platformMatrix = computed(() => {
  const o = overview.value
  if (!o || !o.by_platform) return []
  return AI_PLATFORMS.map(ap => {
    const pd = o.by_platform[ap.value] || {}
    return {
      platform: ap.value,
      label: ap.label,
      checked: pd.checked || 0,
      mentioned: pd.mentioned || 0,
      rate: pd.rate || 0,
      configured: configuredPlatforms.value.includes(ap.value),
    }
  })
})

function formatDate(d) {
  if (!d) return ''
  return d.slice(0, 10)
}

function formatDateTime(d) {
  if (!d) return ''
  return d.slice(0, 16).replace('T', ' ')
}

async function loadOverview() {
  loading.value = true
  try {
    const res = await getMonitorOverview()
    overview.value = res.data
  } catch (e) {
    ElMessage.error('加载概览失败: ' + (e.response?.data?.detail || e.message))
  } finally { loading.value = false }
}

async function loadTrend() {
  trendLoading.value = true
  try {
    const res = await getMonitorTrend(30)
    trendData.value = res.data.data_points || []
  } catch (e) { ElMessage.warning('趋势数据加载失败: ' + (e.response?.data?.detail || e.message)) }
  finally { trendLoading.value = false }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const hist = await getMonitorHistory({ page: 1, page_size: 20 })
    const items = hist.data.items || []
    historyItems.value = items
    recentSessions.value = items.slice(0, 6)
  } catch (e) {
    ElMessage.warning('加载检测历史失败: ' + (e.response?.data?.detail || e.message))
  }
  finally { historyLoading.value = false }
}

async function startCheckAll() {
  if (queryCategories.value.length === 0) {
    ElMessage.warning('请至少选择一个查询分类')
    return
  }
  isChecking.value = true
  try {
    const res = await runMonitorCheckAll({
      platforms: [],
      query_categories: queryCategories.value,
      max_queries_per_category: 3,
      sandtable_type: sandtableType.value,
    })
    ElMessage.success(`检测完成！收录率 ${res.data.mention_rate}%（${res.data.mentioned_count}/${res.data.total_queries}）`)
    await Promise.all([loadOverview(), loadTrend(), loadHistory()])
  } catch (e) {
    ElMessage.error('检测失败: ' + (e.response?.data?.detail || e.message))
  } finally { isChecking.value = false }
}

async function showSessionDetail(sessionId) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    const res = await getMonitorSession(sessionId)
    sessionDetail.value = res.data
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.response?.data?.detail || e.message))
  } finally { detailLoading.value = false }
}

const unmentionedQueries = computed(() => {
  if (!sessionDetail.value?.results) return []
  return sessionDetail.value.results
    .filter(r => !r.brand_mentioned)
    .map(r => ({ platform: r.platform, query: r.query }))
})

function goOptimizeFromMonitor() {
  if (!unmentionedQueries.value.length) return
  const failedPlatforms = [...new Set(unmentionedQueries.value.map(q => q.platform))]
  const hints = unmentionedQueries.value.map(q =>
    `在${q.platform}平台搜索"${q.query}"时品牌未被收录，需优化相关内容以匹配此类查询`
  )
  store.setReoptimizeContext({
    weakPoints: hints,
    suggestions: hints,
    sourceText: '',
    sandtableType: sandtableType.value,
    autoAdoptAll: true,
    fromMonitor: true,
  })
  store.setSelectedPlatforms(failedPlatforms)
  router.push('/workshop')
}

function flagToReputation(row) {
  // 跳转到舆情管理页面，携带预填信息
  router.push({
    path: '/reputation',
    query: {
      platform: row.platform,
      query: row.query,
      autoCreate: 'true',
    },
  })
}

onMounted(async () => {
  try {
    const cfg = await getLLMConfig()
    configuredPlatforms.value = (cfg.data.llm_platforms || [])
      .filter(p => p.configured)
      .map(p => p.platform)
  } catch (e) { ElMessage.warning('平台配置加载失败: ' + (e.response?.data?.detail || e.message)) }
  await Promise.all([loadOverview(), loadTrend(), loadHistory()])
})
</script>

<style scoped>
.brand-monitor { max-width: 1240px; }
.page-header { margin-bottom: 20px; }
.page-title { font-size: 20px; font-weight: 700; color: #2D3142; margin: 0 0 4px; }
.page-desc { font-size: 13px; color: #9B9EAA; margin: 0; }

.stat-row { margin-bottom: 20px; }
.stat-card { text-align: center; border: 1px solid var(--geo-border); }
.stat-card :deep(.el-card__body) { padding: 18px 12px; }
.stat-value { font-size: 26px; font-weight: 700; letter-spacing: -0.3px; }
.stat-label { font-size: 12px; color: #9B9EAA; margin-top: 4px; }

.action-bar { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.action-left { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.action-label { font-size: 13px; color: #6B6E7B; font-weight: 500; }

.card-header { display: flex; justify-content: space-between; align-items: center; }

.platform-row { display: flex; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--geo-border-light); gap: 12px; }
.platform-row:last-child { border-bottom: none; }
.platform-info { display: flex; align-items: center; gap: 8px; min-width: 140px; }
.platform-name { font-size: 14px; font-weight: 600; color: #2D3142; }
.platform-metrics { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #9B9EAA; min-width: 120px; }
.metric-sep { color: #E8E5DF; }
.metric strong { color: #2D3142; }
.platform-bar-wrap { flex: 1; height: 8px; background: #F0EEE8; border-radius: 4px; overflow: hidden; }
.platform-bar { height: 100%; border-radius: 4px; transition: width 0.6s cubic-bezier(0.4,0,0.2,1); }
.platform-rate { font-size: 16px; font-weight: 700; min-width: 48px; text-align: right; }

.trend-bars { display: flex; align-items: flex-end; gap: 4px; height: 80px; padding-top: 8px; }
.trend-bar-item { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; }
.trend-bar-fill { width: 100%; max-width: 20px; background: #C8963E; border-radius: 3px 3px 0 0; min-height: 4px; transition: height 0.3s; }
.trend-date { font-size: 10px; color: #9B9EAA; margin-top: 4px; transform: rotate(-45deg); transform-origin: top left; white-space: nowrap; }

.session-mini { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--geo-border-light); cursor: pointer; transition: background 0.15s; }
.session-mini:last-child { border-bottom: none; }
.session-mini:hover { background: var(--geo-surface-hover); margin: 0 -12px; padding: 10px 12px; border-radius: 6px; }
.session-mini-left { display: flex; gap: 12px; font-size: 13px; }
.session-mini-date { color: #6B6E7B; }
.session-mini-plats { color: #9B9EAA; }
.session-mini-right { display: flex; gap: 10px; align-items: center; }
.session-mini-count { font-size: 13px; color: #2D3142; }
.session-mini-rate { font-size: 16px; font-weight: 700; }

.detail-summary { display: flex; gap: 20px; margin-bottom: 16px; padding: 12px 16px; background: #FAF8F5; border-radius: 8px; font-size: 14px; }
.mention-ctx { font-size: 12px; color: #6B6E7B; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

.empty-state { text-align: center; padding: 40px 0; }
</style>
