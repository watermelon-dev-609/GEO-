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
                <el-checkbox label="jsonld">JSON-LD结构化代码</el-checkbox>
                <el-checkbox label="report">评测报告 (.html)</el-checkbox>
                <el-checkbox label="report_pdf">评测报告 (.pdf)</el-checkbox>
                <el-divider style="margin:8px 0;" />
                <el-checkbox label="keywords">关键词清单 (.csv)</el-checkbox>
                <el-checkbox label="standards">内容规范文档 (.md)</el-checkbox>
                <el-checkbox label="competitors">竞品调研报告 (.md)</el-checkbox>
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

          <el-button
            type="warning"
            size="default"
            :icon="View"
            :disabled="!store.evaluationResult"
            @click="previewReportInline"
            style="width: 100%; margin-top: 8px"
          >
            预览评测报告
          </el-button>

          <el-divider />

          <div class="config-hint" style="margin-top: 8px;">
            <p>💡 提示：文件将自动下载到浏览器默认下载目录</p>
          </div>
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card shadow="never" v-if="exportedFiles.length === 0 && !isExporting" class="empty-card">
          <el-empty description="" :image-size="120">
            <template #default>
              <h3 style="color:#6B6E7B;margin:0 0 8px;">选择导出内容，一键生成可落地成果</h3>
              <p style="color:#9B9EAA;margin:0;">优化文案、JSON-LD代码、评测报告全部就绪</p>
            </template>
          </el-empty>
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

    <!-- 报告预览弹窗 -->
    <el-dialog
      v-model="previewDialogVisible"
      title="评测报告预览"
      fullscreen
      :destroy-on-close="true"
    >
      <div v-loading="previewLoading" style="height: 100%;">
        <iframe
          v-if="previewHtml && !previewLoading"
          :srcdoc="previewHtml"
          style="width: 100%; height: calc(100vh - 120px); border: none; border-radius: 8px;"
          sandbox="allow-same-origin"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useGeoStore } from '../stores/geo'
import { generateJSONLD, generateReport, previewReport, exportKeywordsCSV, generateCompetitorReport } from '../api'
import { ElMessage } from 'element-plus'
import { SANDTABLE_TYPES, scoreColor } from '../constants'

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

const previewDialogVisible = ref(false)
const previewHtml = ref('')
const previewLoading = ref(false)

const sandtableTypes = SANDTABLE_TYPES

const hasCopy = computed(() => store.rewriteResults.length > 0)

