<template>
  <div class="utm-manager" v-loading="store.utmLoading">
    <div class="page-header">
      <h2>UTM追踪管理</h2>
      <p class="page-desc">管理AI平台专属追踪链接，精确归因AI引用带来的流量与转化</p>
      <el-button type="primary" @click="showCreateDialog = true" style="margin-left: auto">+ 新建推广计划</el-button>
    </div>

    <!-- Campaign List -->
    <el-card shadow="hover">
      <template #header>
        <span>推广计划列表</span>
        <el-switch v-model="activeOnly" size="small" active-text="仅活跃" style="margin-left: 12px" @change="load" />
      </template>
      <el-empty v-if="!campaigns.length" description="暂无UTM推广计划，点击上方按钮创建">
        <el-button type="primary" @click="showCreateDialog = true">创建第一个推广计划</el-button>
      </el-empty>
      <el-table v-else :data="campaigns" size="small">
        <el-table-column prop="name" label="计划名称" min-width="160" />
        <el-table-column prop="utm_source" label="UTM Source" width="130">
          <template #default="{ row }">{{ row.utm_source || '(按平台自动)' }}</template>
        </el-table-column>
        <el-table-column prop="utm_medium" label="Medium" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="row.utm_medium === 'ai_referral' ? 'success' : 'info'">{{ row.utm_medium }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="utm_campaign" label="Campaign" width="140" show-overflow-tooltip />
        <el-table-column prop="landing_page_url" label="落地页" min-width="200" show-overflow-tooltip />
        <el-table-column label="关联平台" width="180">
          <template #default="{ row }">
            <el-tag v-for="pid in row.platform_ids" :key="pid" size="small" style="margin: 1px 2px">{{ pid }}</el-tag>
            <span v-if="!row.platform_ids?.length" style="color:#909399">全部平台</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="70">
          <template #default="{ row }">
            <el-tag :type="row.active ? 'success' : 'info'" size="small">{{ row.active ? '活跃' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="showLinks(row)">链接</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Batch Generate Section -->
    <el-card shadow="hover" class="batch-card">
      <template #header>批量生成UTM链接</template>
      <el-form :inline="true" :model="batchForm" size="small">
        <el-form-item label="落地页URL" required>
          <el-input v-model="batchForm.url" placeholder="https://example.com/product" style="width: 340px" />
        </el-form-item>
        <el-form-item label="Medium">
          <el-select v-model="batchForm.medium" style="width: 140px">
            <el-option value="ai_referral" label="AI平台引用" />
            <el-option value="organic" label="自然搜索" />
            <el-option value="social" label="社交媒体" />
            <el-option value="email" label="邮件" />
            <el-option value="cpc" label="付费点击" />
          </el-select>
        </el-form-item>
        <el-form-item label="Campaign">
          <el-input v-model="batchForm.campaign" placeholder="推广活动名" style="width: 160px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleBatchGenerate" :loading="generating">生成全部平台链接</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Generated Links Dialog -->
    <el-dialog v-model="showLinksDialog" title="UTM追踪链接" width="700px" :destroy-on-close="true">
      <div v-if="generatedLinks.length">
        <div class="link-item" v-for="link in generatedLinks" :key="link.platform_id || 'default'">
          <div class="link-platform">
            <el-tag size="small" :type="link.platform_id ? '' : 'info'">{{ link.platform_id || '默认' }}</el-tag>
          </div>
          <div class="link-url">{{ link.full_url }}</div>
          <el-button size="small" @click="copyLink(link.full_url)">复制</el-button>
        </div>
      </div>
      <el-empty v-else description="尚未生成链接" :image-size="60" />
    </el-dialog>

    <!-- Create Campaign Dialog -->
    <el-dialog v-model="showCreateDialog" title="新建UTM推广计划" width="550px" :destroy-on-close="true" @closed="createFormRef?.resetFields()">
      <el-form ref="createFormRef" :model="createForm" label-position="top" size="small">
        <el-form-item label="计划名称" required>
          <el-input v-model="createForm.name" placeholder="例：2026Q2智慧交通GEO推广" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="UTM Source">
              <el-input v-model="createForm.utm_source" placeholder="留空则按AI平台自动设置" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="UTM Medium">
              <el-select v-model="createForm.utm_medium" style="width:100%">
                <el-option value="ai_referral" label="AI平台引用" />
                <el-option value="organic" label="自然搜索" />
                <el-option value="social" label="社交媒体" />
                <el-option value="email" label="邮件" />
                <el-option value="cpc" label="付费点击" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="UTM Campaign">
          <el-input v-model="createForm.utm_campaign" placeholder="推广活动标识" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="UTM Term（关键词）">
              <el-input v-model="createForm.utm_term" placeholder="可选" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="UTM Content（变体）">
              <el-input v-model="createForm.utm_content" placeholder="可选" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="目标落地页URL" required>
          <el-input v-model="createForm.landing_page_url" placeholder="https://example.com/landing" />
        </el-form-item>
        <el-form-item label="关联AI平台">
          <el-select v-model="createForm.platform_ids" multiple placeholder="选择平台（空则全部）" style="width:100%">
            <el-option v-for="p in AI_PLATFORMS" :key="p.value" :value="p.value" :label="p.label" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreate" :loading="creating">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useGeoStore } from '../stores/geo'
import { createCampaign, deleteCampaign, generateUTMLink, batchGenerateUTM } from '../api'
import { AI_PLATFORMS } from '../constants'
import { ElMessage, ElMessageBox } from 'element-plus'

const store = useGeoStore()
const activeOnly = ref(false)
const showCreateDialog = ref(false)
const showLinksDialog = ref(false)
const generating = ref(false)
const creating = ref(false)
const generatedLinks = ref([])
const createFormRef = ref(null)

const batchForm = reactive({ url: store.enterpriseWebsite || 'http://www.weiyida.co', medium: 'ai_referral', campaign: '' })

const createForm = reactive({
  name: '', utm_source: '', utm_medium: 'ai_referral', utm_campaign: '',
  utm_term: '', utm_content: '', landing_page_url: store.enterpriseWebsite || 'http://www.weiyida.co', platform_ids: [],
})

const campaigns = computed(() => store.utmCampaigns || [])

async function load() {
  await store.fetchUTMCampaigns()
}

async function handleCreate() {
  if (!createForm.name || !createForm.landing_page_url) {
    ElMessage.warning('请填写计划名称和落地页URL')
    return
  }
  creating.value = true
  try {
    await createCampaign(createForm)
    ElMessage.success('推广计划创建成功')
    showCreateDialog.value = false
    await load()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    creating.value = false
  }
}

async function showLinks(campaign) {
  showLinksDialog.value = true
  generatedLinks.value = []
  try {
    const res = await generateUTMLink(campaign.id)
    if (res.data?.links) {
      generatedLinks.value = res.data.links
    } else if (res.data?.link) {
      generatedLinks.value = [res.data.link]
    }
  } catch (e) {
    ElMessage.error('生成链接失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function handleBatchGenerate() {
  if (!batchForm.url) {
    ElMessage.warning('请输入落地页URL')
    return
  }
  generating.value = true
  try {
    const res = await batchGenerateUTM({
      landing_page_url: batchForm.url,
      utm_medium: batchForm.medium,
      utm_campaign: batchForm.campaign,
    })
    generatedLinks.value = res.data?.links || []
    showLinksDialog.value = true
    ElMessage.success(`已生成 ${generatedLinks.value.length} 条UTM链接`)
  } catch (e) {
    ElMessage.error('批量生成失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    generating.value = false
  }
}

async function handleDelete(id) {
  try {
    await ElMessageBox.confirm('确定删除该推广计划？', '确认删除', { type: 'warning' })
    await deleteCampaign(id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

function copyLink(url) {
  navigator.clipboard.writeText(url).then(
    () => ElMessage.success('已复制到剪贴板'),
    () => ElMessage.warning('复制失败，请手动复制')
  )
}

onMounted(load)
</script>

<style scoped>
.utm-manager { max-width: 1240px; margin: 0 auto; padding: 24px; }
.page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
.page-header h2 { margin: 0; color: var(--geo-text); font-size: 20px; }
.page-desc { color: #909399; margin: 0; font-size: 13px; }

.batch-card { margin-top: 20px; }
.link-item { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid #f0f0f0; }
.link-platform { width: 80px; flex-shrink: 0; }
.link-url { flex: 1; font-size: 13px; color: #606266; word-break: break-all; font-family: monospace; }
</style>
