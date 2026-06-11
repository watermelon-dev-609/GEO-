<template>
  <div class="template-engine">
    <el-row :gutter="16">
      <!-- 左侧：平台列表 -->
      <el-col :span="5">
        <el-card shadow="hover" class="platform-list-card">
          <template #header>
            <div class="card-header">
              <span>平台列表</span>
              <el-tag size="small" :type="watchdogMode === 'watchdog' ? 'success' : 'warning'" effect="plain" style="margin-left:4px">
                {{ watchdogMode === 'watchdog' ? '🔍 Watching' : '⏱ Polling' }}
              </el-tag>
              <el-button size="small" type="primary" text @click="reloadAll">刷新缓存</el-button>
            </div>
          </template>
          <el-menu :default-active="activePlatform" @select="selectPlatform">
            <el-menu-item v-for="p in platforms" :key="p.platform_id" :index="p.platform_id">
              <template #title>
                <span class="platform-name">{{ p.platform_name }}</span>
                <el-tag size="small" :type="p.valid ? 'success' : 'warning'" style="margin-left:8px">
                  v{{ p.version }}
                </el-tag>
              </template>
            </el-menu-item>
          </el-menu>
        </el-card>
      </el-col>

      <!-- 中间：编辑器 -->
      <el-col :span="12">
        <el-card shadow="hover" v-if="activePlatform">
          <template #header>
            <div class="card-header">
              <span>{{ currentTemplate?.platform_name || activePlatform }} — 模板编辑</span>
              <div>
                <el-button size="small" @click="validateCurrent">校验</el-button>
                <el-button size="small" type="primary" @click="saveTemplate" :loading="saving">保存</el-button>
              </div>
            </div>
          </template>

          <el-tabs v-model="activeTab" v-if="editForm">
            <el-tab-pane label="概览" name="overview">
              <el-form label-width="100px" size="small">
                <el-form-item label="平台名称"><el-input v-model="editForm.platform_name" /></el-form-item>
                <el-form-item label="版本"><el-input-number v-model="editForm.version" :min="1" /></el-form-item>
                <el-form-item label="策略"><el-input v-model="editForm.strategy" type="textarea" :rows="2" /></el-form-item>
                <el-form-item label="引用机制"><el-input v-model="editForm.citation_mechanism" type="textarea" :rows="3" /></el-form-item>
                <el-form-item label="风格"><el-input v-model="editForm.style" /></el-form-item>
              </el-form>
            </el-tab-pane>

            <el-tab-pane label="Header" name="header">
              <el-form label-width="120px" size="small">
                <el-form-item label="标题格式"><el-input v-model="editForm.header.title_format" /></el-form-item>
                <el-form-item label="标题示例"><el-input v-model="editForm.header.title_example" /></el-form-item>
                <el-form-item label="字数范围">
                  <el-row :gutter="8">
                    <el-col :span="8"><el-input-number v-model="editForm.header.word_limits.min" :min="100" /></el-col>
                    <el-col :span="8"><el-input-number v-model="editForm.header.word_limits.target" :min="100" /></el-col>
                    <el-col :span="8"><el-input-number v-model="editForm.header.word_limits.max" :min="100" /></el-col>
                  </el-row>
                </el-form-item>
                <el-form-item label="首段规则">
                  <div v-for="(rule, i) in editForm.header.first_paragraph_rules" :key="i" style="margin-bottom:4px">
                    <el-input v-model="editForm.header.first_paragraph_rules[i]">
                      <template #append><el-button @click="editForm.header.first_paragraph_rules.splice(i,1)" icon="Delete" /></template>
                    </el-input>
                  </div>
                  <el-button size="small" @click="editForm.header.first_paragraph_rules.push('')">+ 添加规则</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <el-tab-pane label="Body" name="body">
              <el-form label-width="120px" size="small">
                <el-form-item label="特殊规则"><el-input v-model="editForm.body.special_rule" type="textarea" :rows="2" /></el-form-item>
                <el-form-item label="H2密度"><el-input v-model="editForm.body.h2_density" /></el-form-item>
                <el-form-item label="段落长度(字)">
                  <el-row :gutter="8">
                    <el-col :span="12"><el-input-number v-model="editForm.body.paragraph_length.min" :min="30" /></el-col>
                    <el-col :span="12"><el-input-number v-model="editForm.body.paragraph_length.max" :min="30" /></el-col>
                  </el-row>
                </el-form-item>
                <el-form-item label="FAQ数量">
                  <el-row :gutter="8">
                    <el-col :span="12"><el-input-number v-model="editForm.body.faq_count.min" :min="0" /></el-col>
                    <el-col :span="12"><el-input-number v-model="editForm.body.faq_count.max" :min="0" /></el-col>
                  </el-row>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <el-tab-pane label="Schema" name="schema">
              <el-form label-width="120px" size="small">
                <el-form-item label="优先类型">
                  <el-select v-model="editForm.schema.preferred_types" multiple allow-create filterable placeholder="选择或输入">
                    <el-option v-for="t in ['Article','FAQPage','Product','Service','Organization','LocalBusiness','TechArticle','Report']" :key="t" :label="t" :value="t" />
                  </el-select>
                </el-form-item>
                <el-form-item label="官网额外类型"><el-input v-model="editForm.schema.official_site_extra" /></el-form-item>
              </el-form>
            </el-tab-pane>

            <el-tab-pane label="Weights" name="weights">
              <el-form label-width="120px" size="small">
                <el-form-item label="内容源权重">
                  <div v-for="(v, k) in editForm.weights.content_sources" :key="k" style="margin-bottom:4px">
                    <el-row :gutter="8">
                      <el-col :span="12"><el-input v-model="editForm.weights._source_keys[idx(k)]" placeholder="源名称" /></el-col>
                      <el-col :span="8"><el-input-number v-model="editForm.weights.content_sources[k]" :min="1" :max="10" /></el-col>
                      <el-col :span="4"><el-button @click="removeSourceWeight(k)" icon="Delete" size="small" /></el-col>
                    </el-row>
                  </div>
                  <el-button size="small" @click="addSourceWeight">+ 添加源</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <el-tab-pane label="验证" name="verification">
              <el-form label-width="100px" size="small">
                <el-form-item label="校验规则">
                  <div v-for="(c, i) in editForm.verification.checks" :key="i" style="margin-bottom:4px">
                    <el-input v-model="editForm.verification.checks[i].description" placeholder="校验描述" />
                  </div>
                </el-form-item>
                <el-form-item label="平台禁词">
                  <el-select v-model="editForm.verification.forbidden_words" multiple allow-create filterable placeholder="输入禁词" />
                </el-form-item>
                <el-form-item label="禁忌模式">
                  <el-select v-model="editForm.verification.taboo_patterns" multiple allow-create filterable placeholder="输入禁忌模式" />
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <el-tab-pane label="Rules" name="rules">
              <el-form-item label="Prompt规则列表">
                <div v-for="(rule, i) in editForm.rules" :key="i" style="margin-bottom:4px">
                  <el-input v-model="editForm.rules[i]" type="textarea" :rows="1">
                    <template #append><el-button @click="editForm.rules.splice(i,1)" icon="Delete" /></template>
                  </el-input>
                </div>
                <el-button size="small" @click="editForm.rules.push('')">+ 添加规则</el-button>
              </el-form-item>
            </el-tab-pane>
          </el-tabs>
        </el-card>

        <el-empty v-else description="从左侧选择一个平台开始编辑" />
      </el-col>

      <!-- 右侧：预览 + 版本历史 -->
      <el-col :span="7">
        <!-- 结构预览 -->
        <el-card shadow="hover" v-if="previewData" style="margin-bottom:16px">
          <template #header>
            <span>结构预览</span>
            <el-button size="small" text style="float:right" @click="doPreview">刷新预览</el-button>
          </template>
          <div class="preview-section">
            <p><strong>标题格式：</strong>{{ previewData.title_format }}</p>
            <p><strong>字数：</strong>{{ previewData.word_limits?.min }}-{{ previewData.word_limits?.max }}字</p>
            <p><strong>H2密度：</strong>{{ previewData.section_structure?.h2_density }}</p>
            <p><strong>段落：</strong>{{ previewData.section_structure?.paragraph_length?.min }}-{{ previewData.section_structure?.paragraph_length?.max }}字</p>
            <p><strong>FAQ：</strong>{{ previewData.section_structure?.faq_count?.min }}-{{ previewData.section_structure?.faq_count?.max }}组</p>
            <p v-if="previewData.schema_config?.preferred_types?.length"><strong>Schema：</strong>{{ previewData.schema_config.preferred_types.join(', ') }}</p>
            <div v-if="previewData.content_source_weights && Object.keys(previewData.content_source_weights).length">
              <strong>内容源权重：</strong>
              <el-tag v-for="(v,k) in previewData.content_source_weights" :key="k" size="small" style="margin:2px">{{ k }}:{{ v }}</el-tag>
            </div>
          </div>
        </el-card>

        <!-- 版本历史 -->
        <el-card shadow="hover" v-if="activePlatform">
          <template #header>
            <span>版本历史</span>
            <el-button size="small" text style="float:right" @click="loadHistory">刷新</el-button>
          </template>
          <el-timeline v-if="history.length">
            <el-timeline-item
              v-for="h in history"
              :key="h.version_id"
              :timestamp="h.saved_at"
              placement="top"
            >
              <p>v{{ h.version_num }}</p>
              <el-button size="small" text type="primary" @click="doRollback(h.version_id)">回滚到此版本</el-button>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="暂无历史版本" :image-size="40" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getEnginePlatforms, getEnginePlatform, updateEnginePlatform,
  validateTemplate, getTemplateHistory, previewTemplate,
  rollbackTemplate, reloadTemplates, getWatchdogStatus
} from '@/api'

