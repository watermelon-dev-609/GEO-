<template>
  <div class="eval-view">
    <div class="page-header">
      <h2 class="page-title">AI评测中心</h2>
      <el-button size="small" @click="openHistory" :icon="Clock">评测历史</el-button>
    </div>

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
              <div v-if="dimensionConfigs.some(d => d.enabled)" class="weight-summary" :class="{ invalid: !weightValid }">
                权重合计: {{ weightSum }}%
                <span v-if="!weightValid" style="color: #F56C6C; margin-left: 4px;">（需为100%）</span>
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
            <el-button type="warning" @click="goToOptimize">返回GEO工坊优化</el-button>
            <el-button type="success" @click="goToExport">导出报告</el-button>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 评测历史抽屉 -->
    <el-drawer v-model="historyDrawerVisible" title="评测历史" size="480px" direction="rtl">
      <div v-if="historyItems.length === 0" class="history-empty">
        <el-icon :size="48" color="#c0c4cc"><Clock /></el-icon>
        <p style="margin-top: 12px; color: #909399;">暂无评测历史</p>
      </div>
      <div v-else>
        <div v-for="item in historyItems" :key="item.session_id" class="history-item">
          <div class="history-item-main" @click="toggleHistoryDetail(item)">
            <div class="history-item-left">
              <el-checkbox
                v-model="item._selected"
                @change="onCompareSelect(item)"
                @click.stop
              />
              <div class="history-item-info">
                <div class="history-item-date">{{ formatDate(item.created_at) }}</div>
                <div class="history-item-meta">
                  <el-tag size="small" type="info">{{ item.sandtable_type || '未知' }}</el-tag>
                  <el-tag size="small" :type="item.status === 'completed' ? 'success' : 'warning'">
                    {{ item.status === 'completed' ? '已完成' : item.status }}
                  </el-tag>
                </div>
              </div>
            </div>
            <div class="history-item-score" :style="{ color: scoreColor(item.overall_score) }">
              {{ item.overall_score ?? '-' }}分
            </div>
            <el-button
              size="small"
              type="danger"
              :icon="Delete"
              circle
              @click.stop="deleteHistoryItem(item)"
            />
          </div>
          <!-- 展开详情 -->
          <div v-if="item._expanded" class="history-item-detail">
            <div v-if="item._loading" v-loading="true" style="min-height: 80px;" />
            <div v-else-if="item._detail">
              <div v-for="dim in getDetailDimensions(item._detail)" :key="dim.key" class="history-dim-row">
                <span>{{ dim.label }}</span>
                <el-progress :percentage="dim.score" :color="scoreColor(dim.score)" :stroke-width="6" style="flex:1;margin:0 8px" />
                <span>{{ dim.score }}分</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 对比按钮 -->
        <div v-if="compareEnabled" style="text-align: center; margin-top: 16px;">
          <el-button type="primary" @click="doCompare">对比评测 ({{ selectedForCompare.length }}/2)</el-button>
        </div>
      </div>
    </el-drawer>

    <!-- 对比弹窗 -->
    <el-dialog v-model="compareDialogVisible" title="评测对比" width="700px" :destroy-on-close="true">
      <div v-if="compareLoading" v-loading="true" style="min-height: 200px;" />
      <div v-else-if="compareData">
        <el-row :gutter="20">
          <el-col :span="11">
            <el-card shadow="never" size="small">
              <template #header><span>评测 1</span></template>
              <div class="compare-score" :style="{ color: scoreColor(compareData.session_1.overall_score) }">
                {{ compareData.session_1.overall_score }}分
              </div>
              <div v-for="(score, key) in compareData.session_1.dimension_scores" :key="key" class="compare-dim">
                <span>{{ key }}</span><span>{{ score }}分</span>
              </div>
            </el-card>
          </el-col>
          <el-col :span="2" style="display:flex;align-items:center;justify-content:center;">
            <div>
              <div v-for="(delta, key) in compareData.deltas" :key="key" style="margin:2px 0;font-size:12px;text-align:center;">
                <span :style="{ color: delta > 0 ? '#67C23A' : delta < 0 ? '#F56C6C' : '#909399' }">
                  {{ delta > 0 ? '+' : '' }}{{ delta }}
                </span>
              </div>
              <div style="font-weight:bold;text-align:center;margin-top:4px;">
                <span :style="{ color: compareData.overall_delta > 0 ? '#67C23A' : compareData.overall_delta < 0 ? '#F56C6C' : '#909399' }">
                  {{ compareData.overall_delta > 0 ? '+' : '' }}{{ compareData.overall_delta }}
                </span>
              </div>
            </div>
          </el-col>
          <el-col :span="11">
            <el-card shadow="never" size="small">
              <template #header><span>评测 2</span></template>
              <div class="compare-score" :style="{ color: scoreColor(compareData.session_2.overall_score) }">
                {{ compareData.session_2.overall_score }}分
              </div>
              <div v-for="(score, key) in compareData.session_2.dimension_scores" :key="key" class="compare-dim">
                <span>{{ key }}</span><span>{{ score }}分</span>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useGeoStore } from '../stores/geo'
