<template>
  <section class="path-page">
    <!-- Enhanced Header -->
    <div class="path-header">
      <div class="path-header-bg-accent"></div>
      <div class="path-header-left">
        <div class="path-header-icon">
          <el-icon :size="28"><Guide /></el-icon>
        </div>
        <div>
          <h2 class="path-title">动态个性化学习路径</h2>
          <p class="path-desc">基于学生画像与测评结果，AI 为你生成可执行的学习路线</p>
        </div>
      </div>
      <div class="path-header-right">
        <div class="path-header-tags">
          <el-tag class="path-badge badge-portrait" effect="plain" round>画像驱动</el-tag>
          <el-tag class="path-badge badge-dynamic" effect="plain" round>动态调整</el-tag>
          <el-tag class="path-badge badge-resource" effect="plain" round>资源推荐</el-tag>
          <el-tag class="path-badge badge-closed" effect="plain" round>闭环评估</el-tag>
        </div>
        <el-button type="primary" :icon="Guide" :loading="loading" @click="planPath">
          生成学习路径
        </el-button>
      </div>
    </div>

    <section v-if="currentStrategy || currentIntervention" class="teaching-strategy-band">
      <div v-if="currentStrategy">
        <span>当前教学策略</span>
        <strong>{{ currentStrategy.strategy_label }}</strong>
        <small>{{ currentStrategy.action_labels?.join(' · ') }}</small>
      </div>
      <div v-if="currentIntervention">
        <span>主动干预任务</span>
        <strong>{{ currentIntervention.knowledge_point }}</strong>
        <small>已进入路径 v{{ currentIntervention.path_version_number || '--' }} · {{ currentIntervention.block_type }}</small>
      </div>
    </section>

    <!-- 只展示真实请求状态；后续接入 AgentRun 后再展示步骤级进度。 -->
    <div v-if="loading" class="path-loading-progress">
      <div class="plp-header">
        <el-icon class="is-loading" :size="18"><Loading /></el-icon>
        <span>正在生成学习路径</span>
      </div>
      <div class="plp-progress">
        <span>后端正在结合当前画像和历史测评生成内容</span>
        <span v-if="showTiming" class="live-timer">已耗时 {{ formatDuration(liveElapsed) }}</span>
      </div>
    </div>

    <section v-if="pathVersion" class="path-version-band">
      <div class="path-version-main">
        <el-tag type="primary" effect="dark">v{{ pathVersion.version_number }}</el-tag>
        <div>
          <strong>当前路径版本</strong>
          <p>{{ pathVersion.replanning_reason || '依据画像、掌握度和课程先修关系生成' }}</p>
        </div>
      </div>
      <div v-if="pathDiff" class="path-diff-summary">
        <span>较 v{{ pathDiff.from_version }} 调整</span>
        <el-tag v-if="pathDiff.added_nodes?.length" type="warning" effect="plain">
          新增 {{ pathDiff.added_nodes.length }} 个补救节点
        </el-tag>
        <el-tag v-if="pathDiff.moved_nodes?.length" effect="plain">
          调序 {{ pathDiff.moved_nodes.length }} 项
        </el-tag>
        <el-button link type="primary" @click="showPathExplanation">为什么调整？</el-button>
      </div>
      <div v-if="pathDiff" class="path-diff-detail">
        <strong>学习路径调整</strong>
        <span
          v-for="change in pathDiff.mastery_change || []"
          :key="change.knowledge_point_id"
        >
          {{ change.knowledge_point }}：{{ Math.round(change.old) }}% →
          {{ Math.round(change.new) }}%
        </span>
        <span
          v-for="node in pathDiff.added_nodes || []"
          :key="`${node.knowledge_point_id}-${node.node_type}-${node.node_order}`"
        >
          新增：{{ node.knowledge_point }}（{{ nodeTypeLabel(node.node_type) }}）
        </span>
      </div>
    </section>

    <!-- Empty State -->
    <div v-if="!hasPathContent && !loading" class="path-empty">
      <div class="path-empty-icon">
        <el-icon :size="48"><Guide /></el-icon>
      </div>
      <h3 class="path-empty-title">还没有学习路径</h3>
      <p class="path-empty-desc">{{ pathError || '点击上方按钮，AI 将根据你的画像生成个性化学习路径' }}</p>
    </div>

    <!-- Path Plan (内联展示) -->
    <div v-if="pathPlan.steps.length" class="path-plan">
      <!-- Progress Section -->
      <div class="path-progress-section">
        <div class="path-progress-header">
          <div class="path-progress-left">
            <el-icon :size="16"><Guide /></el-icon>
            <span>学习总进度</span>
          </div>
          <strong>{{ progressPercent }}%</strong>
        </div>
        <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
        <div v-if="showTiming && generationDuration && !loading" style="margin-top:6px;display:flex;align-items:center;gap:8px;">
          <span class="resource-timing-badge">路径生成耗时 {{ formatDuration(generationDuration) }}</span>
        </div>
      </div>

      <!-- 画像字段 -->
      <!-- <div class="profile-mini-grid">
        <div class="profile-mini-card">
          <div class="mini-card-accent" style="background: linear-gradient(180deg, #3b82f6, #60a5fa);"></div>
          <div class="mini-card-body">
            <span class="mini-card-label">课程主题</span>
            <span class="mini-card-value">{{ profileData.topic || '未设置' }}</span>
          </div>
        </div>
        <div class="profile-mini-card">
          <div class="mini-card-accent" style="background: linear-gradient(180deg, #10b981, #34d399);"></div>
          <div class="mini-card-body">
            <span class="mini-card-label">学习目标</span>
            <span class="mini-card-value">{{ profileData.learning_goal || '未设置' }}</span>
          </div>
        </div>
        <div class="profile-mini-card">
          <div class="mini-card-accent" style="background: linear-gradient(180deg, #3b82f6, #60a5fa);"></div>
          <div class="mini-card-body">
            <span class="mini-card-label">学习风格</span>
            <span class="mini-card-value">{{ formatLearningStyle(profileData.learning_style) }}</span>
          </div>
        </div>
        <div class="profile-mini-card">
          <div class="mini-card-accent" style="background: linear-gradient(180deg, #f59e0b, #fbbf24);"></div>
          <div class="mini-card-body">
            <span class="mini-card-label">可用时间</span>
            <span class="mini-card-value">{{ profileData.time_availability ? formatTimeAvailability(profileData.time_availability) : '未设置' }}</span>
          </div>
        </div>
      </div> -->

      <!-- AI Strategy Card -->
      <div v-if="strategyText" class="path-strategy-card">
        <div class="strategy-header">
          <div class="strategy-header-left">
            <div class="strategy-header-icon">
              <el-icon :size="18"><Connection /></el-icon>
            </div>
            <div>
              <strong>AI 动态规划策略</strong>
              <span>根据当前画像与测评结果生成</span>
            </div>
          </div>
        </div>
        <div class="strategy-body">
          <div class="strategy-agent-icon">
            <svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/><circle cx="20" cy="6" r="2"/><circle cx="4" cy="6" r="2"/></svg>
          </div>
          <p class="strategy-text">{{ strategyText }}</p>
        </div>
      </div>

    
      <!-- Timeline Steps -->
      <div class="path-timeline">
        <article v-for="step in pathPlan.steps" :key="step.index" class="path-step-card" :class="{
          'is-completed': pathCompleted[String(step.index)],
          'is-current': String(step.index) === currentStepId,
          'is-locked': isStepLocked(step),
        }">
          <div class="path-step-marker">
            <span class="path-step-number">{{ step.index }}</span>
            <div class="path-step-line"></div>
          </div>
          <div class="path-step-body" @click="openStepDrawer(step)">
            <header class="path-step-header">
              <div class="path-step-info">
                <h3>{{ step.title }}</h3>
                <span v-if="step.time" class="path-step-time">
                  <el-icon :size="14"><Clock /></el-icon>
                  {{ step.time }}
                </span>
              </div>
              <el-checkbox v-model="pathCompleted[String(step.index)]" size="large" @click.stop @change="(val: boolean) => onInlineStepCompleteChange(val, step.index)" :disabled="isStepLocked(step)">
                <span class="checkbox-label">完成</span>
              </el-checkbox>
            </header>
            <div class="path-step-preview">
              <span class="path-step-preview-text">点击查看详情</span>
              <el-icon :size="16"><ArrowRight /></el-icon>
            </div>
          </div>
        </article>
      </div>
    </div>

    <!-- 原始内容回退 -->
    <div v-if="hasPathContent && !pathPlan.steps.length && !loading" class="path-raw-card">
      <div class="path-raw-header">
        <strong>学习路径已生成</strong>
        <span>当前内容格式未匹配时间轴结构，已先按 Markdown 原文展示。</span>
      </div>
      <div class="markdown path-raw-markdown" v-html="renderMarkdown(pathContent)"></div>
    </div>

    <!-- 步骤详情抽屉 -->
    <el-drawer
      v-model="stepDrawerVisible"
      :size="480"
      direction="rtl"
      class="step-drawer"
    >
      <template #header>
        <div class="step-drawer-header">
          <div class="step-drawer-header-icon">
            <span class="step-drawer-number">{{ activeDrawerStep?.index }}</span>
          </div>
          <div class="step-drawer-header-info">
            <strong>{{ activeDrawerStep?.title }}</strong>
            <span v-if="activeDrawerStep?.time">
              <el-icon :size="14"><Clock /></el-icon>
              {{ activeDrawerStep.time }}
            </span>
          </div>
        </div>
      </template>

      <div v-if="activeDrawerStep" class="step-drawer-body">
        <div class="step-drawer-completion">
          <el-checkbox
            v-model="drawerStepCompleted"
            size="large"
            @change="onDrawerStepCompleteChange"
          >
            <span class="drawer-checkbox-label">标记为已完成</span>
          </el-checkbox>
        </div>

        <div v-if="activeDrawerStep.goal" class="drawer-section">
          <div class="drawer-section-header">
            <span class="drawer-section-tag goal-tag">目标</span>
          </div>
          <div class="drawer-section-content path-detail-markdown" v-html="renderMarkdown(activeDrawerStep.goal)"></div>
        </div>

        <div v-if="activeDrawerStep.task" class="drawer-section">
          <div class="drawer-section-header">
            <span class="drawer-section-tag task-tag">任务</span>
          </div>
          <div class="drawer-section-content path-detail-markdown" v-html="renderMarkdown(activeDrawerStep.task)"></div>
        </div>

        <div v-if="activeDrawerStep.action" class="drawer-section">
          <div class="drawer-section-header">
            <span class="drawer-section-tag action-tag">入口</span>
          </div>
          <div class="drawer-section-content path-detail-markdown" v-html="renderMarkdown(activeDrawerStep.action)"></div>
        </div>

        <div v-if="activeDrawerStep.resource" class="drawer-section">
          <div class="drawer-section-header">
            <span class="drawer-section-tag resource-tag">资源</span>
          </div>
          <div class="drawer-section-content path-detail-markdown" v-html="renderMarkdown(activeDrawerStep.resource)"></div>
        </div>

        <div v-if="activeDrawerNode?.resources?.length" class="drawer-section">
          <div class="drawer-section-header">
            <span class="drawer-section-tag resource-tag">推荐依据</span>
          </div>
          <div
            v-for="binding in activeDrawerNode.resources"
            :key="binding.id"
            class="node-resource-reason"
          >
            <strong>{{ binding.resource?.title || '课程学习资源' }}</strong>
            <span>{{ binding.personalization_reason }}</span>
          </div>
        </div>

        <div v-if="activeDrawerStep.output" class="drawer-section">
          <div class="drawer-section-header">
            <span class="drawer-section-tag output-tag">产出</span>
          </div>
          <div class="drawer-section-content path-detail-markdown" v-html="renderMarkdown(activeDrawerStep.output)"></div>
        </div>

        <div v-if="activeDrawerStep.checkpoint" class="drawer-section">
          <div class="drawer-section-header">
            <span class="drawer-section-tag checkpoint-tag">标准</span>
          </div>
          <div class="drawer-section-content path-detail-markdown" v-html="renderMarkdown(activeDrawerStep.checkpoint)"></div>
        </div>
      </div>
    </el-drawer>

    <el-drawer v-model="pathExplanationVisible" title="路径调整依据" size="460px">
      <template v-if="pathExplanation">
        <h3>{{ pathExplanation.decision }}</h3>
        <div class="explanation-section">
          <strong>调整原因</strong>
          <ul><li v-for="item in pathExplanation.reasons" :key="item">{{ item }}</li></ul>
        </div>
        <div class="explanation-section">
          <strong>触发条件</strong>
          <p>{{ pathExplanation.trigger }}</p>
        </div>
        <div class="explanation-section">
          <strong>保留方案</strong>
          <ul><li v-for="item in pathExplanation.alternatives" :key="item">{{ item }}</li></ul>
        </div>
      </template>
    </el-drawer>

      <!-- 资源自动生成进度 -->
      <div v-if="showAutoGenProgress" class="auto-resource-progress">
        <div class="auto-resource-header">
          <el-icon :size="16"><Files /></el-icon>
          <span>正在自动生成配套资源</span>
        </div>
        <div class="auto-resource-steps">
          <div v-for="step in autoResSteps" :key="step.type" class="auto-resource-step" :class="step.status">
            <div class="auto-resource-step-indicator">
              <el-icon v-if="step.status === 'completed'" :size="18" class="step-done-icon"><CircleCheckFilled /></el-icon>
              <el-icon v-else-if="step.status === 'generating'" :size="18" class="is-loading step-gen-icon"><Loading /></el-icon>
              <div v-else class="step-pending-dot"></div>
            </div>
            <div class="auto-resource-step-body">
              <strong>{{ step.label }}</strong>
              <span>{{ step.desc }}</span>
            </div>
          </div>
        </div>
      </div>

  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheckFilled, Clock, Connection, Files, Guide, Loading, ArrowRight } from '@element-plus/icons-vue'
