<template>
  <section class="dashboard-page">
    <!-- Hero Banner -->
    <div class="dashboard-hero">
      <div class="hero-bg-accent"></div>
      <div class="hero-content">
        <div class="hero-text">
          <h1 class="hero-title">你好，欢迎来到知行智学-学习工作台</h1>
          <p class="hero-desc">基于大模型和课程知识库，为你生成学习资源与个性化学习路径</p>
          <div class="hero-actions">
            <el-button type="primary" size="large" :icon="EditPen" @click="goToProfile">编辑个人画像</el-button>
            <el-button size="large" plain :icon="DataAnalysis" @click="goToQuiz">开始测评评估</el-button>
          </div>
        </div>
        <div class="hero-visual">
          <div class="hero-agent-flow">
            <div class="hero-agent-node" v-for="module in learningModules" :key="module.name">
              <div class="hero-agent-icon" :style="{ background: module.color }">
                <component :is="module.icon" />
              </div>
              <span class="hero-agent-name">{{ module.name }}</span>
              <!-- <span v-if="i < heroAgents.length - 1" class="hero-agent-arrow">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
              </span> -->
            </div>
          </div>
        </div>
      </div>
    </div>

    <section class="learning-decision-band">
      <div class="decision-copy">
        <span class="decision-eyebrow">下一步学习决策</span>
        <h2>{{ learningDecision.recommended_target?.name || '先完成一次诊断测评' }}</h2>
        <p>{{ learningDecision.summary || '正在读取你的掌握度、答题证据和当前学习路径。' }}</p>
        <div class="decision-meta">
          <span>诊断覆盖 {{ Math.round((learningDecision.mastery_overview?.coverage || 0) * 100) }}%</span>
          <span>重点补强 {{ learningDecision.mastery_overview?.focus_count || 0 }} 项</span>
          <span>路径版本 {{ learningDecision.path_version ? `v${learningDecision.path_version}` : '尚未生成' }}</span>
          <span v-if="learningDecision.current_strategy">
            当前策略 {{ learningDecision.current_strategy.strategy_label }}
          </span>
        </div>
      </div>
      <div class="decision-actions">
        <el-button type="primary" @click="goToRoute('diagnosis')">查看诊断依据</el-button>
        <el-button @click="goToRoute('remediation')">开始补救</el-button>
        <el-button @click="goToRoute('adaptive-exam')">自适应测评</el-button>
      </div>
    </section>

    <el-alert
      v-if="learningDecision.current_intervention"
      class="dashboard-intervention"
      :title="`学习阻塞已触发主动干预：${learningDecision.current_intervention.knowledge_point}`"
      :description="`正在执行 ${learningDecision.current_intervention.strategy_type}，已加入路径版本 v${learningDecision.current_intervention.path_version_number || '--'}。`"
      type="warning"
      :closable="false"
      show-icon
    />

    <!-- Quick Actions -->
    <div class="quick-actions">
      <div class="quick-action-card" v-for="action in quickActions" :key="action.label" @click="action.handler">
        <div class="quick-action-icon" :style="{ background: action.bg, color: action.color }">
          <component :is="action.icon" />
        </div>
        <span class="quick-action-label">{{ action.label }}</span>
      </div>
    </div>

    <!-- Student Profile Summary + Metrics -->
    <div class="dashboard-grid">
      <div class="dashboard-col">
        <!-- Metric Cards -->
        <div class="metric-grid">
          <div class="metric-card metric-level">
            <div class="metric-accent"></div>
            <div class="metric-inner">
              <div class="metric-icon-wrap">
                <el-icon :size="20"><Reading /></el-icon>
              </div>
              <div class="metric-body">
                <span class="metric-label">当前水平</span>
                <strong class="metric-value">{{ formatKnowledgeLevel(dashboard.metrics.knowledge_level) }}</strong>
              </div>
            </div>
          </div>
          <div class="metric-card metric-quiz">
            <div class="metric-accent"></div>
            <div class="metric-inner">
              <div class="metric-icon-wrap">
                <el-icon :size="20"><EditPen /></el-icon>
              </div>
              <div class="metric-body">
                <span class="metric-label">测评次数</span>
                <strong class="metric-value">{{ dashboard.metrics.quiz_count }}</strong>
              </div>
            </div>
          </div>
          <div class="metric-card metric-score">
            <div class="metric-accent"></div>
            <div class="metric-inner">
              <div class="metric-icon-wrap">
                <el-icon :size="20"><TrophyBase /></el-icon>
              </div>
              <div class="metric-body">
                <span class="metric-label">最近得分</span>
                <strong class="metric-value">{{ dashboard.metrics.latest_score }}</strong>
              </div>
            </div>
          </div>
        </div>

        <!-- Chart Section -->
        <div class="module chart-module">
          <div class="chart-toolbar">
            <div class="chart-toolbar-left">
              <h3 class="chart-title">成绩趋势</h3>
              <span class="chart-subtitle">历次测评成绩变化曲线</span>
            </div>
            <el-button type="primary" :icon="Refresh" :loading="loading" @click="refreshAll">刷新数据</el-button>
          </div>
          <div v-if="dashboard.scores.length > 0" ref="chartRef" class="chart-box"></div>
          <div v-else class="chart-empty">
            <el-empty description="暂无测评数据" :image-size="60" />
          </div>
        </div>

        <!-- Student Profile Summary -->
        <!-- <div class="module profile-summary">
          <div class="module-header">
            <el-icon :size="18"><UserFilled /></el-icon>
            <span>学生画像摘要</span>
          </div>
          <div class="profile-content">
            <div class="profile-row" v-for="item in profileSummary" :key="item.label">
              <span class="profile-label">{{ item.label }}</span>
              <span class="profile-value">{{ item.value }}</span>
            </div>
            <div class="profile-weak-row">
              <span class="profile-label">薄弱知识点</span>
              <div v-if="weakPoints.length" class="profile-tags">
                <el-tag v-for="tag in weakPoints" :key="tag" size="small" type="danger" effect="plain" round>{{ tag }}</el-tag>
              </div>
              <span v-else class="profile-value">暂无数据</span>
            </div>
          </div>
        </div> -->



      </div>

      <div class="dashboard-col">


        <!-- Today's Recommended Tasks -->
        <div class="module tasks-module">
          <div class="module-header">
            <el-icon :size="18"><List /></el-icon>
            <span>今日推荐任务（完成后自动勾选）</span>
            <el-button size="small" :icon="Refresh" circle @click="refreshTasks" :loading="taskLoading" style="margin-left:auto" />
          </div>
          <div class="task-list">
            <div class="task-item" v-for="task in recommendedTasks" :key="task.id" @click="clickTask(task)" :class="{ 'task-done': task.done }">
              <div class="task-check">
                <svg v-if="task.done" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M8 12l2.5 2.5L16 9.5"/></svg>
                <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#cbd5e1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/></svg>
              </div>
              <div class="task-body">
                <strong>{{ task.label }}</strong>
                <span>{{ task.desc }}</span>
              </div>
              <el-tag size="small" :type="typeTagMap[task.type]?.tagType || 'info'" effect="plain" round>{{ typeTagMap[task.type]?.tag || task.type }}</el-tag>
            </div>
          </div>
        </div>
      </div>
    </div><!--/dashboard-grid-->

  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import * as echarts from 'echarts'
