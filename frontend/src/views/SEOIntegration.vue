<template>
  <div class="seo-page">
    <div class="page-header">
      <h2>SEO数据集成</h2>
      <p class="subtitle">导入百度站长平台/Google Search Console数据，实现GEO+SEO联合分析</p>
    </div>

    <el-row :gutter="16">
      <!-- 导入面板 -->
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header><span>导入SEO数据</span></template>
          <el-upload
            drag
            :auto-upload="false"
            :on-change="handleFileChange"
            :limit="1"
            accept=".csv,.txt"
          >
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div class="upload-text">拖拽CSV文件或点击上传</div>
            <div class="upload-hint">支持百度站长平台、Google Search Console导出格式</div>
          </el-upload>
          <div style="margin-top:12px;">
            <el-select v-model="seoSource" style="width:100%" placeholder="数据来源">
              <el-option label="百度站长平台" value="baidu" />
              <el-option label="Google Search Console" value="google" />
              <el-option label="其他" value="other" />
            </el-select>
          </div>
          <el-button type="primary" @click="importData" :loading="importing" style="width:100%;margin-top:8px;">
            解析并导入
          </el-button>
        </el-card>
      </el-col>

      <!-- 分析面板 -->
      <el-col :span="16">
        <el-card shadow="hover" v-loading="analysisLoading">
          <template #header>
            <div class="card-header">
              <span>GEO+SEO联合分析</span>
              <el-button size="small" @click="loadAnalysis">刷新</el-button>
            </div>
          </template>
          <div v-if="analysis && analysis.status === 'ok'">
            <el-row :gutter="12">
              <el-col :span="6">
                <div class="stat-card">
                  <div class="stat-num">{{ analysis.total_keywords }}</div>
                  <div class="stat-label">总关键词</div>
                </div>
              </el-col>
              <el-col :span="6">
                <div class="stat-card">
                  <div class="stat-num">{{ analysis.rank_distribution?.top3_pct }}%</div>
                  <div class="stat-label">Top3占比</div>
                </div>
              </el-col>
              <el-col :span="6">
                <div class="stat-card">
                  <div class="stat-num">{{ analysis.avg_position }}</div>
                  <div class="stat-label">平均排名</div>
                </div>
              </el-col>
              <el-col :span="6">
                <div class="stat-card">
                  <div class="stat-num">{{ analysis.avg_ctr }}%</div>
                  <div class="stat-label">平均点击率</div>
                </div>
              </el-col>
            </el-row>
            <div style="margin-top:16px;">
              <h4>排名分布</h4>
              <div class="rank-bar">
                <div class="rank-seg rank-top3" :style="{width: analysis.rank_distribution?.top3_pct + '%'}">Top3: {{ analysis.rank_distribution?.top3_count }}</div>
                <div class="rank-seg rank-top10" :style="{width: Math.max(0, (analysis.rank_distribution?.top10_pct || 0) - (analysis.rank_distribution?.top3_pct || 0)) + '%'}">4-10: {{ (analysis.rank_distribution?.top10_count || 0) - (analysis.rank_distribution?.top3_count || 0) }}</div>
                <div class="rank-seg rank-other" :style="{width: Math.max(0, 100 - (analysis.rank_distribution?.top10_pct || 0)) + '%'}">11+: {{ analysis.total_keywords - (analysis.rank_distribution?.top10_count || 0) }}</div>
              </div>
            </div>
            <div v-if="analysis.high_opportunity?.length > 0" style="margin-top:16px;">
              <h4>优化机会词（高展示低排名）</h4>
              <el-table :data="analysis.high_opportunity.slice(0, 5)" size="small" stripe>
                <el-table-column prop="keyword" label="关键词" />
                <el-table-column prop="impressions" label="展示量" width="80" />
                <el-table-column prop="position" label="排名" width="60" />
                <el-table-column prop="ctr" label="点击率" width="70" />
              </el-table>
            </div>
          </div>
          <div v-else class="empty-hint">{{ analysis?.message || '暂无SEO数据' }}</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import api from '../api'

const seoSource = ref('baidu')
const selectedFile = ref(null)
const importing = ref(false)
const analysis = ref(null)
const analysisLoading = ref(false)

function handleFileChange(file) { selectedFile.value = file.raw }

async function importData() {
  if (!selectedFile.value) { ElMessage.warning('请选择CSV文件'); return }
  importing.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    formData.append('source', seoSource.value)
    const res = await api.post('/seo/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success(`导入成功: ${res.data.result.keyword_count} 个关键词`)
    loadAnalysis()
  } catch (e) {
    ElMessage.error('导入失败: ' + (e.response?.data?.detail || e.message))
  } finally { importing.value = false }
}

async function loadAnalysis() {
  analysisLoading.value = true
  try {
    const res = await api.get('/seo/analysis')
    analysis.value = res.data
  } catch (e) {
    if (e.response?.status !== 404) ElMessage.error('加载分析失败: ' + (e.response?.data?.detail || e.message))
  } finally { analysisLoading.value = false }
}

onMounted(loadAnalysis)
</script>

<style scoped>
.seo-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 20px; }
.subtitle { color: #909399; font-size: 13px; margin-top: 4px; }
.upload-icon { font-size: 40px; color: #c0c4cc; }
.upload-text { font-size: 14px; margin-top: 8px; color: #606266; }
.upload-hint { font-size: 11px; color: #c0c4cc; margin-top: 4px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.stat-card { text-align: center; padding: 16px 0; background: #f5f7fa; border-radius: 8px; }
.stat-num { font-size: 28px; font-weight: 700; color: #303133; }
.stat-label { font-size: 12px; color: #909399; margin-top: 4px; }
.rank-bar { display: flex; height: 24px; border-radius: 12px; overflow: hidden; font-size: 11px; line-height: 24px; text-align: center; color: #fff; }
.rank-seg.rank-top3 { background: #67c23a; }
.rank-seg.rank-top10 { background: #e6a23c; }
.rank-seg.rank-other { background: #c0c4cc; }
.empty-hint { text-align: center; padding: 60px 0; color: #c0c4cc; }
h4 { font-size: 14px; margin: 0 0 8px; color: #606266; }
</style>
