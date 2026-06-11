<template>
  <div class="feedback-dashboard">
    <!-- 顶部指标卡片 -->
    <el-row :gutter="16" style="margin-bottom:16px">
      <el-col :span="6" v-for="card in metricCards" :key="card.key">
        <el-card shadow="hover" :class="['metric-card', card.trend]">
          <div class="metric-label">{{ card.label }}</div>
          <div class="metric-value">{{ card.value }}<span class="metric-unit">{{ card.unit }}</span></div>
          <div class="metric-trend" v-if="card.trend !== 'stable'">
            <el-icon><component :is="card.trend === 'up' ? 'Top' : 'Bottom'" /></el-icon>
            {{ card.trendText }}
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 趋势图 + 平台选择 -->
    <el-row :gutter="16" style="margin-bottom:16px">
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>采信率趋势 (12周)</span>
              <el-select v-model="trendPlatform" size="small" style="width:140px" @change="loadTrend">
                <el-option v-for="p in platforms" :key="p" :label="p" :value="p" />
              </el-select>
            </div>
          </template>
          <div ref="trendChart" style="height:260px"></div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="hover">
          <template #header><span>时效衰减曲线（模拟）</span></template>
          <div ref="decayChart" style="height:260px"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 异常告警 + 迭代建议 -->
    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>异常告警</span>
              <el-button size="small" @click="checkAllDrops">检测全部</el-button>
            </div>
          </template>
          <el-alert
            v-for="alert in alerts"
            :key="alert.platform_id"
            :title="`${alert.platform_id}: 采信率下降 ${alert.drop_pct}%`"
            :type="alert.severity === 'critical' ? 'error' : 'warning'"
            :description="`当前 ${alert.current_rate}% (↓${alert.drop_pct}%)`"
            show-icon
            closable
            style="margin-bottom:8px"
          />
          <el-empty v-if="!alerts.length" description="无异常" :image-size="40" />
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>迭代建议</span>
              <el-button size="small" type="primary" @click="runDiagnose" :loading="diagnosing">运行诊断</el-button>
            </div>
          </template>
          <div v-if="recommendation">
            <el-tag :type="recommendation.action === 'iteration_required' ? 'warning' : 'success'" size="small">
              {{ recommendation.action === 'iteration_required' ? '需要迭代' : '状态正常' }}
            </el-tag>
            <div v-if="recommendation.action_steps" style="margin-top:8px">
              <div v-for="(step, i) in recommendation.action_steps" :key="i" style="margin:4px 0">
                <el-tag size="small" type="info">{{ step.type }}</el-tag>
                {{ step.description }}
              </div>
            </div>
            <p v-else style="color:#999;margin-top:8px">{{ recommendation.message }}</p>
          </div>
          <el-empty v-else description="选择平台并运行诊断" :image-size="40" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getCurrentMetrics, getMetricsTrend, checkCitationDrop, diagnosePlatform
} from '@/api'
import * as echarts from 'echarts'

const platforms = ['doubao', 'wenxin', 'tongyi', 'deepseek', 'kimi']
const trendPlatform = ref('doubao')
const diagnosing = ref(false)
const alerts = ref([])
const recommendation = ref(null)

const metricCards = ref([
  { key: 'citation', label: 'AI采信率', value: '--', unit: '%', trend: 'stable', trendText: '' },
  { key: 'structure', label: '结构命中率', value: '--', unit: '%', trend: 'stable', trendText: '' },
  { key: 'ai_traffic', label: 'AI引荐流量', value: '--', unit: '次', trend: 'stable', trendText: '' },
  { key: 'rejection', label: '违规拒采率', value: '--', unit: '%', trend: 'stable', trendText: '' },
  { key: 'ai_conversion', label: 'AI转化率', value: '--', unit: '%', trend: 'stable', trendText: '' },
  { key: 'ai_conv_value', label: 'AI转化价值', value: '--', unit: '元', trend: 'stable', trendText: '' },
])

const trendChart = ref(null)
const decayChart = ref(null)

