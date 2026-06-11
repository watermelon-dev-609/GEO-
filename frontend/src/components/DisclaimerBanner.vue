<template>
  <el-dialog v-model="visible" title="使用须知与免责声明" width="560px" :close-on-click-modal="false" :close-on-press-escape="false" :show-close="false">
    <div class="disclaimer-content">
      <el-alert type="warning" :closable="false" show-icon style="margin-bottom:16px">
        <template #title>请在使用前仔细阅读以下说明</template>
      </el-alert>
      <div class="disclaimer-section">
        <h4>1. AI收录存在随机性</h4>
        <p>AI平台的收录和引用机制受多种因素影响（平台算法变更、训练数据更新、检索策略调整等），GEO优化可显著提高被引用概率，但无法保证100%收录效果。</p>
      </div>
      <div class="disclaimer-section">
        <h4>2. 内容需人工审核</h4>
        <p>AI生成或优化的文案可能存在事实偏差。所有对外发布的内容均需经过人工审核确认，特别是涉及量化数据、客户案例、资质证书等信息。</p>
      </div>
      <div class="disclaimer-section">
        <h4>3. API调用将产生费用</h4>
        <p>GEO优化和AI评测功能需要调用第三方AI平台API，将按各平台标准产生费用。请在「配置API Key」前确认各平台的计费规则。系统提供用量监控面板，建议定期查看。</p>
      </div>
      <div class="disclaimer-section">
        <h4>4. 遵守广告法规</h4>
        <p>系统提供广告法禁词检测功能，但检测结果仅供参考。发布内容前请确保符合《中华人民共和国广告法》相关规定。</p>
      </div>
    </div>
    <template #footer>
      <div style="text-align:center;">
        <el-checkbox v-model="dontShowAgain">不再提示</el-checkbox>
        <el-button type="primary" @click="accept" style="margin-left:12px;">我已阅读并确认</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const DISCLAIMER_KEY = 'geo_disclaimer_accepted'
const visible = ref(false)
const dontShowAgain = ref(false)

function accept() {
  if (dontShowAgain.value) {
    localStorage.setItem(DISCLAIMER_KEY, '1')
  }
  visible.value = false
}

onMounted(() => {
  if (!localStorage.getItem(DISCLAIMER_KEY)) {
    visible.value = true
  }
})
</script>

<style scoped>
.disclaimer-content { font-size: 13px; line-height: 1.8; }
.disclaimer-section { margin-bottom: 16px; }
.disclaimer-section h4 { margin: 0 0 4px; font-size: 14px; color: #303133; }
.disclaimer-section p { margin: 0; color: #606266; }
</style>
