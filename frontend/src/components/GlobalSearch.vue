<template>
  <Teleport to="body">
    <Transition name="search-fade">
      <div v-if="visible" class="search-overlay" @click.self="close">
        <div class="search-dialog">
          <div class="search-input-wrap">
            <el-icon class="search-icon"><Search /></el-icon>
            <input ref="inputRef" v-model="query" class="search-input" placeholder="搜索页面、功能..." @keydown="handleKeydown" @input="filterResults" />
            <kbd class="search-kbd">ESC</kbd>
          </div>
          <div class="search-results" v-if="query && filtered.length > 0">
            <div v-for="(item, i) in filtered" :key="item.path" class="search-result-item" :class="{ active: selectedIndex === i }" @click="navigate(item)" @mouseenter="selectedIndex = i">
              <el-icon class="result-icon"><component :is="item.icon" /></el-icon>
              <div class="result-info">
                <div class="result-title">{{ item.title }}</div>
                <div class="result-desc">{{ item.desc }}</div>
              </div>
              <kbd class="result-shortcut">↵</kbd>
            </div>
          </div>
          <div class="search-empty" v-else-if="query">
            未找到匹配结果
          </div>
          <div class="search-hint" v-else>
            <div v-for="item in quickLinks" :key="item.path" class="search-result-item" @click="navigate(item)">
              <el-icon class="result-icon"><component :is="item.icon" /></el-icon>
              <div class="result-info">
                <div class="result-title">{{ item.title }}</div>
                <div class="result-shortcut-text">{{ item.desc }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'

const router = useRouter()
const visible = ref(false)
const query = ref('')
const selectedIndex = ref(0)
const inputRef = ref(null)

const searchItems = [
  { title: '工作台', desc: '数据看板与快速操作', path: '/dashboard', icon: 'HomeFilled' },
  { title: '文案导入', desc: '文本粘贴、文件上传、快速诊断', path: '/import', icon: 'DocumentAdd' },
  { title: 'GEO优化工坊', desc: '多平台文案优化', path: '/workshop', icon: 'EditPen' },
  { title: 'AI评测中心', desc: '7维评测与历史管理', path: '/evaluation', icon: 'DataAnalysis' },
  { title: '成果导出', desc: '导出文案、报告、JSON-LD', path: '/export', icon: 'Download' },
  { title: '策略中心', desc: '平台监测、竞品调研、关键词库', path: '/strategy', icon: 'TrendCharts' },
  { title: '内容规范', desc: '写作模板、审核标准', path: '/templates', icon: 'Document' },
  { title: 'AI收录监测', desc: '品牌在AI平台上的收录检测', path: '/brand-monitor', icon: 'Monitor' },
  { title: '批量处理', desc: '多篇文案批量清洗/优化/评测', path: '/batch', icon: 'FolderOpened' },
  { title: '定时任务', desc: '自动化监测与报告生成', path: '/scheduler', icon: 'Timer' },
  { title: '系统日志', desc: '查看和下载系统运行日志', path: '/logs', icon: 'Setting' },
  { title: '审计日志', desc: 'API请求操作审计', path: '/audit', icon: 'Clock' },
  { title: '配置API Key', desc: '管理各平台LLM配置', path: '', icon: 'Key' },
]

const filtered = computed(() =>
  query.value
    ? searchItems.filter(item =>
        item.title.includes(query.value) || item.desc.includes(query.value)
      )
    : []
)

const quickLinks = computed(() => searchItems.slice(0, 8))

function open() {
  visible.value = true
  query.value = ''
  selectedIndex.value = 0
  setTimeout(() => inputRef.value?.focus(), 50)
}

function close() {
  visible.value = false
}

function navigate(item) {
  close()
  if (item.path) router.push(item.path)
}

function handleKeydown(e) {
  const results = filtered.value.length > 0 ? filtered.value : []
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    selectedIndex.value = Math.min(selectedIndex.value + 1, Math.max(0, results.length - 1))
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    selectedIndex.value = Math.max(0, selectedIndex.value - 1)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    if (results[selectedIndex.value]) navigate(results[selectedIndex.value])
  } else if (e.key === 'Escape') {
    close()
  }
}

function filterResults() {
  selectedIndex.value = 0
}

function onGlobalKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault()
    open()
  }
}

onMounted(() => window.addEventListener('keydown', onGlobalKeydown))
onUnmounted(() => window.removeEventListener('keydown', onGlobalKeydown))

defineExpose({ open, close })
</script>

<style scoped>
.search-overlay {
  position: fixed; inset: 0; z-index: 3000;
  background: rgba(0,0,0,.4); display: flex; justify-content: center; padding-top: 15vh;
}
.search-dialog {
  width: 520px; max-height: 420px; background: #fff; border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0,0,0,.25); overflow: hidden;
}
.search-input-wrap {
  display: flex; align-items: center; padding: 14px 16px; border-bottom: 1px solid #ebeef5;
}
.search-icon { color: #909399; font-size: 18px; margin-right: 8px; }
.search-input {
  flex: 1; border: none; outline: none; font-size: 15px; color: #303133; background: transparent;
}
.search-input::placeholder { color: #c0c4cc; }
.search-kbd {
  font-size: 11px; color: #909399; background: #f4f4f5; padding: 2px 6px; border-radius: 3px;
  font-family: monospace;
}
.search-results, .search-hint { max-height: 320px; overflow-y: auto; padding: 8px; }
.search-result-item {
  display: flex; align-items: center; padding: 8px 10px; border-radius: 6px; cursor: pointer;
  transition: background .15s;
}
.search-result-item:hover, .search-result-item.active { background: #f0f2f5; }
.result-icon { font-size: 18px; color: #909399; margin-right: 10px; }
.result-info { flex: 1; }
.result-title { font-size: 13px; color: #303133; font-weight: 500; }
.result-desc, .result-shortcut-text { font-size: 11px; color: #909399; margin-top: 2px; }
.result-shortcut { font-size: 10px; color: #c0c4cc; }
.search-empty { text-align: center; padding: 32px; color: #909399; font-size: 13px; }
.search-fade-enter-active, .search-fade-leave-active { transition: opacity .2s; }
.search-fade-enter-from, .search-fade-leave-to { opacity: 0; }
</style>
