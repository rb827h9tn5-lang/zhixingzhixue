<template>
  <div v-if="!session.token" class="login-page">
    <div class="login-panel">
      <section class="intro-panel">
        <div class="intro-badge">
          <span class="badge-dot"></span>
          <span>大模型教育智能体</span>
        </div>
        <h1>
          <span class="gradient-text">知行智学</span>
          <span class="gradient-text">AI 个性化学习助手</span>
        </h1>
        <p class="intro-desc">
          以学生画像和课程知识库为基础，辅助生成学习资源、规划学习路径，并通过测评提供个性化反馈。
        </p>
        <div class="intro-features">
          <div class="intro-feature" v-for="item in features" :key="item.title">
            <div class="feature-icon" :style="{ background: item.bg, color: item.color }">
              <component :is="item.icon" />
            </div>
            <div class="feature-text">
              <strong>{{ item.title }}</strong>
              <span>{{ item.desc }}</span>
            </div>
          </div>
        </div>
        <div class="intro-footer">
          <span class="status-dot online"></span>
          <span>AI 学习辅导</span>
        </div>
      </section>

      <section class="auth-panel">
        <div class="auth-avatar">
          <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>
        </div>
        <h2>{{ authMode === 'login' ? '欢迎回来' : '创建账号' }}</h2>
        <p class="auth-subtitle">{{ authMode === 'login' ? '登录后继续你的个性化学习旅程' : '注册后即可开始个性化学习之旅' }}</p>
        <el-form label-position="top" @submit.prevent>
          <el-form-item label="用户名">
            <el-input v-model="authForm.username" :prefix-icon="User" placeholder="请输入用户名" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input v-model="authForm.password" :prefix-icon="Lock" type="password" show-password placeholder="请输入密码" />
          </el-form-item>
          <el-button type="primary" :loading="loading" style="width: 100%" @click="submitAuth" class="auth-submit-btn">
            {{ authMode === 'login' ? '登录学习工作台' : '注册并进入' }}
          </el-button>
          <div v-if="authMode === 'login'" class="demo-hint">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
            <span>演示账号：student / 123</span>
          </div>
          <el-button link style="width: 100%; margin: 8px 0 0" @click="switchAuthMode">
            {{ authMode === 'login' ? '没有账号？创建登录账号' : '已有账号，去登录' }}
          </el-button>
        </el-form>
      </section>
    </div>
  </div>

  <div v-else class="app-shell">
    <div class="layout">
      <!-- 移动端侧栏遮罩 -->
      <div v-if="isMobile && isMobileSidebarOpen" class="mobile-sidebar-mask" @click="closeMobileSidebar"></div>
      <aside
        class="sidebar"
        :class="{ collapsed: sidebarCollapsed, expanded: sidebarExpanded, frozen: sidebarFrozen, 'mobile-open': isMobileSidebarOpen }"
        @mouseenter="onSidebarEnter"
        @mouseleave="onSidebarLeave"
      >
                <div class="sidebar-inner">
          <!-- 品牌区 -->
          <div class="sidebar-brand">
            <div class="sidebar-logo">
              <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 1 4 4v1a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M4 15c0-2 2-4 8-4s8 2 8 4v1c0 2-2 4-8 4s-8-2-8-4v-1z"/><path d="M4 19c0 2 2 4 8 4s8-2 8-4"/></svg>
            </div>
            <div class="sidebar-brand-text">
              <strong>知行智学</strong>
              <span>功能导航</span>
            </div>
          </div>

          <div class="sidebar-menu-scroll">
            <el-menu :default-active="menuActiveIndex" @select="onMenuSelect" :collapse="false" :collapse-transition="false" :openeds="openedSubMenus" @open="(idx: string) => { if (!openedSubMenus.includes(idx)) openedSubMenus = [...openedSubMenus, idx] }" @close="(idx: string) => { openedSubMenus = openedSubMenus.filter((i: string) => i !== idx) }">

              <!-- 学习总览 -->
              <div class="menu-group-title">学习总览</div>
              <el-menu-item index="dashboard" title="总览"><el-icon><DataAnalysis /></el-icon><span>总览</span></el-menu-item>
              <el-menu-item index="profile" title="个人画像"><el-icon><UserFilled /></el-icon><span>个人画像</span></el-menu-item>
              <el-menu-item index="quiz" title="测评评估"><el-icon><EditPen /></el-icon><span>测评评估</span></el-menu-item>
              <el-menu-item index="path" title="学习路径"><el-icon><Guide /></el-icon><span>学习路径</span></el-menu-item>

              <!-- 学习决策 -->
              <div class="menu-group-title">学习决策</div>
              <el-menu-item index="diagnosis" title="学习诊断"><el-icon><DataAnalysis /></el-icon><span>学习诊断</span></el-menu-item>
              <el-menu-item index="remediation" title="补救计划"><el-icon><Guide /></el-icon><span>补救计划</span></el-menu-item>
              <el-menu-item index="adaptive-exam" title="自适应测评"><el-icon><EditPen /></el-icon><span>自适应测评</span></el-menu-item>
              <el-menu-item index="growth" title="成长报告"><el-icon><Reading /></el-icon><span>成长报告</span></el-menu-item>

              <!-- 知识学习 -->
              <div class="menu-group-title">知识学习</div>
              <el-sub-menu index="resources" title="知识学习">
                <template #title>
                  <el-icon><Collection /></el-icon><span>知识学习</span>
                </template>
                <div class="submenu-container">
                  <el-menu-item index="resources_course_document" title="讲解文档"><el-icon><Reading /></el-icon><span>讲解文档</span></el-menu-item>
                  <el-menu-item index="resources_mind_map" title="思维导图"><el-icon><Share /></el-icon><span>思维导图</span></el-menu-item>
                  <el-menu-item index="resources_exercise_bank" title="练习题库"><el-icon><EditPen /></el-icon><span>练习题库</span></el-menu-item>
                  <el-menu-item index="resources_extension_reading" title="拓展阅读"><el-icon><List /></el-icon><span>拓展阅读</span></el-menu-item>
                  <el-menu-item index="resources_coding_case" title="实操案例"><el-icon><Monitor /></el-icon><span>实操案例</span></el-menu-item>
                  <el-menu-item index="resources_multimedia_video" title="教学视频"><el-icon><Film /></el-icon><span>教学视频</span></el-menu-item>
                  <el-menu-item index="resources_ppt_deck" title="PPT生成"><el-icon><Reading /></el-icon><span>PPT生成</span></el-menu-item>
                </div>
              </el-sub-menu>

              <!-- 学习服务 -->
              <div class="menu-group-title">学习服务</div>
              <el-menu-item index="tutor" title="智能辅导"><el-icon><ChatDotRound /></el-icon><span>智能辅导</span></el-menu-item>
              <el-menu-item index="coding" title="在线编程"><el-icon><Monitor /></el-icon><span>在线编程</span></el-menu-item>

              <!-- 知识底座 -->
              <div class="menu-group-title">知识底座</div>
              <el-menu-item index="knowledge" title="知识库管理"><el-icon><Files /></el-icon><span>知识库管理</span></el-menu-item>
            </el-menu>
          </div>

          <!-- 底部状态卡片 -->
          <div class="sidebar-footer-status">
            <div class="status-card">
              <span class="status-dot online"></span>
              <span>Multi-Agent 学习辅导</span>
            </div>
          </div>
        </div>
        <div v-show="sidebarCollapsed && !sidebarExpanded" class="sidebar-collapsed-hint">功能菜单</div>
      </aside>

      <!-- 主内容区 -->
      <div class="main-layout">
        <!-- 顶部 Header 行 -->
        <div class="top-header">
          <div class="header-left">
            <button class="collapse-btn" @click="toggleSidebarCollapsed" :title="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>
            <button class="mobile-menu-btn" @click="toggleMobileSidebar" :title="isMobileSidebarOpen ? '关闭菜单' : '打开菜单'">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>
            <span class="system-title">{{ systemTitle }}</span>
            <div class="breadcrumb-inline">
              <template v-for="(item, idx) in breadcrumbItems" :key="idx">
                <span v-if="idx > 0" class="breadcrumb-sep">/</span>
                <span :class="['breadcrumb-item', { 'breadcrumb-current': idx === breadcrumbItems.length - 1 }]">{{ item.label }}</span>
              </template>
            </div>
          </div>
          <div class="header-right">
            <ThemeSwitcher />
            <el-tag>{{ session.user?.username || 'student' }}</el-tag>
            <el-button :icon="SwitchButton" @click="session.logout()">退出</el-button>
          </div>
        </div>

        <!-- 页面 Tabs 标签行 -->
        <div v-if="!isMobile" class="tab-bar">
          <div
            v-for="tab in tabsStore.openedTabs"
            :key="tab.key"
            :class="['tab-item', { active: tabsStore.activeTabKey === tab.key }]"
            @click="onTabClick(tab.key)"
          >
            <span>{{ tab.title }}</span>
            <span v-if="!tab.affix" class="tab-close" @click.stop="tabsStore.removeTab(tab.key)">&times;</span>
          </div>
        </div>

        <!-- 页面内容 -->
        <main class="page-content">
          <section v-if="activeMenu === 'dashboard'">
            <DashboardView ref="dashboardRef" @refresh="refreshAll" />
          </section>

          <section v-if="activeMenu === 'profile'">
            <ProfileView />
          </section>

          <section v-if="activeMenu === 'path'">
            <PathView />
          </section>

          <section v-if="activeMenu === 'resources'">
            <ResourcesView :resource-type="resourceSubType" />
          </section>

          <section v-if="activeMenu === 'quiz'">
            <QuizView />
          </section>

          <section v-if="activeMenu === 'diagnosis'">
            <DiagnosisView />
          </section>

          <section v-if="activeMenu === 'remediation'">
            <RemediationView />
          </section>

          <section v-if="activeMenu === 'adaptive-exam'">
            <AdaptiveExamView />
          </section>

          <section v-if="activeMenu === 'growth'">
            <GrowthView />
          </section>

          <section v-if="activeMenu === 'tutor'">
            <TutorView />
          </section>

          <section v-if="activeMenu === 'coding'">
            <OnlineCodeView />
          </section>

          <section v-if="activeMenu === 'knowledge'">
            <KnowledgeView />
          </section>
        </main>
      </div>
    </div>
  </div>

  <!-- 全局语音助手：放在登录后主界面顶层，切换页面不会卸载 -->
  <VoiceAssistant v-if="session.token" />

  <!-- Mobile bottom tab bar -->
  <nav v-if="session.token && isMobile" class="mobile-bottom-bar">
    <button
      v-for="tab in mobileTabs"
      :key="tab.key"
      class="bottom-tab"
      :class="{ active: tab.key === 'more' ? false : activeMenu === tab.key }"
      @click="onMobileTabClick(tab.key)"
    >
      <el-icon :size="20"><component :is="tab.icon" /></el-icon>
      <span>{{ tab.label }}</span>
    </button>
  </nav>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ChatDotRound, Collection, DataAnalysis, EditPen, Files, Guide,
  Lock, SwitchButton, User, UserFilled,
  Refresh, Reading, Share, List, Monitor, Film,
  Menu as IconMenu
} from '@element-plus/icons-vue'
import { useSessionStore } from './stores/session'
import { useTabsStore, getTabTitle } from './stores/tabs'
import { handleAuthExpired, notifyTabSwitch } from './composables/useUtils'
import VoiceAssistant from './components/VoiceAssistant.vue'
import ThemeSwitcher from './components/ThemeSwitcher.vue'

