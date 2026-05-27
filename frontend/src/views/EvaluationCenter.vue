<template>
  <div class="eval-view">
    <h2 class="page-title">AI评测中心</h2>

    <el-row :gutter="20">
      <!-- 左侧：配置面板 -->
      <el-col :span="8">
        <el-card shadow="never" class="config-card">
          <template #header><span>评测配置</span></template>

          <el-form label-position="top" size="default">
            <!-- 评测模式 -->
            <el-form-item label="评测模式">
              <el-radio-group v-model="evalMode" @change="onModeChange">
                <el-radio-button value="pipeline">流程模式</el-radio-button>
                <el-radio-button value="standalone">独立模式</el-radio-button>
              </el-radio-group>
            </el-form-item>

            <!-- 文本来源 -->
            <el-form-item label="评测文本">
              <template v-if="evalMode === 'pipeline'">
                <el-select v-model="textSource" style="width: 100%" @change="onTextSourceChange">
                  <el-option label="使用优化结果（第一条）" value="rewrite" />
                  <el-option label="手动输入" value="manual" />
                </el-select>
                <el-input
                  v-if="textSource === 'manual'"
                  v-model="evalText"
                  type="textarea"
                  :rows="6"
                  placeholder="粘贴需要评测的文案"
                  style="margin-top: 8px"
                />
                <div v-else class="text-preview">{{ evalText?.substring(0, 200) }}{{ evalText?.length > 200 ? '...' : '' }}</div>
              </template>
              <template v-else>
                <el-input v-model="evalText" type="textarea" :rows="8" placeholder="粘贴需要评测的文案..." />
              </template>
            </el-form-item>

            <!-- 对比原文 -->
            <el-form-item>
              <el-collapse>
                <el-collapse-item title="对比原文（可选）" name="original">
                  <el-input v-model="originalText" type="textarea" :rows="4" placeholder="粘贴优化前的原文，用于生成前后对比报告" />
                </el-collapse-item>
              </el-collapse>
            </el-form-item>

            <!-- 沙盘类型 -->
            <el-form-item label="沙盘类型">
              <el-select v-model="sandtableType" style="width: 100%">
                <el-option v-for="t in sandtableTypes" :key="t.value" :label="t.label" :value="t.value" />
              </el-select>
            </el-form-item>

            <!-- 目标平台 -->
            <el-form-item label="目标平台">
              <el-select v-model="targetPlatforms" multiple style="width: 100%" placeholder="选择AI平台">
                <el-option v-for="p in availablePlatforms" :key="p.value" :label="p.label" :value="p.value" />
              </el-select>
            </el-form-item>

            <!-- 用户角色 -->
            <el-form-item label="模拟用户角色">
              <el-checkbox-group v-model="userRoles">
                <el-checkbox v-for="r in roleOptions" :key="r.value" :value="r.value">{{ r.label }}</el-checkbox>
              </el-checkbox-group>
            </el-form-item>

            <!-- 评测维度 + 权重 -->
            <el-form-item label="评测维度">
              <div v-for="dim in dimensionConfigs" :key="dim.key" class="dim-row">
                <el-checkbox
                  v-model="dim.enabled"
                  :disabled="dim.requires_llm && !hasLLM"
                  @change="onDimensionChange"
                >
                  {{ dim.label }}
                  <el-tag v-if="dim.requires_llm" size="small" type="info" style="margin-left: 4px">LLM</el-tag>
                </el-checkbox>
                <el-slider
                  v-if="dim.enabled"
                  v-model="dim.weight"
                  :min="0"
                  :max="100"
                  :step="5"
                  size="small"
                  style="width: 120px; margin-left: 12px"
                  @input="onWeightChange"
                />
                <span v-if="dim.enabled" class="dim-weight">{{ dim.weight }}%</span>
              </div>
            </el-form-item>

            <!-- 自定义问题 -->
            <el-form-item label="自定义问题（可选，一行一个）">
              <el-input v-model="customQuestions" type="textarea" :rows="3" placeholder="自定义评测问题..." />
            </el-form-item>
          </el-form>

          <!-- 操作按钮 -->
          <div class="action-buttons">
            <el-button
              type="primary"
              size="large"
              :loading="isRunning"
              @click="startEval"
              style="width: 100%"
              :disabled="!evalText"
            >
              {{ isRunning ? '评测中...' : '开始评测' }}
            </el-button>
            <el-button
              v-if="isRunning"
              type="danger"
              size="default"
              @click="cancelEval"
              style="width: 100%; margin-top: 8px"
            >
              取消评测
            </el-button>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧：进度/结果区 -->
      <el-col :span="16">
        <!-- 空状态 -->
        <el-card shadow="never" v-if="evalStatus === 'idle'" class="empty-card">
          <div class="empty-state">
            <el-icon :size="64" color="#c0c4cc"><DataAnalysis /></el-icon>
            <h3>配置评测参数并开始评测</h3>
            <p>系统将分阶段执行评测，实时展示各维度结果</p>
          </div>
        </el-card>

        <!-- 进度区 -->
        <el-card shadow="never" v-if="evalStatus !== 'idle'" class="progress-card">
          <template #header>
            <div class="progress-header">
              <span>评测进度</span>
              <el-tag :type="statusTagType" size="small">{{ statusLabel }}</el-tag>
            </div>
          </template>

          <el-progress
            :percentage="evalOverallProgress"
            :status="evalStatus === 'failed' ? 'exception' : (evalStatus === 'completed' ? 'success' : '')"
            :stroke-width="16"
          />

          <!-- 阶段列表 -->
          <div class="phase-list">
            <div
              v-for="phase in phaseOrder"
              :key="phase.key"
              class="phase-row"
              :class="{ 'is-active': phase.status === 'running' }"
            >
              <div class="phase-icon">
                <el-icon v-if="phase.status === 'completed'" color="#67C23A"><CircleCheckFilled /></el-icon>
                <el-icon v-else-if="phase.status === 'running'" color="#409EFF" class="is-loading"><Loading /></el-icon>
                <el-icon v-else-if="phase.status === 'failed'" color="#F56C6C"><CircleCloseFilled /></el-icon>
                <el-icon v-else-if="phase.status === 'skipped'" color="#909399"><RemoveFilled /></el-icon>
                <el-icon v-else color="#c0c4cc"><Clock /></el-icon>
              </div>
              <div class="phase-info">
                <span class="phase-label">{{ phase.label }}</span>
                <span v-if="phase.score !== null" class="phase-score" :style="{ color: scoreColor(phase.score) }">
                  {{ phase.score }}分
                </span>
                <span v-if="phase.status === 'running'" class="phase-running">评测中...</span>
              </div>
            </div>
          </div>
        </el-card>

        <!-- 完成后的综合结果 -->
        <div v-if="evalStatus === 'completed' && evalOverallScore !== null">
          <!-- 综合评分 -->
          <el-card shadow="never" class="score-card" style="margin-top: 16px">
            <div class="overall-score">
              <div class="score-number" :style="{ color: scoreColor(evalOverallScore) }">
                {{ evalOverallScore }}
              </div>
              <div class="score-label">综合评分 / 100</div>
            </div>

            <!-- 维度得分条 -->
            <div class="dim-scores" style="margin-top: 16px">
              <div v-for="dim in completedDimensions" :key="dim.key" class="dim-score-row">
                <span class="dim-name">{{ dim.label }}</span>
                <el-progress
                  :percentage="dim.score"
                  :color="scoreColor(dim.score)"
                  :stroke-width="8"
                  style="flex: 1; margin: 0 12px"
                />
                <span class="dim-value">{{ dim.score }}分</span>
              </div>
            </div>
          </el-card>

          <!-- 前后对比 -->
          <el-card shadow="never" style="margin-top: 16px" v-if="beforeAfter">
            <template #header><span>优化前后对比</span></template>
            <div class="comparison">
              <div class="comp-item">
                <span class="comp-label">优化前</span>
                <span class="comp-value">{{ beforeAfter.before_score }}分</span>
              </div>
              <el-icon :size="24"><ArrowRight /></el-icon>
              <div class="comp-item">
                <span class="comp-label">优化后</span>
                <span class="comp-value">{{ beforeAfter.after_score }}分</span>
              </div>
              <el-tag :type="beforeAfter.improvement_percent > 0 ? 'success' : 'danger'" size="large">
                {{ beforeAfter.improvement_percent > 0 ? '+' : '' }}{{ beforeAfter.improvement_percent }}%
              </el-tag>
            </div>
          </el-card>

          <!-- 短板诊断 -->
          <el-card shadow="never" style="margin-top: 16px" v-if="weakPoints.length">
            <template #header><span>短板诊断</span></template>
            <el-alert
              v-for="(wp, i) in weakPoints"
              :key="i"
              :title="wp"
              type="warning"
              :closable="false"
              style="margin-bottom: 8px"
            />
          </el-card>

          <!-- 优化建议 -->
          <el-card shadow="never" style="margin-top: 16px" v-if="suggestions.length">
            <template #header><span>迭代优化建议</span></template>
            <el-alert
              v-for="(sg, i) in suggestions"
              :key="i"
              :title="sg"
              type="success"
              :closable="false"
              style="margin-bottom: 8px"
            />
          </el-card>

          <!-- 操作 -->
          <div style="text-align: right; margin-top: 16px">
            <el-button type="primary" @click="resetEval">重新评测</el-button>
            <el-button type="success" @click="goToExport">导出报告</el-button>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useGeoStore } from '../stores/geo'
