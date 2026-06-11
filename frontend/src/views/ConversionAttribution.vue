<template>
  <div class="attribution-view" v-loading="loading">
    <div class="page-header">
      <h2>转化归因分析</h2>
      <p class="page-desc">多模型归因，追踪AI引用对实际转化的贡献</p>
      <div class="controls">
        <el-radio-group v-model="model" size="small" @change="refresh">
          <el-radio-button value="last_click">末次点击</el-radio-button>
          <el-radio-button value="first_click">首次点击</el-radio-button>
          <el-radio-button value="linear">线性</el-radio-button>
          <el-radio-button value="time_decay">时间衰减</el-radio-button>
          <el-radio-button value="position_based">位置基础</el-radio-button>
        </el-radio-group>
        <el-radio-group v-model="days" size="small" @change="refresh" style="margin-left: 12px">
          <el-radio-button :value="7">7天</el-radio-button>
          <el-radio-button :value="30">30天</el-radio-button>
          <el-radio-button :value="90">90天</el-radio-button>
        </el-radio-group>
        <el-button size="small" type="primary" @click="refresh" :loading="loading" style="margin-left: 12px">刷新</el-button>
      </div>
    </div>

    <el-result v-if="error" icon="error" title="加载失败" :sub-title="error">
      <template #extra><el-button @click="refresh">重试</el-button></template>
    </el-result>

    <template v-else>
      <!-- Summary Cards -->
      <el-row :gutter="16" class="summary-row">
        <el-col :span="6">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-label">总转化数</div>
            <div class="stat-value">{{ data.total_conversions || 0 }}</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover" class="stat-card highlight">
            <div class="stat-label">AI归因转化</div>
            <div class="stat-value accent">{{ data.ai_attributed_count || 0 }}</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-label">AI转化占比</div>
            <div class="stat-value">{{ data.ai_citation_rate_pct || 0 }}%</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-label">AI转化价值</div>
            <div class="stat-value">¥{{ formatMoney(data.ai_attributed_value || 0) }}</div>
          </el-card>
        </el-col>
      </el-row>

      <!-- Source Breakdown -->
      <el-row :gutter="16" class="charts-row">
        <el-col :span="12">
          <el-card shadow="hover">
            <template #header>按来源渠道分布</template>
            <el-empty v-if="!sourceList.length" description="暂无数据" :image-size="60" />
            <div class="source-list" v-else>
              <div class="source-item" v-for="s in sourceList" :key="s.name">
                <span class="source-name">{{ SOURCE_LABELS[s.name] || s.name }}</span>
                <div class="source-bar-track">
                  <div class="source-bar" :style="{ width: barWidth(s.count, maxSource) }"></div>
                </div>
                <span class="source-count">{{ s.count }}</span>
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="hover">
            <template #header>按AI平台归因</template>
            <el-empty v-if="!platformList.length" description="暂无AI归因数据" :image-size="60" />
            <div class="source-list" v-else>
              <div class="source-item" v-for="p in platformList" :key="p.name">
                <span class="source-name">{{ p.name }}</span>
                <div class="source-bar-track">
                  <div class="source-bar ai-bar" :style="{ width: barWidth(p.count, maxPlatform) }"></div>
                </div>
                <span class="source-count">{{ p.count }}</span>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- Attribution Paths -->
      <el-card shadow="hover">
        <template #header>归因路径</template>
        <el-empty v-if="!attributionPaths.length" description="暂无归因路径数据" :image-size="60" />
        <el-table v-else :data="attributionPaths" size="small" max-height="350">
          <el-table-column prop="path" label="路径" min-width="300" show-overflow-tooltip />
          <el-table-column prop="touchpoint_count" label="触点" width="70" />
          <el-table-column label="转化" width="70">
            <template #default="{ row }">
              <el-tag :type="row.converted ? 'success' : 'danger'" size="small">{{ row.converted ? '是' : '否' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="价值" width="100">
            <template #default="{ row }">¥{{ formatMoney(row.value) }}</template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getAttribution } from '../api'
import { ElMessage } from 'element-plus'

const model = ref('last_click')
const days = ref(30)
const data = ref({})
const loading = ref(false)
const error = ref('')

const SOURCE_LABELS = {
  ai_referral: 'AI平台引用', organic: '自然搜索', social: '社交媒体',
  email: '邮件', cpc: '付费点击', direct: '直接访问',
}

const sourceList = computed(() => {
  const bySource = data.value.by_source || {}
  return Object.entries(bySource)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
})

const platformList = computed(() => {
  const byPlat = data.value.by_ai_platform || {}
  return Object.entries(byPlat)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
})

const attributionPaths = computed(() => data.value.attribution_paths || [])

const maxSource = computed(() => Math.max(...sourceList.value.map(s => s.count), 1))
const maxPlatform = computed(() => Math.max(...platformList.value.map(p => p.count), 1))

function barWidth(val, max) { return ((val / max) * 100).toFixed(0) + '%' }
function formatMoney(v) {
  if (v >= 10000) return (v / 10000).toFixed(1) + '万'
  return (v || 0).toLocaleString()
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const res = await getAttribution({ days: days.value, model: model.value })
    data.value = res.data || {}
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<style scoped>
.attribution-view { max-width: 1240px; margin: 0 auto; padding: 24px; }
.page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
.page-header h2 { margin: 0; color: var(--geo-text); font-size: 20px; }
.page-desc { color: #909399; margin: 0; font-size: 13px; }
.controls { display: flex; align-items: center; margin-left: auto; }

.summary-row { margin-bottom: 20px; }
.stat-card { text-align: center; }
.stat-card.highlight { border-top: 3px solid var(--geo-primary); }
.stat-label { font-size: 13px; color: #909399; margin-bottom: 8px; }
.stat-value { font-size: 28px; font-weight: 700; color: var(--geo-text); }
.stat-value.accent { color: var(--geo-primary); }

.charts-row { margin-bottom: 20px; }
.source-list { display: flex; flex-direction: column; gap: 10px; padding: 10px 0; }
.source-item { display: flex; align-items: center; gap: 10px; font-size: 13px; }
.source-name { width: 100px; text-align: right; color: #606266; flex-shrink: 0; }
.source-bar-track { flex: 1; height: 20px; background: #f0f0f0; border-radius: 10px; overflow: hidden; }
.source-bar { height: 100%; background: #5B8C5A; border-radius: 10px; transition: width 0.5s ease; }
.ai-bar { background: var(--geo-primary); }
.source-count { width: 40px; color: #606266; flex-shrink: 0; }
</style>