import DashboardView from './views/DashboardView.vue'
import ProfileView from './views/ProfileView.vue'
import PathView from './views/PathView.vue'
import ResourcesView from './views/ResourcesView.vue'
import QuizView from './views/QuizView.vue'
import TutorView from './views/TutorView.vue'
import OnlineCodeView from './views/OnlineCodeView.vue'
import KnowledgeView from './views/KnowledgeView.vue'
import DiagnosisView from './views/DiagnosisView.vue'
import RemediationView from './views/RemediationView.vue'
import AdaptiveExamView from './views/AdaptiveExamView.vue'
import GrowthView from './views/GrowthView.vue'

const session = useSessionStore()
const tabsStore = useTabsStore()
const activeMenu = ref('dashboard')
const resourceSubType = ref('course_document')
const sidebarCollapsed = ref(false)
const sidebarExpanded = ref(false)
const sidebarFrozen = ref(false)
const isMobileSidebarOpen = ref(false)
const openedSubMenus = ref<string[]>([])
let sidebarTimer: ReturnType<typeof setTimeout> | null = null
const authMode = ref<'login' | 'register'>('login')
const loading = ref(false)

// 面包屑数据
const breadcrumbItems = computed(() => {
  const menu = activeMenu.value
  const breadcrumbMap: Record<string, string[]> = {
    dashboard: ['首页', '总览'],
    profile: ['首页', '个人画像'],
    quiz: ['首页', '测评评估'],
    path: ['首页', '学习路径'],
    diagnosis: ['学习决策', '学习诊断'],
    remediation: ['学习决策', '补救计划'],
    'adaptive-exam': ['学习决策', '自适应测评'],
    growth: ['学习决策', '成长报告'],
    tutor: ['学习服务', '智能辅导'],
    coding: ['学习服务', '在线编程'],
    knowledge: ['系统管理', '知识库管理'],
  }
  if (menu === 'resources') {
    const subMap: Record<string, string[]> = {
      course_document: ['学习资源', '讲解文档'],
      mind_map: ['学习资源', '思维导图'],
      exercise_bank: ['学习资源', '练习题库'],
      extension_reading: ['学习资源', '拓展阅读'],
      coding_case: ['学习资源', '实操案例'],
      multimedia_video: ['学习资源', '教学视频'],
      ppt_deck: ['学习资源', 'PPT生成'],
    }
    return (subMap[resourceSubType.value] || ['学习资源', '讲解文档']).map(label => ({ label }))
  }
  return (breadcrumbMap[menu] || ['首页']).map(label => ({ label }))
})

