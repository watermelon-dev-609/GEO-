<template>
  <el-drawer v-model="visible" title="版本历史" size="480px" direction="rtl">
    <div v-if="!props.textId" class="empty-hint">未关联文案，无法加载版本</div>
    <div v-else-if="loading" class="loading-hint">加载中...</div>
    <div v-else-if="errorMsg" class="empty-hint" style="color:#f56c6c;">{{ errorMsg }}</div>
    <div v-else-if="versions.length === 0" class="empty-hint">暂无版本记录</div>
    <el-timeline v-else>
      <el-timeline-item
        v-for="v in versions"
        :key="v.version_id"
        :timestamp="v.created_at"
        placement="top"
        :type="v.tags?.includes('回滚') ? 'warning' : 'primary'"
      >
        <div class="version-card">
          <div class="version-header">
            <strong>{{ v.title }}</strong>
            <el-tag v-if="v.tags?.includes('回滚')" size="small" type="warning">回滚</el-tag>
          </div>
          <div class="version-meta">
            <span>{{ v.word_count }}字</span>
            <span v-if="v.platform">· {{ v.platform }}</span>
            <span>· 版本{{ v.version_num }}</span>
          </div>
          <div class="version-actions">
            <el-button size="small" text @click="previewVersion(v)">查看</el-button>
            <el-button size="small" text @click="rollbackVersion(v)">回滚到此版本</el-button>
            <el-button size="small" text type="danger" @click="deleteVersionConfirm(v)">删除</el-button>
          </div>
        </div>
      </el-timeline-item>
    </el-timeline>

    <!-- 版本预览弹窗 -->
    <el-dialog v-model="showPreview" title="版本预览" width="700px">
      <div v-if="previewLoading" class="loading-hint">加载中...</div>
      <div v-else-if="previewError" class="empty-hint" style="color:#f56c6c;">{{ previewError }}</div>
      <div v-else class="preview-content">{{ previewContent }}</div>
    </el-dialog>
  </el-drawer>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const props = defineProps({ textId: { type: String, required: true } })
const emit = defineEmits(['rollback'])
const visible = ref(false)
const versions = ref([])
const loading = ref(false)
const errorMsg = ref('')
const showPreview = ref(false)
const previewLoading = ref(false)
const previewContent = ref('')
const previewError = ref('')

async function loadVersions() {
  if (!props.textId) {
    errorMsg.value = '未关联文案ID'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await api.get(`/versions/${encodeURIComponent(props.textId)}`)
    versions.value = res.data.versions || []
  } catch (e) {
    const detail = e.response?.data?.detail || e.message || '未知错误'
    if (e.response?.status === 404) {
      versions.value = []
    } else {
      errorMsg.value = '加载失败: ' + detail
      ElMessage.error('加载版本历史失败: ' + detail)
    }
  } finally { loading.value = false }
}

async function previewVersion(v) {
  showPreview.value = true
  previewLoading.value = true
  previewContent.value = ''
  previewError.value = ''
  try {
    const res = await api.get(`/versions/${encodeURIComponent(props.textId)}/${v.version_id}`)
    previewContent.value = res.data.content || '（无内容）'
  } catch (e) {
    const detail = e.response?.data?.detail || e.message || '未知错误'
    previewError.value = '加载版本内容失败: ' + detail
  } finally { previewLoading.value = false }
}

async function rollbackVersion(v) {
  try {
    await ElMessageBox.confirm(`确定回滚到「${v.title}」？当前内容将被保存为新版本。`, '确认回滚', { type: 'warning' })
    const res = await api.post(`/versions/${encodeURIComponent(props.textId)}/rollback/${v.version_id}`)
    ElMessage.success(`已回滚，生成新版本：${res.data.new_version.title}`)
    loadVersions()
    emit('rollback', v)
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('回滚失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function deleteVersionConfirm(v) {
  try {
    await ElMessageBox.confirm('确定删除此版本？', '确认删除', { type: 'warning' })
    await api.delete(`/versions/${encodeURIComponent(props.textId)}/${v.version_id}`)
    ElMessage.success('已删除')
    loadVersions()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

function open() { visible.value = true; loadVersions() }
defineExpose({ open })
</script>

<style scoped>
.loading-hint, .empty-hint { text-align: center; padding: 40px; color: #909399; }
.version-card { padding: 4px 0; }
.version-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.version-meta { font-size: 12px; color: #909399; margin-bottom: 8px; }
.version-actions { display: flex; gap: 4px; }
.preview-content { white-space: pre-wrap; max-height: 400px; overflow-y: auto; font-size: 13px; line-height: 1.8; }
</style>
