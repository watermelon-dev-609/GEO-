<template>
  <div class="export-view">
    <h2 class="page-title">成果导出</h2>

    <el-row :gutter="20">
      <el-col :span="8">
        <el-card shadow="never">
          <template #header><span>导出选项</span></template>

          <el-form label-position="top">
            <el-form-item label="导出内容">
              <el-checkbox-group v-model="exportItems">
                <el-checkbox label="copy" :disabled="!hasCopy">优化文案 (.md)</el-checkbox>
                <el-checkbox label="docx" :disabled="!hasCopy">优化文案 (.docx)</el-checkbox>
                <el-checkbox label="jsonld">JSON-LD结构化代码</el-checkbox>
                <el-checkbox label="report">评测报告 (.html)</el-checkbox>
                <el-checkbox label="report_pdf">评测报告 (.pdf)</el-checkbox>
              </el-checkbox-group>
            </el-form-item>

            <el-form-item label="沙盘类型（用于JSON-LD生成）">
              <el-select v-model="sandtableType" style="width: 100%">
                <el-option v-for="t in sandtableTypes" :key="t.value" :label="t.label" :value="t.value" />
              </el-select>
            </el-form-item>

            <el-form-item label="企业名称">
              <el-input v-model="enterpriseName" />
            </el-form-item>

            <el-form-item label="企业官网URL（可选）">
              <el-input v-model="enterpriseUrl" placeholder="https://www.example.com" />
            </el-form-item>
          </el-form>

          <el-button
            type="primary"
            size="large"
            :icon="Download"
            :loading="isExporting"
            @click="startExport"
            style="width: 100%"
            :disabled="exportItems.length === 0"
          >
            {{ isExporting ? '导出中...' : '一键导出' }}
          </el-button>

          <el-divider />

          <el-button size="small" @click="exportAllZip" style="width: 100%">
            <el-icon><FolderOpened /></el-icon> 打包全部下载 (ZIP)
          </el-button>
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card shadow="never" v-if="exportedFiles.length === 0 && !isExporting" class="empty-card">
          <div class="empty-state">
            <el-icon :size="64" color="#c0c4cc"><Download /></el-icon>
            <h3>选择导出内容，一键生成可落地成果</h3>
            <p>优化文案、JSON-LD代码、评测报告全部就绪</p>
          </div>
        </el-card>

        <div v-if="exportedFiles.length > 0">
          <el-card shadow="never" v-for="file in exportedFiles" :key="file.name" class="exported-file">
            <div class="file-info">
              <el-tag :type="file.type === 'jsonld' ? 'primary' : file.type === 'report' ? 'warning' : 'success'" size="large">
                {{ file.label }}
              </el-tag>
              <span class="file-name">{{ file.name }}</span>
              <span class="file-size" v-if="file.size">{{ file.size }}</span>
            </div>
            <div class="file-actions">
              <el-button size="small" type="primary" @click="previewFile(file)" v-if="file.preview">
                <el-icon><View /></el-icon> 预览
              </el-button>
              <el-button size="small" @click="downloadFile(file)">
                <el-icon><Download /></el-icon> 下载
              </el-button>
            </div>
          </el-card>
        </div>

        <!-- JSON-LD 预览 -->
        <el-card shadow="never" style="margin-top: 16px;" v-if="showJSONLDPreview">
          <template #header>
            <div class="card-header">
              <span>JSON-LD 结构化代码预览</span>
              <el-button size="small" @click="copyText(jsonldCode)">复制代码</el-button>
            </div>
          </template>
          <pre class="jsonld-preview">{{ jsonldCode }}</pre>
        </el-card>

        <!-- 报告预览 -->
        <el-card shadow="never" style="margin-top: 16px;" v-if="showReportPreview">
          <template #header><span>评测报告预览</span></template>
          <div v-if="evalResult" class="report-mini">
            <div class="mini-score">
              综合评分: <strong :style="{ color: scoreColor(evalResult.overall_score) }">{{ evalResult.overall_score }}分</strong>
            </div>
            <div v-if="evalResult.before_after_comparison">
              优化提升: <strong>{{ evalResult.before_after_comparison.improvement_percent }}%</strong>
            </div>
            <div v-if="evalResult.weak_points?.length">
              诊断问题: {{ evalResult.weak_points.length }}条
            </div>
          </div>
          <div v-else class="empty-state" style="padding: 24px;">暂无评测数据，请先在AI评测中心完成评测</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useGeoStore } from '../stores/geo'
import { generateJSONLD, generateReport } from '../api'
import { ElMessage } from 'element-plus'

const store = useGeoStore()

const exportItems = ref(['copy', 'jsonld', 'report'])
const sandtableType = ref(store.currentSandtableType || 'smart_traffic')
const enterpriseName = ref('武汉微艺达智能科技有限公司')
const enterpriseUrl = ref('')
const isExporting = ref(false)
const exportedFiles = ref([])
const showJSONLDPreview = ref(false)
const showReportPreview = ref(false)
const jsonldCode = ref('')
const evalResult = computed(() => store.evaluationResult)

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

