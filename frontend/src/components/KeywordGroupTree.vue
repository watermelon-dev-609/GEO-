<template>
  <div class="group-tree">
    <div class="group-header">
      <span>分组管理</span>
      <el-button size="small" text @click="showAddGroup = true">+ 新建</el-button>
    </div>
    <div v-if="groups.length === 0" class="empty-hint">暂无分组</div>
    <div v-for="g in groups" :key="g.name" class="group-node" :class="{ active: activeGroup === g.name }" @click="selectGroup(g.name)">
      <span class="group-color" :style="{ background: g.color || '#C8963E' }"></span>
      <span class="group-name">{{ g.name }}</span>
      <el-tag size="small">{{ g.count || 0 }}</el-tag>
    </div>

    <el-dialog v-model="showAddGroup" title="新建分组" width="400px">
      <el-form label-position="top">
        <el-form-item label="分组名称">
          <el-input v-model="newGroupName" placeholder="例如：核心品牌词" />
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="newGroupColor" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddGroup = false">取消</el-button>
        <el-button type="primary" @click="createGroup">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const props = defineProps({ sandtableType: { type: String, default: 'smart_traffic' } })
const emit = defineEmits(['select'])
const groups = ref([])
const activeGroup = ref('')
const showAddGroup = ref(false)
const newGroupName = ref('')
const newGroupColor = ref('#C8963E')

async function loadGroups() {
  try {
    const res = await api.get(`/keywords/${props.sandtableType}`)
    const data = res.data
    if (data?.groups) {
      groups.value = data.groups.map(g => ({
        name: g.name || g,
        color: g.color || '#C8963E',
        count: g.keyword_ids?.length || g.count || 0,
      }))
    }
  } catch (e) {
    if (e.response?.status !== 404) {
      console.warn('加载关键词分组失败:', e.message)
    }
  }
}

function selectGroup(name) {
  activeGroup.value = name
  emit('select', name)
}

async function createGroup() {
  if (!newGroupName.value.trim()) { ElMessage.warning('请输入分组名称'); return }
  try {
    await api.post(`/keywords/${props.sandtableType}/groups`, {
      name: newGroupName.value.trim(),
      color: newGroupColor.value,
    })
    ElMessage.success('分组已创建')
    showAddGroup.value = false
    newGroupName.value = ''
    loadGroups()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.response?.data?.detail || e.message))
  }
}

function refresh() { loadGroups() }
defineExpose({ loadGroups, refresh })
</script>

<style scoped>
.group-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; margin-bottom: 8px; }
.group-node { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 6px; cursor: pointer; transition: background .15s; }
.group-node:hover { background: #f5f7fa; }
.group-node.active { background: #ecf5ff; }
.group-color { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.group-name { flex: 1; font-size: 13px; color: #303133; }
.empty-hint { text-align: center; padding: 20px; color: #c0c4cc; font-size: 12px; }
</style>
