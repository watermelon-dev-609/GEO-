<template>
  <div class="import-view">
    <h2 class="page-title">文案导入与智能清洗</h2>

    <el-row :gutter="20">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span>内容导入</span></template>
          <el-tabs v-model="importMode">
            <el-tab-pane label="文本粘贴" name="paste">
              <el-input
                v-model="rawText"
                type="textarea"
                :rows="14"
                placeholder="在此粘贴需要优化的企业文案、产品介绍、案例描述等..."
              />
            </el-tab-pane>
            <el-tab-pane label="文件上传" name="file">
              <el-upload
                drag
                :auto-upload="false"
                :on-change="handleFileChange"
                accept=".txt,.md,.docx"
                :limit="5"
              >
                <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
                <div>将文件拖到此处，或点击上传</div>
                <template #tip>
                  <div class="el-upload__tip">支持 .txt .md .docx 格式</div>
                </template>
              </el-upload>
              <div v-if="fileContent" class="file-preview">
                <el-alert title="文件内容已读取" type="success" :closable="false" />
              </div>
            </el-tab-pane>
            <el-tab-pane label="快速诊断" name="diagnosis">
              <el-input
                v-model="diagText"
                type="textarea"
                :rows="10"
                placeholder="粘贴需要诊断的官网文案、产品介绍、宣传内容等..."
              />
              <el-select v-model="diagSandtable" placeholder="沙盘类型（可选）" clearable size="small" style="width:100%;margin-top:12px;">
                <el-option v-for="t in sandtableTypes" :key="t.value" :label="t.label" :value="t.value" />
              </el-select>
              <el-button type="warning" size="small" :loading="diagLoading" @click="startDiagnosis" style="width:100%;margin-top:12px;">
                {{ diagLoading ? '正在诊断...' : 'GEO健康体检' }}
              </el-button>
              <div v-if="diagResult" class="diag-result" style="margin-top:16px;">
                <div class="diag-score-row">
                  <span class="diag-overall">{{ diagResult.overall_score }}<small>/100</small></span>
                  <el-tag :type="diagResult.overall_score >= 70 ? 'success' : diagResult.overall_score >= 40 ? 'warning' : 'danger'" size="large">GEO健康度</el-tag>
                </div>
                <div v-for="(dim, key) in diagResult.dimensions" :key="key" class="diag-dim">
                  <div class="diag-dim-header">
                    <span>{{ dimLabels[key] || key }}</span>
                    <span :style="{ color: dim.score >= 70 ? '#5B8C5A' : dim.score >= 40 ? '#D4956A' : '#C5554A', fontWeight:'bold' }">{{ dim.score }}分</span>
                  </div>
                  <el-progress :percentage="dim.score" :color="dim.score >= 70 ? '#5B8C5A' : dim.score >= 40 ? '#D4956A' : '#C5554A'" :stroke-width="6" />
                  <div class="diag-dim-note" v-if="dim.note">{{ dim.note }}</div>
                </div>
                <div v-if="diagResult.top_issues?.length" style="margin-top:12px;">
                  <el-alert v-for="(issue, i) in diagResult.top_issues" :key="i" :title="issue" type="warning" show-icon :closable="false" style="margin-bottom:6px;" />
                </div>
                <el-button type="primary" size="small" style="margin-top:12px;" @click="goDiagnosisToWorkshop" :disabled="!cleanedText && !rawText">
                  一键优化 → GEO工坊
                </el-button>
              </div>
            </el-tab-pane>
          </el-tabs>

          <div style="margin-top: 16px;">
            <el-form label-position="top">
              <el-form-item label="沙盘业务类型（可选，不选自动识别）">
                <el-select v-model="sandtableType" placeholder="自动识别" clearable style="width: 100%;">
                  <el-option
                    v-for="t in sandtableTypes"
                    :key="t.value"
                    :label="t.label"
                    :value="t.value"
                  />
                </el-select>
              </el-form-item>
            </el-form>
          </div>

          <el-button
            type="primary"
            size="large"
            :icon="MagicStick"
            :loading="isCleaning"
            @click="startCleaning"
            style="width: 100%; margin-top: 8px;"
            :disabled="!rawText && !fileContent"
          >
            {{ isCleaning ? '正在智能清洗...' : '开始智能清洗' }}
          </el-button>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>清洗结果</span>
              <div v-if="cleanedText">
                <el-tag type="success" size="small">清洗完成</el-tag>
                <span style="margin-left: 8px; font-size: 12px; color: #9B9EAA;">
                  字数: {{ rawText.length }} → {{ cleanedText.length }}
                </span>
              </div>
            </div>
          </template>

          <div v-if="!cleanedText" class="empty-state">
            <el-empty description="导入文案并点击清洗后，结果将显示在这里" :image-size="80" />
          </div>

          <div v-else>
            <!-- 清洗摘要 -->
            <div class="clean-summary">
              <span class="clean-stat">
                清洗前 <strong>{{ beforeText.length }}</strong> 字符 →
                清洗后 <strong>{{ cleanedText.length }}</strong> 字符
              </span>
              <el-tag :type="changePercent > 30 ? 'warning' : 'success'" size="small">
                {{ changePercent > 0 ? `精简 ${changePercent}%` : '无变化' }}
              </el-tag>
            </div>

            <!-- 清洗前后对比 -->
            <el-tabs v-model="viewMode" type="card" size="small">
              <el-tab-pane label="清洗后结果" name="cleaned">
                <div class="cleaned-text">{{ cleanedText }}</div>
              </el-tab-pane>
              <el-tab-pane label="清洗前原文" name="original">
                <div class="original-text">{{ beforeText }}</div>
              </el-tab-pane>
              <el-tab-pane label="并排对比" name="diff">
                <el-row :gutter="12" class="diff-row">
                  <el-col :span="12">
                    <div class="diff-label">清洗前</div>
                    <div class="diff-text original">{{ beforeText }}</div>
                  </el-col>
                  <el-col :span="12">
                    <div class="diff-label">清洗后</div>
                    <div class="diff-text cleaned">{{ cleanedText }}</div>
                  </el-col>
                </el-row>
              </el-tab-pane>
            </el-tabs>
          </div>
        </el-card>

        <el-card shadow="never" style="margin-top: 16px;" v-if="dimensions">
          <template #header>
            <div class="card-header">
              <span>五维信息提取</span>
              <el-tag v-if="detectedType" size="small">{{ detectedType }}</el-tag>
            </div>
          </template>
          <el-collapse>
            <el-collapse-item v-for="dim in dimList" :key="dim.key" :title="`${dim.label} (${(dimensions[dim.key] || []).length}条)`">
              <el-tag v-for="(item, i) in (dimensions[dim.key] || [])" :key="i" style="margin: 2px 4px;">{{ item }}</el-tag>
              <span v-if="!dimensions[dim.key]?.length" style="color: #9B9EAA;">暂无数据</span>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </el-col>
    </el-row>

    <div style="text-align: right; margin-top: 20px;" v-if="cleanedText">
      <el-button type="success" size="large" @click="goToWorkshop">
        进入GEO优化工坊 <el-icon><ArrowRight /></el-icon>
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useGeoStore } from '../stores/geo'
import { cleanText, extractInfo, quickDiagnosis } from '../api'
import { ElMessage } from 'element-plus'
import { SANDTABLE_TYPES, DIAGNOSIS_LABELS } from '../constants'