import { api } from '../api/learning'
import { formatLearningStyle, formatTimeAvailability, getErrorMessage, hashText, renderMarkdown } from '../composables/useUtils'
import { useSessionStore } from '../stores/session'

interface PathStep {
  index: number
  title: string
  time: string
  goal: string
  task: string
  action: string
  resource: string
  output: string
  checkpoint: string
}

interface PathPlan {
  title: string
  meta: Array<{ label: string; value: string }>
  steps: PathStep[]
}

const loading = ref(false)
const genStartedAt = ref(0)
const generationDuration = ref<number | null>(null)
const liveElapsed = ref(0)
let liveTimerInterval: ReturnType<typeof setInterval> | null = null
const session = useSessionStore()
const pathContent = ref('')
const activePathId = ref('')
const pathError = ref('')
const pathCompleted = reactive<Record<string, boolean>>({})
const pathVersion = ref<any | null>(null)
const pathDiff = ref<any | null>(null)
const pathExplanationVisible = ref(false)
const pathExplanation = ref<any | null>(null)
const currentStrategy = ref<any | null>(null)
const currentIntervention = ref<any | null>(null)
let isRestoringPathProgress = false

// 步骤抽屉状态
const stepDrawerVisible = ref(false)
const activeDrawerStep = ref<PathStep | null>(null)
const drawerStepCompleted = ref(false)