import {
  ChatDotRound, Collection, DataAnalysis,
  EditPen, Files, Guide, List, Reading, Refresh, TrophyBase, Upload,
  UserFilled
} from '@element-plus/icons-vue'
import { api } from '../api/learning'
import { formatKnowledgeLevel, formatLearningStyle, getErrorMessage } from '../composables/useUtils'
import { ElMessage } from 'element-plus'

const emit = defineEmits<{ (e: 'refresh'): void }>()

const chartRef = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
const loading = ref(false)
const taskLoading = ref(false)
const dashboard = reactive({
  metrics: { knowledge_level: 'beginner', resource_coverage: '0/6', quiz_count: 0, latest_score: 0 },
  scores: [] as number[]
})
const learningDecision = reactive<any>({
  summary: '',
  recommended_target: null,
  next_action: '',
  mastery_overview: {},
  path_version: null,
  current_node: null,
  latest_change: null,
  current_strategy: null,
  current_intervention: null,
})

// Real data populated from API
const realProfile = reactive({
  major: '待完善',
  knowledgeLevel: '待完善',
  learningStyle: '待完善',
  goal: '待完善',
  weeklyTime: '待完善',
  weakPoints: [] as string[],
})
const realStats = reactive({
  resourceCount: 0,
})

// Hero section
const learningModules = [
  { name: '画像分析', icon: UserFilled, color: 'linear-gradient(135deg, #3b82f6, #60a5fa)' },
  { name: '测评评估', icon: DataAnalysis, color: 'linear-gradient(135deg, #f59e0b, #fbbf24)' },
  { name: '路径规划', icon: Guide, color: 'linear-gradient(135deg, #10b981, #34d399)' },
  { name: '知识学习', icon: Collection, color: 'linear-gradient(135deg, #3b82f6, #60a5fa)' },
  { name: '知识检索', icon: Files, color: 'linear-gradient(135deg, #06b6d4, #22d3ee)' },
]