import { getEvalDimensions, startEvalSSE, cancelEval as apiCancelEval } from '../api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const store = useGeoStore()

// ── 配置状态 ──
const evalMode = ref(store.evalMode || 'pipeline')
const textSource = ref('rewrite')
const evalText = ref('')
const originalText = ref('')
const sandtableType = ref(store.currentSandtableType || 'smart_traffic')
const targetPlatforms = ref(store.selectedPlatforms.length > 0 ? store.selectedPlatforms : ['deepseek'])
const userRoles = ref(['b_end_procurement', 'general_consultant'])
const customQuestions = ref('')

const dimensionConfigs = ref([])
const hasLLM = computed(() => store.configuredPlatforms.length > 0)

// ── 评测运行状态 ──
const isRunning = ref(false)
const evalStatus = ref('idle')
const evalOverallProgress = ref(0)
const evalOverallScore = ref(null)
const evalSessionId = ref(null)
const sseConnection = ref(null)

const phaseStates = ref({})

const phaseOrderDef = [
  { key: 'generating_questions', label: '生成评测问题', status: 'pending', score: null, result: null },
  { key: 'brand_recall', label: '品牌召回率', status: 'pending', score: null, result: null },
  { key: 'solution_match', label: '方案匹配度', status: 'pending', score: null, result: null },
  { key: 'advantage_citation', label: '优势采信率', status: 'pending', score: null, result: null },
  { key: 'structure_quality', label: '结构化程度', status: 'pending', score: null, result: null },
  { key: 'differentiation', label: '差异化程度', status: 'pending', score: null, result: null },
  { key: 'comprehensive', label: '综合评分', status: 'pending', score: null, result: null },
]