import { getEvalDimensions, startEvalSSE, cancelEval as apiCancelEval, getEvalHistory, getEvalHistoryDetail, deleteEvalHistory, compareEvalHistory } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Clock, Delete } from '@element-plus/icons-vue'

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

// ── 历史相关 ──
const historyDrawerVisible = ref(false)
const historyItems = ref([])
const selectedForCompare = ref([])
const compareDialogVisible = ref(false)
const compareLoading = ref(false)
const compareData = ref(null)

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
const compareEnabled = computed(() => selectedForCompare.value.length === 2)

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
  // 当用户勾选/取消勾选维度时，重新均分权重（这是一次性操作，之后用户可自由调整）
  const enabled = dimensionConfigs.value.filter(d => d.enabled)
  if (enabled.length === 0) return
  const each = Math.floor(100 / enabled.length)
  const remainder = 100 - each * enabled.length
  enabled.forEach((d, i) => {
    d.weight = each + (i === enabled.length - 1 ? remainder : 0)
  })
}
function onWeightChange() {
  // 用户自由调整权重，不做强制均分
  // 只做视觉反馈：总和不是100时高亮提示
}
const weightSum = computed(() => {
  const enabled = dimensionConfigs.value.filter(d => d.enabled)
  return enabled.reduce((s, d) => s + d.weight, 0)
})
const weightValid = computed(() => Math.abs(weightSum.value - 100) <= 1)