const router = useRouter()
const store = useGeoStore()

const importMode = ref('paste')
const rawText = ref('')
const fileContent = ref('')
const sandtableType = ref('')
const isCleaning = ref(false)
const cleanedText = ref('')
const beforeText = ref('')
const viewMode = ref('cleaned')
const dimensions = ref(null)
const detectedType = ref('')
const changePercent = computed(() => {
  if (!beforeText.value.length) return 0
  return Math.round((1 - cleanedText.value.length / beforeText.value.length) * 100)
})

const sandtableTypes = SANDTABLE_TYPES

const dimList = [
  { key: 'core_advantages', label: '核心优势' },
  { key: 'applicable_scenarios', label: '适用场景' },
  { key: 'technical_features', label: '技术特点' },
  { key: 'service_capabilities', label: '服务能力' },
  { key: 'implementation_value', label: '落地价值' },
]

async function handleFileChange(file) {
  const raw = file.raw
  const ext = raw.name.split('.').pop()?.toLowerCase()

  if (ext === 'docx') {
    try {
      const mammoth = await import('mammoth')
      const arrayBuffer = await raw.arrayBuffer()
      const result = await mammoth.extractRawText({ arrayBuffer })
      fileContent.value = result.value
      rawText.value = result.value
      if (result.messages?.length) {
        ElMessage.info('Word文档已解析，部分格式可能已简化')
      }
    } catch (e) {
      ElMessage.error('Word文档解析失败: ' + (e.message || '未知错误'))
    }
    return
  }

  const reader = new FileReader()
  reader.onload = (e) => {
    fileContent.value = e.target.result
    rawText.value = e.target.result
  }
  reader.readAsText(raw)
}