const profileData = reactive({
  topic: '',
  learning_goal: '',
  learning_style: '',
  time_availability: '',
})

// ===== Computed =====
const pathPlan = computed(() => parsePathPlan(pathContent.value))
const hasPathContent = computed(() => Boolean(pathContent.value.trim()))
const showTiming = computed(() => import.meta.env.VITE_ENABLE_RESOURCE_TIMING === 'true')
const progressPercent = computed(() => {
  if (pathPlan.value.steps.length === 0) return 0
  const done = Object.values(pathCompleted).filter(Boolean).length
  return Math.round((done / pathPlan.value.steps.length) * 100)
})

const currentStepId = computed(() => {
  for (const step of pathPlan.value.steps) {
    if (!pathCompleted[String(step.index)]) return String(step.index)
  }
  return ''
})

const strategyText = computed(() => {
  const s = pathPlan.value.meta.find(m => m.label.includes('策略'))
  return s?.value || ''
})
const activeDrawerNode = computed(() => (
  activeDrawerStep.value ? nodeForStep(activeDrawerStep.value) : null
))

function nodeTypeLabel(type: string) {
  return {
    normal: '常规学习',
    review: '复习',
    remediation: '补救学习',
    assessment: '复测',
  }[type] || type
}

async function showPathExplanation() {
  if (!pathVersion.value?.id) return
  try {
    const { data } = await api.explainDecision({
      decision_type: 'path_change',
      path_version_id: pathVersion.value.id,
    })
    pathExplanation.value = data.explanation
    pathExplanationVisible.value = true
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}

function nodeForStep(step: PathStep) {
  return pathVersion.value?.nodes?.find(
    (node: any) => Number(node.node_order) === Number(step.index),
  )
}

function isStepLocked(step: PathStep) {
  const node = nodeForStep(step)
  if (node) return node.status === 'locked'
  return step.index > 1 && !pathCompleted[String(step.index - 1)]
}

function applyStructuredVersion(version: any) {
  pathVersion.value = version || null
  if (!version?.nodes?.length) return false
  isRestoringPathProgress = true
  resetPathProgress()
  for (const node of version.nodes) {
    pathCompleted[String(node.node_order)] = node.status === 'completed'
  }
  isRestoringPathProgress = false
  return true
}

// ===== 步骤抽屉 =====
async function openStepDrawer(step: PathStep) {
  if (isStepLocked(step)) {
    ElMessage.warning('请先完成前一个学习节点')
    return
  }
  activeDrawerStep.value = step
  drawerStepCompleted.value = Boolean(pathCompleted[String(step.index)])
  stepDrawerVisible.value = true
  const node = nodeForStep(step)
  if (node && node.status !== 'completed') {
    try {
      const { data } = await api.openPathNode(node.id)
      Object.assign(node, data.node || {})
    } catch (error) {
      ElMessage.error(getErrorMessage(error))
    }
  }
}

async function onDrawerStepCompleteChange(completed: boolean) {
  if (!activeDrawerStep.value) return
  const index = activeDrawerStep.value.index
  if (isStepLocked(activeDrawerStep.value)) {
    drawerStepCompleted.value = false
    ElMessage.warning('请先完成前一步')
    return
  }
  if (!completed && nodeForStep(activeDrawerStep.value)) {
    drawerStepCompleted.value = true
    ElMessage.info('已记录的学习事件不能撤销')
    return
  }
  if (completed && !(await completeStructuredStep(activeDrawerStep.value))) return
  const key = String(index)
  pathCompleted[key] = completed
  if (!completed) {
    const steps = pathPlan.value.steps
    for (let i = index + 1; i <= steps.length; i++) {
      delete pathCompleted[String(i)]
    }
  }
}

// 行内 checkbox 取消勾选时级联清除后续步骤
async function onInlineStepCompleteChange(completed: boolean, index: number) {
  const step = pathPlan.value.steps.find(item => item.index === index)
  if (step && nodeForStep(step)) {
    if (!completed) {
      pathCompleted[String(index)] = true
      ElMessage.info('已记录的学习事件不能撤销')
      return
    }
    if (!(await completeStructuredStep(step))) {
      pathCompleted[String(index)] = false
      return
    }
  }
  if (!completed) {
    const steps = pathPlan.value.steps
    for (let i = index + 1; i <= steps.length; i++) {
      delete pathCompleted[String(i)]
    }
  }
}

async function completeStructuredStep(step: PathStep) {
  const node = nodeForStep(step)
  if (!node || node.status === 'completed') return true
  try {
    await api.completePathNode(node.id)
    await loadPath()
    ElMessage.success('学习节点已完成，掌握度证据已更新')
    return true
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
    return false
  }
}

function formatDuration(seconds: number) {
  if (seconds == null) return ''
  if (seconds < 60) return `${Math.floor(seconds)}秒`
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}分${secs}秒`
}

function startLiveTimer() {
  stopLiveTimer()
  liveElapsed.value = 0
  const _start = Date.now()
  liveTimerInterval = setInterval(() => {
    liveElapsed.value = Math.floor((Date.now() - _start) / 1000)
  }, 1000)
}

function stopLiveTimer() {
  if (liveTimerInterval) {
    clearInterval(liveTimerInterval)
    liveTimerInterval = null
  }
}

function formatLiveTime(seconds: number) {
  if (seconds == null || seconds < 0) return ''
  if (seconds < 60) return `${seconds}秒`
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}分${secs}秒`
}