// ── 开始评测 ──
async function startEval() {
  if (!evalText.value) {
    ElMessage.warning('请先输入评测文本')
    return
  }
  if (!weightValid.value && dimensionConfigs.value.some(d => d.enabled)) {
    ElMessage.warning(`评测维度权重合计需为100%（当前${weightSum.value}%），请调整后再开始`)
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
        // 保存到历史
        store.pushToHistory({
          session_id: payload.session_id,
          status: 'completed',
          overall_score: payload.data?.overall_score ?? null,
          sandtable_type: sandtableType.value,
          mode: evalMode.value,
          created_at: new Date().toISOString(),
          phases: payload.data,
          evaluated_text: evalText.value,
        })
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
// ── 历史抽屉 ──
async function openHistory() {
  historyDrawerVisible.value = true
  await loadHistory()
}

async function loadHistory() {
  try {
    const res = await getEvalHistory()
    historyItems.value = (res.data.items || []).map(item => ({
      ...item,
      _selected: false,
      _expanded: false,
      _loading: false,
      _detail: null,
    }))
  } catch {
    // 静默失败
  }
}

function toggleHistoryDetail(item) {
  item._expanded = !item._expanded
  if (item._expanded && !item._detail && !item._loading) {
    loadHistoryDetail(item)
  }
}

async function loadHistoryDetail(item) {
  item._loading = true
  try {
    const res = await getEvalHistoryDetail(item.session_id)
    item._detail = res.data
    item._loading = false
  } catch {
    item._loading = false
  }
}

function getDetailDimensions(detail) {
  const comp = detail?.phases?.comprehensive?.result
  if (!comp?.dimension_scores) return []
  return Object.entries(comp.dimension_scores).map(([key, score]) => {
    const dim = dimensionConfigs.value.find(d => d.key === key)
    return { key, label: dim?.label || key, score }
  })
}

function onCompareSelect(item) {
  if (item._selected) {
    if (selectedForCompare.value.length >= 2) {
      // 取消最早选择的
      const first = selectedForCompare.value.shift()
      const found = historyItems.value.find(h => h.session_id === first.session_id)
      if (found) found._selected = false
    }
    selectedForCompare.value.push(item)
  } else {
    selectedForCompare.value = selectedForCompare.value.filter(h => h.session_id !== item.session_id)
  }
}

async function doCompare() {
  if (selectedForCompare.value.length !== 2) return
  compareDialogVisible.value = true
  compareLoading.value = true
  try {
    const res = await compareEvalHistory({
      session_ids: [selectedForCompare.value[0].session_id, selectedForCompare.value[1].session_id],
    })
    compareData.value = res.data
  } catch {
    // ignore
  } finally {
    compareLoading.value = false
  }
}

async function deleteHistoryItem(item) {
  try {
    await ElMessageBox.confirm(`确定要删除这条评测记录吗？`, '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await deleteEvalHistory(item.session_id)
    historyItems.value = historyItems.value.filter(h => h.session_id !== item.session_id)
    selectedForCompare.value = selectedForCompare.value.filter(h => h.session_id !== item.session_id)
    ElMessage.success('已删除')
  } catch {
    // 用户取消
  }
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// ── 重优化 ──
function goToOptimize() {
  store.setReoptimizeContext({
    weakPoints: weakPoints.value,
    suggestions: suggestions.value,
    sourceText: evalText.value,
    sandtableType: sandtableType.value,
  })
  router.push('/workshop')
}

function goToExport() {
  router.push('/export')
}
</script>

<style scoped>
.eval-view { max-width: 1300px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header .page-title { margin-bottom: 0; }
.page-title { font-size: 20px; margin-bottom: 20px; color: #303133; }

.config-card { position: sticky; top: 24px; }
.text-preview { background: #fafafa; padding: 10px; border-radius: 6px; font-size: 13px; color: #606266; max-height: 80px; overflow: hidden; }

.dim-row { display: flex; align-items: center; margin-bottom: 8px; }
.dim-weight { font-size: 13px; color: #909399; width: 40px; text-align: right; }
.weight-summary { font-size: 13px; color: #67C23A; margin-top: 8px; padding: 4px 8px; background: #f0f9eb; border-radius: 4px; display: inline-block; }
.weight-summary.invalid { color: #E6A23C; background: #fdf6ec; }

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

.history-empty { text-align: center; padding: 60px 0; }
.history-item { border-bottom: 1px solid #ebeef5; padding: 12px 0; }
.history-item-main { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.history-item-left { display: flex; align-items: center; flex: 1; gap: 8px; }
.history-item-info { flex: 1; }
.history-item-date { font-size: 13px; color: #303133; }
.history-item-meta { display: flex; gap: 4px; margin-top: 4px; }
.history-item-score { font-size: 20px; font-weight: bold; min-width: 60px; text-align: right; }
.history-item-detail { padding: 12px 0 4px 32px; }
.history-dim-row { display: flex; align-items: center; margin: 6px 0; font-size: 13px; }
.compare-score { font-size: 36px; font-weight: bold; text-align: center; padding: 8px 0; }
.compare-dim { display: flex; justify-content: space-between; font-size: 13px; margin: 4px 0; padding: 2px 8px; }
</style>