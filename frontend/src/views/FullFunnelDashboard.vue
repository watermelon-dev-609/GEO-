<template>
  <div class="funnel-dashboard" v-loading="store.trafficLoading || store.conversionLoading">
    <div class="page-header">
      <h2>全域转化漏斗</h2>
      <p class="page-desc">AI曝光 → AI引用 → 网站访问 → 转化 — 全链路追踪</p>
      <div class="period-selector">
        <el-radio-group v-model="days" size="small" @change="refresh">
          <el-radio-button :value="7">近7天</el-radio-button>
          <el-radio-button :value="30">近30天</el-radio-button>
          <el-radio-button :value="90">近90天</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- Error state -->
    <el-result v-if="error" icon="error" title="数据加载失败" :sub-title="error">
      <template #extra>
        <el-button type="primary" @click="refresh">重试</el-button>
      </template>
    </el-result>

    <!-- Empty state -->
    <el-empty v-else-if="!hasData" description="暂无漏斗数据，请先运行AI采信测试并接入流量与转化数据">
      <el-button type="primary" @click="$router.push('/brand-monitor')">前往AI收录监测</el-button>
    </el-empty>

    <template v-else>
      <!-- Row 1: Funnel Metric Cards -->
      <el-row :gutter="16" class="funnel-cards">
        <el-col :span="6" v-for="(stage, idx) in funnelData.stages" :key="stage.stage_name">
          <el-card shadow="hover" class="stage-card" :class="'stage-' + idx">
            <div class="stage-order">{{ idx + 1 }}</div>
            <div class="stage-label">{{ stage.label }}</div>
            <div class="stage-count">{{ formatNumber(stage.count) }}</div>
            <div class="stage-rate" v-if="idx > 0">
              转化率 <strong>{{ stage.rate_to_previous_pct }}%</strong>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- Row 2: Funnel + Platform Breakdown -->
      <el-row :gutter="16" class="charts-row">
        <el-col :span="12">
          <el-card shadow="hover">
            <template #header>漏斗转化率</template>
            <div class="chart-container">
              <div class="funnel-visual">
                <div class="funnel-bar" v-for="(stage, idx) in funnelData.stages" :key="idx"
                     :style="{ width: ((funnelData.stages.length - idx) / funnelData.stages.length * 100) + '%' }">
                  <span class="funnel-bar-label">{{ stage.label }}</span>
                  <span class="funnel-bar-value">{{ formatNumber(stage.count) }}</span>
                  <span class="funnel-bar-rate" v-if="idx > 0">{{ stage.rate_to_previous_pct }}%</span>
                </div>
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="hover">
            <template #header>AI平台分解</template>
            <el-table :data="platformBreakdown" size="small" max-height="280">
              <el-table-column prop="platform" label="平台" width="90" />
              <el-table-column prop="impressions" label="曝光" width="70" />
              <el-table-column prop="citations" label="引用" width="60" />
              <el-table-column prop="visits" label="访问" width="60" />
              <el-table-column prop="conversions" label="转化" width="60" />
              <el-table-column label="转化率" width="80">
                <template #default="{ row }">
                  <el-tag :type="conversionRateTag(row)" size="small">
                    {{ calcPlatformRate(row) }}%
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>

      <!-- Row 3: Traffic + Conversion Trend -->
      <el-row :gutter="16" class="charts-row">
        <el-col :span="12">
          <el-card shadow="hover">
            <template #header>流量趋势（近{{ days }}天）</template>
            <el-empty v-if="!store.trafficTrend.length" description="暂无流量数据" :image-size="60" />
            <div class="chart-container" v-else>
              <div class="simple-bar-chart">
                <div class="bar-item" v-for="p in store.trafficTrend" :key="p.date">
                  <div class="bar-label">{{ p.date.slice(5) }}</div>
                  <div class="bar-track">
                    <div class="bar-fill bar-pv" :style="{ width: barWidth(p.page_views, maxPV) }" />
                  </div>
                  <div class="bar-value">{{ p.page_views }}</div>
                </div>
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="hover">
            <template #header>转化趋势（近{{ days }}天）</template>
            <el-empty v-if="!store.conversionTrend.length" description="暂无转化数据" :image-size="60" />
            <div class="chart-container" v-else>
              <div class="simple-bar-chart">
                <div class="bar-item" v-for="p in store.conversionTrend" :key="p.date">
                  <div class="bar-label">{{ p.date.slice(5) }}</div>
                  <div class="bar-track">
                    <div class="bar-fill bar-conv" :style="{ width: barWidth(p.ai_attributed, maxConv) }" />
                  </div>
                  <div class="bar-value">{{ p.ai_attributed }}</div>
                </div>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- Row 4: Recent Conversion Events -->
      <el-card shadow="hover" class="events-card">
        <template #header>
          <span>最近转化事件（AI归因）</span>
          <el-tag type="success" size="small" style="margin-left: 8px">
            AI转化占比 {{ funnelData.overall_conversion_rate_pct }}%
          </el-tag>
        </template>
        <el-empty v-if="!recentAIConversions.length" description="暂无AI归因转化事件" :image-size="60" />
        <el-table v-else :data="recentAIConversions" size="small" max-height="300">
          <el-table-column prop="timestamp" label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.timestamp) }}</template>
          </el-table-column>
          <el-table-column prop="type" label="类型" width="100">
            <template #default="{ row }">
              <el-tag size="small">{{ CONV_TYPE_LABELS[row.type] || row.type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="ai_platform" label="AI平台" width="100" />
          <el-table-column prop="value" label="价值" width="100">
            <template #default="{ row }">¥{{ formatMoney(row.value) }}</template>
          </el-table-column>
          <el-table-column prop="landing_page" label="落地页" min-width="200" show-overflow-tooltip />
        </el-table>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useGeoStore } from '../stores/geo'

const store = useGeoStore()
const days = ref(30)
const error = ref('')

const CONV_TYPE_LABELS = {
  form_submit: '表单提交', phone_call: '电话咨询', download: '资料下载',
  registration: '注册', purchase: '购买', custom: '自定义',
}

const funnelData = computed(() => store.funnelData || { stages: [], platform_breakdown: {}, overall_conversion_rate_pct: 0 })

const hasData = computed(() => funnelData.value.stages?.length > 0)

const platformBreakdown = computed(() => {
  const bd = funnelData.value.platform_breakdown || {}
  return Object.entries(bd).map(([platform, data]) => ({ platform, ...data }))
})

const recentAIConversions = computed(() => {
  if (!store.conversionSummary) return []
  // 从store中获取AI归因转化事件
  return (store.conversionsByPlatform || [])
    .flatMap(p => (p.events || []).map(e => ({ ...e, ai_platform: e.ai_platform || p.platform })))
    .slice(0, 20)
})

const maxPV = computed(() => Math.max(...store.trafficTrend.map(t => t.page_views), 1))
const maxConv = computed(() => Math.max(...store.conversionTrend.map(t => t.ai_attributed), 1))

function formatNumber(n) {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n || 0)
}