const phaseOrder = computed(() => phaseOrderDef.map(p => ({
  ...p,
  status: phaseStates.value[p.key]?.status || 'pending',
  score: phaseStates.value[p.key]?.score ?? null,
  result: phaseStates.value[p.key]?.result ?? null,
})))

const beforeAfter = computed(() => {
  const comp = phaseStates.value['comprehensive']?.result
  return comp?.before_after_comparison || null
})
const weakPoints = computed(() => {
  return phaseStates.value['comprehensive']?.result?.weak_points || []
})
const suggestions = computed(() => {
  return phaseStates.value['comprehensive']?.result?.suggestions || []
})
const completedDimensions = computed(() => {
  const comp = phaseStates.value['comprehensive']?.result
  if (!comp?.dimension_scores) return []
  return Object.entries(comp.dimension_scores).map(([key, score]) => {
    const dim = dimensionConfigs.value.find(d => d.key === key)
    return { key, label: dim?.label || key, score }
  })
})

const statusTagType = computed(() => {
  if (evalStatus.value === 'completed') return 'success'
  if (evalStatus.value === 'failed') return 'danger'
  if (evalStatus.value === 'cancelled') return 'warning'
  return 'info'
})
const statusLabel = computed(() => {
  if (evalStatus.value === 'running') return '评测中'
  if (evalStatus.value === 'completed') return '已完成'
  if (evalStatus.value === 'cancelled') return '已取消'
  if (evalStatus.value === 'failed') return '失败'
  return ''
})

