<template>
  <div class="batch-page">
    <div class="page-header">
      <h2>批量处理</h2>
      <p class="subtitle">支持多篇文案的批量导入、清洗、优化、评测和导出</p>
    </div>

    <el-row :gutter="16" class="batch-layout">
      <!-- 左侧：文本列表 -->
      <el-col :span="7">
        <el-card shadow="hover" class="text-list-card">
          <template #header>
            <div class="card-header">
              <span>文本列表 ({{ texts.length }})</span>
              <el-button-group>
                <el-button size="small" @click="addText">添加</el-button>
                <el-button size="small" type="primary" @click="showBatchPaste = true">批量粘贴</el-button>
              </el-button-group>
            </div>
          </template>
          <div v-if="texts.length === 0" class="empty-hint">点击「添加」或「批量粘贴」导入文案</div>
          <el-scrollbar height="400px">
            <div v-for="(item, i) in texts" :key="item.id" class="text-item" :class="{ active: selectedIndex === i }" @click="selectedIndex = i">
              <div class="text-item-header">
                <el-input v-model="item.title" size="small" placeholder="标题" @click.stop />
              </div>
              <div class="text-item-preview">{{ item.content.slice(0, 80) }}{{ item.content.length > 80 ? '...' : '' }}</div>
              <div class="text-item-meta">
                <span>{{ item.content.length }}字</span>
                <el-button size="small" type="danger" text @click.stop="removeText(i)">删除</el-button>
              </div>
            </div>
          </el-scrollbar>
        </el-card>
      </el-col>

      <!-- 中间：操作配置 -->
      <el-col :span="9">
        <el-card shadow="hover" class="action-card">
          <template #header>
            <span>处理配置</span>
          </template>
          <el-form label-position="top" size="default">
            <el-form-item label="沙盘类型">
              <el-select v-model="sandtableType" style="width:100%" placeholder="选择沙盘类型">
                <el-option v-for="t in sandtableTypes" :key="t.value" :label="t.label" :value="t.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="目标平台">
              <el-checkbox-group v-model="selectedPlatforms">
                <el-checkbox v-for="p in platforms" :key="p.value" :value="p.value" :label="p.label" />
              </el-checkbox-group>
            </el-form-item>
            <el-form-item label="操作步骤">
              <div class="action-buttons">
                <el-button type="primary" @click="startBatchClean" :loading="isRunning" :disabled="texts.length === 0">
                  1. 批量清洗
                </el-button>
                <el-button type="success" @click="startBatchDiagnose" :loading="isRunning" :disabled="texts.length === 0">
                  快速诊断
                </el-button>
                <el-button type="warning" @click="startBatchOptimize" :loading="isRunning" :disabled="texts.length === 0 || selectedPlatforms.length === 0">
                  2. 批量优化
                </el-button>
                <el-button type="danger" @click="startBatchEvaluate" :loading="isRunning" :disabled="texts.length === 0">
                  3. 批量评测
                </el-button>
                <el-button @click="startBatchExport" :loading="isExporting" :disabled="texts.length === 0">
                  4. 批量导出
                </el-button>
              </div>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 合规检测 -->
        <el-card v-if="currentCompliance" shadow="hover" class="compliance-card" style="margin-top:12px;">
          <template #header>
            <div class="card-header">
              <span>合规检测</span>
              <el-tag :type="currentCompliance.passed ? 'success' : 'danger'" size="small">
                {{ currentCompliance.passed ? '通过' : `${currentCompliance.violation_count}个违规` }}
              </el-tag>
            </div>
          </template>
          <div v-if="!currentCompliance.passed">
            <div v-for="(v, vi) in currentCompliance.violations" :key="vi" class="violation-item">
              <span class="violation-word">{{ v.word }}</span>
              <span class="violation-cat">{{ v.category }}</span>
              <div class="violation-sug">{{ v.suggestion }}</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧：进度与结果 -->
      <el-col :span="8">
        <el-card shadow="hover" class="progress-card">
          <template #header>
            <div class="card-header">
              <span>处理进度</span>
              <span v-if="isRunning" class="progress-text">
                {{ completedCount }}/{{ texts.length }}
              </span>
              <el-button v-if="isRunning" size="small" type="danger" @click="cancelTask">取消</el-button>
            </div>
          </template>
          <el-progress v-if="isRunning" :percentage="Math.round((completedCount / Math.max(1, texts.length)) * 100)" :stroke-width="16" :text-inside="true" />
          <div v-if="!isRunning && batchResults.length === 0" class="empty-hint">点击左侧操作按钮开始处理</div>
          <el-scrollbar height="360px">
            <div v-for="(item, i) in batchItems" :key="i" class="progress-item">
              <div class="progress-item-title">
                <el-tag :type="statusType(item.status)" size="small">{{ statusLabel(item.status) }}</el-tag>
                <span>{{ item.title }}</span>
              </div>
              <div v-if="item.error" class="progress-item-error">{{ item.error }}</div>
              <div v-if="item.result" class="progress-item-result">
                <span v-if="item.result.overall_score">评分: {{ item.result.overall_score }}</span>
                <span v-else-if="item.result.platform_results">
                  {{ Object.keys(item.result.platform_results).length }}平台已优化
                </span>
              </div>
            </div>
          </el-scrollbar>
        </el-card>
      </el-col>
    </el-row>

    <!-- 批量粘贴弹窗 -->
    <el-dialog v-model="showBatchPaste" title="批量粘贴文案" width="700px">
      <el-alert type="info" :closable="false" show-icon style="margin-bottom:12px;">
        每行一篇文案，或用「---」分隔多篇。每篇至少50字符。
      </el-alert>
      <el-input v-model="batchPasteText" type="textarea" :rows="12" placeholder="粘贴多篇文案，用 --- 分隔..." />
      <template #footer>
        <el-button @click="showBatchPaste = false">取消</el-button>
        <el-button type="primary" @click="parseBatchPaste">解析并导入</el-button>
      </template>
    </el-dialog>

    <!-- 文本编辑弹窗 -->
    <el-dialog v-model="showTextEditor" title="编辑文案" width="700px">
      <el-input v-model="editingText.content" type="textarea" :rows="15" />
      <template #footer>
        <el-button @click="showTextEditor = false">取消</el-button>
        <el-button type="primary" @click="saveTextEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  batchClean, batchDiagnose, batchExport,
  startBatchOptimizeSSE, startBatchEvaluateSSE, cancelBatchTask,
  checkCompliance,
} from '../api'
import { SANDTABLE_TYPES, AI_PLATFORMS } from '../constants'

