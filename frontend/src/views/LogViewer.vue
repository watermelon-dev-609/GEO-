<template>
  <div class="log-page">
    <div class="page-header">
      <h2>系统日志</h2>
      <div class="toolbar">
        <el-select v-model="level" size="small" style="width:100px">
          <el-option label="ERROR" value="ERROR" />
          <el-option label="WARNING" value="WARNING" />
          <el-option label="INFO" value="INFO" />
          <el-option label="DEBUG" value="DEBUG" />
        </el-select>
        <el-select v-model="hours" size="small" style="width:100px">
          <el-option label="1小时" :value="1" />
          <el-option label="6小时" :value="6" />
          <el-option label="24小时" :value="24" />
          <el-option label="7天" :value="168" />
        </el-select>
        <el-button size="small" @click="fetchLogs" :loading="loading">刷新</el-button>
        <el-button size="small" @click="downloadLog">下载日志</el-button>
      </div>
    </div>
    <el-card shadow="hover">
      <div class="log-container" ref="logContainer">
        <div v-if="entries.length === 0" class="empty-hint">{{ loading ? '加载中...' : '暂无日志' }}</div>
        <div v-for="(entry, i) in entries" :key="i" class="log-line" :class="logClass(entry.line)">
          <span class="log-num">{{ i + 1 }}</span>
          <code>{{ entry.line }}</code>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getRecentLogs, downloadLogs } from '../api'

const level = ref('ERROR')
const hours = ref(24)
const entries = ref([])
const loading = ref(false)

async function fetchLogs() {
  loading.value = true
  try {
    const res = await getRecentLogs({ level: level.value, hours: hours.value, limit: 200 })
    entries.value = res.data.entries || []
  } catch (e) {
    if (e.response?.status !== 404) ElMessage.error('加载日志失败: ' + (e.response?.data?.detail || e.message))
  } finally { loading.value = false }
}

function logClass(line) {
  if (line?.includes('[ERROR]')) return 'log-error'
  if (line?.includes('[WARNING]')) return 'log-warn'
  return ''
}

async function downloadLog() {
  try {
    const res = await downloadLogs()
    const blob = new Blob([res.data], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `geo-system-log-${Date.now()}.log`; a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('日志下载已开始')
  } catch (e) { ElMessage.error('下载失败: ' + (e.response?.data?.detail || e.message)) }
}

fetchLogs()
</script>

<style scoped>
.log-page { padding: 4px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 20px; }
.toolbar { display: flex; gap: 8px; align-items: center; }
.log-container { background: #1e1e1e; color: #d4d4d4; font-family: 'Courier New', monospace; font-size: 12px;
  padding: 12px; border-radius: 6px; max-height: 600px; overflow-y: auto; }
.log-line { padding: 2px 0; display: flex; gap: 8px; }
.log-num { color: #858585; min-width: 32px; text-align: right; user-select: none; }
.log-line.log-error { background: rgba(244,67,54,.15); }
.log-line.log-warn { background: rgba(255,152,0,.1); }
code { white-space: pre-wrap; word-break: break-all; }
.empty-hint { text-align: center; color: #858585; padding: 40px 0; }
</style>
