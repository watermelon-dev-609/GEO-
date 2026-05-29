<template>
  <div class="templates-page">
    <div class="page-intro">
      <h2>内容质量中心</h2>
      <div class="intro-desc">
        管理写作模板与审核标准，确保生成的文案稳定达到 AI 搜索收录要求。
        <el-button size="small" link type="primary" @click="activeTab = 'guide'">查看使用指引</el-button>
      </div>
    </div>

    <!-- 统计概览 -->
    <el-row :gutter="16" class="overview-row">
      <el-col :span="6">
        <div class="ov-card" @click="activeTab = 'templates'">
          <div class="ov-num blue">{{ templates.length }}</div>
          <div class="ov-label">写作模板</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="ov-card" @click="activeTab = 'standards'">
          <div class="ov-num green">{{ checklist.filter(c => c.enabled).length }}</div>
          <div class="ov-label">已启用审核项</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="ov-card">
          <div class="ov-num purple">{{ totalWeight }}%</div>
          <div class="ov-label">权重覆盖率</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="ov-card ov-action" @click="doQuickExport">
          <div class="ov-num">
            <el-icon :size="22"><Download /></el-icon>
          </div>
          <div class="ov-label">一键导出规范文档</div>
        </div>
      </el-col>
    </el-row>

    <el-tabs v-model="activeTab" type="border-card" class="main-tabs">
      <!-- Tab 1: 写作模板 -->
      <el-tab-pane label="写作模板" name="templates">
        <div class="tab-toolbar">
          <el-select v-model="tplFilter" size="small" placeholder="按沙盘筛选" clearable style="width:200px;">
            <el-option v-for="s in SANDTABLE_TYPES" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
          <el-button size="small" type="primary" @click="openNewTemplate">新建模板</el-button>
          <el-button size="small" @click="loadTemplates" :loading="tplLoading" :icon="Refresh">刷新</el-button>
        </div>

        <div v-if="tplLoading" v-loading="true" style="min-height:200px;" />

        <div v-else-if="filteredTemplates.length === 0 && !tplFilter" class="empty-guide">
          <el-icon :size="48"><EditPen /></el-icon>
          <h3>还没有写作模板</h3>
          <p>模板能为不同沙盘类型预设标准的文案结构，LLM 改写时将严格遵循。</p>
          <el-button type="primary" @click="openNewTemplate">创建第一个模板</el-button>
        </div>

        <div v-else-if="filteredTemplates.length === 0" class="empty-guide">
          <p>该沙盘类型暂无模板，<el-button size="small" type="primary" link @click="tplFilter = ''">查看全部</el-button></p>
        </div>

        <div v-else class="tpl-grid">
          <div v-for="tpl in filteredTemplates" :key="tpl.id" class="tpl-card" @click="previewTemplate(tpl)">
            <div class="tpl-card-top">
              <span class="tpl-card-name">{{ tpl.name }}</span>
              <el-tag size="small" effect="plain">{{ tpl.category }}</el-tag>
            </div>
            <p class="tpl-card-desc">{{ tpl.description }}</p>
            <div class="tpl-card-vars" v-if="tpl.variables?.length">
              <el-tag v-for="v in tpl.variables.slice(0, 4)" :key="v.name" size="small" type="info" effect="plain">
                {{ v.name }}
              </el-tag>
              <span v-if="tpl.variables.length > 4" style="font-size:11px;color:#9B9EAA;">+{{ tpl.variables.length - 4 }}</span>
            </div>
            <div class="tpl-card-actions" @click.stop>
              <el-button size="small" link type="primary" @click="editTemplate(tpl)">编辑</el-button>
              <el-button size="small" link type="primary" @click="previewTemplate(tpl)">预览</el-button>
              <el-button size="small" link type="danger" @click="deleteTemplate(tpl.id)">删除</el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 2: 审核标准 -->
      <el-tab-pane label="审核标准" name="standards">
        <div class="tab-toolbar">
          <span class="tab-desc">配置每条审核标准的权重和及格线，权重总和应为 100%。</span>
          <el-button size="small" type="primary" @click="resetStandards" link>恢复默认</el-button>
        </div>

        <div class="stds-grid">
          <div v-for="item in checklist" :key="item.key" class="std-card" :class="{ disabled: !item.enabled }">
            <div class="std-card-left">
              <el-switch v-model="item.enabled" size="small" />
            </div>
            <div class="std-card-body">
              <div class="std-card-title">{{ item.label }}</div>
              <div class="std-card-desc">{{ item.description }}</div>
            </div>
            <div class="std-card-right">
              <div class="std-slider-group">
                <div class="std-slider-label">权重 {{ item.weight }}%</div>
                <el-slider v-model="item.weight" :min="0" :max="100" :step="5" :show-tooltip="false" size="small" style="width:120px;" />
              </div>
              <div class="std-slider-group">
                <div class="std-slider-label">阈值 {{ item.threshold }}分</div>
                <el-slider v-model="item.threshold" :min="0" :max="100" :step="5" :show-tooltip="false" size="small" style="width:120px;" />
              </div>
            </div>
          </div>
        </div>

        <div class="stds-summary">
          <span>权重合计: <strong :style="{ color: totalWeight === 100 ? '#5B8C5A' : '#C5554A' }">{{ totalWeight }}%</strong></span>
          <span v-if="totalWeight !== 100" style="color:#C5554A;margin-left:8px;">（建议调整为 100%）</span>
          <el-button type="primary" size="small" style="margin-left:16px;" @click="saveStandards" :loading="stdsSaving">保存审核标准</el-button>
        </div>
      </el-tab-pane>

      <!-- Tab 3: 使用指引 -->
      <el-tab-pane label="使用指引" name="guide">
        <el-row :gutter="24">
          <el-col :span="16">
            <div class="guide-section">
              <h3>这个页面做什么</h3>
              <div class="guide-flow">
                <div class="guide-step">
                  <div class="guide-step-num">1</div>
                  <div>
                    <strong>先配置审核标准</strong>
                    <p>定义"好内容"的评判维度——实体完整性、结构质量、量化数据等。这些标准会在 AI 评测阶段自动应用。</p>
                  </div>
                </div>
                <div class="guide-arrow">→</div>
                <div class="guide-step">
                  <div class="guide-step-num">2</div>
                  <div>
                    <strong>再创建写作模板</strong>
                    <p>为不同沙盘类型（智慧交通、智慧城市等）预设 Markdown 模板。模板中的变量会在 GEO 工坊自动填充企业信息。</p>
                  </div>
                </div>
                <div class="guide-arrow">→</div>
                <div class="guide-step">
                  <div class="guide-step-num">3</div>
                  <div>
                    <strong>在 GEO 工坊中应用</strong>
                    <p>改写时会自动读取模板和审核标准，约束 LLM 按规范生成。评测阶段的 differentiation 和 structure_quality 维度会参考这些标准打分。</p>
                  </div>
                </div>
                <div class="guide-arrow">→</div>
                <div class="guide-step">
                  <div class="guide-step-num">4</div>
                  <div>
                    <strong>导出规范同步团队</strong>
                    <p>一键导出 Markdown 文档，包含模板、标准和 AI 采信六原则，可作为团队内部写作规范。</p>
                  </div>
                </div>
              </div>
            </div>
          </el-col>
          <el-col :span="8">
            <div class="guide-sidebar">
              <h4>AI 采信六原则</h4>
              <div class="principle-list">
                <div class="principle-item"><span class="principle-dot"></span><strong>实体锚定</strong> — 企业名/地域/产品名完整清晰</div>
                <div class="principle-item"><span class="principle-dot"></span><strong>定义优先</strong> — 专业概念给出权威定义</div>
                <div class="principle-item"><span class="principle-dot"></span><strong>量化事实</strong> — 所有能力用数字支撑</div>
                <div class="principle-item"><span class="principle-dot"></span><strong>FAQ结构</strong> — 嵌入自然问答对</div>
                <div class="principle-item"><span class="principle-dot"></span><strong>层级结构化</strong> — H2/H3 + 列表</div>
                <div class="principle-item"><span class="principle-dot"></span><strong>信息增量</strong> — 本地化细节 + 行业独特信息</div>
              </div>
              <el-divider />
              <h4>快速导出</h4>
              <el-checkbox-group v-model="exportItems" style="margin-bottom:12px;">
                <el-checkbox label="templates">写作模板</el-checkbox>
                <el-checkbox label="standards">审核标准</el-checkbox>
                <el-checkbox label="guide">GEO写作指南</el-checkbox>
              </el-checkbox-group>
              <el-button type="primary" size="small" @click="doExport" :disabled="exportItems.length === 0" :loading="exporting" style="width:100%;">
                导出选中项 (.md)
              </el-button>
            </div>
          </el-col>
        </el-row>
      </el-tab-pane>
    </el-tabs>

    <!-- 模板编辑器弹窗 -->
    <el-dialog v-model="editorVisible" :title="editingTpl?.id ? '编辑模板' : '新建模板'" width="760px" top="4vh">
      <el-form label-position="top" size="small">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="模板名称">
              <el-input v-model="tplForm.name" placeholder="如：智慧交通沙盘企业介绍" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="模板类型">
              <el-select v-model="tplForm.category" style="width:100%;">
                <el-option label="企业介绍" value="企业介绍" />
                <el-option label="产品文案" value="产品文案" />
                <el-option label="案例模板" value="案例模板" />
                <el-option label="FAQ模板" value="FAQ模板" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="一句话描述这个模板的用途">
          <el-input v-model="tplForm.description" placeholder="如：适用于智慧交通沙盘的企业官网介绍页，突出技术实力和项目经验" />
        </el-form-item>
        <el-form-item label="Markdown 正文（用 {变量名} 做占位符）">
          <el-input v-model="tplForm.content" type="textarea" :rows="14" placeholder="# {enterprise_name} — {sandtable_type}解决方案&#10;&#10;## 公司概况&#10;{enterprise_name}坐落于{enterprise_location}..." />
        </el-form-item>
        <el-form-item label="变量定义">
          <div class="var-row" v-for="(v, i) in tplForm.variables" :key="i">
            <el-input v-model="v.name" size="small" placeholder="变量名（英文）" style="width:160px;" />
            <el-input v-model="v.description" size="small" placeholder="中文说明" style="flex:1;" />
            <el-button size="small" type="danger" :icon="Delete" circle @click="tplForm.variables.splice(i,1)" />
          </div>
          <el-button size="small" @click="tplForm.variables.push({name:'',description:''})">
            <el-icon><Plus /></el-icon> 添加变量
          </el-button>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editorVisible = false">取消</el-button>
        <el-button type="primary" @click="saveTemplate" :loading="savingTpl">保存模板</el-button>
      </template>
    </el-dialog>

    <!-- 预览弹窗 -->
    <el-dialog v-model="previewVisible" title="模板预览" width="700px" top="4vh">
      <div class="markdown-preview" v-html="renderedPreview"></div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Delete, Refresh, Plus, Download, EditPen } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listTemplates, saveTemplate as apiSaveTemplate, deleteTemplate as apiDeleteTemplate, getStandards, saveStandards as apiSaveStandards } from '../api'