const sandtableTypes = SANDTABLE_TYPES

const platforms = AI_PLATFORMS

const texts = ref([])
const selectedIndex = ref(-1)
const sandtableType = ref('smart_traffic')
const selectedPlatforms = ref(['deepseek'])
const isRunning = ref(false)
const isExporting = ref(false)
const currentCompliance = ref(null)
const batchItems = ref([])
const batchResults = ref([])
const completedCount = ref(0)
const failedCount = ref(0)
const currentTask = ref(null)
const showBatchPaste = ref(false)
const batchPasteText = ref('')
const showTextEditor = ref(false)
const editingText = reactive({ id: '', title: '', content: '' })

let _idCounter = 0
function newId() { return `text_${Date.now()}_${_idCounter++}` }

function addText() {
  const item = { id: newId(), title: `文案${texts.value.length + 1}`, content: '' }
  texts.value.push(item)
  editingText.id = item.id
  editingText.title = item.title
  editingText.content = item.content
  showTextEditor.value = true
}

function removeText(i) {
  texts.value.splice(i, 1)
  if (selectedIndex.value >= texts.value.length) selectedIndex.value = texts.value.length - 1
}

function parseBatchPaste() {
  const raw = batchPasteText.value.trim()
  if (!raw) { ElMessage.warning('请粘贴文案内容'); return }
  const parts = raw.split(/\n?---\n?/).filter(p => p.trim())
  if (parts.length === 0) {
    const lines = raw.split('\n').filter(l => l.trim())
    if (lines.length === 0) { ElMessage.warning('未解析到有效文案'); return }
    lines.forEach((line, i) => {
      texts.value.push({ id: newId(), title: `文案${texts.value.length + 1}`, content: line.trim() })
    })
  } else {
    parts.forEach((part, i) => {
      texts.value.push({ id: newId(), title: `文案${texts.value.length + 1}`, content: part.trim() })
    })
  }
  ElMessage.success(`已导入 ${Math.max(parts.length, raw.split('\n').filter(l => l.trim()).length)} 篇文案`)
  showBatchPaste.value = false
  batchPasteText.value = ''
}

