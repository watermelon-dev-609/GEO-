<template>
  <div class="eval-view">
    <h2 class="page-title">AI评测中心</h2>

    <el-row :gutter="20">
      <el-col :span="8">
        <el-card shadow="never">
          <template #header><span>评测配置</span></template>
          <el-form label-position="top">
            <el-form-item label="待评测文案">
              <el-select v-model="selectedTextSource" style="width: 100%" @change="onSourceChange">
                <el-option label="使用优化结果（第一条）" value="rewrite" />
                <el-option label="手动输入" value="manual" />
              </el-select>
              <el-input
                v-if="selectedTextSource === 'manual'"
                v-model="evalText"
                type="textarea"
                :rows="6"
                placeholder="粘贴需要评测的文案"
                style="margin-top: 8px;"
              />
              <div v-else class="selected-text-preview">{{ evalText.substring(0, 200) }}...</div>
            </el-form-item>

            <el-form-item label="沙盘类型">
              <el-select v-model="sandtableType" style="width: 100%">
                <el-option v-for="t in sandtableTypes" :key="t.value" :label="t.label" :value="t.value" />
              </el-select>
            </el-form-item>

            <el-form-item label="模拟用户角色">
              <el-checkbox-group v-model="userRoles">
                <el-checkbox v-for="r in roleOptions" :key="r.value" :value="r.value" :label="r.label" />
              </el-checkbox-group>
            </el-form-item>

            <el-form-item label="自定义问题（可选，一行一个）">
              <el-input v-model="customQuestions" type="textarea" :rows="4" placeholder="自定义评测问题..." />
            </el-form-item>
          </el-form>

          <el-button
            type="primary"
            size="large"
            :icon="DataAnalysis"
            :loading="isEvaluating"
            @click="startEvaluate"
            style="width: 100%"
            :disabled="!evalText"
          >
            {{ isEvaluating ? '评测中...' : '开始评测' }}
          </el-button>

          <el-divider />

          <el-button size="small" :icon="MagicStick" @click="quickBrandCheck" style="width: 100%">
            快速品牌曝光检测
          </el-button>
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card shadow="never" v-if="!evalResult" class="empty-card">
          <div class="empty-state">
            <el-icon :size="64" color="#c0c4cc"><DataAnalysis /></el-icon>
            <h3>配置评测参数并开始评测</h3>
            <p>系统将模拟真实用户提问，检测品牌曝光与内容采信效果</p>
          </div>
        </el-card>

        <div v-if="evalResult">
          <el-card shadow="never" class="score-overview">
            <div class="overall">
              <div class="overall-number" :style="{ color: scoreColor(evalResult.overall_score) }">
                {{ evalResult.overall_score }}
              </div>
              <div class="overall-label">综合评分 / 100</div>
            </div>
          </el-card>

          <el-card shadow="never" style="margin-top: 16px;" v-if="evalResult.before_after_comparison">
            <template #header><span>优化前后对比</span></template>
            <div class="comparison">
              <div class="comp-item">
                <span class="comp-label">优化前</span>
                <span class="comp-value">{{ evalResult.before_after_comparison.before_score }}分</span>
              </div>
              <el-icon :size="24"><ArrowRight /></el-icon>
              <div class="comp-item">
                <span class="comp-label">优化后</span>
                <span class="comp-value">{{ evalResult.before_after_comparison.after_score }}分</span>
              </div>
              <el-tag :type="evalResult.before_after_comparison.improvement_percent > 0 ? 'success' : 'danger'" size="large">
                {{ evalResult.before_after_comparison.improvement_percent > 0 ? '+' : '' }}{{ evalResult.before_after_comparison.improvement_percent }}%
              </el-tag>
            </div>
          </el-card>

          <el-card shadow="never" style="margin-top: 16px;" v-if="evalResult.platform_results?.length">
            <template #header><span>各平台评分详情</span></template>
            <el-table :data="evalResult.platform_results" size="small">
              <el-table-column prop="platform" label="平台" width="120" />
              <el-table-column label="综合评分" width="100">
                <template #default="scope">
                  <span :style="{ color: scoreColor(scope.row.overall_score), fontWeight: 'bold', fontSize: '18px' }">
                    {{ scope.row.overall_score }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="详细维度">
                <template #default="scope">
                  <div v-for="s in scope.row.scores" :key="s.dimension" style="margin: 2px 0; font-size: 12px;">
                    {{ s.dimension }}: {{ s.score }}分
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <el-card shadow="never" style="margin-top: 16px;" v-if="evalResult.weak_points?.length">
            <template #header><span>短板诊断</span></template>
            <el-alert
              v-for="(wp, i) in evalResult.weak_points"
              :key="i"
              :title="wp"
              type="warning"
              :closable="false"
              style="margin-bottom: 8px;"
            />
          </el-card>

          <el-card shadow="never" style="margin-top: 16px;" v-if="evalResult.suggestions?.length">
            <template #header><span>迭代优化建议</span></template>
            <el-alert
              v-for="(sg, i) in evalResult.suggestions"
              :key="i"
              :title="sg"
              type="success"
              :closable="false"
              style="margin-bottom: 8px;"
            />
          </el-card>
        </div>
      </el-col>
    </el-row>

    <div style="text-align: right; margin-top: 20px;" v-if="evalResult">
      <el-button type="success" size="large" @click="goToExport">
        生成报表并导出 <el-icon><ArrowRight /></el-icon>
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useGeoStore } from '../stores/geo'
import { evaluateSemantic, quickBrandCheck as apiQuickBrandCheck } from '../api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const store = useGeoStore()