const quickActions = [
  { label: '编辑个人画像', icon: UserFilled, bg: 'linear-gradient(135deg, #eff6ff, #dbeafe)', color: '#3b82f6', handler: () => goToRoute('profile') },
  { label: '进行学习测评', icon: EditPen, bg: 'linear-gradient(135deg, #fff7ed, #ffedd5)', color: '#ea580c', handler: () => goToRoute('quiz') },
  { label: '生成学习路径', icon: Guide, bg: 'linear-gradient(135deg, #ecfeff, #cffafe)', color: '#0891b2', handler: () => goToRoute('path') },
  { label: '进入知识学习', icon: Collection, bg: 'linear-gradient(135deg, #fdf4ff, #fae8ff)', color: '#9333ea', handler: () => goToRoute('resources') },
  { label: '开始智能问答', icon: ChatDotRound, bg: 'linear-gradient(135deg, #f0fdf4, #dcfce7)', color: '#059669', handler: () => goToRoute('tutor') },
  // { label: '生成 PPT', icon: Reading, bg: 'linear-gradient(135deg, #eff6ff, #dbeafe)', color: '#3b82f6', handler: () => goToRoute('resources_ppt_deck') },
]

const profileSummary = computed(() => [
  { label: '专业方向', value: realProfile.major },
  // { label: '当前水平', value: realProfile.knowledgeLevel },
  { label: '学习风格', value: realProfile.learningStyle },
  { label: '学习目标', value: realProfile.goal },
  { label: '学习时间', value: realProfile.weeklyTime },
])
const weakPoints = computed(() => realProfile.weakPoints)

interface RecommendedTask {
  id: string
  type: 'review' | 'assessment' | 'path' | 'practice'
  label: string
  desc: string
  status: 'pending' | 'completed'
  action: string
  source?: string
  done: boolean
}

const typeTagMap: Record<string, { tag: string; tagType: string }> = {
  review: { tag: '复习', tagType: 'warning' },
  assessment: { tag: '测评', tagType: 'danger' },
  path: { tag: '路径', tagType: 'primary' },
  practice: { tag: '实践', tagType: 'success' },
}

const TASKS_CACHE_KEY = 'study_recommended_tasks'
const TASKS_FORCE_REFRESH_KEY = 'study_tasks_force_refresh'
const TASKS_CACHE_VERSION = 2 // 任务数据格式版本，变更时自动清除旧缓存
const TASKS_CACHE_TTL_MS = 16 * 60 * 60 * 1000 // 16 小时过期（用于兜底）