onMounted(async () => {
  await loadMetrics()
  await checkAllDrops()
  await nextTick()
  renderTrendChart()
  renderDecayChart()
})

async function loadMetrics() {
  try {
    const { data } = await getCurrentMetrics(trendPlatform.value)
    const summary = data.summary || {}
    const platform = data.platforms?.[trendPlatform.value] || {}
    metricCards.value[0].value = platform.citation_rate ?? summary.avg_citation_rate ?? '--'
    metricCards.value[1].value = platform.structure_hit_rate ?? '--'
    metricCards.value[2].value = summary.ai_traffic_visits ?? '--'
    metricCards.value[3].value = platform.rejection_rate ?? summary.avg_rejection_rate ?? '--'
    metricCards.value[4].value = summary.ai_conversion_rate_pct ?? '--'
    metricCards.value[5].value = (summary.total_conversions ?? 0) > 0
      ? (summary.total_conversions * 100).toFixed(0) : '--'

    const trend = platform.citation_trend
    metricCards.value[0].trend = trend || 'stable'
    metricCards.value[0].trendText = trend === 'down' ? '下降中' : trend === 'up' ? '上升中' : '稳定'
  } catch (e) { /* silent */ }
}

async function loadTrend() {
  try {
    const { data } = await getMetricsTrend(trendPlatform.value, 12)
    await nextTick()
    renderTrendChart(data.history || [])
  } catch (e) { /* silent */ }
}

async function checkAllDrops() {
  alerts.value = []
  for (const p of platforms) {
    try {
      const { data } = await checkCitationDrop(p)
      if (data.dropping) alerts.value.push(data.details)
    } catch (e) { /* skip */ }
  }
}

async function runDiagnose() {
  diagnosing.value = true
  try {
    const { data } = await diagnosePlatform(trendPlatform.value)
    recommendation.value = data.recommendation
  } catch (e) {
    ElMessage.error('诊断失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    diagnosing.value = false
  }
}

function renderTrendChart(history = []) {
  if (!trendChart.value) return
  const chart = echarts.init(trendChart.value)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: history.map(h => h.week_start?.slice(5) || '') },
    yAxis: { type: 'value', max: 100 },
    series: [
      { name: '采信率', type: 'line', data: history.map(h => h.citation_rate || 0), smooth: true, itemStyle: { color: '#409eff' } },
      { name: '结构命中率', type: 'line', data: history.map(h => h.structure_hit_rate || 0), smooth: true, itemStyle: { color: '#67c23a' } },
      { name: '拒采率', type: 'line', data: history.map(h => h.rejection_rate || 0), smooth: true, itemStyle: { color: '#f56c6c' } },
    ],
    grid: { top: 10, right: 20, bottom: 30, left: 50 },
  })
}

function renderDecayChart() {
  if (!decayChart.value) return
  const chart = echarts.init(decayChart.value)
  const days = ['发布日', '7天', '15天', '30天', '90天']
  chart.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: days },
    yAxis: { type: 'value', max: 100, name: '引用率(%)' },
    series: [
      { name: '豆包', type: 'line', data: [80, 65, 50, 35, 15], smooth: true },
      { name: 'DeepSeek', type: 'line', data: [75, 68, 60, 50, 35], smooth: true },
      { name: '文心一言', type: 'line', data: [70, 60, 52, 45, 30], smooth: true },
    ],
    grid: { top: 10, right: 20, bottom: 30, left: 50 },
  })
}
</script>

<style scoped>
.feedback-dashboard { padding: 4px; }
.metric-card { text-align: center; cursor: pointer; }
.metric-card.down { border-top: 3px solid #f56c6c; }
.metric-card.up { border-top: 3px solid #67c23a; }
.metric-card.stable { border-top: 3px solid #409eff; }
.metric-label { font-size: 13px; color: #999; }
.metric-value { font-size: 28px; font-weight: bold; margin: 8px 0; }
.metric-unit { font-size: 14px; color: #999; }
.metric-trend { font-size: 12px; color: #666; display: flex; align-items: center; justify-content: center; gap: 4px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
</style>