// ===== 资源自动生成进度 =====
const autoResLabels: Record<string, { label: string; desc: string }> = {
  course_document: { label: '讲解文档', desc: '生成课程讲解材料' },
  mind_map: { label: '思维导图', desc: '生成知识思维导图' },
  exercise_bank: { label: '练习题库', desc: '生成练习题与测验' },
  extension_reading: { label: '拓展阅读', desc: '推荐拓展阅读资料' },
  coding_case: { label: '实操案例', desc: '生成可动手实践的案例' },
}
const showAutoGenProgress = ref(false)
const autoResSteps = reactive<{ type: string; label: string; desc: string; status: string }[]>([])
let autoGenPollTimer: ReturnType<typeof setInterval> | null = null

function startAutoGenProgress(since: string) {
  showAutoGenProgress.value = true
  autoResSteps.length = 0
  const autoTypes = ['course_document', 'mind_map', 'exercise_bank', 'extension_reading', 'coding_case']
  for (const rtype of autoTypes) {
    const item = autoResLabels[rtype]
    autoResSteps.push({ type: rtype, label: item.label, desc: item.desc, status: 'generating' })
  }

  autoGenPollTimer = setInterval(async () => {
    try {
      const { data } = await api.getAutoResourceStatus(since)
      for (const step of autoResSteps) {
        if (data.status[step.type] === 'completed') {
          step.status = 'completed'
        }
      }
      if (data.all_completed) {
        if (autoGenPollTimer) {
          clearInterval(autoGenPollTimer)
          autoGenPollTimer = null
        }
        ElMessage.success('5类个性化资源已全部自动生成')
      }
    } catch {
      // 轮询失败时静默重试
    }
  }, 3000)
}

// ===== Navigation =====
function navigateTo(menuIndex: string) {
  window.dispatchEvent(new CustomEvent('navigate-to', { detail: menuIndex }))
}

