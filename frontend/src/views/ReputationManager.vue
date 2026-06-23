<template>
  <div class="reputation-manager">
    <div class="page-header">
      <h2 class="page-title">品牌舆情管理</h2>
      <p class="page-desc">追踪、评估、处理AI平台上关于品牌的情感言论和不实信息，维护品牌口碑</p>
    </div>

    <!-- 使用指引 -->
    <el-alert type="info" :closable="false" style="margin-bottom: 16px;">
      <template #title>
        <strong>🛡️ 舆情管理工作流</strong>
      </template>
      <div style="font-size:13px;line-height:1.8;color:#6B6E7B;">
        1. 点击<strong>"一键扫描"</strong> → 系统在各大AI平台检测品牌情感和不实信息<br/>
        2. 查看<strong>事件列表</strong> → 按严重度优先处理 critical/high 事件<br/>
        3. 点击事件进入<strong>详情</strong> → 查看AI原始回复、情感分析、事实核查结果<br/>
        4. <strong>生成纠正内容</strong> → 系统自动生成结构化纠正文案，确认后发布<br/>
        5. 发布后<strong>3-7天验证效果</strong> → 重新检测确认纠正是否被AI平台采信
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
          <el-select v-model="filterPlatform" placeholder="AI平台" clearable style="width:140px;">
            <el-option v-for="p in platforms" :key="p.value" :label="p.label" :value="p.value" />
          </el-select>
          <el-select v-model="filterSeverity" placeholder="严重度" clearable style="width:120px;">
            <el-option v-for="s in severities" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
          <el-select v-model="filterStatus" placeholder="状态" clearable style="width:120px;">
            <el-option v-for="s in statuses" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
          <el-button :icon="Search" @click="fetchIncidents" :loading="loading">查询</el-button>
        </div>
        <div class="action-right">
          <el-button type="primary" :icon="Refresh" @click="runScan" :loading="scanning">
            {{ scanning ? '扫描中...' : '一键扫描' }}
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 事件列表 -->
    <el-card shadow="never" v-loading="loading">
      <template #header>
        <div class="card-header">
          <span>舆情事件列表</span>
          <el-tag size="small" type="info">{{ totalIncidents }} 条</el-tag>
        </div>
      </template>
      <el-table :data="incidents" style="width:100%" @row-click="showDetail" highlight-current-row>
        <el-table-column prop="incident_id" label="事件ID" width="180">
          <template #default="{ row }">
            <span style="font-family:monospace;font-size:12px;">{{ row.incident_id?.slice(-12) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="platform" label="平台" width="100">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ row.platform }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="query" label="触发查询" min-width="200" show-overflow-tooltip />
        <el-table-column prop="severity" label="严重度" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="severityType(row.severity)">{{ severityLabel(row.severity) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="情感" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="polarityType(row.sentiment?.polarity)">
              {{ polarityLabel(row.sentiment?.polarity) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }">{{ (row.created_at || '').slice(0, 16).replace('T', ' ') }}</template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click.stop="showDetail(row)">详情</el-button>
            <el-button link type="success" size="small" @click.stop="handleCorrect(row)"
              v-if="row.sentiment?.factual_accuracy === 'inaccurate' && !row.correction_published">
              纠正
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 事件详情抽屉 -->
    <el-drawer v-model="drawerVisible" title="事件详情" size="600px">
      <template v-if="currentIncident">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="事件ID">{{ currentIncident.incident_id }}</el-descriptions-item>
          <el-descriptions-item label="平台">{{ currentIncident.platform }}</el-descriptions-item>
          <el-descriptions-item label="严重度">
            <el-tag :type="severityType(currentIncident.severity)" size="small">{{ severityLabel(currentIncident.severity) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusType(currentIncident.status)" size="small">{{ statusLabel(currentIncident.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="触发查询" :span="2">{{ currentIncident.query }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ (currentIncident.created_at || '').slice(0, 19).replace('T', ' ') }}</el-descriptions-item>
          <el-descriptions-item label="解决时间">{{ (currentIncident.resolved_at || '未解决').slice(0, 19).replace('T', ' ') }}</el-descriptions-item>
        </el-descriptions>

        <h4 style="margin-top:20px;">AI原始回复</h4>
        <el-input type="textarea" :rows="4" :model-value="currentIncident.ai_response_snippet" readonly />

        <h4 style="margin-top:20px;">情感 & 事实分析</h4>
        <el-descriptions v-if="currentIncident.sentiment" :column="2" border size="small">
          <el-descriptions-item label="情感极性">
            <el-tag :type="polarityType(currentIncident.sentiment.polarity)" size="small">{{ polarityLabel(currentIncident.sentiment.polarity) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="置信度">{{ currentIncident.sentiment.confidence?.toFixed(0) }}%</el-descriptions-item>
          <el-descriptions-item label="事实准确性">
            <el-tag :type="accuracyType(currentIncident.sentiment.factual_accuracy)" size="small">{{ currentIncident.sentiment.factual_accuracy }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="分析方法">{{ currentIncident.sentiment.method }}</el-descriptions-item>
          <el-descriptions-item label="分析摘要" :span="2">{{ currentIncident.sentiment.summary }}</el-descriptions-item>
        </el-descriptions>

        <div v-if="currentIncident.sentiment?.factual_issues?.length" style="margin-top:16px;">
          <h4>事实核查明细</h4>
          <div v-for="(issue, idx) in currentIncident.sentiment.factual_issues" :key="idx"
            style="padding:8px;margin-bottom:8px;background:#f5f7fa;border-radius:4px;font-size:13px;">
            <div><strong>声称:</strong> {{ issue.claim }}</div>
            <div><strong>准确:</strong> <el-tag :type="issue.is_accurate ? 'success' : 'danger'" size="small">{{ issue.is_accurate ? '是' : '否' }}</el-tag></div>
            <div v-if="issue.evidence"><strong>依据:</strong> {{ issue.evidence }}</div>
            <div v-if="issue.correction"><strong>建议:</strong> {{ issue.correction }}</div>
          </div>
        </div>

        <h4 style="margin-top:20px;">纠正内容
          <span v-if="currentIncident.correction_published" style="color:#67C23A;font-size:13px;">（已发布）</span>
        </h4>
        <el-input type="textarea" :rows="5" :model-value="currentIncident.correction_content || '尚未生成纠正内容'"
          readonly v-if="currentIncident.correction_content" />
        <el-button type="primary" :icon="Edit" @click="handleCorrect(currentIncident)" style="margin-top:8px;"
          :disabled="correcting" v-if="!currentIncident.correction_content || !currentIncident.correction_published">
          {{ currentIncident.correction_content ? '重新生成' : '生成纠正内容' }}
        </el-button>

        <h4 style="margin-top:20px;">事件时间线</h4>
        <el-timeline v-if="timeline.length">
          <el-timeline-item v-for="(entry, idx) in timeline" :key="idx"
            :timestamp="(entry.timestamp || '').slice(0, 19).replace('T', ' ')"
            :type="entry.action === 'created' ? 'primary' : entry.action.includes('resolved') ? 'success' : 'info'">
            {{ entry.notes }}
          </el-timeline-item>
        </el-timeline>

        <div style="margin-top:24px;display:flex;gap:8px;">
          <el-select v-model="targetStatus" placeholder="更新状态" size="small" style="width:140px;">
            <el-option v-for="s in nextStatuses" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
          <el-button type="primary" size="small" @click="updateStatus" :disabled="!targetStatus">更新状态</el-button>
          <el-button v-if="currentIncident.correction_content && !currentIncident.correction_published"
            type="success" size="small" @click="publishCorrectionHandler">发布纠正内容</el-button>
        </div>
      </template>
    </el-drawer>

    <!-- 情感趋势图 -->
    <el-card shadow="never" style="margin-top:20px;" v-loading="trendLoading">
      <template #header>
        <span>情感趋势（近30天）</span>
        <el-button link size="small" @click="fetchTrend" style="float:right;">刷新</el-button>
      </template>
      <div ref="trendChart" style="height:300px;"></div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh, Edit } from '@element-plus/icons-vue'
import {
  getReputationIncidents, getReputationIncident, updateIncidentStatus,
  runReputationScan, getReputationStats, getSentimentTrend,
  generateCorrection, publishCorrection,
} from '../api/index.js'
import * as echarts from 'echarts'

// ── 状态 ──
const loading = ref(false)
const scanning = ref(false)
const correcting = ref(false)
const trendLoading = ref(false)
const incidents = ref([])
const totalIncidents = ref(0)
const drawerVisible = ref(false)
const currentIncident = ref(null)
const timeline = ref([])
const targetStatus = ref('')
const trendChart = ref(null)
let chartInstance = null

// 筛选
const filterPlatform = ref('')
const filterSeverity = ref('')
const filterStatus = ref('')

// 统计
const stats = ref({ total_incidents: 0, open_incidents: 0, critical_incidents: 0, resolved_this_month: 0, positive_rate: 0, negative_rate: 0 })

// 下拉选项
const platforms = [
  { value: 'deepseek', label: 'DeepSeek' }, { value: 'doubao', label: '豆包' },
  { value: 'wenxin', label: '文心一言' }, { value: 'tongyi', label: '通义千问' },
  { value: 'kimi', label: 'Kimi' }, { value: 'yuanbao', label: '元宝' }, { value: 'xinghuo', label: '讯飞星火' },
]
const severities = [
  { value: 'critical', label: '严重' }, { value: 'high', label: '高' },
  { value: 'medium', label: '中' }, { value: 'low', label: '低' },
]
const statuses = [
  { value: 'open', label: '待处理' }, { value: 'investigating', label: '调查中' },
  { value: 'responding', label: '响应中' }, { value: 'resolved', label: '已解决' }, { value: 'dismissed', label: '已忽略' },
]

const nextStatuses = computed(() => {
  const s = currentIncident.value?.status || 'open'
  const map = {
    open: [{ value: 'investigating', label: '开始调查' }, { value: 'dismissed', label: '忽略' }],
    investigating: [{ value: 'responding', label: '开始响应' }, { value: 'dismissed', label: '忽略' }],
    responding: [{ value: 'resolved', label: '解决' }, { value: 'dismissed', label: '忽略' }],
    resolved: [], dismissed: [{ value: 'open', label: '重新打开' }],
  }
  return map[s] || []
})

const statCards = computed(() => [
  { label: '待处理事件', value: stats.value.open_incidents, color: stats.value.open_incidents > 5 ? '#F56C6C' : '#E6A23C' },
  { label: '严重事件', value: stats.value.critical_incidents, color: stats.value.critical_incidents > 0 ? '#F56C6C' : '#909399' },
  { label: '本月已解决', value: stats.value.resolved_this_month, color: '#67C23A' },
  { label: '正面情感率', value: stats.value.positive_rate + '%', color: '#67C23A' },
  { label: '负面情感率', value: stats.value.negative_rate + '%', color: stats.value.negative_rate > 30 ? '#F56C6C' : '#E6A23C' },
  { label: '总事件数', value: stats.value.total_incidents, color: '#409EFF' },
])

// ── 标签样式 ──
const severityType = (s) => ({ critical: 'danger', high: 'warning', medium: 'info', low: '' }[s] || 'info')
const severityLabel = (s) => ({ critical: '严重', high: '高', medium: '中', low: '低' }[s] || s)
const polarityType = (p) => ({ positive: 'success', neutral: 'info', negative: 'danger' }[p] || 'info')
const polarityLabel = (p) => ({ positive: '正面', neutral: '中性', negative: '负面' }[p] || '未知')
const statusType = (s) => ({ open: 'danger', investigating: 'warning', responding: '', resolved: 'success', dismissed: 'info' }[s] || 'info')
const statusLabel = (s) => ({ open: '待处理', investigating: '调查中', responding: '响应中', resolved: '已解决', dismissed: '已忽略' }[s] || s)
const accuracyType = (a) => ({ accurate: 'success', partially_accurate: 'warning', inaccurate: 'danger', unverifiable: 'info' }[a] || 'info')

// ── 方法 ──
async function fetchStats() {
  try {
    const { data } = await getReputationStats()
    stats.value = data
  } catch { /* 静默 */ }
}

async function fetchIncidents() {
  loading.value = true
  try {
    const params = { limit: 50 }
    if (filterPlatform.value) params.platform = filterPlatform.value
    if (filterSeverity.value) params.severity = filterSeverity.value
    if (filterStatus.value) params.status = filterStatus.value
    const { data } = await getReputationIncidents(params)
    incidents.value = data.items || []
    totalIncidents.value = data.total || 0
  } catch (e) {
    ElMessage.error('加载事件失败: ' + (e.response?.data?.detail || e.message))
  } finally { loading.value = false }
}

async function showDetail(row) {
  try {
    const { data } = await getReputationIncident(row.incident_id)
    currentIncident.value = data.incident
    timeline.value = data.timeline || []
    targetStatus.value = ''
    drawerVisible.value = true
  } catch (e) {
    ElMessage.error('加载详情失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function updateStatus() {
  try {
    await updateIncidentStatus(currentIncident.value.incident_id, {
      status: targetStatus.value,
      notes: '',
    })
    ElMessage.success('状态已更新')
    targetStatus.value = ''
    await showDetail(currentIncident.value)
    await fetchIncidents()
    await fetchStats()
  } catch (e) {
    ElMessage.error('更新失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function runScan() {
  scanning.value = true
  try {
    const { data } = await runReputationScan({ sandtable_type: 'general', platforms: [], auto_create_incidents: true })
    ElMessage.success(`扫描完成: 发现 ${data.issues_found} 个问题, 创建 ${data.incidents_created} 个事件`)
    await fetchIncidents()
    await fetchStats()
  } catch (e) {
    ElMessage.error('扫描失败: ' + (e.response?.data?.detail || e.message))
  } finally { scanning.value = false }
}

async function handleCorrect(row) {
  correcting.value = true
  try {
    const { data } = await generateCorrection({
      incident_id: row.incident_id,
      target_platform: row.platform || '',
      sandtable_type: 'general',
    })
    ElMessage.success('纠正内容已生成')
    row.correction_content = data.correction_text
    // 刷新当前详情
    if (drawerVisible.value && currentIncident.value?.incident_id === row.incident_id) {
      await showDetail(row)
    }
  } catch (e) {
    ElMessage.error('生成失败: ' + (e.response?.data?.detail || e.message))
  } finally { correcting.value = false }
}

async function publishCorrectionHandler() {
  try {
    await ElMessageBox.confirm('确认发布纠正内容？发布后将在推荐渠道传播。', '确认发布', { type: 'warning' })
    await publishCorrection(currentIncident.value.incident_id)
    ElMessage.success('纠正内容已发布')
    await showDetail(currentIncident.value)
  } catch { /* 取消 */ }
}

async function fetchTrend() {
  trendLoading.value = true
  try {
    const { data } = await getSentimentTrend(30)
    renderChart(data.data_points || [])
  } catch (e) {
    ElMessage.error('趋势加载失败: ' + (e.response?.data?.detail || e.message))
  } finally { trendLoading.value = false }
}

function renderChart(dataPoints) {
  if (!trendChart.value) return
  if (!chartInstance) {
    chartInstance = echarts.init(trendChart.value)
  }
  const dates = dataPoints.map(d => d.date)
  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['正面', '中性', '负面', '严重事件'], top: 0 },
    grid: { left: 40, right: 20, top: 30, bottom: 30 },
    xAxis: { type: 'category', data: dates, axisLabel: { rotate: 45, fontSize: 10 } },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '正面', type: 'line', data: dataPoints.map(d => d.positive), smooth: true, itemStyle: { color: '#67C23A' } },
      { name: '中性', type: 'line', data: dataPoints.map(d => d.neutral), smooth: true, itemStyle: { color: '#909399' } },
      { name: '负面', type: 'line', data: dataPoints.map(d => d.negative), smooth: true, itemStyle: { color: '#F56C6C' } },
      { name: '严重事件', type: 'bar', data: dataPoints.map(d => d.critical), itemStyle: { color: '#E6A23C' } },
    ],
  })
}

// ── 生命周期 ──
onMounted(async () => {
  await Promise.all([fetchStats(), fetchIncidents(), fetchTrend()])
})

watch(trendChart, () => { if (trendChart.value && chartInstance) { chartInstance.resize() } })
</script>

<style scoped>
.page-header { margin-bottom: 16px; }
.page-title { font-size: 20px; font-weight: 600; color: #1a1b1c; }
.page-desc { font-size: 13px; color: #909399; margin-top: 4px; }
.stat-row { margin-bottom: 16px; }
.stat-card { text-align: center; }
.stat-value { font-size: 28px; font-weight: 700; }
.stat-label { font-size: 13px; color: #909399; margin-top: 4px; }
.action-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.action-left { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
h4 { font-size: 14px; font-weight: 600; color: #303133; }
</style>