const hasCopy = computed(() => store.rewriteResults.length > 0)

async function startExport() {
  isExporting.value = true
  exportedFiles.value = []

  try {
    // 1. 导出文案
    if ((exportItems.value.includes('copy') || exportItems.value.includes('docx')) && store.rewriteResults.length > 0) {
      for (const r of store.rewriteResults) {
        if (r.optimized_text) {
          const ext = exportItems.value.includes('docx') ? 'docx' : 'md'
          const blob = new Blob([r.optimized_text], { type: 'text/markdown;charset=utf-8' })
          const filename = `GEO优化文案_${sandtableType.value}_${r.platform}.${ext}`
          saveBlob(blob, filename)
          exportedFiles.value.push({ name: filename, label: `${r.platform}文案`, type: 'copy', size: `${(blob.size / 1024).toFixed(1)} KB` })
        }
      }
    }

    // 2. JSON-LD
    if (exportItems.value.includes('jsonld')) {
      try {
        const res = await generateJSONLD({
          sandtable_type: sandtableType.value,
          enterprise_info: {
            name: enterpriseName.value,
            url: enterpriseUrl.value,
            location: '武汉',
          },
          product_info: {
            name: sandtableTypes.find(t => t.value === sandtableType.value)?.label || '',
            description: '',
          },
        })
        jsonldCode.value = res.data.json_ld_code
        const blob = new Blob([jsonldCode.value], { type: 'application/json;charset=utf-8' })
        const filename = `JSON-LD结构化代码_${sandtableType.value}.json`
        saveBlob(blob, filename)
        exportedFiles.value.push({ name: filename, label: 'JSON-LD代码', type: 'jsonld', size: `${(blob.size / 1024).toFixed(1)} KB`, preview: true })
      } catch (e) {
        ElMessage.warning('JSON-LD生成失败: ' + (e.response?.data?.detail || e.message))
      }
    }

    // 3. 评测报告
    if ((exportItems.value.includes('report') || exportItems.value.includes('report_pdf')) && store.evaluationResult) {
      try {
        const format = exportItems.value.includes('report_pdf') ? 'pdf' : 'html'
        const reportData = {
          ...store.evaluationResult,
          format,
          include_charts: true,
        }
        const res = await generateReport(reportData)
        const ext = format === 'pdf' ? 'pdf' : 'html'
        const filename = `GEO评测报告_${res.data.report_id}.${ext}`
        exportedFiles.value.push({
          name: filename,
          label: `评测报告 (${format.toUpperCase()})`,
          type: 'report',
          reportId: res.data.report_id,
          format,
          preview: format === 'html',
        })
        ElMessage.success('报表已生成，可在后端 data/reports/ 目录查看')
      } catch (e) {
        ElMessage.warning('报告生成失败: ' + (e.response?.data?.detail || e.message))
      }
    }

    ElMessage.success(`导出完成！共 ${exportedFiles.value.length} 个文件`)
  } catch (e) {
    ElMessage.error('导出失败')
  } finally {
    isExporting.value = false
  }
}

async function exportAllZip() {
  ElMessage.info('打包功能：请将导出的文件手动打包为ZIP，或使用后端批量导出接口')
}

function previewFile(file) {
  if (file.type === 'jsonld') {
    showJSONLDPreview.value = true
    showReportPreview.value = false
  } else if (file.type === 'report' && file.reportId) {
    showReportPreview.value = true
    showJSONLDPreview.value = false
  }
}

function downloadFile(file) {
  if (file.type === 'report' && file.reportId) {
    window.open(`/api/reports/export/${file.reportId}?format=${file.format || 'html'}`, '_blank')
  }
  ElMessage.success(`正在下载: ${file.name}`)
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => ElMessage.success('已复制'))
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function scoreColor(score) {
  if (score >= 80) return '#67C23A'
  if (score >= 60) return '#E6A23C'
  return '#F56C6C'
}
</script>

<style scoped>
.export-view { max-width: 1200px; }
.page-title { font-size: 20px; margin-bottom: 20px; color: #303133; }
.empty-card { min-height: 400px; display: flex; align-items: center; justify-content: center; }
.empty-state { text-align: center; color: #909399; padding: 60px 0; }
.empty-state h3 { margin: 16px 0 8px; color: #606266; }
.exported-file { margin-bottom: 12px; }
.exported-file .el-card__body { display: flex; justify-content: space-between; align-items: center; }
.file-info { display: flex; align-items: center; gap: 12px; }
.file-name { font-size: 14px; color: #303133; }
.file-size { font-size: 12px; color: #909399; }
.file-actions { display: flex; gap: 8px; }
.jsonld-preview { background: #1d1e2c; color: #e5e5e5; padding: 16px; border-radius: 8px; overflow-x: auto; font-size: 12px; line-height: 1.6; max-height: 400px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.mini-score { font-size: 18px; margin-bottom: 8px; }
</style>
