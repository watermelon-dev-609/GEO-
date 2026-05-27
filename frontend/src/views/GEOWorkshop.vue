<template>
  <div class="workshop-view">
    <h2 class="page-title">GEO优化工坊</h2>

    <el-row :gutter="20">
      <el-col :span="8">
        <el-card shadow="never">
          <template #header><span>优化配置</span></template>
          <el-form label-position="top">
            <el-form-item label="沙盘业务类型">
              <el-select v-model="sandtableType" style="width: 100%" @change="onTypeChange">
                <el-option v-for="t in sandtableTypes" :key="t.value" :label="t.label" :value="t.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="目标AI平台">
              <el-checkbox-group v-model="selectedPlatforms">
                <el-checkbox v-for="p in availablePlatforms" :key="p.value" :value="p.value" :label="p.value">
                  <span>{{ p.label }}</span>
                </el-checkbox>
              </el-checkbox-group>
            </el-form-item>
            <el-form-item label="源文案（清洗后）">
              <el-input v-model="sourceText" type="textarea" :rows="6" placeholder="从文案导入页面获取，或手动粘贴" />
            </el-form-item>
          </el-form>

          <el-button
            type="primary"
            size="large"
            :icon="MagicStick"
            :loading="isRewriting"
            @click="startRewrite"
            style="width: 100%"
            :disabled="!sourceText || selectedPlatforms.length === 0"
          >
            {{ isRewriting ? '正在生成...' : '开始GEO优化' }}
          </el-button>

          <el-divider />

          <div class="config-hint">
            <p>💡 <strong>提示：</strong></p>
            <ul>
              <li>选择多个平台将并行生成</li>
              <li>每平台独立适配AI采信规则</li>
              <li>下拉选择可查看实时流式生成效果</li>
            </ul>
          </div>
        </el-card>
      </el-col>

      <el-col :span="16">
        <!-- 重优化诊断上下文 -->
        <div v-if="showReoptContext" style="margin-bottom: 16px;">
          <el-alert
            title="评测诊断结果 — 请根据以下诊断针对性优化文案"
            type="warning"
            :closable="true"
            @close="showReoptContext = false"
          >
            <div v-for="(wp, i) in reoptWeakPoints" :key="'wp-'+i" style="margin: 4px 0; font-size: 13px;">
              - {{ wp }}
            </div>
          </el-alert>
          <el-alert
            v-if="reoptSuggestions.length > 0"
            title="优化建议"
            type="success"
            :closable="false"
            style="margin-top: 8px;"
          >
            <div v-for="(sg, i) in reoptSuggestions" :key="'sg-'+i" style="margin: 2px 0; font-size: 13px;">
              - {{ sg }}
            </div>
          </el-alert>
        </div>

        <el-card shadow="never" v-if="results.length === 0 && !isRewriting" class="empty-card">
          <div class="empty-state">
            <el-icon :size="64" color="#c0c4cc"><EditPen /></el-icon>
            <h3>选择沙盘类型和AI平台，开始GEO优化</h3>
            <p>系统将针对每个平台的AI收录逻辑生成专属优化文案</p>
          </div>
        </el-card>

        <div v-if="isRewriting" class="streaming-area">
          <el-alert title="正在生成优化文案..." type="info" :closable="false" />
          <div v-if="streamText" class="stream-output">{{ streamText }}</div>
        </div>

        <el-tabs v-model="activeTab" v-if="results.length > 0">
          <el-tab-pane
            v-for="r in results"
            :key="r.platform"
            :label="r.platform"
            :name="r.platform"
          >
            <el-card shadow="never">
              <div class="result-text">{{ r.optimized_text }}</div>

              <el-collapse style="margin-top: 16px;">
                <el-collapse-item title="优化策略说明" name="strategy">
                  <div class="strategy-notes" v-html="renderMarkdown(r.strategy_notes)"></div>
                </el-collapse-item>
              </el-collapse>

              <div class="result-meta">
                <el-tag size="small">字数: {{ r.word_count }}</el-tag>
                <el-button size="small" type="primary" link @click="copyText(r.optimized_text)">
                  <el-icon><CopyDocument /></el-icon> 复制
                </el-button>
              </div>
            </el-card>
          </el-tab-pane>
        </el-tabs>
      </el-col>
    </el-row>

    <div style="text-align: right; margin-top: 20px;" v-if="results.length > 0">
      <el-button type="warning" size="large" @click="goToEvaluate">
        进入AI评测中心 <el-icon><ArrowRight /></el-icon>
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useGeoStore } from '../stores/geo'
import { rewriteText, getSandtableProfile } from '../api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const store = useGeoStore()

const sandtableType = ref(store.currentSandtableType || 'smart_traffic')
const selectedPlatforms = ref(store.selectedPlatforms || [])
const sourceText = ref(store.cleanedText || '')
const isRewriting = ref(false)
const streamText = ref('')
const results = ref([])
const activeTab = ref('')
const sandtableProfile = ref(null)
const showReoptContext = ref(false)
const reoptWeakPoints = ref([])
const reoptSuggestions = ref([])

const sandtableTypes = [
  { value: 'smart_traffic', label: '智慧交通沙盘' },
  { value: 'smart_city', label: '智慧城市沙盘' },
  { value: 'smart_industry', label: '智慧工业沙盘' },
  { value: 'smart_agriculture', label: '智慧农业沙盘' },
  { value: 'smart_logistics', label: '智慧物流沙盘' },
  { value: 'military_terrain', label: '军事地形沙盘' },
  { value: 'digital_multimedia', label: '数字多媒体沙盘' },
  { value: 'real_estate', label: '地产/规划/展厅沙盘' },
]