/** 计算到次日 0 点的毫秒数（每日刷新） */
function msUntilMidnight(): number {
  const now = new Date()
  const midnight = new Date(now)
  midnight.setDate(midnight.getDate() + 1)
  midnight.setHours(0, 0, 0, 0)
  return midnight.getTime() - now.getTime()
}

function loadTasksFromCache(): { tasks: RecommendedTask[]; dayKey: string } | null {
  try {
    const raw = localStorage.getItem(TASKS_CACHE_KEY)
    if (!raw) return null
    const { tasks, expiresAt, dayKey, version } = JSON.parse(raw)
    if (version !== TASKS_CACHE_VERSION) {
      localStorage.removeItem(TASKS_CACHE_KEY)
      return null
    }
    if (Date.now() > expiresAt) {
      localStorage.removeItem(TASKS_CACHE_KEY)
      return null
    }
    const today = new Date().toISOString().slice(0, 10)
    if (dayKey && dayKey !== today) {
      localStorage.removeItem(TASKS_CACHE_KEY)
      return null
    }
    return {
      tasks: tasks.map((t: any) => ({ ...t, done: t.done ?? t.status === 'completed' })),
      dayKey: dayKey || today,
    }
  } catch {
    return null
  }
}

function saveTasksToCache(tasks: RecommendedTask[], dayKey: string) {
  try {
    localStorage.setItem(TASKS_CACHE_KEY, JSON.stringify({
      tasks,
      dayKey,
      version: TASKS_CACHE_VERSION,
      expiresAt: Date.now() + msUntilMidnight(),
    }))
  } catch { /* quota exceeded */ }
}

function clearTasksCache() {
  localStorage.removeItem(TASKS_CACHE_KEY)
}

const recommendedTasks = ref<RecommendedTask[]>([])


function applyTaskCompletion(tasks: RecommendedTask[], completion: Record<string, boolean>): RecommendedTask[] {
  return tasks.map(task => {
    const hasServerSignal = Object.prototype.hasOwnProperty.call(completion, task.id)
    const isDone = hasServerSignal ? Boolean(completion[task.id]) : task.status === 'completed'
    return { ...task, done: isDone, status: isDone ? 'completed' as const : 'pending' as const }
  })
}

/** 点击任务：仅跳转，完成状态由后端行为自动判定 */
function clickTask(task: RecommendedTask) {
  if (task.done) {
    // 已完成的任务仍然允许点击跳转
    goToRoute(task.action)
    return
  }
  goToRoute(task.action)
}

async function loadTasks(forceRefresh = false) {
  try {
    const shouldRefresh = forceRefresh || localStorage.getItem(TASKS_FORCE_REFRESH_KEY) === '1'
    if (shouldRefresh) {
      clearTasksCache()
      localStorage.removeItem(TASKS_FORCE_REFRESH_KEY)
    }
    const { data } = await api.getRecommendedTasks(shouldRefresh)
    const serverTasks: RecommendedTask[] = (data.tasks || []).map((t: any) => ({ ...t, done: t.status === 'completed', status: t.status === 'completed' ? 'completed' as const : 'pending' as const }))
    const dayKey: string = data.day_key || new Date().toISOString().slice(0, 10)
    const tasks = applyTaskCompletion(serverTasks, data.completion || {})
    recommendedTasks.value = tasks
    saveTasksToCache(tasks, dayKey)
  } catch {
    // 接口失败时从缓存读取，但重置完成状态（避免 token 失效后仍显示已完成的假象）
    const cached = loadTasksFromCache()
    if (cached) {
      recommendedTasks.value = cached.tasks.map(t => ({ ...t, done: false, status: 'pending' as const }))
    } else {
      recommendedTasks.value = []
    }
  }
}

function goToRoute(name: string) {
  const menuIndexMap: Record<string, string> = {
    dashboard: 'dashboard',
    profile: 'profile',
    path: 'path',
    resources: 'resources',
    quiz: 'quiz',
    tutor: 'tutor',
    knowledge: 'knowledge',
  }
  const event = new CustomEvent('navigate-to', { detail: menuIndexMap[name] || name })
  window.dispatchEvent(event)
}