const platforms = ref([])
const activePlatform = ref('')
const currentTemplate = ref(null)
const editForm = ref(null)
const activeTab = ref('overview')
const saving = ref(false)
const previewData = ref(null)
const history = ref([])
const watchdogMode = ref('polling')

onMounted(async () => {
  await loadPlatforms()
  await checkWatchdogStatus()
})

async function checkWatchdogStatus() {
  try {
    const { data } = await getWatchdogStatus()
    watchdogMode.value = data.mode || 'polling'
  } catch {
    watchdogMode.value = 'polling'
  }
}

async function loadPlatforms() {
  try {
    const { data } = await getEnginePlatforms()
    platforms.value = data.platforms || []
  } catch (e) {
    ElMessage.error('加载平台列表失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function selectPlatform(pid) {
  activePlatform.value = pid
  activeTab.value = 'overview'
  try {
    const { data } = await getEnginePlatform(pid)
    const tmpl = data.template
    currentTemplate.value = tmpl

    // Deep clone for editing
    const form = JSON.parse(JSON.stringify(tmpl))
    // Ensure all nested objects exist
    form.header = form.header || { title_format: '', first_paragraph_rules: [], word_limits: { min: 800, max: 1500, target: 1200 } }
    form.body = form.body || { special_rule: '', h2_density: '', paragraph_length: { min: 100, max: 400 }, faq_count: { min: 2, max: 4 } }
    form.schema = form.schema || { preferred_types: [], official_site_extra: '' }
    form.weights = form.weights || { content_sources: {}, citation: {} }
    form.verification = form.verification || { checks: [], forbidden_words: [], taboo_patterns: [] }
    form.rules = form.rules || []
    // Track source keys separately for editing
    form.weights._source_keys = Object.keys(form.weights.content_sources || {})
    editForm.value = form

    await Promise.all([doPreview(), loadHistory()])
  } catch (e) {
    ElMessage.error('加载模板失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function saveTemplate() {
  saving.value = true
  try {
    // Clean up _source_keys before sending
    const config = JSON.parse(JSON.stringify(editForm.value))
    delete config.weights._source_keys
    delete config._source
    delete config.platform_id

    await updateEnginePlatform(activePlatform.value, { config })
    ElMessage.success('模板已保存，缓存已刷新')
    await loadPlatforms()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function validateCurrent() {
  try {
    const { data } = await validateTemplate(activePlatform.value)
    if (data.valid) {
      ElMessage.success('模板校验通过')
    } else {
      ElMessage.warning('校验发现问题: ' + data.issues.join('; '))
    }
  } catch (e) {
    ElMessage.error('校验失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function doPreview() {
  try {
    const { data } = await previewTemplate({ platform_id: activePlatform.value, sandtable_type: 'smart_city' })
    previewData.value = data.preview
  } catch (e) {
    // Silently fail for preview
  }
}

async function loadHistory() {
  try {
    const { data } = await getTemplateHistory(activePlatform.value)
    history.value = data.history || []
  } catch (e) {
    history.value = []
  }
}

async function doRollback(versionId) {
  try {
    await ElMessageBox.confirm(`确认回滚到版本 ${versionId}？当前版本将被自动保存为历史版本。`, '确认回滚', { type: 'warning' })
    await rollbackTemplate(activePlatform.value, versionId)
    ElMessage.success('回滚成功')
    await selectPlatform(activePlatform.value)
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('回滚失败: ' + (e.response?.data?.detail || e.message))
    }
  }
}

async function reloadAll() {
  try {
    await reloadTemplates()
    ElMessage.success('缓存已刷新')
    await loadPlatforms()
  } catch (e) {
    ElMessage.error('刷新失败: ' + (e.response?.data?.detail || e.message))
  }
}

// Helper: index into _source_keys array
function idx(k) {
  return editForm.value.weights._source_keys.indexOf(k)
}

function addSourceWeight() {
  const newKey = '新源' + Date.now().toString(36)
  editForm.value.weights._source_keys.push(newKey)
  editForm.value.weights.content_sources[newKey] = 5
}

function removeSourceWeight(k) {
  const i = editForm.value.weights._source_keys.indexOf(k)
  if (i >= 0) editForm.value.weights._source_keys.splice(i, 1)
  delete editForm.value.weights.content_sources[k]
}
</script>

<style scoped>
.template-engine { padding: 4px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.platform-list-card .el-menu { border-right: none; }
.platform-name { flex: 1; overflow: hidden; text-overflow: ellipsis; }
.preview-section { font-size: 13px; line-height: 1.8; }
.preview-section p { margin: 4px 0; }
</style>