const availablePlatforms = [
  { value: 'wenxin', label: '文心一言' },
  { value: 'tongyi', label: '通义千问' },
  { value: 'gpt', label: 'GPT' },
  { value: 'claude', label: 'Claude' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'doubao', label: '字节豆包' },
  { value: 'yuanbao', label: '腾讯元宝' },
]

onMounted(() => {
  sourceText.value = store.cleanedText
  if (store.currentSandtableType) sandtableType.value = store.currentSandtableType

  // 检测从评测中心传入的重优化上下文
  if (store.reoptimizeContext) {
    const ctx = store.reoptimizeContext
    if (ctx.sourceText) sourceText.value = ctx.sourceText
    if (ctx.sandtableType) sandtableType.value = ctx.sandtableType
    if (ctx.weakPoints?.length) reoptWeakPoints.value = ctx.weakPoints
    if (ctx.suggestions?.length) reoptSuggestions.value = ctx.suggestions
    showReoptContext.value = true
    store.clearReoptimizeContext()
  }
})

async function onTypeChange(val) {
  try {
    const res = await getSandtableProfile(val)
    sandtableProfile.value = res.data
  } catch { /* ignore */ }
}

async function startRewrite() {
  if (selectedPlatforms.value.length === 0) {
    ElMessage.warning('请至少选择一个AI平台')
    return
  }

  isRewriting.value = true
  streamText.value = ''
  results.value = []

  // 单平台使用 SSE 流式生成，多平台使用批处理
  if (selectedPlatforms.value.length === 1) {
    await startStreamRewrite(selectedPlatforms.value[0])
  } else {
    await startBatchRewrite()
  }
  isRewriting.value = false
}

async function startStreamRewrite(platform) {
  const url = `/api/geo/rewrite/stream`
  const body = {
    cleaned_text: sourceText.value,
    sandtable_type: sandtableType.value,
    platforms: [platform],
    dimensions: store.dimensions,
  }

  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const dataMatch = line.match(/^data: (.+)$/)
        if (!dataMatch) continue
        if (dataMatch[1] === '[DONE]') continue

        try {
          const chunk = JSON.parse(dataMatch[1])
          if (chunk.type === 'token') {
            streamText.value += chunk.content
          } else if (chunk.type === 'done') {
            results.value = [{
              platform,
              optimized_text: chunk.full_text,
              strategy_notes: chunk.strategy_notes || '',
              word_count: chunk.word_count,
            }]
            activeTab.value = platform
            store.setRewriteResults(results.value)
            store.setSelectedPlatforms(selectedPlatforms.value)
            ElMessage.success(`流式生成完成（${chunk.word_count} 字）`)
          } else if (chunk.type === 'error') {
            ElMessage.error('流式生成失败: ' + chunk.message)
          }
        } catch { /* 跳过非 JSON 行 */ }
      }
    }
  } catch (e) {
    if (!e.response?.data?.detail) {
      ElMessage.error('流式连接中断: ' + (e.message || '未知错误'))
    }
  }
}

async function startBatchRewrite() {
  try {
    const res = await rewriteText({
      cleaned_text: sourceText.value,
      sandtable_type: sandtableType.value,
      platforms: selectedPlatforms.value,
      dimensions: store.dimensions,
    })

    results.value = res.data.results || []
    activeTab.value = results.value[0]?.platform || ''

    store.setRewriteResults(results.value)
    store.setSelectedPlatforms(selectedPlatforms.value)

    const successCount = results.value.filter(r => r.optimized_text).length
    ElMessage.success(`优化完成！${successCount}/${results.value.length} 个平台生成成功`)

    store.addToHistory({
      name: 'GEO优化',
      sandtableType: sandtableType.value,
      status: `已优化 (${successCount}平台)`,
    })
  } catch (e) {
    ElMessage.error('优化失败: ' + (e.response?.data?.detail || e.message))
  }
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => ElMessage.success('已复制'))
}

function renderMarkdown(text) {
  return text.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
}

function goToEvaluate() {
  router.push('/evaluation')
}
</script>

<style scoped>
.workshop-view { max-width: 1200px; }
.page-title { font-size: 20px; margin-bottom: 20px; color: #303133; }
.empty-card { min-height: 400px; display: flex; align-items: center; justify-content: center; }
.empty-state { text-align: center; color: #909399; padding: 60px 0; }
.empty-state h3 { margin: 16px 0 8px; color: #606266; }
.streaming-area { margin-bottom: 16px; }
.stream-output { background: #1d1e2c; color: #e5e5e5; padding: 16px; border-radius: 8px; margin-top: 12px; max-height: 400px; overflow-y: auto; white-space: pre-wrap; font-family: monospace; font-size: 13px; line-height: 1.8; }
.result-text { white-space: pre-wrap; line-height: 1.8; font-size: 14px; max-height: 500px; overflow-y: auto; }
.result-meta { margin-top: 12px; display: flex; gap: 8px; align-items: center; }
.strategy-notes { white-space: normal; line-height: 1.8; font-size: 13px; }
.config-hint { font-size: 13px; color: #909399; }
.config-hint ul { padding-left: 18px; margin-top: 4px; }
.config-hint li { margin: 2px 0; }
</style>