function formatMoney(v) {
  if (v >= 10000) return (v / 10000).toFixed(1) + '万'
  return (v || 0).toLocaleString()
}

function formatTime(ts) {
  if (!ts) return '-'
  return ts.replace('T', ' ').slice(0, 19)
}

function barWidth(val, max) { return ((val / max) * 100).toFixed(0) + '%' }

function calcPlatformRate(row) {
  const v = row.visits || 0
  const c = row.conversions || 0
  return v > 0 ? ((c / v) * 100).toFixed(1) : '0'
}

function conversionRateTag(row) {
  const rate = parseFloat(calcPlatformRate(row))
  if (rate >= 5) return 'success'
  if (rate >= 2) return 'warning'
  return 'danger'
}

async function refresh() {
  error.value = ''
  try {
    await Promise.all([
      store.fetchFunnelData({ days: days.value }),
      store.fetchTrafficTrend({ days: days.value }),
      store.fetchConversionTrend({ days: days.value }),
      store.fetchConversionsByPlatform({ days: days.value }),
    ])
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  }
}

onMounted(refresh)
</script>

<style scoped>
.funnel-dashboard { max-width: 1240px; margin: 0 auto; padding: 24px; }
.page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
.page-header h2 { margin: 0; color: var(--geo-text); font-size: 20px; }
.page-desc { color: #909399; margin: 0; font-size: 13px; }

.funnel-cards { margin-bottom: 20px; }
.stage-card { text-align: center; border-top: 3px solid var(--geo-primary); }
.stage-card.stage-0 { border-top-color: #C8963E; }
.stage-card.stage-1 { border-top-color: #D4956A; }
.stage-card.stage-2 { border-top-color: #5B8C5A; }
.stage-card.stage-3 { border-top-color: #4A90B8; }
.stage-order { font-size: 12px; color: #909399; margin-bottom: 4px; }
.stage-label { font-size: 13px; color: #606266; margin-bottom: 8px; }
.stage-count { font-size: 28px; font-weight: 700; color: var(--geo-text); }
.stage-rate { font-size: 12px; color: #909399; margin-top: 6px; }

.charts-row { margin-bottom: 20px; }
.chart-container { min-height: 200px; }

.funnel-visual { padding: 20px 0; display: flex; flex-direction: column; align-items: center; gap: 8px; }
.funnel-bar { height: 40px; border-radius: 4px; display: flex; align-items: center; justify-content: space-between;
  padding: 0 12px; color: #fff; font-size: 13px; min-width: 120px; }
.funnel-bar:nth-child(1) { background: #C8963E; }
.funnel-bar:nth-child(2) { background: #D4956A; }
.funnel-bar:nth-child(3) { background: #5B8C5A; }
.funnel-bar:nth-child(4) { background: #4A90B8; }

.simple-bar-chart { display: flex; flex-direction: column; gap: 4px; }
.bar-item { display: flex; align-items: center; gap: 8px; font-size: 11px; }
.bar-label { width: 52px; text-align: right; color: #909399; flex-shrink: 0; }
.bar-track { flex: 1; height: 14px; background: #f0f0f0; border-radius: 7px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 7px; transition: width 0.4s ease; }
.bar-pv { background: #5B8C5A; }
.bar-conv { background: #4A90B8; }
.bar-value { width: 36px; color: #606266; flex-shrink: 0; }

.events-card { margin-top: 0; }
</style>
