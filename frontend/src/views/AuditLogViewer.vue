<template>
  <div class="audit-page">
    <div class="page-header">
      <h2>审计日志</h2>
      <div class="toolbar">
        <el-date-picker v-model="date" type="date" size="small" placeholder="选择日期" />
        <el-input v-model="pathFilter" size="small" placeholder="路径过滤" style="width:160px" clearable />
        <el-button size="small" @click="fetchLogs" :loading="loading">查询</el-button>
        <el-button size="small" @click="exportCSV">导出CSV</el-button>
      </div>
    </div>
    <el-card shadow="hover">
      <el-table :data="entries" stripe size="small" max-height="500" v-loading="loading">
        <el-table-column prop="timestamp" label="时间" width="180" />
        <el-table-column prop="method" label="方法" width="70" />
        <el-table-column prop="path" label="路径" min-width="200" />
        <el-table-column prop="client_ip" label="客户端IP" width="130" />
        <el-table-column prop="status" label="状态码" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status < 400 ? 'success' : 'danger'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="duration_ms" label="耗时" width="80">
          <template #default="{ row }">{{ row.duration_ms }}ms</template>
        </el-table-column>
      </el-table>
      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          @current-change="fetchLogs"
          small
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getAuditLogs, exportAuditLogs } from '../api'

const date = ref(null)
const pathFilter = ref('')
const entries = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)

function formatDate(d) {
  if (!d) return new Date().toISOString().slice(0, 10)
  return new Date(d).toISOString().slice(0, 10)
}

async function fetchLogs() {
  loading.value = true
  try {
    const params = { date: formatDate(date.value), page: page.value, page_size: pageSize.value }
    if (pathFilter.value) params.action = pathFilter.value
    const res = await getAuditLogs(params)
    entries.value = res.data.entries || []
    total.value = res.data.total || 0
  } catch (e) {
    if (e.response?.status !== 404) ElMessage.error('加载审计日志失败: ' + (e.response?.data?.detail || e.message))
  } finally { loading.value = false }
}

async function exportCSV() {
  try {
    const res = await exportAuditLogs(formatDate(date.value))
    const blob = new Blob([res.data], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `audit-log-${formatDate(date.value)}.csv`; a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e) { ElMessage.error('导出失败: ' + (e.response?.data?.detail || e.message)) }
}

fetchLogs()
</script>

<style scoped>
.audit-page { padding: 4px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 20px; }
.toolbar { display: flex; gap: 8px; align-items: center; }
.pagination { margin-top: 12px; display: flex; justify-content: center; }
</style>