async function startCleaning() {
  const content = rawText.value || fileContent.value
  if (!content.trim()) {
    ElMessage.warning('请先导入文案内容')
    return
  }

  beforeText.value = content
  isCleaning.value = true
  try {
    const res = await cleanText({
      content,
      sandtable_type: sandtableType.value || undefined,
      extract_dimensions: true,
    })

    cleanedText.value = res.data.cleaned_text
    dimensions.value = res.data.dimensions
    detectedType.value = res.data.detected_type

    store.setOriginalText(content)
    store.setCleanedText(res.data.cleaned_text)
    store.setSandtableType(res.data.detected_type || sandtableType.value)
    store.setDimensions(res.data.dimensions)

    ElMessage.success(`清洗完成！字数 ${res.data.word_count_before} → ${res.data.word_count_after}`)
    store.addToHistory({
      name: '文案清洗',
      sandtableType: res.data.detected_type || sandtableType.value || '未知',
      status: '已清洗',
    })
  } catch (e) {
    ElMessage.error('清洗失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    isCleaning.value = false
  }
}

function goToWorkshop() {
  router.push('/workshop')
}

// ── 快速诊断 ──
const diagText = ref('')
const diagSandtable = ref('')
const diagLoading = ref(false)
const diagResult = ref(null)
const dimLabels = DIAGNOSIS_LABELS

async function startDiagnosis() {
  if (!diagText.value.trim()) { ElMessage.warning('请粘贴需要诊断的文本'); return }
  diagLoading.value = true
  try {
    const res = await quickDiagnosis({ text: diagText.value, sandtable_type: diagSandtable.value })
    diagResult.value = res.data
    // 把诊断文本同步到 rawText，方便后续一键优化
    rawText.value = diagText.value
    ElMessage.success(`GEO健康度: ${res.data.overall_score}/100`)
  } catch (e) {
    ElMessage.error('诊断失败: ' + (e.response?.data?.detail || e.message))
  } finally { diagLoading.value = false }
}

async function goDiagnosisToWorkshop() {
  if (!cleanedText.value && rawText.value) {
    store.setOriginalText(rawText.value)
    store.setSandtableType(diagSandtable.value)
    try {
      const res = await cleanText({
        content: rawText.value,
        sandtable_type: diagSandtable.value || undefined,
        extract_dimensions: true,
      })
      cleanedText.value = res.data.cleaned_text
      dimensions.value = res.data.dimensions
      detectedType.value = res.data.detected_type
      store.setCleanedText(res.data.cleaned_text)
      store.setDimensions(res.data.dimensions)
      if (res.data.detected_type) store.setSandtableType(res.data.detected_type)
    } catch (e) {
      ElMessage.warning('诊断完成但清洗失败: ' + (e.response?.data?.detail || e.message))
    }
  }
  router.push('/workshop')
}
</script>

<style scoped>
.import-view { max-width: 1240px; }
.page-title { font-size: 20px; margin-bottom: 20px; color: #2D3142; font-weight: 700; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.empty-state { text-align: center; padding: 48px 0; color: #9B9EAA; }
.empty-state p { margin-top: 12px; }
.cleaned-text { max-height: 400px; overflow-y: auto; white-space: pre-wrap; line-height: 1.8; font-size: 14px; background: #FAF8F5; padding: 16px; border-radius: 10px; }
.original-text { max-height: 400px; overflow-y: auto; white-space: pre-wrap; line-height: 1.8; font-size: 14px; background: rgba(212,149,106,0.06); padding: 16px; border-radius: 10px; color: #9B9EAA; }
.clean-summary { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; padding: 10px 14px; background: rgba(91,140,90,0.06); border-radius: 10px; }
.clean-stat { font-size: 14px; color: #2D3142; }
.diff-row { margin-top: 8px; }
.diff-label { font-size: 13px; font-weight: bold; color: #6B6E7B; margin-bottom: 8px; }
.diff-text { white-space: pre-wrap; font-size: 13px; line-height: 1.7; padding: 12px; border-radius: 10px; max-height: 500px; overflow-y: auto; }
.diff-text.original { background: rgba(212,149,106,0.06); color: #9B9EAA; }
.diff-text.cleaned { background: rgba(91,140,90,0.06); color: #2D3142; }
.file-preview { margin-top: 12px; }
.diag-result { padding: 12px; background: #FAF8F5; border-radius: 10px; }
.diag-score-row { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.diag-overall { font-size: 42px; font-weight: bold; color: #C8963E; }
.diag-overall small { font-size: 16px; color: #9B9EAA; }
.diag-dim { margin-bottom: 10px; }
.diag-dim-header { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 2px; }
.diag-dim-note { font-size: 11px; color: #9B9EAA; margin-top: 2px; }
</style>