import { SANDTABLE_TYPES } from '../constants'

const activeTab = ref('templates')

// ── 写作模板 ──
const templates = ref([])
const tplLoading = ref(false)
const tplFilter = ref('')
const editorVisible = ref(false)
const previewVisible = ref(false)
const editingTpl = ref(null)
const savingTpl = ref(false)
const tplForm = ref({ name: '', category: '企业介绍', description: '', content: '', variables: [] })

const filteredTemplates = computed(() => {
  if (!tplFilter.value) return templates.value
  return templates.value.filter(t => t.category.includes(tplFilter.value) || t.name.includes(tplFilter.value) || t.description.includes(tplFilter.value))
})

const renderedPreview = computed(() => {
  if (!editingTpl.value?.content) return ''
  return editingTpl.value.content
    .replace(/</g, '&lt;')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/#{([^}]+)}/g, '<mark>$1</mark>')
    .replace(/^(.+)$/gm, (line) => {
      if (line.startsWith('#')) return `<strong style="font-size:18px;">${line.replace(/^#+\s*/, '')}</strong>`
      if (line.startsWith('- ')) return `&bull; ${line.slice(2)}`
      return line
    })
})

async function loadTemplates() {
  tplLoading.value = true
  try {
    const res = await listTemplates()
    templates.value = res.data.templates || []
  } catch (e) {
    ElMessage.error('加载模板失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    tplLoading.value = false
  }
}

function openNewTemplate() {
  editingTpl.value = null
  tplForm.value = { name: '', category: '企业介绍', description: '', content: '', variables: [] }
  editorVisible.value = true
}

function editTemplate(tpl) {
  editingTpl.value = tpl
  tplForm.value = {
    name: tpl.name, category: tpl.category,
    description: tpl.description, content: tpl.content,
    variables: [...(tpl.variables || [])].map(v => typeof v === 'string' ? { name: v, description: '' } : { ...v }),
  }
  editorVisible.value = true
}

function previewTemplate(tpl) {
  editingTpl.value = tpl
  previewVisible.value = true
}

async function saveTemplate() {
  if (!tplForm.value.name.trim()) { ElMessage.warning('请输入模板名称'); return }
  savingTpl.value = true
  try {
    const payload = {
      id: editingTpl.value?.id || null,
      name: tplForm.value.name,
      category: tplForm.value.category,
      description: tplForm.value.description,
      content: tplForm.value.content,
      variables: tplForm.value.variables.filter(v => v.name.trim()),
    }
    await apiSaveTemplate(payload)
    editorVisible.value = false
    ElMessage.success('模板已保存')
    await loadTemplates()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    savingTpl.value = false
  }
}

async function deleteTemplate(id) {
  try {
    await ElMessageBox.confirm('确定删除此模板？', '确认删除', { type: 'warning' })
    await apiDeleteTemplate(id)
    ElMessage.success('已删除')
    await loadTemplates()
  } catch (e) {
    if (e !== 'cancel' && e?.response) {
      ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
    }
  }
}

// ── 审核标准 ──
const checklist = ref([
  { key: 'entity', label: '实体完整性', enabled: true, weight: 20, threshold: 60, description: '企业名、地域、产品名是否完整且位置突出' },
  { key: 'structure', label: '结构化程度', enabled: true, weight: 15, threshold: 50, description: '是否有清晰的H2/H3标题层级、合理段落长度和列表结构' },
  { key: 'quantified', label: '量化数据', enabled: true, weight: 25, threshold: 50, description: '数字+单位的量化表述密度，如"200+项目""1:1000精度"等' },
  { key: 'faq', label: 'FAQ友好度', enabled: true, weight: 15, threshold: 40, description: '是否包含自然问答对，适配对话式AI检索' },
  { key: 'source', label: '信源一致性', enabled: true, weight: 25, threshold: 70, description: '内容在五维信源数据中是否有依据，是否存在编造或夸大' },
])
const stdsLoading = ref(false)
const stdsSaving = ref(false)

const totalWeight = computed(() => {
  return checklist.value.filter(c => c.enabled).reduce((s, c) => s + c.weight, 0)
})

async function loadStandards() {
  stdsLoading.value = true
  try {
    const res = await getStandards()
    if (res.data.checklist?.length) checklist.value = res.data.checklist
  } catch (e) {
    ElMessage.error('加载审核标准失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    stdsLoading.value = false
  }
}

async function saveStandards() {
  if (totalWeight.value !== 100) {
    try { await ElMessageBox.confirm(`当前权重合计 ${totalWeight.value}%，非标准 100%。确定保存？`, '权重提示', { type: 'warning', confirmButtonText: '仍然保存' }) }
    catch { return }
  }
  stdsSaving.value = true
  try {
    await apiSaveStandards({ checklist: checklist.value })
    ElMessage.success('审核标准已保存')
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    stdsSaving.value = false
  }
}

function resetStandards() {
  checklist.value = [
    { key: 'entity', label: '实体完整性', enabled: true, weight: 20, threshold: 60, description: '企业名、地域、产品名是否完整且位置突出' },
    { key: 'structure', label: '结构化程度', enabled: true, weight: 15, threshold: 50, description: '是否有清晰的H2/H3标题层级、合理段落长度和列表结构' },
    { key: 'quantified', label: '量化数据', enabled: true, weight: 25, threshold: 50, description: '数字+单位的量化表述密度，如"200+项目""1:1000精度"等' },
    { key: 'faq', label: 'FAQ友好度', enabled: true, weight: 15, threshold: 40, description: '是否包含自然问答对，适配对话式AI检索' },
    { key: 'source', label: '信源一致性', enabled: true, weight: 25, threshold: 70, description: '内容在五维信源数据中是否有依据，是否存在编造或夸大' },
  ]
  ElMessage.success('已恢复默认标准')
}

// ── 导出 ──
const exportItems = ref(['templates', 'standards', 'guide'])
const exporting = ref(false)

async function doExport() {
  exporting.value = true
  try {
    let content = '# GEO内容规范文档\n\n> 生成时间：' + new Date().toLocaleDateString('zh-CN') + '\n\n'
    if (exportItems.value.includes('templates')) {
      content += '## 写作模板\n\n'
      templates.value.forEach(t => {
        content += `### ${t.name}（${t.category}）\n\n${t.description}\n\n\`\`\`markdown\n${t.content}\n\`\`\`\n\n`
      })
    }
    if (exportItems.value.includes('standards')) {
      content += '## 审核标准\n\n'
      checklist.value.filter(c => c.enabled).forEach(c => {
        content += `- **${c.label}**（权重 ${c.weight}%，阈值 ${c.threshold} 分）：${c.description}\n`
      })
    }
    if (exportItems.value.includes('guide')) {
      content += '\n## GEO 写作指南\n\n'
      content += '### AI 采信六原则\n\n'
      content += '1. **实体锚定** — 首次出现企业名、地域、产品名必须完整清晰\n'
      content += '2. **定义优先** — 专业概念给1-2句权威定义\n'
      content += '3. **量化事实** — 所有能力用具体数字支撑\n'
      content += '4. **FAQ结构** — 嵌入自然问答对提高对话检索命中率\n'
      content += '5. **层级结构化** — H2/H3标题 + 列表组织信息\n'
      content += '6. **信息增量** — 本地化细节 + 行业独特信息，区别于通用模板\n'
    }
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'GEO内容规范文档.md'; a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('规范文档已导出')
  } catch (e) {
    ElMessage.error('导出失败: ' + (e.message || ''))
  } finally {
    exporting.value = false
  }
}

function doQuickExport() {
  activeTab.value = 'guide'
}

onMounted(() => {
  loadTemplates()
  loadStandards()
})
</script>

<style scoped>
.templates-page { max-width: 1240px; }
.page-intro { margin-bottom: 20px; }
.page-intro h2 { font-size: 20px; color: #2D3142; margin-bottom: 6px; }
.intro-desc { font-size: 13px; color: #9B9EAA; display: flex; align-items: center; gap: 12px; }

/* 概览卡片 */
.overview-row { margin-bottom: 20px; }
.ov-card { background: #fff; border-radius: 10px; padding: 18px 20px; text-align: center; cursor: pointer; border: 1px solid #E8E5DF; transition: box-shadow 0.22s cubic-bezier(0.4,0,0.2,1); }
.ov-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.06); }
.ov-card.ov-action { background: #FAF8F5; border-style: dashed; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; }
.ov-num { font-size: 32px; font-weight: 700; }
.ov-num.blue { color: #C8963E; }
.ov-num.green { color: #5B8C5A; }
.ov-num.purple { color: #8065E6; }
.ov-num .el-icon { color: #6B6E7B; }
.ov-label { font-size: 12px; color: #9B9EAA; margin-top: 2px; }

.main-tabs { margin-top: 0; }
.tab-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
.tab-desc { font-size: 12px; color: #9B9EAA; flex: 1; }

/* 模板网格 */
.tpl-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.tpl-card { background: #fff; border: 1px solid #E8E5DF; border-radius: 10px; padding: 18px; cursor: pointer; transition: all 0.22s cubic-bezier(0.4,0,0.2,1); }
.tpl-card:hover { border-color: #C8963E; box-shadow: 0 4px 16px rgba(64,158,255,0.08); transform: translateY(-1px); }
.tpl-card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.tpl-card-name { font-size: 15px; font-weight: 600; color: #2D3142; }
.tpl-card-desc { font-size: 12px; color: #9B9EAA; line-height: 1.6; margin-bottom: 10px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.tpl-card-vars { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }
.tpl-card-actions { display: flex; gap: 4px; padding-top: 12px; border-top: 1px solid #F0EDE8; }

/* 审核标准网格 */
.stds-grid { display: flex; flex-direction: column; gap: 8px; }
.std-card { display: flex; align-items: center; gap: 16px; background: #fff; border: 1px solid #E8E5DF; border-radius: 10px; padding: 16px 20px; transition: opacity 0.22s cubic-bezier(0.4,0,0.2,1); }
.std-card.disabled { opacity: 0.45; }
.std-card-left { flex-shrink: 0; }
.std-card-body { flex: 1; min-width: 0; }
.std-card-title { font-size: 14px; font-weight: 600; color: #2D3142; margin-bottom: 4px; }
.std-card-desc { font-size: 12px; color: #9B9EAA; }
.std-card-right { display: flex; gap: 24px; flex-shrink: 0; }
.std-slider-group { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.std-slider-label { font-size: 11px; color: #9B9EAA; white-space: nowrap; }
.stds-summary { display: flex; align-items: center; margin-top: 16px; padding: 12px 16px; background: #FAF8F5; border-radius: 10px; font-size: 13px; color: #6B6E7B; }

/* 使用指引 */
.guide-section h3 { font-size: 16px; color: #2D3142; margin-bottom: 20px; }
.guide-flow { display: flex; align-items: flex-start; gap: 0; flex-wrap: wrap; }
.guide-step { display: flex; gap: 12px; flex: 1; min-width: 180px; }
.guide-step-num { width: 28px; height: 28px; border-radius: 50%; background: #C8963E; color: #fff; font-size: 13px; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.guide-step strong { font-size: 14px; color: #2D3142; }
.guide-step p { font-size: 12px; color: #9B9EAA; line-height: 1.6; margin: 4px 0 0; }
.guide-arrow { font-size: 20px; color: #9B9EAA; padding: 4px 8px; flex-shrink: 0; }

.guide-sidebar { background: #FAF8F5; border-radius: 10px; padding: 20px; }
.guide-sidebar h4 { font-size: 14px; color: #2D3142; margin-bottom: 12px; }
.principle-list { display: flex; flex-direction: column; gap: 8px; }
.principle-item { font-size: 12px; color: #6B6E7B; line-height: 1.6; display: flex; align-items: flex-start; gap: 6px; }
.principle-dot { width: 6px; height: 6px; border-radius: 50%; background: #C8963E; flex-shrink: 0; margin-top: 6px; }

/* 空状态 */
.empty-guide { text-align: center; padding: 60px 20px; color: #9B9EAA; }
.empty-guide .el-icon { color: #9B9EAA; margin-bottom: 12px; }
.empty-guide h3 { font-size: 16px; color: #6B6E7B; margin-bottom: 8px; }
.empty-guide p { font-size: 13px; margin-bottom: 16px; max-width: 400px; margin-left: auto; margin-right: auto; }

/* 编辑器 */
.var-row { display: flex; gap: 8px; margin-bottom: 6px; }
.markdown-preview { background: #FAF8F5; padding: 24px; border-radius: 10px; line-height: 1.9; font-size: 14px; color: #6B6E7B; }
.markdown-preview :deep(mark) { background: rgba(200,150,62,0.06); color: #C8963E; padding: 1px 4px; border-radius: 3px; font-weight: 500; }
</style>