// 系统标题
const systemTitle = computed(() => {
  const menu = activeMenu.value
  if (['dashboard', 'profile', 'path', 'quiz'].includes(menu)) return '学习总览'
  if (['diagnosis', 'remediation', 'adaptive-exam', 'growth'].includes(menu)) return '学习决策中心'
  if (menu === 'resources') return '知识学习'
  if (['tutor', 'coding'].includes(menu)) return '学习中心'
  if (menu === 'knowledge') return '知识底座'
  return '知行智学-学习平台'
})

const isMobile = ref(window.innerWidth < 900)

// 移动端底部导航标签
const mobileTabs = [
  { key: 'dashboard', label: '总览', icon: DataAnalysis },
  { key: 'quiz', label: '测评', icon: EditPen },
  { key: 'path', label: '路径', icon: Guide },
  { key: 'tutor', label: '辅导', icon: ChatDotRound },
  { key: 'knowledge', label: '知识库', icon: Files },
  { key: 'more', label: '更多', icon: IconMenu },
]

function onMobileTabClick(key: string) {
  if (key === 'more') {
    toggleMobileSidebar()
    return
  }
  onMenuSelect(key)
}

function onResize() {
  isMobile.value = window.innerWidth < 900
  if (isMobile.value && !sidebarCollapsed.value) {
    sidebarCollapsed.value = true
  }
  if (!isMobile.value) {
    closeMobileSidebar()
  }
}

