<template>
  <div class="adaptation-pipeline">
    <div class="toolbar">
      <el-select v-model="createPlatform" placeholder="选择平台" size="default" style="width:180px">
        <el-option v-for="p in ['wenxin','doubao','tongyi','deepseek','kimi','yuanbao','xinghuo','claude','openai']" :key="p" :label="p" :value="p" />
      </el-select>
      <el-button type="primary" @click="createRun" :loading="creating">创建适配运行</el-button>
      <el-divider direction="vertical" />
      <el-select v-model="filterStatus" placeholder="筛选状态" clearable size="default" style="width:140px">
        <el-option label="进行中" value="in_progress" />
        <el-option label="已完成" value="completed" />
        <el-option label="已回滚" value="rolled_back" />
      </el-select>
      <el-button @click="loadRuns">刷新</el-button>
    </div>

    <!-- Kanban 视图 -->
    <div class="kanban" v-if="runs.length">
      <div class="kanban-column" v-for="run in runs" :key="run.run_id">
        <el-card :class="['run-card', run.status]" shadow="hover">
          <template #header>
            <div class="run-header">
              <span class="run-platform">{{ run.platform_id }}</span>
              <el-tag :type="statusType(run.status)" size="small">{{ run.status }}</el-tag>
            </div>
          </template>

          <div class="run-body">
            <p class="run-id">{{ run.run_id?.slice(-12) }}</p>
            <div class="stage-progress">
              <el-steps :active="stageIndex(run.stage)" direction="vertical" size="small">
                <el-step v-for="(label, key) in stageLabels" :key="key" :title="label" :status="stepStatus(run.stage, key)" />
              </el-steps>
            </div>
            <div class="stats" v-if="run.articles_affected > 0">
              <span>受影响: {{ run.articles_affected }}</span>
              <span v-if="run.articles_regenerated">已生成: {{ run.articles_regenerated }}</span>
              <span v-if="run.articles_published">已发布: {{ run.articles_published }}</span>
            </div>
          </div>

          <div class="run-actions">
            <el-button-group size="small">
              <el-button @click="advanceRun(run)" :disabled="run.status === 'completed' || run.status === 'rolled_back'">下一阶段</el-button>
              <el-button @click="scanRun(run)" :disabled="run.status === 'completed'">扫描存量</el-button>
              <el-button @click="doPublish(run, 'grayscale_10')" :disabled="['monitor_detected','structure_requirement','template_updated','inventory_scanned'].includes(run.stage)">灰度10%</el-button>
              <el-button @click="doPublish(run, 'full')" :disabled="['monitor_detected','structure_requirement','template_updated','inventory_scanned'].includes(run.stage)">全量</el-button>
              <el-button @click="doRollback(run)" type="danger" :disabled="run.status === 'rolled_back'">回滚</el-button>
            </el-button-group>
          </div>

          <div class="post-test" v-if="run.stage?.startsWith('published')">
            <el-button size="small" @click="doPostTest(run, 3)">3天测试</el-button>
            <el-button size="small" @click="doPostTest(run, 7)">7天测试</el-button>
          </div>
        </el-card>
      </div>
    </div>
    <el-empty v-else description="暂无适配运行" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getAdaptationRuns, createAdaptationRun, advanceAdaptationRun,
  scanInventory, publishRun, rollbackRun, postTestRun
} from '@/api'

const createPlatform = ref('doubao')
const creating = ref(false)
const filterStatus = ref('')
const runs = ref([])

const stageLabels = {
  monitor_detected: '监控发现',
  structure_requirement: '调整需求',
  template_updated: '模板更新',
  inventory_scanned: '存量扫描',
  regenerated: '内容重生成',
  validated: '自动校验',
  spot_checked: '人工抽检',
  published_10pct: '灰度10%',
  published_100pct: '全量发布',
  post_test_3d: '3天测试',
  post_test_7d: '7天测试',
}

const stageOrder = Object.keys(stageLabels)

onMounted(() => loadRuns())

async function loadRuns() {
  try {
    const params = {}
    if (filterStatus.value) params.status = filterStatus.value
    const { data } = await getAdaptationRuns(params)
    runs.value = data.runs || []
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function createRun() {
  creating.value = true
  try {
    await createAdaptationRun({ platform_id: createPlatform.value })
    ElMessage.success('适配运行已创建')
    await loadRuns()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    creating.value = false
  }
}

async function advanceRun(run) {
  try {
    const { data } = await advanceAdaptationRun(run.run_id)
    ElMessage.success(`已推进到: ${stageLabels[data.run?.stage] || data.run?.stage}`)
    await loadRuns()
  } catch (e) {
    ElMessage.error('推进失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function scanRun(run) {
  try {
    const { data } = await scanInventory(run.run_id)
    ElMessage.success(`扫描完成: ${data.affected}/${data.total} 篇需要调整`)
    await loadRuns()
  } catch (e) {
    ElMessage.error('扫描失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function doPublish(run, strategy) {
  try {
    await ElMessageBox.confirm(`确认${strategy === 'grayscale_10' ? '灰度发布10%' : '全量发布'}？`, '确认发布', { type: 'warning' })
    await publishRun(run.run_id, strategy)
    ElMessage.success('发布成功')
    await loadRuns()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('发布失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function doRollback(run) {
  try {
    await ElMessageBox.confirm('确认回滚？将恢复旧模板版本。', '确认回滚', { type: 'warning' })
    await rollbackRun(run.run_id)
    ElMessage.success('已回滚')
    await loadRuns()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('回滚失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function doPostTest(run, days) {
  try {
    const { data } = await postTestRun(run.run_id, days)
    ElMessage.success(`${days}天测试完成`)
    await loadRuns()
  } catch (e) {
    ElMessage.error('测试失败: ' + (e.response?.data?.detail || e.message))
  }
}

function stageIndex(stage) {
  const i = stageOrder.indexOf(stage)
  return i >= 0 ? i : 0
}

function stepStatus(current, key) {
  const ci = stageOrder.indexOf(current)
  const ki = stageOrder.indexOf(key)
  if (ki < ci) return 'success'
  if (ki === ci) return 'process'
  return 'wait'
}

function statusType(s) {
  if (s === 'completed') return 'success'
  if (s === 'rolled_back') return 'danger'
  if (s === 'in_progress') return 'warning'
  return 'info'
}
</script>

<style scoped>
.adaptation-pipeline { padding: 4px; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; }
.kanban { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 8px; }
.kanban-column { min-width: 340px; max-width: 380px; }
.run-card { border-left: 3px solid #409eff; }
.run-card.completed { border-left-color: #67c23a; }
.run-card.rolled_back { border-left-color: #f56c6c; opacity: 0.7; }
.run-header { display: flex; justify-content: space-between; align-items: center; }
.run-platform { font-weight: bold; text-transform: capitalize; }
.run-id { font-size: 12px; color: #999; margin: 4px 0; }
.stage-progress { margin: 8px 0; max-height: 280px; overflow-y: auto; }
.stats { font-size: 12px; color: #666; margin: 8px 0; }
.stats span { margin-right: 12px; }
.run-actions { margin-top: 8px; }
.post-test { margin-top: 8px; display: flex; gap: 4px; }
</style>