function saveTextEdit() {
  const idx = texts.value.findIndex(t => t.id === editingText.id)
  if (idx >= 0) {
    texts.value[idx].title = editingText.title
    texts.value[idx].content = editingText.content
  }
  showTextEditor.value = false
}

function statusType(s) {
  return s === 'completed' ? 'success' : s === 'failed' ? 'danger' : s === 'running' ? 'warning' : 'info'
}
function statusLabel(s) {
  return s === 'completed' ? '完成' : s === 'failed' ? '失败' : s === 'running' ? '处理中' : '等待'
}

function initBatchItems() {
  batchItems.value = texts.value.map(t => ({ id: t.id, title: t.title, status: 'pending', result: null, error: '' }))
  completedCount.value = 0
  failedCount.value = 0
}
function updateBatchItem(itemId, updates) {
  const item = batchItems.value.find(it => it.id === itemId)
  if (item) Object.assign(item, updates)
}

async function startBatchClean() {
  if (texts.value.length === 0) { ElMessage.warning('请先添加文案'); return }
  isRunning.value = true
  initBatchItems()
  try {
    const payload = { texts: texts.value.map(t => ({ id: t.id, title: t.title, content: t.content })), sandtable_type: sandtableType.value }
    const res = await batchClean(payload)
    res.data.forEach((r, i) => {
      updateBatchItem(r.id, { status: r.status, result: { cleaned_word_count: r.cleaned_word_count, dimensions: r.dimensions }, error: r.error || '' })
      if (r.status === 'completed') {
        completedCount.value++
        texts.value[i] && (texts.value[i].content = r.cleaned_word_count ? '(已清洗)' : texts.value[i].content)
      } else { failedCount.value++ }
    })
    ElMessage.success(`批量清洗完成: ${completedCount.value}成功 / ${failedCount.value}失败`)
  } catch (e) {
    ElMessage.error('批量清洗失败: ' + (e.response?.data?.detail || e.message))
  } finally { isRunning.value = false }
}

async function startBatchDiagnose() {
  if (texts.value.length === 0) { ElMessage.warning('请先添加文案'); return }
  isRunning.value = true
  initBatchItems()
  try {
    const payload = { texts: texts.value.map(t => ({ id: t.id, title: t.title, content: t.content })), sandtable_type: sandtableType.value }
    const res = await batchDiagnose(payload)
    res.data.forEach(r => {
      updateBatchItem(r.id, { status: 'completed', result: { overall_score: r.overall_score, scores: r.scores } })
      completedCount.value++
    })
    ElMessage.success(`批量诊断完成: ${completedCount.value}篇`)
  } catch (e) {
    ElMessage.error('批量诊断失败: ' + (e.response?.data?.detail || e.message))
  } finally { isRunning.value = false }
}

function startBatchOptimize() {
  if (texts.value.length === 0) { ElMessage.warning('请先添加文案'); return }
  if (selectedPlatforms.value.length === 0) { ElMessage.warning('请选择至少一个目标平台'); return }
  isRunning.value = true
  initBatchItems()
  const payload = {
    texts: texts.value.map(t => ({ id: t.id, title: t.title, content: t.content })),
    sandtable_type: sandtableType.value,
    platforms: selectedPlatforms.value,
  }
  currentTask.value = startBatchOptimizeSSE(payload,
    (type, data) => {
      if (type === 'done') { isRunning.value = false; ElMessage.success(`批量优化完成: ${completedCount.value}成功 / ${failedCount.value}失败`) }
      else if (data.type === 'item_start') updateBatchItem(data.item_id, { status: 'running' })
      else if (data.type === 'item_done') { updateBatchItem(data.item_id, { status: 'completed', result: { platform_results: data.platform_results } }); completedCount.value++ }
      else if (data.type === 'item_error') { updateBatchItem(data.item_id, { status: 'failed', error: data.error }); failedCount.value++ }
      else if (data.type === 'batch_done') { isRunning.value = false }
      else if (data.type === 'cancelled') { isRunning.value = false; ElMessage.info('任务已取消') }
    },
    (err) => { isRunning.value = false; ElMessage.error('批量优化失败: ' + err.message) }
  )
}

