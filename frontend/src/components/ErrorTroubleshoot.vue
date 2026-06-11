<template>
  <el-dialog v-model="visible" title="故障排查指引" width="540px" :destroy-on-close="false">
    <div v-if="info" class="error-detail">
      <div class="error-header">
        <el-tag :type="severityTag(info.severity)" size="default">{{ severityLabel(info.severity) }}</el-tag>
        <span class="error-code">{{ code }}</span>
      </div>
      <div class="error-section">
        <h4>错误描述</h4>
        <p>{{ info.message }}</p>
      </div>
      <div class="error-section">
        <h4>可能原因</h4>
        <p>{{ detail || '请参考下方解决步骤' }}</p>
      </div>
      <div class="error-section">
        <h4>建议解决步骤</h4>
        <p class="error-suggestion">{{ info.suggestion }}</p>
      </div>
    </div>
    <div v-else class="empty-hint">未知错误，请截图并联系技术支持。</div>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="primary" @click="copyError">复制错误信息</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'

const visible = ref(false)
const code = ref('')
const detail = ref('')
const info = ref(null)

const errorCodes = {
  GEO_001: { message: '网络连接失败', suggestion: '请检查网络连接，确认是否能访问外部API。如使用代理，请检查代理设置。', severity: 'high' },
  GEO_002: { message: 'API请求超时', suggestion: 'AI平台响应较慢，已自动重试。如持续超时，请检查API平台状态或切换其他平台。', severity: 'medium' },
  GEO_011: { message: 'API调用配额已用尽', suggestion: '当月API调用次数已达上限。请等待下月重置，或在设置中提高限额。', severity: 'high' },
  GEO_022: { message: '内容合规检测未通过', suggestion: '文案中包含广告法禁词。请根据检测结果修改后重新提交。', severity: 'medium' },
  GEO_030: { message: 'AI生成内容为空', suggestion: 'AI平台返回了空内容。请尝试切换其他AI平台，或调整文案后重试。', severity: 'high' },
  GEO_033: { message: '信源一致性过低', suggestion: 'AI生成内容与原文案严重偏离。请重新优化，确保五维信息完整。', severity: 'high' },
}

function severityTag(s) { return s === 'critical' ? 'danger' : s === 'high' ? 'danger' : s === 'medium' ? 'warning' : 'info' }
function severityLabel(s) { return s === 'critical' ? '严重' : s === 'high' ? '高' : s === 'medium' ? '中' : '低' }

function show(errorCode, errorDetail = '') {
  code.value = errorCode
  detail.value = errorDetail
  info.value = errorCodes[errorCode] || { message: errorDetail || '未知错误', suggestion: '请截图错误信息并联系技术支持。', severity: 'medium' }
  visible.value = true
}

function copyError() {
  const text = `[${code.value}] ${info.value?.message || ''}\n详情: ${detail.value}\n建议: ${info.value?.suggestion || ''}`
  navigator.clipboard.writeText(text).then(() => ElMessage.success('已复制'))
    .catch(() => ElMessage.warning('复制失败，请手动选择'))
}

defineExpose({ show })
</script>

<style scoped>
.error-detail { line-height: 1.7; }
.error-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.error-code { font-family: monospace; font-size: 16px; color: #303133; }
.error-section { margin-bottom: 16px; }
.error-section h4 { margin: 0 0 4px; font-size: 14px; color: #606266; }
.error-section p { margin: 0; color: #909399; font-size: 13px; }
.error-suggestion { color: #409eff !important; }
.empty-hint { text-align: center; padding: 20px; color: #909399; }
</style>
