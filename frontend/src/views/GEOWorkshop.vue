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
              <div v-if="store.configuredPlatforms.length === 0" style="margin-bottom:8px;">
                <el-alert title="暂未配置任何AI平台，请先在 config/api_keys.yaml 中配置API Key" type="warning" :closable="false" />
              </div>
              <el-checkbox-group v-model="selectedPlatforms">
                <el-checkbox v-for="p in availablePlatforms" :key="p.value" :value="p.value" :label="p.value">
                  <span>{{ p.label }}</span>
                  <el-tag v-if="isPlatformConfigured(p.value)" size="small" type="success" effect="plain" style="margin-left:4px;">已配置</el-tag>
                  <el-tag v-else size="small" type="danger" effect="plain" style="margin-left:4px;">未配置</el-tag>
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
            :disabled="!sourceText || selectedPlatforms.length === 0 || isRewriting"
          >
            {{ isRewriting ? rewriteProgressText : '开始GEO优化' }}
          </el-button>

          <el-button
            v-if="isRewriting"
            type="danger"
            size="default"
            @click="cancelRewrite"
            style="width: 100%; margin-top: 8px"
          >
            停止生成
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
            title="迭代优化建议（点击「采纳」将自动带入优化指令）"
            type="success"
            :closable="false"
            style="margin-top: 8px;"
          >
            <div
              v-for="(sg, i) in reoptSuggestions"
              :key="'sg-'+i"
              class="suggestion-row"
              :class="{ adopted: adoptedHints.includes(sg) }"
            >
              <span class="suggestion-text">- {{ sg }}</span>
              <el-button
                v-if="!adoptedHints.includes(sg)"
                size="small"
                type="success"
                @click="adoptHint(sg)"
              >采纳</el-button>
              <el-button
                v-else
                size="small"
                type="danger"
                @click="removeHint(sg)"
              >取消</el-button>
            </div>
            <div v-if="adoptedHints.length > 0" class="adopted-summary">
              已采纳 {{ adoptedHints.length }} 条建议，将在优化时作为重点改进方向
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
          <el-alert :title="rewriteProgressText" type="info" :closable="false" />
          <div v-if="selectedPlatforms.length > 1" class="batch-progress">
            <el-progress :percentage="Math.round(batchCompleted / batchTotal * 100)" :stroke-width="12" />
            <div class="batch-detail">
              <span v-for="p in selectedPlatforms" :key="p" class="batch-platform" :class="{ done: batchDoneSet.has(p), active: batchCurrent === p }">
                {{ p }}
                <el-icon v-if="batchDoneSet.has(p)" color="#5B8C5A" :size="14"><CircleCheckFilled /></el-icon>
                <el-icon v-else-if="batchCurrent === p" color="#C8963E" :size="14" class="is-loading"><Loading /></el-icon>
                <el-icon v-else color="#c0c4cc" :size="14"><Clock /></el-icon>
              </span>
            </div>
          </div>
          <div v-if="streamText" class="stream-output">{{ streamText }}</div>
        </div>

        <!-- 平台对比摘要 -->
        <div v-if="results.length > 1" class="platform-compare">
          <el-table :data="results" size="small" stripe>
            <el-table-column prop="platform" label="平台" width="100" />
            <el-table-column prop="word_count" label="字数" width="80" align="right" />
            <el-table-column label="优化策略" min-width="200">
              <template #default="scope">
                <span style="font-size:12px;color:#6B6E7B;">{{ scope.row.strategy_notes?.substring(0, 60) }}{{ scope.row.strategy_notes?.length > 60 ? '...' : '' }}</span>
              </template>
            </el-table-column>
          </el-table>
          <el-divider />
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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useGeoStore } from '../stores/geo'
import { rewriteText, getSandtableProfile } from '../api'
import { ElMessage } from 'element-plus'
import { SANDTABLE_TYPES, AI_PLATFORMS } from '../constants'

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
const adoptedHints = ref([])