function startBatchEvaluate() {
  if (texts.value.length === 0) { ElMessage.warning('请先添加文案'); return }
  isRunning.value = true
  initBatchItems()
  const payload = {
    texts: texts.value.map(t => ({ id: t.id, title: t.title, content: t.content })),
    sandtable_type: sandtableType.value,
    platforms: selectedPlatforms.value,
  }
  currentTask.value = startBatchEvaluateSSE(payload,
    (type, data) => {
      if (type === 'done') { isRunning.value = false; ElMessage.success(`批量评测完成: ${completedCount.value}成功 / ${failedCount.value}失败`) }
      else if (data.type === 'item_start') updateBatchItem(data.item_id, { status: 'running' })
      else if (data.type === 'item_done') { updateBatchItem(data.item_id, { status: 'completed', result: { overall_score: data.overall_score } }); completedCount.value++ }
      else if (data.type === 'item_error') { updateBatchItem(data.item_id, { status: 'failed', error: data.error }); failedCount.value++ }
      else if (data.type === 'batch_done') { isRunning.value = false }
      else if (data.type === 'cancelled') { isRunning.value = false; ElMessage.info('任务已取消') }
    },
    (err) => { isRunning.value = false; ElMessage.error('批量评测失败: ' + err.message) }
  )
}

async function startBatchExport() {
  if (texts.value.length === 0) { ElMessage.warning('请先添加文案'); return }
  isExporting.value = true
  try {
    const res = await batchExport({ text_ids: texts.value.map(t => t.id), format: 'zip' })
    const blob = new Blob([res.data], { type: 'application/zip' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `geo-batch-export-${Date.now()}.zip`; a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('批量导出完成')
  } catch (e) {
    ElMessage.error('导出失败: ' + (e.response?.data?.detail || e.message))
  } finally { isExporting.value = false }
}

function cancelTask() {
  if (currentTask.value) { currentTask.value.close(); currentTask.value = null }
  isRunning.value = false
}

// 合规检测（选中文本变化时自动检测）
import { watch } from 'vue'
watch(() => texts.value.map(t => t.content).join('|||'), async (val) => {
  if (!val || val.length < 50) { currentCompliance.value = null; return }
  try {
    const res = await checkCompliance({ text: val.slice(0, 5000) })
    currentCompliance.value = res.data
  } catch { currentCompliance.value = null }
}, { debounce: 1000 })
</script>

<style scoped>
.batch-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 20px; }
.subtitle { margin: 4px 0 0; color: #909399; font-size: 13px; }
.batch-layout { margin-top: 12px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.text-item {
  padding: 10px 12px; border-bottom: 1px solid #ebeef5; cursor: pointer; transition: background .2s;
}
.text-item:hover { background: #f5f7fa; }
.text-item.active { background: #ecf5ff; border-left: 3px solid #409eff; }
.text-item-header { margin-bottom: 4px; }
.text-item-preview { font-size: 12px; color: #606266; line-height: 1.5; }
.text-item-meta { display: flex; justify-content: space-between; align-items: center; margin-top: 6px; font-size: 11px; color: #c0c4cc; }
.action-buttons { display: flex; flex-wrap: wrap; gap: 8px; }
.progress-item { padding: 8px 0; border-bottom: 1px solid #ebeef5; }
.progress-item-title { display: flex; align-items: center; gap: 8px; }
.progress-item-error { font-size: 12px; color: #f56c6c; margin-top: 4px; }
.progress-item-result { font-size: 12px; color: #67c23a; margin-top: 4px; }
.violation-item { padding: 8px 0; border-bottom: 1px solid #fde2e2; }
.violation-word { font-weight: bold; color: #f56c6c; margin-right: 8px; }
.violation-cat { font-size: 11px; color: #909399; background: #f4f4f5; padding: 1px 6px; border-radius: 3px; }
.violation-sug { font-size: 12px; color: #909399; margin-top: 4px; }
.empty-hint { text-align: center; color: #c0c4cc; padding: 40px 0; font-size: 13px; }
.progress-text { font-size: 12px; color: #409eff; }
.compliance-card { border-left: 3px solid #e6a23c; }
</style>
