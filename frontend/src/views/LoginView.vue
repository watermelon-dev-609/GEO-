<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <span class="login-icon">🎯</span>
        <h2>GEO优化系统</h2>
        <p>武汉微艺达智能科技有限公司</p>
      </div>
      <el-form @submit.prevent="handleLogin">
        <el-form-item>
          <el-input v-model="password" type="password" show-password placeholder="请输入系统密码" size="large" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="large" @click="handleLogin" :loading="loading" style="width:100%">
            登录
          </el-button>
        </el-form-item>
      </el-form>
      <div v-if="error" class="login-error">{{ error }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authLogin } from '../api'

const router = useRouter()
const password = ref('')
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  if (!password.value) { error.value = '请输入密码'; return }
  loading.value = true
  error.value = ''
  try {
    const res = await authLogin({ password: password.value })
    if (res.data.token) {
      sessionStorage.setItem('auth_token', res.data.token)
      router.replace('/dashboard')
    }
  } catch (e) {
    error.value = e.response?.data?.detail || '登录失败'
  } finally { loading.value = false }
}
</script>

<style scoped>
.login-page {
  display: flex; align-items: center; justify-content: center;
  min-height: 100vh; background: linear-gradient(135deg, #1e2030 0%, #2d3045 100%);
}
.login-card {
  background: #fff; border-radius: 12px; padding: 40px; width: 400px;
  box-shadow: 0 20px 60px rgba(0,0,0,.3);
}
.login-header { text-align: center; margin-bottom: 32px; }
.login-icon { font-size: 48px; }
.login-header h2 { margin: 12px 0 4px; font-size: 22px; color: #303133; }
.login-header p { margin: 0; color: #909399; font-size: 13px; }
.login-error { color: #f56c6c; font-size: 13px; text-align: center; margin-top: 12px; }
</style>