function onSidebarEnter() {
  if (isMobile.value) return
  if (sidebarTimer) { clearTimeout(sidebarTimer); sidebarTimer = null }
  if (!sidebarFrozen.value) sidebarExpanded.value = true
}

function onSidebarLeave() {
  if (isMobile.value) return
  if (sidebarFrozen.value) return
  sidebarTimer = setTimeout(() => {
    sidebarExpanded.value = false
  }, 150)
}

function toggleSidebarFrozen() {
  sidebarFrozen.value = !sidebarFrozen.value
  if (!sidebarFrozen.value) {
    sidebarExpanded.value = false
  }
}

function toggleSidebarCollapsed() {
  sidebarCollapsed.value = !sidebarCollapsed.value
  if (!sidebarCollapsed.value && sidebarFrozen.value) {
    sidebarFrozen.value = false
    sidebarExpanded.value = false
  }
  if (isMobile.value && !sidebarCollapsed.value) {
    sidebarExpanded.value = true
  }
}

function toggleMobileSidebar() {
  isMobileSidebarOpen.value = !isMobileSidebarOpen.value
  // 打开时自动展开 resources 子菜单
  if (isMobileSidebarOpen.value && !openedSubMenus.value.includes('resources')) {
    openedSubMenus.value = ['resources', ...openedSubMenus.value]
  }
}