function adoptHint(sg) { adoptedHints.value.push(sg) }
function removeHint(sg) { adoptedHints.value = adoptedHints.value.filter(h => h !== sg) }

// ── 取消/进度控制 ──
const abortController = ref(null)
const batchCompleted = ref(0)
const batchTotal = ref(0)
const batchDoneSet = ref(new Set())
const batchCurrent = ref('')

const rewriteProgressText = computed(() => {
  if (!isRewriting.value) return '开始GEO优化'
  if (selectedPlatforms.value.length > 1) {
    return `正在生成... (${batchCompleted.value}/${batchTotal.value})`
  }
  return '正在生成...'
})

const sandtableTypes = SANDTABLE_TYPES
const availablePlatforms = AI_PLATFORMS

onMounted(() => {
  // 只在文本为空或来自重优化时自动填充，避免覆盖用户手动编辑
  if (!sourceText.value || store.reoptimizeContext) {
    sourceText.value = store.cleanedText
  }
  if (store.currentSandtableType && !sandtableType.value) {
    sandtableType.value = store.currentSandtableType
  }

  // 检测从评测中心传入的重优化上下文
  if (store.reoptimizeContext) {
    const ctx = store.reoptimizeContext
    if (ctx.sourceText) sourceText.value = ctx.sourceText
    if (ctx.sandtableType) sandtableType.value = ctx.sandtableType
    if (ctx.weakPoints?.length) reoptWeakPoints.value = ctx.weakPoints
    if (ctx.suggestions?.length) {
      reoptSuggestions.value = ctx.suggestions
      if (ctx.autoAdoptAll) {
        adoptedHints.value = [...ctx.suggestions]
      }
    }
    showReoptContext.value = true
    store.clearReoptimizeContext()
  }
})

onUnmounted(() => {
  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
  }
})

function isPlatformConfigured(platformValue) {
  return store.configuredPlatforms.some(p => p.platform === platformValue)
}

async function onTypeChange(val) {
  try {
    const res = await getSandtableProfile(val)
    sandtableProfile.value = res.data
  } catch (e) { console.error('onTypeChange failed:', e) }
}

async function startRewrite() {
  if (selectedPlatforms.value.length === 0) {
    ElMessage.warning('请至少选择一个AI平台')
    return
  }

  isRewriting.value = true
  streamText.value = ''
  results.value = []
  batchCompleted.value = 0
  batchTotal.value = selectedPlatforms.value.length
  batchDoneSet.value = new Set()
  batchCurrent.value = ''

  if (selectedPlatforms.value.length === 1) {
    await startStreamRewrite(selectedPlatforms.value[0])
  } else {
    await startBatchRewrite()
  }
  isRewriting.value = false
  abortController.value = null
}

function cancelRewrite() {
  if (abortController.value) {
    abortController.value.abort()
  }
  isRewriting.value = false
  ElMessage.info('已停止生成')
}

async function startStreamRewrite(platform) {
  const controller = new AbortController()
  abortController.value = controller
  batchCurrent.value = platform

  const url = `/api/geo/rewrite/stream`
  const body = {
    cleaned_text: sourceText.value,
    sandtable_type: sandtableType.value,
    platforms: [platform],
    dimensions: store.dimensions,
    optimization_hints: adoptedHints.value,
  }

  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
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
            batchCompleted.value = 1
            batchDoneSet.value = new Set([platform])
            store.setRewriteResults(results.value)
            store.setSelectedPlatforms(selectedPlatforms.value)
            ElMessage.success(`优化完成（${chunk.word_count} 字）`)
          } else if (chunk.type === 'error') {
            ElMessage.error('流式生成失败: ' + chunk.message)
          }
        } catch { /* 跳过非 JSON 行 */ }
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') return
    ElMessage.error('流式连接中断: ' + (e.message || '未知错误'))
  }
}