// ── 沙盘类型 / 平台 / 角色选项 ──
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
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'wenxin', label: '文心一言' },
  { value: 'tongyi', label: '通义千问' },
  { value: 'gpt', label: 'GPT' },
  { value: 'claude', label: 'Claude' },
  { value: 'doubao', label: '字节豆包' },
  { value: 'yuanbao', label: '腾讯元宝' },
]
const roleOptions = [
  { value: 'b_end_procurement', label: 'B端政企采购' },
  { value: 'technical_selection', label: '技术人员选型' },
  { value: 'project_manager', label: '项目经办人' },
  { value: 'general_consultant', label: '普通咨询用户' },
]

// ── 初始化 ──
onMounted(async () => {
  try {
    const res = await getEvalDimensions()
    const dims = res.data.dimensions || []
    dimensionConfigs.value = dims.map(d => ({
      ...d,
      enabled: !(d.requires_llm && !hasLLM.value),
    }))
  } catch { /* 使用默认 */ }

  const firstResult = store.rewriteResults[0]
  evalText.value = firstResult?.optimized_text || store.cleanedText || ''
  originalText.value = store.originalText || ''
})

// ── 模式切换 ──
function onModeChange(val) {
  store.setEvalMode(val)
  if (val === 'standalone') {
    evalText.value = ''
  } else {
    const firstResult = store.rewriteResults[0]
    evalText.value = firstResult?.optimized_text || store.cleanedText || ''
  }
}
function onTextSourceChange(val) {
  if (val === 'rewrite') {
    const firstResult = store.rewriteResults[0]
    evalText.value = firstResult?.optimized_text || store.cleanedText || ''
  } else {
    evalText.value = ''
  }
}

// ── 维度配置变化 ──
function onDimensionChange() {
  normalizeWeights()
}
function onWeightChange() {
  normalizeWeights()
}
function normalizeWeights() {
  const enabled = dimensionConfigs.value.filter(d => d.enabled)
  if (enabled.length === 0) return
  const each = Math.floor(100 / enabled.length)
  const remainder = 100 - each * enabled.length
  enabled.forEach((d, i) => {
    d.weight = each + (i === enabled.length - 1 ? remainder : 0)
  })
}

// ── 开始评测 ──
async function startEval() {
  if (!evalText.value) {
    ElMessage.warning('请先输入评测文本')
    return
  }

  isRunning.value = true
  evalStatus.value = 'running'
  evalOverallProgress.value = 0
  evalOverallScore.value = null
  phaseStates.value = {}

  const customQs = customQuestions.value
    .split('\n')
    .map(q => q.trim())
    .filter(q => q)

  sseConnection.value = startEvalSSE(
    {
      optimized_text: evalText.value,
      original_text: originalText.value || null,
      sandtable_type: sandtableType.value,
      platforms: targetPlatforms.value,
      user_roles: userRoles.value,
      custom_questions: customQs,
      dimensions: dimensionConfigs.value
        .filter(d => d.enabled)
        .map(d => ({ key: d.key, label: d.label, requires_llm: d.requires_llm, weight: d.weight, enabled: d.enabled })),
      mode: evalMode.value,
    },
    // onEvent
    (eventType, payload) => {
      const phase = payload.phase
      evalSessionId.value = payload.session_id
      evalOverallProgress.value = payload.progress || 0

      if (eventType === 'phase_complete' || eventType === 'phase_skipped') {
        const data = payload.data || {}
        const score = data.average ?? data.overall_score ?? null
        phaseStates.value = {
          ...phaseStates.value,
          [phase]: {
            status: eventType === 'phase_skipped' ? 'skipped' : 'completed',
            score,
            result: data,
          },
        }
      } else if (eventType === 'phase_failed') {
        phaseStates.value = {
          ...phaseStates.value,
          [phase]: { status: 'failed', score: null, result: null },
        }
      }

      if (eventType === 'eval_complete') {
        evalStatus.value = 'completed'
        evalOverallScore.value = payload.data?.overall_score ?? null
        isRunning.value = false
        store.setEvaluationResult(payload.data)
        store.addToHistory({
          name: 'AI评测',
          sandtableType: sandtableType.value,
          status: `评分: ${evalOverallScore.value}分`,
        })
        ElMessage.success(`评测完成！综合评分: ${evalOverallScore.value}分`)
      }

      if (eventType === 'eval_error') {
        evalStatus.value = 'failed'
        isRunning.value = false
        ElMessage.error('评测过程出错: ' + (payload.data?.error || '未知错误'))
      }
    },
    // onError
    (err) => {
      if (err.name === 'AbortError') return
      evalStatus.value = 'failed'
      isRunning.value = false
      ElMessage.error('评测连接中断: ' + (err.message || '网络错误'))
    }
  )
}