function goToProfile() { goToRoute('profile') }
function goToResource() { goToRoute('resources') }
function goToPath() { goToRoute('path') }
function goToQuiz() { goToRoute('quiz') }

async function loadDashboard() {
  try {
    const [dashRes, profileRes, resourcesRes] = await Promise.all([
      api.dashboard(),
      api.getProfile().catch(() => ({ data: {} })),
      api.listResources().catch(() => ({ data: { resources: [] } })),
    ])
    Object.assign(dashboard.metrics, dashRes.data.metrics)
    dashboard.scores = dashRes.data.scores || []
    Object.assign(learningDecision, dashRes.data.learning_decision || {})

    const p = profileRes.data.profile || profileRes.data || {}
    if (p.major) realProfile.major = p.major
    if (p.knowledge_level) realProfile.knowledgeLevel = formatKnowledgeLevel(p.knowledge_level)
    if (p.learning_style) realProfile.learningStyle = formatLearningStyle(p.learning_style)
    if (p.learning_goal || p.goal) realProfile.goal = p.learning_goal || p.goal
    if (p.time_availability || p.weekly_time) realProfile.weeklyTime = p.time_availability || p.weekly_time
    if (Array.isArray(dashRes.data.weak_points) && dashRes.data.weak_points.length) {
      realProfile.weakPoints = dashRes.data.weak_points
    } else if (p.weak_points) {
      realProfile.weakPoints = Array.isArray(p.weak_points)
        ? p.weak_points
        : String(p.weak_points).split(/[;；、,，\n]/).map((s: string) => s.trim()).filter(Boolean)
    }

    const resources = resourcesRes.data.resources || []
    realStats.resourceCount = resources.length

    await nextTick()
    renderChart()
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}

async function refreshAll() {
  loading.value = true
  try {
    emit('refresh')
    await loadDashboard()
  } finally {
    loading.value = false
  }
}

async function refreshTasks() {
  taskLoading.value = true
  try {
    clearTasksCache()
    recommendedTasks.value = recommendedTasks.value.map(task => ({
      ...task,
      done: false,
      status: 'pending' as const,
    }))
    await api.resetTasks()
    await loadTasks(true)
    ElMessage.success('今日推荐任务已刷新')
  } finally {
    taskLoading.value = false
  }
}

function renderChart() {
  if (!chartRef.value || dashboard.scores.length === 0) return
  try {
    if (!chart) chart = echarts.init(chartRef.value)
    const primaryColor = getComputedStyle(document.documentElement)
      .getPropertyValue('--primary-500').trim() || '#3b82f6'
    chart.setOption({
      color: [primaryColor],
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(255,255,255,0.95)',
        borderColor: '#e2e8f0',
        borderWidth: 1,
        textStyle: { color: '#1e293b', fontSize: 13 },
        formatter: (params: any) => {
          const item = Array.isArray(params) ? params[0] : params
          return `<strong>${item.axisValue}</strong><br/>得分：<span style="color:${primaryColor};font-weight:600">${item.value}</span>`
        }
      },
      grid: { left: 40, right: 24, top: 36, bottom: 32 },
      xAxis: {
        type: 'category',
        data: dashboard.scores.map((_, index) => `第${index + 1}次`),
        axisLine: { lineStyle: { color: '#e2e8f0' } },
        axisLabel: { color: '#94a3b8', fontSize: 12 },
        splitLine: { show: false }
      },
      yAxis: {
        type: 'value', min: 0, max: 100,
        splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' as const } },
        axisLabel: { color: '#94a3b8', fontSize: 12 }
      },
      series: [{
        type: 'line', smooth: true, data: dashboard.scores,
        symbol: 'circle', symbolSize: 8,
        lineStyle: { width: 3 },
        areaStyle: {
          color: {
            type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: primaryColor + '40' },
              { offset: 1, color: primaryColor + '05' }
            ]
          }
        }
      }]
    })
  } catch (e) {
    console.error('图表渲染失败:', e)
  }
}