const selectedTextSource = ref('rewrite')
const evalText = ref('')
const sandtableType = ref(store.currentSandtableType || 'smart_traffic')
const userRoles = ref(['b_end_procurement', 'general_consultant'])
const customQuestions = ref('')
const isEvaluating = ref(false)
const evalResult = ref(null)

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

const roleOptions = [
  { value: 'b_end_procurement', label: 'B端政企采购' },
  { value: 'technical_selection', label: '技术人员选型' },
  { value: 'project_manager', label: '项目经办人' },
  { value: 'general_consultant', label: '普通咨询用户' },
]

// 初始化评测文本
const firstResult = store.rewriteResults[0]
evalText.value = firstResult?.optimized_text || store.cleanedText || ''

function onSourceChange(val) {
  if (val === 'rewrite') {
    const r = store.rewriteResults[0]
    evalText.value = r?.optimized_text || store.cleanedText || ''
  } else {
    evalText.value = ''
  }
}

async function startEvaluate() {
  if (!evalText.value) {
    ElMessage.warning('请先输入或选择评测文案')
    return
  }

  isEvaluating.value = true
  try {
    const customQs = customQuestions.value
      .split('\n')
      .map(q => q.trim())
      .filter(q => q)

    const res = await evaluateSemantic({
      optimized_text: evalText.value,
      original_text: store.originalText || undefined,
      sandtable_type: sandtableType.value,
      platforms: store.selectedPlatforms.length > 0 ? store.selectedPlatforms : ['deepseek'],
      user_roles: userRoles.value,
      custom_questions: customQs,
    })

    evalResult.value = res.data
    store.setEvaluationResult(res.data)

    ElMessage.success(`评测完成！综合评分: ${res.data.overall_score}分`)
    store.addToHistory({
      name: 'AI评测',
      sandtableType: sandtableType.value,
      status: `评分: ${res.data.overall_score}分`,
    })
  } catch (e) {
    // axios 拦截器已显示 e.response.data.detail，仅在无服务端响应时补充提示
    if (!e.response?.data?.detail) {
      ElMessage.error('评测请求失败: ' + (e.message || '网络错误，请检查连接'))
    }
  } finally {
    isEvaluating.value = false
  }
}

async function quickBrandCheck() {
  if (!evalText.value) {
    ElMessage.warning('请先输入评测文案')
    return
  }
  try {
    const res = await apiQuickBrandCheck({ text: evalText.value })
    ElMessage.success(`品牌曝光均分: ${res.data.average_score}分`)
  } catch (e) {
    ElMessage.error('检测失败')
  }
}

function scoreColor(score) {
  if (score >= 80) return '#67C23A'
  if (score >= 60) return '#E6A23C'
  return '#F56C6C'
}

function goToExport() {
  router.push('/export')
}
</script>

<style scoped>
.eval-view { max-width: 1200px; }
.page-title { font-size: 20px; margin-bottom: 20px; color: #303133; }
.empty-card { min-height: 400px; display: flex; align-items: center; justify-content: center; }
.empty-state { text-align: center; color: #909399; padding: 60px 0; }
.empty-state h3 { margin: 16px 0 8px; color: #606266; }
.score-overview { text-align: center; padding: 24px 0; }
.overall-number { font-size: 72px; font-weight: bold; }
.overall-label { font-size: 16px; color: #909399; margin-top: 4px; }
.comparison { display: flex; align-items: center; gap: 20px; padding: 12px 0; }
.comp-item { text-align: center; }
.comp-label { font-size: 13px; color: #909399; display: block; }
.comp-value { font-size: 24px; font-weight: bold; color: #303133; }
.selected-text-preview { background: #fafafa; padding: 12px; border-radius: 6px; font-size: 13px; color: #606266; max-height: 100px; overflow: hidden; }
</style>
