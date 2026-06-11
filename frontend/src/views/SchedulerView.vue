<template>
  <div class="scheduler-page">
    <div class="page-header">
      <h2>定时任务管理</h2>
      <div class="toolbar">
        <el-button type="primary" size="small" @click="showCreateDialog = true">创建任务</el-button>
        <el-button size="small" @click="refreshJobs" :loading="loading">刷新</el-button>
      </div>
    </div>

    <!-- 异常告警 -->
    <el-card v-if="anomalies.length > 0" shadow="hover" class="anomaly-card">
      <template #header>
        <div class="card-header">
          <span style="color:#e6a23c;">⚠ 异常告警 ({{ anomalies.length }})</span>
        </div>
      </template>
      <div v-for="(a, i) in anomalies" :key="i" class="anomaly-item">
        <el-tag :type="a.level === 'critical' ? 'danger' : 'warning'" size="small">{{ a.level === 'critical' ? '严重' : '警告' }}</el-tag>
        <span>{{ a.message }}</span>
        <span class="anomaly-time">{{ a.detected_at }}</span>
      </div>
    </el-card>

    <!-- 任务列表 -->
    <el-card shadow="hover" style="margin-top:12px;">
      <el-table :data="jobs" stripe size="small" v-loading="loading">
        <el-table-column prop="name" label="任务名称" min-width="160" />
        <el-table-column prop="type" label="类型" width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ typeLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="trigger_value" label="触发规则" width="140">
          <template #default="{ row }">
            {{ row.trigger === 'cron' ? row.trigger_value : `每${row.trigger_value}分钟` }}
          </template>
        </el-table-column>
        <el-table-column prop="enabled" label="状态" width="80">
          <template #default="{ row }">
            <el-switch :model-value="row.enabled" @change="(v) => toggleJob(row.id, v)" size="small" />
          </template>
        </el-table-column>
        <el-table-column prop="last_run" label="上次执行" width="160">
          <template #default="{ row }">{{ row.last_run || '尚未执行' }}</template>
        </el-table-column>
        <el-table-column prop="run_count" label="执行次数" width="80" />
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button size="small" type="danger" text @click="deleteJobConfirm(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="jobs.length === 0 && !loading" class="empty-hint">暂无定时任务，点击「创建任务」开始</div>
    </el-card>

    <!-- 创建任务弹窗 -->
    <el-dialog v-model="showCreateDialog" title="创建定时任务" width="500px">
      <el-form label-position="top">
        <el-form-item label="任务名称">
          <el-input v-model="newJob.name" placeholder="例如：每日品牌收录监测" />
        </el-form-item>
        <el-form-item label="任务类型">
          <el-select v-model="newJob.type" style="width:100%">
            <el-option label="品牌收录监测" value="brand_monitor" />
            <el-option label="平台规则检查" value="platform_check" />
            <el-option label="周报生成" value="weekly_report" />
            <el-option label="月报生成" value="monthly_report" />
          </el-select>
        </el-form-item>
        <el-form-item label="触发器类型">
          <el-radio-group v-model="newJob.trigger">
            <el-radio value="interval">间隔执行</el-radio>
            <el-radio value="cron">Cron表达式</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="newJob.trigger === 'cron' ? 'Cron表达式' : '间隔（分钟）'">
          <el-input v-if="newJob.trigger === 'cron'" v-model="newJob.triggerValue" placeholder="0 9 * * 1 (每周一早9点)" />
          <el-input-number v-else v-model="newJob.triggerValue" :min="5" :max="10080" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="createJob" :loading="creating">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const jobs = ref([])
const anomalies = ref([])
const loading = ref(false)
const creating = ref(false)
const showCreateDialog = ref(false)
const newJob = ref({ name: '', type: 'brand_monitor', trigger: 'interval', triggerValue: 1440 })

function typeLabel(t) {
  return { brand_monitor: '品牌监测', platform_check: '平台检查', weekly_report: '周报', monthly_report: '月报' }[t] || t
}

async function refreshJobs() {
  loading.value = true
  try {
    const [jobsRes, anomRes] = await Promise.all([
      api.get('/scheduler/jobs'),
      api.get('/scheduler/anomalies'),
    ])
    jobs.value = jobsRes.data.jobs || []
    anomalies.value = anomRes.data.alerts || []
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.response?.data?.detail || e.message))
  } finally { loading.value = false }
}

async function createJob() {
  if (!newJob.value.name) { ElMessage.warning('请输入任务名称'); return }
  creating.value = true
  try {
    await api.post('/scheduler/jobs', null, {
      params: {
        name: newJob.value.name,
        job_type: newJob.value.type,
        trigger: newJob.value.trigger,
        trigger_value: String(newJob.value.triggerValue),
      },
    })
    ElMessage.success('任务创建成功')
    showCreateDialog.value = false
    newJob.value = { name: '', type: 'brand_monitor', trigger: 'interval', triggerValue: 1440 }
    refreshJobs()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.response?.data?.detail || e.message))
  } finally { creating.value = false }
}

async function toggleJob(id, enabled) {
  try {
    await api.put(`/scheduler/jobs/${id}`, null, { params: { enabled } })
    const job = jobs.value.find(j => j.id === id)
    if (job) job.enabled = enabled
    ElMessage.success(enabled ? '已启用' : '已停用')
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function deleteJobConfirm(id) {
  try {
    await ElMessageBox.confirm('确定删除此定时任务？', '确认', { type: 'warning' })
    await api.delete(`/scheduler/jobs/${id}`)
    jobs.value = jobs.value.filter(j => j.id !== id)
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

onMounted(refreshJobs)
</script>

<style scoped>
.scheduler-page { padding: 4px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 20px; }
.toolbar { display: flex; gap: 8px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.anomaly-card { border: 1px solid #e6a23c; }
.anomaly-item { padding: 8px 0; border-bottom: 1px solid #ebeef5; display: flex; align-items: center; gap: 8px; font-size: 13px; }
.anomaly-time { color: #909399; font-size: 11px; margin-left: auto; }
.empty-hint { text-align: center; color: #c0c4cc; padding: 40px 0; }
</style>