// ===== Parsing =====
function parsePathPlan(content: string): PathPlan {
  const lines = (content || '').split(/\r?\n/)
  const title = lines.find((line) => line.startsWith('## '))?.replace(/^##\s*/, '').trim() || '学习计划路径'
  const meta: Array<{ label: string; value: string }> = []
  const steps: PathStep[] = []
  let current: PathStep | null = null

  const keyMap: Record<string, Exclude<keyof PathStep, 'index'>> = {
    时间: 'time',
    预估时间: 'time',
    建议时间: 'time',
    学习目标: 'goal',
    目标: 'goal',
    阶段目标: 'goal',
    学习任务: 'task',
    任务: 'task',
    具体任务: 'task',
    操作入口: 'action',
    入口: 'action',
    平台入口: 'action',
    使用资源: 'resource',
    资源: 'resource',
    推荐资源: 'resource',
    产出物: 'output',
    产出: 'output',
    学习产出: 'output',
    完成标准: 'checkpoint',
    检查点: 'checkpoint',
    标准: 'checkpoint',
    验收标准: 'checkpoint',
    达成标准: 'checkpoint',
  }
  const fieldLabels = Object.keys(keyMap).sort((a, b) => b.length - a.length)
  const fieldPattern = new RegExp(`(?:\\*\\*|__)?\\s*(${fieldLabels.map(escapeRegExp).join('|')})\\s*(?:\\*\\*|__)?\\s*[:：]`, 'g')

  function cleanKey(key: string) {
    return key
      .replace(/[*_`~#>\-\s]/g, '')
      .replace(/[：:]+$/, '')
      .trim()
  }

  function cleanValue(value: string) {
    return value
      .replace(/^[\s,，;；、]+/, '')
      .replace(/[\s,，;；、]+$/, '')
      .trim()
  }

  function assignField(step: PathStep, field: Exclude<keyof PathStep, 'index'>, rawValue: string) {
    const value = cleanValue(rawValue)
    if (!value) return
    step[field] = step[field] ? `${step[field]}；${value}` : value
  }

  function parseStepItem(step: PathStep, item: string) {
    const matches = Array.from(item.matchAll(fieldPattern))
    if (matches.length) {
      matches.forEach((match, index) => {
        const label = cleanKey(match[1])
        const field = keyMap[label]
        if (!field) return
        const valueStart = (match.index || 0) + match[0].length
        const nextStart = matches[index + 1]?.index ?? item.length
        assignField(step, field, item.slice(valueStart, nextStart))
      })
      return true
    }

    const separatorMatch = item.match(/[:：]/)
    const separator = separatorMatch?.index ?? -1
    if (separator > 0) {
      const key = cleanKey(item.slice(0, separator))
      const value = item.slice(separator + 1)
      const field = keyMap[key]
      if (field) {
        assignField(step, field, value)
      } else if (value.trim()) {
        assignField(step, 'task', `${key}：${value}`)
      }
      return true
    }

    assignField(step, 'task', item)
    return true
  }

  for (const line of lines) {
    const trimmed = line.trim()
    const stepMatch =
      trimmed.match(/^###\s*第\s*([一二三四五六七八九十\d]+)\s*(?:步|阶段|节)?\s*[:：]\s*(.+)$/) ||
      trimmed.match(/^###\s*阶段\s*([一二三四五六七八九十\d]+)\s*[:：]\s*(.+)$/) ||
      trimmed.match(/^###\s*(\d+)[.、]\s*(.+)$/)
    if (stepMatch) {
      current = {
        index: parseStepIndex(stepMatch[1], steps.length + 1),
        title: stepMatch[2],
        time: '',
        goal: '',
        task: '',
        action: '',
        resource: '',
        output: '',
        checkpoint: '',
      }
      steps.push(current)
      continue
    }
    if (!trimmed.startsWith('- ')) continue
    const item = trimmed.slice(2)
    if (current) {
      parseStepItem(current, item)
      continue
    }
    const separatorMatch = item.match(/[:：]/)
    const separator = separatorMatch?.index ?? -1
    if (!current && separator > 0 && meta.length < 8 && !item.startsWith('按顺序') && !item.startsWith('每一步') && !item.startsWith('不建议')) {
      meta.push({ label: cleanKey(item.slice(0, separator)), value: cleanValue(item.slice(separator + 1)) })
    }
  }
  return { title, meta, steps }
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function parseStepIndex(value: string, fallback: number) {
  const normalized = value.trim()
  const numeric = Number(normalized)
  if (Number.isFinite(numeric) && numeric > 0) return numeric
  const digitMap: Record<string, number> = {
    一: 1,
    二: 2,
    三: 3,
    四: 4,
    五: 5,
    六: 6,
    七: 7,
    八: 8,
    九: 9,
  }
  if (normalized === '十') return 10
  if (normalized.startsWith('十')) return 10 + (digitMap[normalized.slice(1)] || 0)
  if (normalized.endsWith('十')) return (digitMap[normalized[0]] || 1) * 10
  if (normalized.includes('十')) {
    const [ten, one] = normalized.split('十')
    return (digitMap[ten] || 1) * 10 + (digitMap[one] || 0)
  }
  return digitMap[normalized] || fallback
}

// ===== Progress Persistence =====
function resetPathProgress() {
  Object.keys(pathCompleted).forEach((key) => delete pathCompleted[key])
}

function pathProgressStorageKey() {
  if (!activePathId.value) return ''
  const userId = session.user?.id || session.user?.username || 'guest'
  return `study-path-progress:${userId}:${activePathId.value}`
}

function savePathProgress() {
  if (pathVersion.value) return
  if (isRestoringPathProgress) return
  const key = pathProgressStorageKey()
  if (!key) return
  localStorage.setItem(key, JSON.stringify({ ...pathCompleted }))
}

function restorePathProgress() {
  isRestoringPathProgress = true
  resetPathProgress()
  const key = pathProgressStorageKey()
  if (key) {
    try {
      const saved = JSON.parse(localStorage.getItem(key) || '{}')
      Object.entries(saved).forEach(([step, completed]) => {
        pathCompleted[step] = Boolean(completed)
      })
    } catch {
      resetPathProgress()
    }
  }
  isRestoringPathProgress = false
}

function initializePathProgress() {
  isRestoringPathProgress = true
  resetPathProgress()
  isRestoringPathProgress = false
  savePathProgress()
}

function pathIdOf(path: any) {
  if (!path) return ''
  return String(path.id || hashText(path.content || ''))
}

// ===== API =====
async function planPath() {
  if (loading.value) return
  loading.value = true
  genStartedAt.value = Date.now()
  generationDuration.value = null
  pathError.value = ''
  startLiveTimer()
  try {
    const { data } = await api.planPath()
    const path = data?.path
    const content = String(path?.content || data?.content || '').trim()
    if (!content) {
      throw new Error('学习路径生成结果为空，请检查后端服务或稍后重试')
    }
    pathContent.value = content
    activePathId.value = pathIdOf(path || { content })
    pathDiff.value = null
    if (!applyStructuredVersion(data?.version || path?.latest_version)) {
      initializePathProgress()
    }
    // 启动后台资源生成进度轮询（仅当后端实际开启了自动生成）
    const createdAt = data?.path?.created_at || ''
    if (createdAt && data?.auto_resource_status === 'background') {
      startAutoGenProgress(createdAt)
    }
    generationDuration.value = (Date.now() - genStartedAt.value) / 1000
    liveElapsed.value = Math.floor((Date.now() - genStartedAt.value) / 1000)
    if (data?.auto_resource_status === 'background') { ElMessage.success('学习路径已生成，后台自动生成 5 类个性化资源') } else { ElMessage.success('学习路径已生成') }
  } catch (error) {
    pathError.value = getErrorMessage(error)
    ElMessage.error(pathError.value)
  } finally {
    stopLiveTimer()
    loading.value = false
  }
}

async function loadPath() {
  try {
    const { data } = await api.latestPath()
    if (data.path) {
      pathContent.value = data.path.content || ''
      activePathId.value = pathIdOf(data.path)
      pathError.value = ''
      if (!applyStructuredVersion(data.version || data.path.latest_version)) {
        restorePathProgress()
      }
      try {
        const diffResponse = await api.getLatestPathDiff()
        pathDiff.value = diffResponse.data?.diff || null
      } catch {
        pathDiff.value = null
      }
    } else {
      pathContent.value = ''
      activePathId.value = ''
      pathVersion.value = null
      pathDiff.value = null
      initializePathProgress()
    }
  } catch (error) {
    if (error instanceof Error && !error.message.includes('404')) {
      console.error('加载学习路径失败:', error)
    }
  }
}

async function loadTeachingState() {
  try {
    const [strategyResponse, interventionResponse] = await Promise.all([
      api.getCurrentTeachingStrategy(),
      api.getTeachingInterventions(1),
    ])
    currentStrategy.value = strategyResponse.data.strategy || null
    currentIntervention.value = (
      interventionResponse.data.interventions || []
    ).find((item: any) => item.status === 'active') || null
  } catch {
    currentStrategy.value = null
    currentIntervention.value = null
  }
}

function loadProfile() {
  api.getProfile().then(({ data }) => {
    const p = data.profile || {}
    profileData.topic = p.topic || ''
    profileData.learning_goal = p.learning_goal || ''
    profileData.learning_style = p.learning_style || ''
    profileData.time_availability = p.time_availability || ''
  }).catch(() => {})
}

watch(pathCompleted, savePathProgress, { deep: true })

onMounted(() => {
  loadPath()
  loadProfile()
  loadTeachingState()
  // 通知后端：用户访问了学习路径页面（触发 continue_path 任务完成）
  api.logTaskAction('visit_path').catch(() => {})
})
</script>

<style scoped>
.teaching-strategy-band {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  margin: 16px 0;
  border: 1px solid #cbd5e1;
  border-left: 4px solid #2563eb;
  background: #e2e8f0;
}
.teaching-strategy-band > div {
  display: grid;
  gap: 4px;
  padding: 13px 16px;
  background: #fff;
}
.teaching-strategy-band span, .teaching-strategy-band small {
  color: #64748b;
  font-size: 12px;
}
.path-version-band {
  margin: 16px 0;
  padding: 14px 16px;
  border: 1px solid #cbd5e1;
  border-left: 4px solid #2563eb;
  border-radius: 8px;
  background: #ffffff;
  display: grid;
  grid-template-columns: minmax(240px, 1fr) auto;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.path-version-main,
.path-diff-summary {
  display: flex;
  align-items: center;
  gap: 10px;
}

.path-version-main p {
  margin: 3px 0 0;
  color: #64748b;
  font-size: 12px;
}

.path-diff-summary > span {
  color: #475569;
  font-size: 13px;
}

.path-diff-detail {
  grid-column: 1 / -1;
  padding-top: 10px;
  border-top: 1px solid #e2e8f0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  color: #475569;
  font-size: 12px;
}

.path-diff-detail strong {
  color: #1e293b;
}

.node-resource-reason {
  padding: 10px 12px;
  border-left: 3px solid #0f766e;
  background: #f0fdfa;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.node-resource-reason span {
  color: #475569;
  font-size: 13px;
  line-height: 1.6;
}

@media (max-width: 720px) {
  .path-version-band {
    grid-template-columns: 1fr;
  }
  .path-diff-summary {
    align-items: flex-start;
    flex-direction: column;
  }
}

.resource-timing-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  color: #3b82f6;
  background: linear-gradient(135deg, #eff6ff, #dbeafe);
  border: 1px solid #bfdbfe;
  border-radius: 12px;
  padding: 1px 10px;
  white-space: nowrap;
}

.live-timer {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  font-weight: 500;
  color: #3b82f6;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 12px;
  padding: 1px 10px;
  margin-left: 8px;
  white-space: nowrap;
  animation: timer-pulse 2s ease-in-out infinite;
}

@keyframes timer-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

/* ======= Page ======= */
.path-page {
  max-width: 1200px;
  margin: 0 auto;
  animation: pathFadeIn 0.4s ease-out;
}

@keyframes pathFadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ======= Header ======= */
.path-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 28px 32px;
  margin-bottom: 24px;
  border-radius: var(--radius-xl, 20px);
  position: relative;
  overflow: hidden;
  background: linear-gradient(135deg, #eff6ff 0%, #f8faff 50%, #e0f2fe 100%);
  border: 1px solid #bfdbfe;
}

.path-header-bg-accent {
  position: absolute;
  inset: 0;
  background: none;
  pointer-events: none;
}
.path-header-bg-accent::before {
  content: '';
  position: absolute;
  top: -30px;
  right: -10px;
  width: 140px;
  height: 140px;
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.06);
}
.path-header-bg-accent::after {
  content: '';
  position: absolute;
  bottom: -20px;
  right: 80px;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: rgba(56, 189, 248, 0.06);
}

.path-header-left {
  display: flex;
  align-items: center;
  gap: 16px;
  position: relative;
  z-index: 1;
}

.path-header-icon {
  width: 52px;
  height: 52px;
  border-radius: var(--radius-lg, 12px);
  background: linear-gradient(135deg, var(--primary-500, #6366f1), var(--primary-600, #4f46e5));
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.35);
  flex-shrink: 0;
}

.path-title {
  font-size: 22px;
  font-weight: 800;
  color: var(--surface-900, #0f172a);
  margin: 0 0 4px;
  letter-spacing: -0.3px;
}

.path-desc {
  font-size: 14px;
  color: var(--surface-500, #64748b);
  margin: 0;
  line-height: 1.5;
  max-width: 520px;
}

.path-header-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12px;
  position: relative;
  z-index: 1;
  flex-shrink: 0;
}

.path-header-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.path-badge {
  border: none !important;
  font-weight: 600;
  font-size: 12px;
  padding: 0 12px;
  height: 24px;
  line-height: 24px;
  letter-spacing: 0.2px;
}
.path-badge.badge-portrait { background: #eef2ff; color: #4f46e5; border: 1px solid #c7d2fe !important; }
.path-badge.badge-dynamic { background: #ecfeff; color: #0891b2; border: 1px solid #cffafe !important; }
.path-badge.badge-resource { background: #f5f3ff; color: #7c3aed; border: 1px solid #ddd6fe !important; }
.path-badge.badge-closed { background: #ecfdf5; color: #059669; border: 1px solid #bbf7d0 !important; }

.path-header .el-button--primary {
  background: linear-gradient(135deg, #3b82f6, #3b82f6);
  border: none;
  border-radius: var(--radius-md, 8px);
  height: 40px;
  padding: 0 22px;
  font-weight: 600;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.3);
  transition: all 0.2s ease;
}

.path-header .el-button--primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4);
}

.path-header .el-button--primary:active {
  transform: translateY(0);
}

/* ======= Empty State ======= */
.path-empty {
  text-align: center;
  padding: 80px 20px;
  background: #ffffff;
  border: 1px dashed var(--surface-200, #e2e8f0);
  border-radius: var(--radius-xl, 16px);
  animation: pathFadeIn 0.4s ease-out;
}

.path-empty-icon {
  width: 100px;
  height: 100px;
  margin: 0 auto 20px;
  border-radius: 50%;
  background: linear-gradient(135deg, #eff6ff, #e0f2fe);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary-400, #818cf8);
}

.path-empty-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--surface-700, #334155);
  margin: 0 0 8px;
}

.path-empty-desc {
  font-size: 14px;
  color: var(--surface-400, #94a3b8);
  margin: 0;
}

/* ======= Path Plan ======= */
.path-plan {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ======= Progress Section ======= */
.path-progress-section {
  background: #ffffff;
  border: 1px solid var(--surface-100, #f1f5f9);
  border-radius: var(--radius-xl, 16px);
  padding: 18px 24px;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.05));
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.path-progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.path-progress-left {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-700, #334155);
}

.path-progress-header strong {
  font-size: 18px;
  font-weight: 700;
  color: var(--primary-600, #4f46e5);
}

/* ======= Profile Mini Cards ======= */
.profile-mini-grid {
  display: flex;
  flex-direction: row;
  gap: 12px;
}

.profile-mini-card {
  flex: 1;
  background: #ffffff;
  border: 1px solid var(--surface-100, #f1f5f9);
  border-radius: var(--radius-lg, 12px);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-sm, 0 1px 3px rgba(0,0,0,0.04));
  transition: all 0.25s ease;
}

.profile-mini-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md, 0 4px 12px rgba(0,0,0,0.08));
}

.mini-card-accent {
  height: 3px;
  flex-shrink: 0;
}

.mini-card-body {
  padding: 14px 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  text-align: center;
  align-items: center;
}

.mini-card-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--surface-400, #94a3b8);
  letter-spacing: 0.3px;
  line-height: 1.4;
}

.mini-card-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-800, #1e293b);
  line-height: 1.5;
  word-break: break-word;
}

/* ======= Strategy Card ======= */
.path-strategy-card {
  background: linear-gradient(135deg, #eff6ff 0%, #eff6ff 50%, #ffffff 100%);
  border: 1px solid #dbeafe;
  border-radius: var(--radius-xl, 16px);
  overflow: hidden;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.05));
  transition: box-shadow 0.2s ease;
}

.path-strategy-card:hover {
  box-shadow: var(--shadow-md, 0 4px 12px rgba(0,0,0,0.08));
}

.path-replan-card {
  margin-top: 18px;
}

.strategy-header {
  padding: 16px 22px;
  border-bottom: 1px solid rgba(99, 102, 241, 0.1);
}

.strategy-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.strategy-header-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, #eff6ff, #dbeafe);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary-600, #4f46e5);
  flex-shrink: 0;
}

.strategy-header-left div strong {
  display: block;
  font-size: 15px;
  font-weight: 600;
  color: var(--surface-800, #1e293b);
}

.strategy-header-left div span {
  display: block;
  font-size: 13px;
  color: var(--surface-400, #94a3b8);
  margin-top: 2px;
}

.strategy-body {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 18px 22px;
}

.strategy-agent-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: linear-gradient(135deg, #eff6ff, #f0fdf4);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary-500, #6366f1);
  flex-shrink: 0;
}

.strategy-text {
  flex: 1;
  font-size: 14px;
  color: var(--surface-600, #475569);
  line-height: 1.7;
  margin: 0;
}

.strategy-agents {
  display: flex;
  gap: 16px;
  padding: 12px 22px 18px;
  flex-wrap: wrap;
}

.strategy-agent {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--surface-500, #64748b);
}

.strategy-agent-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* ======= Timeline ======= */
.path-timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
  position: relative;
}

/* ======= Step Card ======= */
.path-step-card {
  display: flex;
  gap: 20px;
  position: relative;
  padding-bottom: 0;
}

.path-step-card:last-child .path-step-line {
  display: none;
}

.path-step-marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 40px;
  flex-shrink: 0;
  position: relative;
  padding-top: 4px;
}

.path-step-number {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--primary-500, #6366f1), var(--primary-600, #4f46e5));
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  box-shadow: 0 3px 8px rgba(99, 102, 241, 0.25);
  position: relative;
  z-index: 2;
  flex-shrink: 0;
  transition: all 0.3s ease;
}

.path-step-card.is-completed .path-step-number {
  background: linear-gradient(135deg, #10b981, #34d399);
  box-shadow: 0 3px 8px rgba(16, 185, 129, 0.3);
}

.path-step-card.is-current .path-step-number {
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.2), 0 3px 8px rgba(99, 102, 241, 0.25);
}

.path-step-card.is-locked .path-step-body {
  cursor: not-allowed;
  opacity: 0.6;
}

.path-step-card.is-locked .path-step-body:hover {
  transform: none;
  border-color: var(--surface-100, #f1f5f9);
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.05));
}

.path-step-line {
  width: 2px;
  flex: 1;
  min-height: 24px;
  background: linear-gradient(180deg, var(--primary-200, #c7d2fe) 0%, var(--surface-200, #e2e8f0) 100%);
  position: relative;
  z-index: 1;
}

/* ======= Step Body ======= */
.path-step-body {
  flex: 1;
  background: #ffffff;
  border: 1px solid var(--surface-100, #f1f5f9);
  border-radius: var(--radius-lg, 12px);
  padding: 20px 24px;
  margin-bottom: 20px;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.05));
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;
}

.path-step-body:hover {
  border-color: var(--primary-200, #c7d2fe);
  box-shadow: var(--shadow-md, 0 4px 12px -1px rgba(0,0,0,0.08));
  transform: translateX(4px);
}

.path-step-card.is-completed .path-step-body {
  border-left: 3px solid #10b981;
  background: linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%);
}

.path-step-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  margin-bottom: 10px;
  border-bottom: 1px solid var(--surface-100, #f1f5f9);
  gap: 12px;
}

.path-step-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.path-step-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--surface-800, #1e293b);
  margin: 0;
}

.path-step-time {
  font-size: 14px;
  color: var(--surface-400, #94a3b8);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.checkbox-label {
  font-size: 14px;
}

/* ======= Step Preview ======= */
.path-step-preview {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--primary-400, #818cf8);
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s ease;
}

.path-step-body:hover .path-step-preview {
  color: var(--primary-500, #6366f1);
  gap: 10px;
}

.path-step-preview-text {
  transition: all 0.2s ease;
}

/* ======= 步骤抽屉 ======= */
.step-drawer :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--surface-100, #f1f5f9);
}

.step-drawer :deep(.el-drawer__body) {
  padding: 20px 24px;
  overflow-y: auto;
}

.step-drawer-header {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
}

.step-drawer-header-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #3b82f6, #3b82f6);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 3px 8px rgba(99, 102, 241, 0.25);
}

.step-drawer-number {
  font-size: 16px;
  font-weight: 700;
  color: #ffffff;
}

.step-drawer-header-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.step-drawer-header-info strong {
  font-size: 17px;
  font-weight: 700;
  color: var(--surface-800, #1e293b);
  line-height: 1.3;
}

.step-drawer-header-info span {
  font-size: 14px;
  color: var(--surface-400, #94a3b8);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.step-drawer-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.step-drawer-completion {
  padding: 14px 16px;
  background: #f8fafc;
  border: 1px solid var(--surface-100, #f1f5f9);
  border-radius: var(--radius-md, 10px);
}

.drawer-checkbox-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-700, #334155);
}

.drawer-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.drawer-section-header {
  display: flex;
  align-items: center;
}

.drawer-section-tag {
  display: inline-block;
  padding: 2px 12px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 600;
  line-height: 22px;
}

.drawer-section-content {
  font-size: 14px;
  line-height: 1.7;
  color: var(--surface-700, #334155);
  padding: 0 4px;
}

.path-detail-markdown {
  display: block;
  width: 100%;
  max-width: none;
  color: var(--surface-700, #334155);
  white-space: normal;
  word-break: normal;
  overflow-wrap: break-word;
}

.path-detail-markdown :deep(p) {
  margin: 0;
  line-height: 1.55;
}

.path-detail-markdown :deep(strong) {
  font-weight: 700;
  color: var(--surface-800, #1e293b);
}

.path-detail-markdown :deep(code) {
  padding: 1px 5px;
  border-radius: 4px;
  background: #f1f5f9;
  color: #1d4ed8;
  font-size: 13px;
}

.goal-tag { background: #eff6ff; color: var(--primary-600, #4f46e5); }
.task-tag { background: #f0fdf4; color: #16a34a; }
.action-tag { background: #fff7ed; color: #ea580c; }
.resource-tag { background: #fdf2f8; color: #db2777; }
.output-tag { background: #eff6ff; color: #3b82f6; }
.checkpoint-tag { background: #fffbeb; color: #d97706; }

.path-raw-card {
  background: #ffffff;
  border: 1px solid var(--surface-100, #f1f5f9);
  border-radius: var(--radius-xl, 16px);
  padding: 28px 32px;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.05));
}

.path-raw-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding-bottom: 16px;
  margin-bottom: 18px;
  border-bottom: 1px solid var(--surface-100, #f1f5f9);
}

.path-raw-header strong {
  font-size: 16px;
  color: var(--surface-800, #1e293b);
}

.path-raw-header span {
  font-size: 14px;
  color: var(--surface-500, #64748b);
}

.path-raw-markdown {
  max-width: none;
}

.path-raw-markdown :deep(h2:first-child) {
  margin-top: 0;
}

/* ======= Loading Skeleton ======= */
.w-60 { width: 60%; }
.w-80 { width: 80%; }
.w-40 { width: 40%; }

/* ======= Path Generation Progress ======= */
.path-loading-progress {
  background:
    radial-gradient(circle at 92% 0%, rgba(14, 165, 233, 0.12), transparent 28%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.96));
  border: 1px solid rgba(199, 210, 254, 0.72);
  border-radius: var(--radius-xl, 16px);
  padding: 18px 20px;
  margin-bottom: 20px;
  box-shadow: 0 14px 34px rgba(79, 70, 229, 0.1);
}
.plp-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--surface-700, #334155);
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--surface-100, #f1f5f9);
}
.plp-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary-500, #6366f1);
  animation: plpPulse 1.4s ease-in-out infinite;
}
@keyframes plpPulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.8); }
}
.plp-steps {
  display: flex;
  align-items: stretch;
  gap: 10px;
  min-width: 0;
}
.plp-step {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 8px;
  position: relative;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(226, 232, 240, 0.72);
}
.plp-step.running {
  border-color: rgba(129, 140, 248, 0.58);
  background: rgba(238, 242, 255, 0.82);
}
.plp-step.done {
  border-color: rgba(16, 185, 129, 0.38);
  background: rgba(236, 253, 245, 0.78);
}
.plp-step-indicator {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  position: relative;
  z-index: 1;
}
.step-pending {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--surface-200, #e2e8f0);
  transition: all 0.3s ease;
}
.plp-step.running .step-pending { background: var(--primary-400, #818cf8); }
.step-running { color: var(--primary-500, #6366f1); }
.step-done { color: #10b981; }
.plp-step-body {
  flex: 1;
  min-width: 0;
}
.plp-step-body strong {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-800, #1e293b);
}
.plp-step-body span {
  display: block;
  font-size: 13px;
  color: var(--surface-400, #94a3b8);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.plp-step-tail {
  position: absolute;
  left: calc(100% - 1px);
  top: 50%;
  width: 12px;
  height: 2px;
  transform: translateY(-50%);
  z-index: 0;
  pointer-events: none;
}
.tail-line {
  width: 100%;
  height: 2px;
  background: var(--surface-200, #e2e8f0);
  transition: background 0.3s ease;
}
.tail-line.active {
  background: #10b981;
}
.plp-progress {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--surface-100, #f1f5f9);
  font-size: 14px;
  color: var(--primary-600, #4f46e5);
  display: flex;
  align-items: center;
  gap: 6px;
}

/* ======= El-Checkbox ======= */
:deep(.el-checkbox) {
  transition: all 0.2s ease;
}

:deep(.el-checkbox.is-checked) {
  transform: scale(1.05);
}

:deep(.el-checkbox.is-checked .el-checkbox__inner) {
  background-color: #10b981;
  border-color: #10b981;
}

/* ======= El-Progress ======= */
:deep(.el-progress) {
  background: var(--surface-100, #f1f5f9);
  border-radius: 10px;
}

:deep(.el-progress-bar__outer) {
  background: var(--surface-100, #f1f5f9) !important;
}

:deep(.el-progress-bar__inner) {
  border-radius: 10px !important;
  transition: width 0.8s ease;
}

/* ======= Responsive ======= */
@media (max-width: 900px) {
  .path-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
    padding: 24px 20px;
  }
  .path-header-right {
    align-items: flex-start;
    width: 100%;
  }
  .path-header-tags {
    justify-content: flex-start;
  }
  .path-step-body {
    padding: 16px;
  }
  .path-step-header {
    flex-direction: column;
    align-items: flex-start;
  }
  .strategy-body {
    flex-direction: column;
  }
  .plp-steps {
    flex-direction: column;
  }
  .plp-step {
    align-items: flex-start;
    padding: 10px 12px;
  }
  .plp-step-tail {
    left: 23px;
    top: 36px;
    bottom: -11px;
    width: 2px;
    height: auto;
    transform: none;
  }
  .plp-step-tail .tail-line {
    width: 2px;
    height: 100%;
  }
  .plp-step-body span {
    white-space: normal;
  }
}

@media (max-width: 600px) {
  .path-title {
    font-size: 18px;
  }
  .path-header-icon {
    width: 44px;
    height: 44px;
  }
  .path-step-marker {
    width: 32px;
  }
  .path-step-number {
    width: 28px;
    height: 28px;
    font-size: 13px;
  }
  .path-header-tags {
    flex-wrap: wrap;
  }
  .profile-mini-grid {
    flex-direction: column;
  }
}

/* ===== 资源自动生成进度 ===== */
.auto-resource-progress {
  margin-top: 24px;
  background: #ffffff;
  border-radius: var(--radius-lg, 12px);
  padding: 20px 24px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}
.auto-resource-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--primary-600, #4f46e5);
  margin-bottom: 16px;
}
.auto-resource-header .el-icon {
  color: var(--primary-500, #6366f1);
}
.auto-resource-steps {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.auto-resource-step {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 8px 0;
  transition: all 0.3s ease;
}
.auto-resource-step-indicator {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 2px;
}
.step-done-icon {
  color: #10b981;
}
.step-gen-icon {
  color: var(--primary-400, #818cf8);
}
.step-pending-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--surface-300, #cbd5e1);
}
.auto-resource-step.generating .step-pending-dot {
  background: var(--primary-400, #818cf8);
  animation: pulse 1.5s ease-in-out infinite;
}
.auto-resource-step-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}
.auto-resource-step-body strong {
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-700, #334155);
}
.auto-resource-step.completed .auto-resource-step-body strong {
  color: #10b981;
}
.auto-resource-step-body span {
  font-size: 12px;
  color: var(--surface-400, #94a3b8);
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.3); }
}
</style>