async function startExport() {
  isExporting.value = true
  exportedFiles.value = []

  try {
    // 1. 导出文案
    if (exportItems.value.includes('copy') && store.rewriteResults.length > 0) {
      for (const r of store.rewriteResults) {
        if (r.optimized_text) {
          const blob = new Blob([r.optimized_text], { type: 'text/markdown;charset=utf-8' })
          const filename = `GEO优化文案_${sandtableType.value}_${r.platform}.md`
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

    // 4. 关键词清单
    if (exportItems.value.includes('keywords')) {
      try {
        const st = sandtableType.value || 'smart_traffic'
        const res = await exportKeywordsCSV(st)
        const blob = new Blob(['﻿' + res.data.csv], { type: 'text/csv;charset=utf-8;' })
        const filename = `关键词清单_${st}.csv`
        saveBlob(blob, filename)
        exportedFiles.value.push({ name: filename, label: '关键词清单', type: 'copy', size: `${(blob.size / 1024).toFixed(1)} KB` })
      } catch (e) { ElMessage.warning('关键词导出失败: ' + (e.response?.data?.detail || e.message)) }
    }

    // 5. 内容规范文档
    if (exportItems.value.includes('standards')) {
      try {
        let content = '# GEO内容规范文档\n\n## 审核标准\n\n'
        content += '### AI采信六原则\n\n1. 实体锚定：企业名、地域、产品名完整清晰\n2. 定义优先：专业概念给出权威定义\n3. 量化事实：所有能力用数字支撑\n4. FAQ结构：嵌入自然问答对\n5. 层级结构化：H2/H3+列表\n6. 信息增量：本地化细节+行业独特信息\n\n'
        content += '### 写作规范\n\n- 每段200-300字，包含一个可独立提取的信息点\n- 标题使用H2/H3层级，列表使用•或-\n- 量化数据优先于形容词\n- 品牌名首次出现必须完整\n- 地域标识必须出现至少2次\n'
        const blob = new Blob([content], { type: 'text/markdown;charset=utf-8;' })
        const filename = 'GEO内容规范.md'
        saveBlob(blob, filename)
        exportedFiles.value.push({ name: filename, label: '内容规范', type: 'copy', size: `${(blob.size / 1024).toFixed(1)} KB` })
      } catch (e) { ElMessage.warning('规范导出失败') }
    }

    // 6. 竞品调研报告
    if (exportItems.value.includes('competitors')) {
      try {
        const res = await generateCompetitorReport({ competitor_ids: [] })
        const blob = new Blob([res.data.report], { type: 'text/markdown;charset=utf-8;' })
        const filename = '竞品调研报告.md'
        saveBlob(blob, filename)
        exportedFiles.value.push({ name: filename, label: '竞品报告', type: 'copy', size: `${(blob.size / 1024).toFixed(1)} KB` })
      } catch (e) { ElMessage.warning('竞品报告导出失败: ' + (e.response?.data?.detail || e.message)) }
    }

    ElMessage.success(`导出完成！共 ${exportedFiles.value.length} 个文件`)
  } catch (e) {
    ElMessage.error('导出失败')
  } finally {
    isExporting.value = false
  }
}

async function previewReportInline() {
  if (!store.evaluationResult) {
    ElMessage.warning('暂无可预览的评测数据，请先完成评测')
    return
  }
  previewDialogVisible.value = true
  previewLoading.value = true
  try {
    const res = await previewReport({
      ...store.evaluationResult,
      format: 'html',
      include_charts: true,
    })
    previewHtml.value = res.data.html
  } catch (e) {
    ElMessage.error('报告预览生成失败')
    previewDialogVisible.value = false
  } finally {
    previewLoading.value = false
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
    const url = `/api/reports/export/${file.reportId}?format=${file.format || 'html'}`
    const a = document.createElement('a')
    a.href = url
    a.download = file.name || `report.${file.format || 'html'}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    return
  }
  // 对于 copy 和 jsonld 类型，重新生成 blob 并触发下载
  if (file.type === 'copy') {
    const result = store.rewriteResults.find(r => file.name.includes(r.platform))
    if (result?.optimized_text) {
      const blob = new Blob([result.optimized_text], { type: 'text/markdown;charset=utf-8' })
      saveBlob(blob, file.name)
      return
    }
  }
  if (file.type === 'jsonld' && jsonldCode.value) {
    const blob = new Blob([jsonldCode.value], { type: 'application/json;charset=utf-8' })
    saveBlob(blob, file.name)
    return
  }
  ElMessage.warning('无法重新下载此文件，请重新导出')
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

</script>

<style scoped>
.export-view { max-width: 1240px; }
.page-title { font-size: 20px; margin-bottom: 20px; color: #2D3142; font-weight: 700; }
.empty-card { min-height: 400px; display: flex; align-items: center; justify-content: center; }
.empty-state { text-align: center; color: #9B9EAA; padding: 60px 0; }
.empty-state h3 { margin: 16px 0 8px; color: #6B6E7B; }
.exported-file { margin-bottom: 12px; }
.exported-file .el-card__body { display: flex; justify-content: space-between; align-items: center; }
.file-info { display: flex; align-items: center; gap: 12px; }
.file-name { font-size: 14px; color: #2D3142; }
.file-size { font-size: 12px; color: #9B9EAA; }
.file-actions { display: flex; gap: 8px; }
.jsonld-preview { background: #151721; color: #e5e5e5; padding: 16px; border-radius: 10px; overflow-x: auto; font-size: 12px; line-height: 1.6; max-height: 400px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.mini-score { font-size: 18px; margin-bottom: 8px; }
</style>