function onWindowResize() {
  chart?.resize()
}

function onPageVisible() {
  if (document.visibilityState === 'visible') {
    loadTasks()
  }
}

onBeforeUnmount(() => {
  window.removeEventListener('resize', onWindowResize)
  document.removeEventListener('visibilitychange', onPageVisible)
  chart?.dispose()
  chart = null
})

onMounted(() => {
  loadDashboard()
  loadTasks()
  window.addEventListener('resize', onWindowResize)
  document.addEventListener('visibilitychange', onPageVisible)
})

defineExpose({ loadDashboard, renderChart, refreshTasks })
</script>

<style scoped>
.dashboard-page {
  max-width: 1200px;
  margin: 0 auto;
  animation: pageEnter 0.5s ease-out;
}
.learning-decision-band {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 24px;
  padding: 20px 24px;
  margin-bottom: 18px;
  border: 1px solid #bfdbfe;
  border-left: 4px solid #2563eb;
  border-radius: 6px;
  background: #ffffff;
}
.decision-copy { min-width: 0; }
.decision-eyebrow {
  color: #2563eb;
  font-size: 12px;
  font-weight: 700;
}
.decision-copy h2 {
  margin: 5px 0 6px;
  font-size: 20px;
  color: #172033;
}
.decision-copy p {
  margin: 0;
  color: #475569;
  font-size: 13px;
  line-height: 1.6;
}
.decision-meta {
  display: flex;
  gap: 18px;
  margin-top: 10px;
  color: #64748b;
  font-size: 12px;
}
.dashboard-intervention { margin: -6px 0 16px; }
.decision-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  flex-shrink: 0;
}
@media (max-width: 900px) {
  .learning-decision-band { align-items: flex-start; flex-direction: column; }
  .decision-actions { justify-content: flex-start; }
  .decision-meta { flex-wrap: wrap; gap: 8px 14px; }
}
@keyframes pageEnter { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

/* ======= Hero Banner ======= */
.dashboard-hero {
  position: relative;
  overflow: hidden;
  border-radius: var(--radius-xl, 20px);
  margin-bottom: 20px;
  background: linear-gradient(135deg, #eff6ff 0%, #f8faff 50%, #e0f2fe 100%);
  border: 1px solid #bfdbfe;
}
.hero-bg-accent {
  position: absolute;
  inset: 0;
  background: none;
  pointer-events: none;
}
.hero-bg-accent::before {
  content: '';
  position: absolute;
  top: -30px;
  right: -10px;
  width: 140px;
  height: 140px;
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.06);
}
.hero-bg-accent::after {
  content: '';
  position: absolute;
  bottom: -20px;
  right: 80px;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: rgba(56, 189, 248, 0.06);
}
.hero-content {
  position: relative;
  z-index: 1;
  padding: 32px 36px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 32px;
}
.hero-text { flex: 1; min-width: 0; }
.hero-title {
  font-size: 26px;
  font-weight: 800;
  color: var(--surface-800, #1e293b);
  margin: 0 0 10px;
  line-height: 1.25;
  letter-spacing: -0.3px;
}
.hero-desc {
  font-size: 14px;
  color: var(--surface-500, #64748b);
  margin: 0 0 24px;
  line-height: 1.7;
  max-width: 560px;
}
.hero-actions { display: flex; gap: 12px; flex-wrap: wrap; }
.hero-actions .el-button--primary {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  border: none;
  border-radius: 10px;
  height: 44px;
  padding: 0 28px;
  font-weight: 600;
  box-shadow: 0 4px 20px rgba(59, 130, 246, 0.4);
}
.hero-actions .el-button--primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 30px rgba(59, 130, 246, 0.5);
}
.hero-actions .el-button.is-plain {
  color: var(--primary-600, #4f46e5);
  border-color: #bfdbfe;
  background: rgba(255, 255, 255, 0.78);
  border-radius: 10px;
  height: 44px;
  padding: 0 28px;
  font-weight: 500;
}
.hero-actions .el-button.is-plain:hover {
  background: #ffffff;
  border-color: var(--primary-300, #a5b4fc);
  color: var(--primary-700, #4338ca);
}
.hero-visual { flex-shrink: 0; }
.hero-agent-flow {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px 20px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(191, 219, 254, 0.78);
  border-radius: 16px;
  backdrop-filter: blur(8px);
}
.hero-agent-node {
  display: flex;
  align-items: center;
  gap: 8px;
}
.hero-agent-icon {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 14px;
  flex-shrink: 0;
}
.hero-agent-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--surface-700, #334155);
  white-space: nowrap;
}
.hero-agent-arrow {
  color: rgba(59, 130, 246, 0.45);
  display: flex;
  align-items: center;
}

/* ======= Quick Actions ======= */
.quick-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.quick-action-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 20px;
  background: #ffffff;
  border: 1px solid var(--surface-100);
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.25s ease;
  box-shadow: var(--shadow-sm);
  flex: 1;
  min-width: 130px;
}
.quick-action-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-md);
  border-color: var(--primary-200);
}
.quick-action-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}
.quick-action-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-700);
}

