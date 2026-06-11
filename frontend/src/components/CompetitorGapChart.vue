<template>
  <el-dialog v-model="visible" :title="'竞品差距分析: ' + competitorName" width="700px">
    <div v-if="loading" style="text-align:center;padding:40px;">分析中...</div>
    <div v-else-if="!chartData" style="text-align:center;padding:40px;color:#909399;">暂无对比数据</div>
    <div v-else>
      <div ref="chartRef" style="width:100%;height:420px;"></div>
      <el-divider />
      <h4 style="margin-bottom:8px;">差距溯源</h4>
      <el-table :data="gapItems" size="small" stripe>
        <el-table-column prop="dimension" label="维度" width="120" />
        <el-table-column prop="ours" label="我方" width="80" />
        <el-table-column prop="theirs" label="竞品" width="80" />
        <el-table-column prop="gap" label="差距">
          <template #default="{ row }">
            <span :style="{ color: row.gap > 0 ? '#67c23a' : '#f56c6c' }">
              {{ row.gap > 0 ? '+' : '' }}{{ row.gap }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="suggestion" label="建议" min-width="200" />
      </el-table>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'
import * as echarts from 'echarts'

const visible = ref(false)
const loading = ref(false)
const competitorName = ref('')
const chartRef = ref(null)
const chartData = ref(null)
const gapItems = ref([])

const DIMENSIONS = ['品牌曝光', '内容结构', '量化数据', 'FAQ友好', '差异化', '信源可信']

async function show(competitorId, competitorTitle) {
  visible.value = true
  competitorName.value = competitorTitle
  loading.value = true
  chartData.value = null
  try {
    const res = await api.get(`/competitors/${competitorId}`)
    const comp = res.data
    const features = comp.content_features || {}
    const exposure = comp.platform_exposure || {}

    const ours = [
      features.our_brand_score || 50,
      features.our_structure || 45,
      features.our_quantified || 40,
      features.our_faq || 35,
      features.our_differentiation || 55,
      features.our_credibility || 60,
    ]
    const theirs = [
      features.brand_score || 60,
      features.structure || 55,
      features.quantified || 50,
      features.faq || 40,
      features.differentiation || 50,
      features.credibility || 55,
    ]

    gapItems.value = DIMENSIONS.map((dim, i) => ({
      dimension: dim,
      ours: ours[i],
      theirs: theirs[i],
      gap: ours[i] - theirs[i],
      suggestion: ours[i] >= theirs[i] ? '保持优势' : `需提升${dim}，竞品领先${theirs[i] - ours[i]}分`,
    }))

    chartData.value = { ours, theirs }
    await nextTick()
    renderChart(ours, theirs)
  } catch (e) {
    ElMessage.error('加载竞品数据失败: ' + (e.response?.data?.detail || e.message))
  } finally { loading.value = false }
}

function renderChart(ours, theirs) {
  if (!chartRef.value) return
  const chart = echarts.init(chartRef.value)
  chart.setOption({
    tooltip: {},
    legend: { data: ['我方', '竞品'], bottom: 0 },
    radar: {
      indicator: DIMENSIONS.map(d => ({ name: d, max: 100 })),
      center: ['50%', '55%'],
      radius: '65%',
    },
    series: [{
      type: 'radar',
      data: [
        { value: ours, name: '我方', areaStyle: { color: 'rgba(200,150,62,0.2)' }, lineStyle: { color: '#C8963E' }, itemStyle: { color: '#C8963E' } },
        { value: theirs, name: '竞品', areaStyle: { color: 'rgba(91,138,172,0.2)' }, lineStyle: { color: '#5B8AAC' }, itemStyle: { color: '#5B8AAC' } },
      ],
    }],
  })
  setTimeout(() => chart.resize(), 100)
}

defineExpose({ show })
</script>

<style scoped>
h4 { font-size: 14px; color: #606266; }
</style>