// ── 取消评测 ──
async function cancelEval() {
  if (evalSessionId.value) {
    try {
      await apiCancelEval(evalSessionId.value)
    } catch { /* ignore */ }
  }
  sseConnection.value?.close()
  evalStatus.value = 'cancelled'
  isRunning.value = false
  ElMessage.info('评测已取消，已完成阶段的结果保留')
}

// ── 工具函数 ──
function scoreColor(score) {
  if (score >= 80) return '#67C23A'
  if (score >= 60) return '#E6A23C'
  return '#F56C6C'
}
function resetEval() {
  evalStatus.value = 'idle'
  evalOverallProgress.value = 0
  evalOverallScore.value = null
  evalSessionId.value = null
  phaseStates.value = {}
}
function goToExport() {
  router.push('/export')
}
</script>

<style scoped>
.eval-view { max-width: 1300px; }
.page-title { font-size: 20px; margin-bottom: 20px; color: #303133; }

.config-card { position: sticky; top: 24px; }
.text-preview { background: #fafafa; padding: 10px; border-radius: 6px; font-size: 13px; color: #606266; max-height: 80px; overflow: hidden; }

.dim-row { display: flex; align-items: center; margin-bottom: 8px; }
.dim-weight { font-size: 13px; color: #909399; width: 40px; text-align: right; }

.action-buttons { margin-top: 12px; }

.empty-card { min-height: 400px; display: flex; align-items: center; justify-content: center; }
.empty-state { text-align: center; color: #909399; padding: 60px 0; }
.empty-state h3 { margin: 16px 0 8px; color: #606266; }

.progress-card { min-height: 300px; }
.progress-header { display: flex; justify-content: space-between; align-items: center; }

.phase-list { margin-top: 20px; }
.phase-row { display: flex; align-items: center; padding: 10px 12px; border-radius: 8px; margin-bottom: 4px; transition: background 0.2s; }
.phase-row.is-active { background: #ecf5ff; }
.phase-icon { width: 28px; font-size: 18px; }
.phase-info { flex: 1; display: flex; align-items: center; gap: 8px; }
.phase-label { font-size: 14px; color: #303133; }
.phase-score { font-size: 18px; font-weight: bold; }
.phase-running { font-size: 12px; color: #409EFF; }

.overall-score { text-align: center; padding: 20px 0; }
.score-number { font-size: 72px; font-weight: bold; line-height: 1; }
.score-label { font-size: 16px; color: #909399; margin-top: 8px; }

.dim-score-row { display: flex; align-items: center; margin-bottom: 12px; }
.dim-name { width: 90px; font-size: 13px; color: #606266; }
.dim-value { width: 48px; text-align: right; font-size: 14px; font-weight: bold; color: #303133; }

.comparison { display: flex; align-items: center; gap: 20px; padding: 12px 0; }
.comp-item { text-align: center; }
.comp-label { font-size: 13px; color: #909399; display: block; }
.comp-value { font-size: 24px; font-weight: bold; color: #303133; }
</style>