.innovation-module {
  margin-bottom: 20px;
}
.innovation-module .module-header {
  padding: 10px 16px;
  font-size: 14px;
}
.innovation-overview {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  padding: 12px 16px;
}

.innovation-item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(99, 102, 241, 0.14);
  box-shadow: var(--shadow-sm);
}

.innovation-icon {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  flex-shrink: 0;
}

.innovation-item strong {
  display: block;
  color: var(--surface-900);
  font-size: 13px;
  margin-bottom: 2px;
}

.innovation-item span {
  display: block;
  color: var(--surface-500);
  font-size: 12px;
  line-height: 1.4;
}

/* ======= Dashboard Grid ======= */
.dashboard-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}
.dashboard-col { display: flex; flex-direction: column; gap: 20px; min-width: 0; }

/* ======= Module ======= */
.module {
  background: #ffffff;
  border: 1px solid var(--surface-100);
  border-radius: var(--radius-xl, 16px);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  transition: box-shadow 0.2s ease;
}
.module:hover { box-shadow: var(--shadow-md); }
.module-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--surface-100);
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-700);
  background: linear-gradient(180deg, #ffffff 0%, #fafbfc 100%);
}
.module-header .el-icon { color: var(--primary-500); }

/* ======= Profile Summary ======= */
.profile-content { padding: 16px 20px; }
.profile-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px dashed var(--surface-100);
}
.profile-row:last-of-type { border-bottom: none; }
.profile-label { font-size: 14px; color: var(--surface-500); }
.profile-value { font-size: 14px; font-weight: 600; color: var(--surface-800); }
.profile-weak-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
}
.profile-weak-row .profile-label { padding-top: 2px; }
.profile-tags { display: flex; gap: 4px; flex-wrap: wrap; }