async function startBatchRewrite() {
  const controller = new AbortController()
  abortController.value = controller

  // 逐个平台请求，每个都可感知进度
  const allPlatforms = [...selectedPlatforms.value]
  const allResults = []
  let successCount = 0

  for (const platform of allPlatforms) {
    if (abortController.value?.signal?.aborted) break
    batchCurrent.value = platform

    try {
      const res = await rewriteText({
        cleaned_text: sourceText.value,
        sandtable_type: sandtableType.value,
        platforms: [platform],
        dimensions: store.dimensions,
        optimization_hints: adoptedHints.value,
      }, { signal: abortController.value?.signal })

      const platformResult = res.data.results?.[0]
      if (platformResult?.optimized_text) {
        allResults.push(platformResult)
        successCount++
      }
    } catch (e) {
      if (e.name === 'AbortError' || e.code === 'ERR_CANCELED') break
      // 单个平台失败不影响其他平台
    }

    batchCompleted.value++
    batchDoneSet.value = new Set([...batchDoneSet.value, platform])
  }

  results.value = allResults
  if (allResults.length > 0) {
    activeTab.value = allResults[0]?.platform || ''
  }

  store.setRewriteResults(results.value)
  store.setSelectedPlatforms(selectedPlatforms.value)

  if (successCount > 0) {
    ElMessage.success(`优化完成！${successCount}/${allPlatforms.length} 个平台生成成功`)
    store.addToHistory({
      name: 'GEO优化',
      sandtableType: sandtableType.value,
      status: `已优化 (${successCount}平台)`,
    })
  }
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => ElMessage.success('已复制'))
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function renderMarkdown(text) {
  if (!text) return ''
  return escapeHtml(text)
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
}

function goToEvaluate() {
  router.push('/evaluation')
}
</script>

<style scoped>
.workshop-view { max-width: 1240px; }
.page-title { font-size: 20px; margin-bottom: 20px; color: #2D3142; font-weight: 700; }
.empty-card { min-height: 400px; display: flex; align-items: center; justify-content: center; }
.empty-state { text-align: center; color: #9B9EAA; padding: 60px 0; }
.empty-state h3 { margin: 16px 0 8px; color: #6B6E7B; }
.streaming-area { margin-bottom: 16px; }
.batch-progress { margin: 12px 0; }
.batch-detail { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.batch-platform { display: flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 6px; font-size: 13px; background: #FAF8F5; border: 1px solid #E8E5DF; }
.batch-platform.done { background: rgba(91,140,90,0.08); border-color: rgba(91,140,90,0.18); color: #5B8C5A; }
.batch-platform.active { background: rgba(200,150,62,0.08); border-color: rgba(200,150,62,0.18); color: #C8963E; }
.stream-output { background: #151721; color: #e5e5e5; padding: 16px; border-radius: 10px; margin-top: 12px; max-height: 400px; overflow-y: auto; white-space: pre-wrap; font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 13px; line-height: 1.8; }
.result-text { white-space: pre-wrap; line-height: 1.8; font-size: 14px; max-height: 500px; overflow-y: auto; }
.result-meta { margin-top: 12px; display: flex; gap: 8px; align-items: center; }
.strategy-notes { white-space: normal; line-height: 1.8; font-size: 13px; }
.suggestion-row { display: flex; align-items: center; justify-content: space-between; margin: 4px 0; padding: 4px 8px; border-radius: 4px; transition: background 0.22s cubic-bezier(0.4,0,0.2,1); }
.suggestion-row.adopted { background: rgba(91,140,90,0.08); }
.suggestion-text { flex: 1; font-size: 13px; margin-right: 8px; }
.adopted-summary { margin-top: 8px; padding: 6px 10px; background: rgba(91,140,90,0.08); border-radius: 4px; font-size: 13px; color: #5B8C5A; font-weight: bold; }
.config-hint { font-size: 13px; color: #9B9EAA; }
.config-hint ul { padding-left: 18px; margin-top: 4px; }
.config-hint li { margin: 2px 0; }
.platform-compare { margin-bottom: 16px; }
</style>
