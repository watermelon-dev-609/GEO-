<template>
  <el-dialog v-model="visible" title="版本对比" width="800px" top="5vh">
    <div v-if="loading" class="loading-hint">加载中...</div>
    <div v-else-if="!diffData" class="empty-hint">暂无对比数据</div>
    <div v-else class="diff-container">
      <div class="diff-meta">
        <span>v{{ diffData.version1?.num }}: {{ diffData.version1?.title }} ({{ diffData.version1?.word_count }}字)</span>
        <el-icon><Right /></el-icon>
        <span>v{{ diffData.version2?.num }}: {{ diffData.version2?.title }} ({{ diffData.version2?.word_count }}字)</span>
        <span class="diff-stats">
          <span style="color:#67c23a;">+{{ diffData.added_lines }}</span>
          <span style="color:#f56c6c;">-{{ diffData.removed_lines }}</span>
          <span>{{ diffData.word_diff > 0 ? '+' : '' }}{{ diffData.word_diff }}字</span>
        </span>
      </div>
      <div class="diff-lines">
        <div v-for="(line, i) in diffData.diff_lines" :key="i" class="diff-line" :class="diffLineClass(line)">
          <span class="diff-line-num">{{ i + 1 }}</span>
          <code>{{ line }}</code>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const visible = ref(false)
const loading = ref(false)
const diffData = ref(null)

function diffLineClass(line) {
  if (line.startsWith('+') && !line.startsWith('+++')) return 'line-added'
  if (line.startsWith('-') && !line.startsWith('---')) return 'line-removed'
  if (line.startsWith('@@')) return 'line-hunk'
  return ''
}

async function show(textId, v1Id, v2Id) {
  visible.value = true
  loading.value = true
  diffData.value = null
  try {
    const res = await api.get(`/versions/${textId}/compare`, { params: { v1: v1Id, v2: v2Id } })
    diffData.value = res.data
  } catch (e) {
    ElMessage.error('加载对比失败: ' + (e.response?.data?.detail || e.message))
  } finally { loading.value = false }
}

defineExpose({ show })
</script>

<style scoped>
.loading-hint, .empty-hint { text-align: center; padding: 40px; color: #909399; }
.diff-meta { display: flex; align-items: center; gap: 8px; font-size: 13px; margin-bottom: 12px; padding: 8px; background: #f5f7fa; border-radius: 6px; }
.diff-stats { margin-left: auto; display: flex; gap: 12px; font-weight: bold; }
.diff-lines { background: #1e1e1e; color: #d4d4d4; font-family: 'Courier New', monospace; font-size: 12px;
  border-radius: 6px; max-height: 420px; overflow-y: auto; }
.diff-line { display: flex; padding: 1px 8px; }
.diff-line.line-added { background: rgba(103,194,58,.15); }
.diff-line.line-removed { background: rgba(245,108,108,.15); }
.diff-line.line-hunk { background: rgba(64,158,255,.1); color: #409eff; }
.diff-line-num { color: #858585; min-width: 40px; text-align: right; margin-right: 8px; user-select: none; }
code { white-space: pre-wrap; word-break: break-all; }
</style>