/* ======= Agent Grid ======= */
.agent-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  padding: 16px 20px;
}
.agent-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--surface-100);
  transition: all 0.2s ease;
  cursor: default;
}
.agent-card:hover {
  border-color: var(--primary-200);
  background: var(--primary-50);
  transform: translateY(-2px);
}
.agent-card-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}
.agent-card-info { flex: 1; min-width: 0; }
.agent-card-info strong {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-800);
}
.agent-card-info span {
  display: block;
  font-size: 12px;
  color: var(--surface-400);
  margin-top: 1px;
}
.agent-status {
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 20px;
  flex-shrink: 0;
}
.agent-status.online { background: #d1fae5; color: #059669; }
.agent-status.standby { background: var(--surface-100); color: var(--surface-500); }

/* ======= Metric Grid ======= */
.metric-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}
.metric-card {
  position: relative;
  overflow: hidden;
  border-radius: var(--radius-lg, 14px);
  border: 1px solid var(--surface-100);
  background: #ffffff;
  box-shadow: var(--shadow-sm);
  transition: all 0.3s ease;
  cursor: default;
}
.metric-card:hover { transform: translateY(-4px); box-shadow: var(--shadow-lg); }
.metric-accent { height: 3px; width: 100%; }
.metric-level .metric-accent { background: linear-gradient(90deg, #3b82f6, #60a5fa); }
.metric-quiz .metric-accent { background: linear-gradient(90deg, #3b82f6, #60a5fa); }
.metric-score .metric-accent { background: linear-gradient(90deg, #10b981, #34d399); }
.metric-inner { display: flex; align-items: center; gap: 14px; padding: 16px; }
.metric-icon-wrap {
  width: 44px; height: 44px;
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.metric-level .metric-icon-wrap { background: #eff6ff; color: #3b82f6; }
.metric-quiz .metric-icon-wrap { background: #eff6ff; color: #3b82f6; }
.metric-score .metric-icon-wrap { background: #ecfdf5; color: #10b981; }
.metric-body { min-width: 0; }
.metric-label { display: block; font-size: 13px; font-weight: 500; color: var(--surface-500); margin-bottom: 2px; }
.metric-value { display: block; font-size: 24px; font-weight: 700; color: var(--surface-900); line-height: 1.2; }

/* ======= Chart ======= */
.chart-module { border-radius: var(--radius-xl, 16px); }
.chart-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 18px 24px; border-bottom: 1px solid var(--surface-100);
  background: linear-gradient(180deg, #ffffff 0%, #fafbfc 100%);
}
.chart-toolbar-left { display: flex; flex-direction: column; gap: 2px; }
.chart-title { font-size: 16px; font-weight: 600; color: var(--surface-800); margin: 0; }
.chart-subtitle { font-size: 14px; color: var(--surface-400); }
.chart-box { height: 260px; padding: 16px 12px 8px; background: #ffffff; }
.chart-empty { display: flex; align-items: center; justify-content: center; min-height: 200px; padding: 40px 20px; }

/* ======= Tasks ======= */
.tasks-module { border-radius: var(--radius-xl, 16px); }
.task-list { padding: 8px 16px 16px; }
.task-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  transition: all 0.2s ease;
  cursor: pointer;
  border: 1px solid transparent;
}
.task-item:hover { background: var(--primary-50); border-color: var(--primary-200); }
.task-check { flex-shrink: 0; }
.task-body { flex: 1; min-width: 0; }
.task-body strong { display: block; font-size: 14px; font-weight: 600; color: var(--surface-800); }
.task-body span { display: block; font-size: 13px; color: var(--surface-400); margin-top: 2px; }
.task-item .el-tag { flex-shrink: 0; }
.task-done { opacity: 0.5; text-decoration: line-through; }
.task-done:hover { background: transparent; border-color: transparent; cursor: default; }

/* ======= Responsive ======= */
@media (max-width: 1100px) {
  .dashboard-grid { grid-template-columns: 1fr; }
  .agent-grid { grid-template-columns: 1fr 1fr; }
  .innovation-overview { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 768px) {
  .hero-content { flex-direction: column; padding: 28px 24px; }
  .hero-title { font-size: 22px; }
  .hero-visual { width: 100%; }
  .hero-agent-flow { flex-direction: row; flex-wrap: wrap; justify-content: center; }
  .quick-actions { flex-direction: column; }
  .quick-action-card { min-width: 0; }
  .innovation-overview { grid-template-columns: 1fr; }
  .metric-grid { grid-template-columns: repeat(3, 1fr); gap: 10px; }
  .agent-grid { grid-template-columns: 1fr; }
  .chart-toolbar { flex-direction: column; align-items: flex-start; gap: 12px; }
  .chart-box { height: 220px; }
}
</style>