function closeMobileSidebar() {
  isMobileSidebarOpen.value = false
}

watch(sidebarExpanded, (expanded) => {
  if (!expanded && activeMenu.value !== 'resources') {
    openedSubMenus.value = []
  }
})

watch(activeMenu, (menu) => {
  if (menu === 'resources') {
    if (!openedSubMenus.value.includes('resources')) {
      openedSubMenus.value = ['resources', ...openedSubMenus.value]
    }
  }
  notifyTabSwitch()
})

// 移动端抽屉打开时禁止 body 滚动穿透
watch(isMobileSidebarOpen, (open) => {
  if (isMobile.value) {
    document.body.style.overflow = open ? 'hidden' : ''
  }
})

const menuActiveIndex = computed(() => {
  if (activeMenu.value === 'resources') return `resources_${resourceSubType.value}`
  return activeMenu.value
})

const authForm = reactive({ username: 'student', password: '123' })
const features = [
  { title: '对话画像', desc: '自然语言构建动态学生画像', icon: User, bg: 'var(--primary-50)', color: 'var(--primary-600)' },
  { title: '资源生成', desc: '讲义、题库、导图与案例一键生成', icon: EditPen, bg: 'var(--primary-50)', color: 'var(--primary-600)' },
  { title: '路径规划', desc: '结合测评结果动态调整学习路线', icon: Guide, bg: 'var(--primary-50)', color: 'var(--primary-600)' },
  { title: '知识库问答', desc: '优先参考已上传的课程资料', icon: Files, bg: 'var(--primary-50)', color: 'var(--primary-600)' },
  { title: '内容检查', desc: '提供基础安全与结构检查', icon: DataAnalysis, bg: 'var(--primary-50)', color: 'var(--primary-600)' },
  { title: '学习反馈', desc: '根据测评结果给出复习建议', icon: Refresh, bg: 'var(--primary-50)', color: 'var(--primary-600)' },
]

const dashboardRef = ref<any>(null)

function switchAuthMode() {
  authMode.value = authMode.value === 'login' ? 'register' : 'login'
}

function onTabClick(key: string) {
  tabsStore.setActiveTab(key)
  if (key.startsWith('resources_')) {
    activeMenu.value = 'resources'
    resourceSubType.value = key.replace('resources_', '') as any
  } else {
    activeMenu.value = key
  }
}

function onMenuSelect(index: string) {
  if (index.startsWith('resources_')) {
    activeMenu.value = 'resources'
    resourceSubType.value = index.replace('resources_', '') as any
  } else {
    activeMenu.value = index
  }
  // 打开新页面时自动新增标签
  tabsStore.addTab(index, getTabTitle(index), index === 'dashboard')
  // 移动端点击菜单后自动关闭抽屉
  if (isMobile.value) {
    closeMobileSidebar()
  }
}

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
    // 登录成功后清除今日任务缓存，确保仪表盘加载最新推荐
    localStorage.removeItem('study_recommended_tasks')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function refreshAll() {
  dashboardRef.value?.loadDashboard()
}

function onNavigateTo(e: Event) {
  const detail = (e as CustomEvent).detail
  if (detail) {
    let key: string
    if (typeof detail === 'string' && detail.startsWith('resources_')) {
      activeMenu.value = 'resources'
      resourceSubType.value = detail.replace('resources_', '') as any
      key = detail
    } else {
      activeMenu.value = detail
      key = detail
    }
    tabsStore.addTab(key, getTabTitle(key), key === 'dashboard')
  }
}

onMounted(() => {
  tabsStore.restoreTabs()
  // 恢复到上次激活的标签
  const activeKey = tabsStore.activeTabKey
  if (activeKey !== 'dashboard') {
    if (activeKey.startsWith('resources_')) {
      activeMenu.value = 'resources'
      resourceSubType.value = activeKey.replace('resources_', '') as any
    } else {
      activeMenu.value = activeKey
    }
  }
  window.addEventListener('auth-expired', handleAuthExpired)
  window.addEventListener('navigate-to', onNavigateTo)
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  window.removeEventListener('auth-expired', handleAuthExpired)
  window.removeEventListener('navigate-to', onNavigateTo)
  window.removeEventListener('resize', onResize)
  document.body.style.overflow = ''
})
</script>
