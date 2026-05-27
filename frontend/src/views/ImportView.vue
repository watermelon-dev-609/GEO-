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
                accept=".txt,.md,.docx,.xlsx"
                :limit="5"
              >
                <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
                <div>将文件拖到此处，或点击上传</div>
                <template #tip>
                  <div class="el-upload__tip">支持 .txt .md .docx .xlsx 格式</div>
                </template>
              </el-upload>
              <div v-if="fileContent" class="file-preview">
                <el-alert title="文件内容已读取" type="success" :closable="false" />
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
                <span style="margin-left: 8px; font-size: 12px; color: #909399;">
                  字数: {{ rawText.length }} → {{ cleanedText.length }}
                </span>
              </div>
            </div>
          </template>

          <div v-if="!cleanedText" class="empty-state">
            <el-icon :size="48" color="#c0c4cc"><Document /></el-icon>
            <p>导入文案并点击清洗后，结果将显示在这里</p>
          </div>

          <div v-else>
            <div class="cleaned-text">{{ cleanedText }}</div>
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
              <span v-if="!dimensions[dim.key]?.length" style="color: #909399;">暂无数据</span>
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
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useGeoStore } from '../stores/geo'
import { cleanText, extractInfo } from '../api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const store = useGeoStore()

const importMode = ref('paste')
const rawText = ref('')
const fileContent = ref('')
const sandtableType = ref('')
const isCleaning = ref(false)
const cleanedText = ref('')
const dimensions = ref(null)
const detectedType = ref('')

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

const dimList = [
  { key: 'core_advantages', label: '核心优势' },
  { key: 'applicable_scenarios', label: '适用场景' },
  { key: 'technical_features', label: '技术特点' },
  { key: 'service_capabilities', label: '服务能力' },
  { key: 'implementation_value', label: '落地价值' },
]

function handleFileChange(file) {
  const reader = new FileReader()
  reader.onload = (e) => {
    fileContent.value = e.target.result
    rawText.value = e.target.result
  }
  reader.readAsText(file.raw)
}

async function startCleaning() {
  const content = rawText.value || fileContent.value
  if (!content.trim()) {
    ElMessage.warning('请先导入文案内容')
    return
  }

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
</script>

<style scoped>
.import-view { max-width: 1200px; }
.page-title { font-size: 20px; margin-bottom: 20px; color: #303133; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.empty-state { text-align: center; padding: 48px 0; color: #909399; }
.empty-state p { margin-top: 12px; }
.cleaned-text { max-height: 400px; overflow-y: auto; white-space: pre-wrap; line-height: 1.8; font-size: 14px; background: #fafafa; padding: 16px; border-radius: 8px; }
.file-preview { margin-top: 12px; }
</style>
