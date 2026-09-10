<template>
  <div class="login-page">
    <div class="login-panel">
      <section class="intro-panel">
        <el-tag type="success">A3 赛题演示系统</el-tag>
        <h1>AI 个性化学习助手</h1>
        <p>覆盖学生画像、AI 资源生成、学习路径规划、在线练习评估、智能辅导和课程知识库。</p>
        <el-row :gutter="12">
          <el-col :span="12" v-for="item in featureTags" :key="item">
            <el-alert :title="item" type="info" :closable="false" show-icon />
          </el-col>
        </el-row>
      </section>

      <section class="auth-panel">
        <h2>{{ authMode === 'login' ? '登录' : '注册' }}</h2>
        <el-form label-position="top" @submit.prevent>
          <el-form-item label="用户名">
            <el-input v-model="authForm.username" :prefix-icon="User" placeholder="student" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input v-model="authForm.password" :prefix-icon="Lock" type="password" show-password />
          </el-form-item>
          <el-button type="primary" :loading="loading" style="width: 100%" @click="submitAuth">
            {{ authMode === 'login' ? '登录' : '注册并进入' }}
          </el-button>
          <el-button link style="width: 100%; margin: 12px 0 0" @click="authMode = authMode === 'login' ? 'register' : 'login'">
            {{ authMode === 'login' ? '没有账号，去注册' : '已有账号，去登录' }}
          </el-button>
        </el-form>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'
import { useSessionStore } from '../stores/session'
const loading = ref(false)

const emit = defineEmits<{
  (e: 'login-success'): void
}>()

const session = useSessionStore()
const authMode = ref<'login' | 'register'>('login')
const featureTags = ['对话式画像', '知识学习', '学习路径', 'RAG 问答', '后端护栏', '学习闭环']

const authForm = reactive({ username: 'student', password: '123' })

async function submitAuth() {
  if (!authForm.username || !authForm.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    if (authMode.value === 'login') {
      await session.login(authForm.username, authForm.password)
    } else {
      await session.register(authForm.username, authForm.password)
    }
    emit('login-success')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}
</script>
