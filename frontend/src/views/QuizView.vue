<template>
  <section class="quiz-page">
    <!-- Header -->
    <div class="quiz-header">
      <div class="quiz-header-left">
        <div class="quiz-header-icon">
          <el-icon :size="28"><EditPen /></el-icon>
        </div>
        <div>
          <h2 class="quiz-page-title">学习效果诊断中心</h2>
          <p class="quiz-desc">追踪练习表现，识别薄弱知识点并动态优化学习方案</p>
        </div>
      </div>
      <div class="quiz-header-badges">
        <el-tag size="small" effect="plain" round style="background:#eff6ff;color:#3b82f6;border-color:#bfdbfe;font-weight:600;">智能出题</el-tag>
        <el-tag size="small" effect="plain" round style="background:#ecfeff;color:#0891b2;border-color:#cffafe;font-weight:600;">自动诊断</el-tag>
        <el-tag size="small" effect="plain" round style="background:#fff7ed;color:#ea580c;border-color:#ffedd5;font-weight:600;">错题归因</el-tag>
        <el-tag size="small" effect="plain" round style="background:#f0fdf4;color:#059669;border-color:#dcfce7;font-weight:600;">路径更新</el-tag>
      </div>
    </div>

    <!-- Stat Cards -->
    <div class="quiz-stats">
      <div class="stat-card">
        <div class="stat-icon" style="background:#eff6ff;color:#3b82f6;">
          <el-icon :size="20"><EditPen /></el-icon>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ quizStats.latestScore }}</span>
          <span class="stat-label">最近测评分</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background:#f0fdf4;color:#059669;">
          <el-icon :size="20"><EditPen /></el-icon>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ quizStats.completedCount }}</span>
          <span class="stat-label">已完成测评</span>
        </div>
      </div>
      <el-tooltip
        placement="bottom"
        effect="light"
        :disabled="allWeakPoints.length === 0"
        :content="weakPointsTooltip"
      >
        <div class="stat-card">
          <div class="stat-icon" style="background:#fff7ed;color:#ea580c;">
            <el-icon :size="20"><EditPen /></el-icon>
          </div>
          <div class="stat-info">
            <span class="stat-value">{{ quizStats.weaknessCount }}</span>
            <span class="stat-label">薄弱知识点</span>
          </div>
        </div>
      </el-tooltip>
      <div class="stat-card">
        <div class="stat-icon" style="background:#ecfeff;color:#0891b2;">
          <el-icon :size="20"><EditPen /></el-icon>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ quizStats.masteryLevel }}</span>
          <span class="stat-label">平均分</span>
        </div>
      </div>
    </div>

    <!-- Workbench -->
    <div class="quiz-workbench">
      <!-- History Sidebar -->
      <aside class="quiz-history">
        <div class="history-header">
          <el-icon :size="18"><Clock /></el-icon>
          <span>历史记录</span>
        </div>
        <div class="history-list">
          <div
            v-for="item in evaluationHistoryRecords"
            :key="item.id"
            class="history-item"
            :class="{ active: selectedQuizRecord?.id === item.id }"
            @click="selectQuizHistory(item)"
          >
            <div class="history-item-top">
              <div class="history-title-row">
                <el-icon :size="14" class="history-item-icon"><EditPen /></el-icon>
                <strong class="history-title" :title="quizRecordTitle(item)">{{ quizRecordTitle(item) }}</strong>
              </div>
              <div class="history-actions">
                <el-button :icon="EditPen" size="small" text circle title="重命名记录" @click.stop="renameQuizRecord(item)" />
                <el-button :icon="Delete" size="small" text circle type="danger" title="删除记录" @click.stop="deleteQuizRecord(item)" />
              </div>
            </div>
            <div class="history-meta">
              <span class="history-time" :title="formatDateTime(item.created_at)">{{ formatDateTime(item.created_at) || '--' }}</span>
              <el-tag size="small" effect="plain" round>测评</el-tag>
              <span v-if="item.answers?.details?.length" class="history-score" :class="item.score >= 60 ? 'score-high' : 'score-low'">{{ scoreText(item.score) }}</span>
              <span v-else class="history-score score-none">未完成</span>
            </div>
          </div>
          <div v-if="evaluationHistoryRecords.length === 0" class="history-empty">
            <el-empty description="暂无测评记录" :image-size="80" />
          </div>
        </div>
      </aside>

      <!-- Main Content -->
      <main class="quiz-main">
        <!-- Toolbar -->
        <div class="quiz-toolbar">
          <div class="quiz-toolbar-left">
            <el-select v-model="quizForm.difficulty" style="width: 120px">
              <el-option label="基础" value="beginner" />
              <el-option label="中级" value="intermediate" />
              <el-option label="高级" value="advanced" />
            </el-select>
            <el-input v-model="quizForm.focus" placeholder="聚焦知识点" style="width: 180px" clearable>
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
            <div class="count-control">
              <span class="count-label">题数</span>
              <el-input-number v-model="quizForm.count" :min="3" :max="10" size="small" controls-position="right" />
            </div>
          </div>
          <el-button type="primary" :icon="EditPen" :loading="quizLoading" @click="handleGenerateQuiz">
            生成题目
          </el-button>
        </div>

        <!-- 只展示真实请求状态；后续接入 AgentRun 后再展示步骤级进度。 -->
        <div v-if="quizGenerating" class="quiz-generating">
          <div class="qg-header">
            <el-icon class="is-loading" :size="18"><Loading /></el-icon>
            <span>正在生成测评题目</span>
          </div>
          <div class="qg-progress">
            <span>后端正在根据当前主题、难度和画像生成题目</span>
            <span v-if="showTiming" class="live-timer">已耗时 {{ formatDuration(liveElapsed) }}</span>
          </div>
        </div>

        <!-- Question Area -->
        <div v-if="structuredQuiz && !quizGenerating" class="quiz-content">
          <div class="quiz-title-bar">
            <h2>{{ structuredQuiz.title }}</h2>
            <span v-if="showTiming && quizGenerationDuration" class="resource-timing-badge">生成耗时 {{ formatDuration(quizGenerationDuration) }}</span>
            <el-tag v-if="quizResult" :type="quizResult.score >= 60 ? 'success' : 'danger'" size="large" effect="dark">
              得分 {{ quizResult.score }}/100
            </el-tag>
          </div>

          <section v-for="question in structuredQuiz.questions" :key="question.id" class="question-card">
            <div class="question-heading">
              <span class="question-number">{{ question.id }}</span>
              <h3>{{ question.prompt }}</h3>
              <div class="question-tags">
                <el-tag size="small" effect="plain" round>{{ questionTypeLabel(question.type) }}</el-tag>
                <el-tag size="small" effect="plain" round type="info">{{ question.concept }}</el-tag>
              </div>
            </div>

            <div class="question-options">
              <el-checkbox-group v-if="question.type === 'multiple_choice'" v-model="quizAnswers[String(question.id)]" :disabled="Boolean(selectedQuizRecord)">
                <el-checkbox v-for="(option, optionIndex) in question.options" :key="option" :value="optionValue(optionIndex)" class="option-item">
                  {{ optionLabel(optionIndex, option) }}
                </el-checkbox>
              </el-checkbox-group>
              <el-radio-group v-else-if="question.options.length" v-model="quizAnswers[String(question.id)]" :disabled="Boolean(selectedQuizRecord)">
                <el-radio v-for="(option, optionIndex) in question.options" :key="option" :value="optionValue(optionIndex)" class="option-item">
                  {{ optionLabel(optionIndex, option) }}
                </el-radio>
              </el-radio-group>
              <el-input v-else v-model="quizAnswers[String(question.id)]" type="textarea" :rows="question.type === 'fill_blank' ? 2 : 3" placeholder="填写你的答案" :disabled="Boolean(selectedQuizRecord)" class="fill-input" />
            </div>

            <el-collapse class="hint-collapse">
              <el-collapse-item title="💡 提示" :name="`quiz-hint-${question.id}`">
                {{ question.hint }}
              </el-collapse-item>
            </el-collapse>

            <!-- Answer Result -->
            <div v-if="quizResult" class="answer-explain">
              <div class="answer-row">
                <span class="answer-label">作答结果</span>
                <el-tag size="small" :type="answerStatusType(getQuizDetail(question.id)?.status)" effect="dark" round>
                  {{ answerStatusLabel(getQuizDetail(question.id)?.status) }}
                </el-tag>
              </div>
              <div class="answer-row">
                <span class="answer-label">你的答案</span>
                <span class="answer-value">{{ getQuizDetail(question.id)?.user_answer || '未填写' }}</span>
              </div>
              <div class="answer-row">
                <span class="answer-label">参考答案</span>
                <span class="answer-value answer-ref">{{ getQuizDetail(question.id)?.reference_answer }}</span>
              </div>
              <div class="answer-row answer-row-explain">
                <span class="answer-label">解析</span>
                <span class="answer-value">{{ getQuizDetail(question.id)?.explanation }}</span>
              </div>
            </div>
          </section>

          <!-- Score Summary -->
          <div v-if="quizResult" class="score-summary-card">
            <div class="score-circle" :class="quizResult.score >= 60 ? 'score-pass' : 'score-fail'">
              <span class="score-number">{{ quizResult.score }}</span>
              <span class="score-unit">/100</span>
            </div>
            <div class="score-info">
              <h3>测评完成</h3>
              <p>{{ quizResult.summary }}</p>
            </div>
          </div>

          <section v-if="quizResult?.mastery_changes?.length" class="mastery-change-panel">
            <div class="result-panel-title">知识掌握度变化</div>
            <div
              v-for="change in quizResult.mastery_changes"
              :key="change.knowledge_point_id"
              class="mastery-change-row"
            >
              <strong>{{ change.knowledge_point }}</strong>
              <span>{{ Math.round(change.old) }}% → {{ Math.round(change.new) }}%</span>
              <el-tag :type="change.delta >= 0 ? 'success' : 'danger'" effect="plain">
                {{ change.delta > 0 ? '+' : '' }}{{ change.delta }}
              </el-tag>
              <small>{{ change.reason }}</small>
            </div>
          </section>

          <el-alert
            v-if="quizResult?.replanning?.triggered"
            title="学习路径已自动调整"
            type="warning"
            show-icon
            :closable="false"
            class="quiz-replanning"
          >
            <p>{{ quizResult.replanning.reason }}</p>
            <span v-if="quizResult.replanning.version_number">
              已生成路径 v{{ quizResult.replanning.version_number }}
            </span>
          </el-alert>

          <DigitalHumanPanel
            v-if="quizResult && selectedQuizRecord?.id"
            :key="selectedQuizRecord.id"
            :result-id="Number(selectedQuizRecord.id)"
            :score="Number(quizResult.score || 0)"
          />

          <!-- AI Evaluation -->
          <el-alert v-if="quizResult && evaluationLoading" title="AI 正在生成评价与建议..." type="warning" show-icon :closable="false" class="quiz-evaluation">
            <div class="evaluation-loading">
              <el-icon class="is-loading" :size="18"><Loading /></el-icon>
              <span>请稍候，AI 正在根据你的作答情况生成个性化的评价与学习建议...</span>
            </div>
          </el-alert>
          <el-alert v-if="quizResult && quizResult.evaluation && !evaluationLoading" title="AI 评价建议" type="warning" show-icon :closable="false" class="quiz-evaluation">
            <div v-if="currentWeakPoints.length" class="weak-points-panel">
              <span class="weak-points-label">薄弱知识点</span>
              <el-tag v-for="point in currentWeakPoints" :key="point" size="small" type="danger" effect="plain" round>{{ point }}</el-tag>
            </div>
            <div class="markdown" v-html="renderMarkdown(quizResult.evaluation)"></div>
          </el-alert>
          <!-- Readonly / Submit -->
          <el-alert v-if="selectedQuizRecord" title="当前正在查看历史答题记录，内容为只读。" type="info" show-icon :closable="false" class="quiz-readonly-alert" />
          <div v-else-if="structuredQuiz && !quizResult && !quizGenerating" class="submit-bar">
            <el-button type="primary" size="large" :icon="EditPen" :loading="quizLoading" @click="handleSubmitQuiz">
              提交答案并查看解析
            </el-button>
          </div>
        </div>

        <!-- Empty State -->
        <div v-else class="quiz-empty">
          <div class="quiz-empty-icon">
            <el-icon :size="52"><EditPen /></el-icon>
          </div>
          <h3>开始你的首次学习诊断</h3>
          <!-- <p class="quiz-empty-desc">系统将基于课程知识库和学生画像生成个性化题目，测评完成后自动识别薄弱点并更新学习路径。</p> -->
          <!-- <div class="quiz-quick-actions">
            <el-button size="default" round @click="quickQuiz('机器学习基础')">
              <el-icon style="margin-right:4px"><EditPen /></el-icon>
              机器学习基础测评
            </el-button>
            <el-button size="default" round @click="quickQuiz('强化学习专项')">
              <el-icon style="margin-right:4px"><EditPen /></el-icon>
              强化学习专项测评
            </el-button>
            <el-button size="default" round @click="quickQuiz('课程综合')">
              <el-icon style="margin-right:4px"><EditPen /></el-icon>
              课程综合测评
            </el-button>
          </div> -->
        </div>
      </main>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Clock, Delete, EditPen, Loading, Search } from '@element-plus/icons-vue'
import { api } from '../api/learning'
import { formatDateTime, getErrorMessage, scoreText, renderMarkdown } from '../composables/useUtils'
import { useQuiz } from '../composables/useQuiz'
import DigitalHumanPanel from '../components/digital-human/DigitalHumanPanel.vue'

const {
  quizLoading,
  quizForm,
  structuredQuiz,
  quizAnswers,
  quizResult,
  evaluationHistoryRecords,
  selectedQuizRecord,
  getQuizDetail,
  quizRecordTitle,
  questionTypeLabel,
  optionLabel,
  optionValue,
  answerStatusLabel,
  answerStatusType,
  generateQuiz,
  submitStructuredQuiz,
  loadQuizHistory,
  loadQuizHistoryByCategory,
  selectQuizHistory,
  renameQuizRecord,
  deleteQuizRecord,
} = useQuiz()

const evaluationLoading = ref(false)
const quizGenerationDuration = ref<number | null>(null)
const liveElapsed = ref(0)
let liveTimerInterval: ReturnType<typeof setInterval> | null = null
const showTiming = computed(() => import.meta.env.VITE_ENABLE_RESOURCE_TIMING === 'true')

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

const quizGenerating = ref(false)

function normalizeWeakPoint(value: unknown) {
  return String(value || '')
    .replace(/^第?\d+题[:：、.\s-]*/, '')
    .replace(/^(错题|知识点|概念)[:：\s]*/, '')
    .trim()
}

function extractWeakPointsFromRecord(record: any) {
  const payload = record?.answers || {}
  const points: string[] = []
  const pushPoint = (value: unknown) => {
    const text = normalizeWeakPoint(value)
    if (text && !points.includes(text)) points.push(text)
  }

  if (Array.isArray(payload.weak_points)) payload.weak_points.forEach(pushPoint)
  if (Array.isArray(payload.details)) {
    payload.details
      .filter((item: any) => item && !item.is_correct)
      .forEach((item: any) => pushPoint(item.concept || item.knowledge_point || item.id))
  }
  String(record?.wrong_questions || '')
    .split(/[;；、,，\n]/)
    .forEach(pushPoint)
  return points.slice(0, 8)
}

const currentWeakPoints = computed(() => {
  const fromResult = extractWeakPointsFromRecord({
    answers: {
      weak_points: quizResult.value?.weak_points,
      details: quizResult.value?.details || [],
    },
    wrong_questions: selectedQuizRecord.value?.wrong_questions,
  })
  if (fromResult.length) return fromResult
  return extractWeakPointsFromRecord(selectedQuizRecord.value)
})

const allWeakPoints = computed(() => {
  const points = new Set<string>()
  ;(evaluationHistoryRecords.value || [])
    .filter((record: any) => record.answers?.details?.length)
    .forEach((record: any) => extractWeakPointsFromRecord(record).forEach(point => points.add(point)))
  return Array.from(points).slice(0, 12)
})

const weakPointsTooltip = computed(() => {
  if (!allWeakPoints.value.length) return '暂无明确薄弱知识点'
  return allWeakPoints.value.join('、')
})

const quizStats = computed(() => {
  const records = evaluationHistoryRecords.value || []
  const completed = records.filter((r: any) => r.answers?.details?.length)
  const scores = completed
    .map((r: any) => Number(r.score))
    .filter((score: number) => Number.isFinite(score))
  const latestScore = scores.length > 0 ? `${Math.round(scores[0])}分` : '待测评'
  const avgScore = scores.length > 0 ? Math.round(scores.reduce((a: number, b: number) => a + b, 0) / scores.length) : 0
  return {
    latestScore,
    completedCount: completed.length,
    weaknessCount: completed.length > 0 ? allWeakPoints.value.length || '暂无' : '待测评',
    masteryLevel: scores.length > 0 ? `${avgScore}分` : '待测评',
  }
})

function quickQuiz(topic: string) {
  quizForm.focus = topic
  quizForm.difficulty = 'beginner'
  handleGenerateQuiz()
}

async function handleGenerateQuiz() {
  if (quizLoading.value) return
  evaluationLoading.value = false
  quizGenerationDuration.value = null
  const _quizGenStart = Date.now()
  startLiveTimer()
  quizGenerating.value = true
  try {
    await generateQuiz(quizForm.focus, quizForm.count, quizForm.difficulty)
    quizGenerationDuration.value = (Date.now() - _quizGenStart) / 1000
    liveElapsed.value = Math.floor((Date.now() - _quizGenStart) / 1000)
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    stopLiveTimer()
    quizGenerating.value = false
  }
}

async function handleSubmitQuiz() {
  try {
    await submitStructuredQuiz(undefined, 'evaluation')
    await runPostSubmitAnalysis()
  } catch (error) {
    evaluationLoading.value = false
    ElMessage.error(getErrorMessage(error))
  }
}

async function runPostSubmitAnalysis() {
  if (!quizResult.value) return
  evaluationLoading.value = true

  const payload = {
    quiz: structuredQuiz.value,
    answers: { ...quizAnswers },
    details: quizResult.value?.details || [],
    score: quizResult.value?.score || 0,
    record_id: selectedQuizRecord.value?.id,
  }

  try {
    const evaluationRes = await api.evaluateQuiz(payload)
    quizResult.value = {
      ...quizResult.value,
      evaluation: evaluationRes.data?.evaluation || buildLocalQuizEvaluation(),
      weak_points: evaluationRes.data?.weak_points || currentWeakPoints.value,
    }
  } catch {
    quizResult.value = {
      ...quizResult.value,
      evaluation: buildLocalQuizEvaluation(),
      weak_points: currentWeakPoints.value,
    }
  } finally {
    evaluationLoading.value = false
  }

  await loadQuizHistoryByCategory('evaluation')
}

function buildLocalQuizEvaluation() {
  const score = Number(quizResult.value?.score || 0)
  const details = quizResult.value?.details || []
  const wrong = details.filter((item: any) => item && !item.is_correct)
  const weakText = currentWeakPoints.value.length ? currentWeakPoints.value.join('、') : '暂无明确薄弱知识点'
  const level = score >= 85 ? '整体掌握较好' : score >= 60 ? '基础已经建立，但仍有局部薄弱点' : '当前掌握不够稳定，需要先回到基础概念'
  const wrongSummary = wrong.length
    ? `本次共有 ${wrong.length} 道题需要复盘，重点关注：${weakText}。`
    : '本次答题没有明显错误项，可以继续提高题目难度或做迁移练习。'
  return [
    '### 总体表现',
    `本次得分为 **${Math.round(score)} 分**，${level}。${wrongSummary}`,
    '### 学习建议',
    '- 先回顾错题对应的概念定义、适用条件和典型反例。',
    '- 对薄弱点做 2-3 道同类题，确认不是偶然答错。',
    '- 完成复盘后再生成学习路径或相关讲解文档，让后续资源围绕薄弱点展开。',
  ].join('\n\n')
}

onMounted(() => {
  loadQuizHistoryByCategory('evaluation')
  // 通知后端：用户访问了测评页面（触发 review_wrong_questions 任务完成）
  api.logTaskAction('visit_quiz').catch(() => {})
})

onUnmounted(() => {
  stopLiveTimer()
})
</script>

<style scoped>
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
.quiz-page {
  display: flex;
  flex-direction: column;
  max-width: 1380px;
  margin: 0 auto;
  width: 100%;
  min-height: 100%;
  overflow: visible;
  animation: quizFadeIn 0.4s ease-out;
}

@keyframes quizFadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ======= Header ======= */
.quiz-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24px 28px;
  margin-bottom: 24px;
  border-radius: var(--radius-xl, 16px);
  background: linear-gradient(135deg, #eff6ff 0%, #f8faff 50%, #e0f2fe 100%);
  border: 1px solid #bfdbfe;
  position: relative;
  overflow: hidden;
}

.quiz-header::before {
  content: '';
  position: absolute;
  top: -30px;
  right: -10px;
  width: 140px;
  height: 140px;
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.06);
  pointer-events: none;
}

.quiz-header::after {
  content: '';
  position: absolute;
  bottom: -20px;
  right: 80px;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: rgba(56, 189, 248, 0.06);
  pointer-events: none;
}

.quiz-header-left {
  display: flex;
  align-items: center;
  gap: 16px;
  position: relative;
  z-index: 1;
}

.quiz-header-icon {
  width: 52px;
  height: 52px;
  border-radius: var(--radius-lg, 12px);
  background: linear-gradient(135deg, var(--primary-500, #6366f1), var(--primary-600, #4f46e5));
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25);
  flex-shrink: 0;
}

.quiz-page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--surface-800, #1e293b);
  margin: 0 0 4px;
}

.quiz-desc {
  font-size: 14px;
  color: var(--surface-500, #64748b);
  margin: 0;
}

/* ======= Workbench Layout ======= */
.quiz-workbench {
  flex: 0 0 auto;
  min-height: 0;
  height: calc(100vh - 96px);
  display: flex;
  align-items: stretch;
  gap: 14px;
  overflow: hidden;
}

/* ======= History Sidebar ======= */
.quiz-history {
  order: 2;
  width: 44px;
  flex-shrink: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  max-height: none;
  position: relative;
  top: auto;
  background: linear-gradient(180deg, #eff6ff 0%, #e0f2fe 100%);
  border: 1px solid #dbeafe;
  border-radius: 14px;
  padding: 18px 10px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  margin-left: 0;
  z-index: 12;
  transition: width 0.26s ease, padding 0.26s ease, box-shadow 0.26s ease, margin-left 0.26s ease;
}

.quiz-history:hover {
  width: 260px;
  margin-left: -216px;
  padding: 18px 14px;
  background: #ffffff;
  box-shadow: -8px 0 28px rgba(99, 102, 241, 0.12), 0 1px 3px rgba(0,0,0,0.04);
}

.quiz-history:not(:hover) .history-header {
  justify-content: center;
  padding: 0 0 14px;
  border-bottom: none;
  height: 100%;
}

.quiz-history:not(:hover) .history-header .el-icon {
  display: none;
}

.quiz-history:not(:hover) .history-header span {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  letter-spacing: 4px;
  font-size: 14px;
  font-weight: 700;
  color: #3b82f6;
  opacity: 1;
  pointer-events: none;
}

.quiz-history:not(:hover) .history-list {
  opacity: 0;
  pointer-events: none;
}

.quiz-history .history-list,
.quiz-history .history-header span {
  transition: opacity 0.16s ease;
}

.history-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  padding: 0 6px 14px;
  border-bottom: 1px solid #f1f5f9;
  flex-shrink: 0;
}

.history-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-top: 10px;
  display: flex;
  flex-direction: column;
}

.history-list::-webkit-scrollbar {
  width: 4px;
}

.history-list::-webkit-scrollbar-track {
  background: transparent;
}

.history-list::-webkit-scrollbar-thumb {
  background: #e2e8f0;
  border-radius: 4px;
}

.history-item {
  padding: 12px 14px 12px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-bottom: 8px;
  border: 1px solid transparent;
  display: flex;
  flex-direction: column;
}

.history-item:last-child {
  margin-bottom: 0;
}

.history-item:hover {
  background: #f8fafc;
  border-color: #f1f5f9;
}

.history-item.active {
  background: #eff6ff;
  border-color: #bfdbfe;
}

.history-item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.history-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex: 1;
}

.history-item-icon {
  color: #3b82f6;
  flex-shrink: 0;
}

.history-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: block;
  max-width: 9em;
}

.history-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.history-item:hover .history-actions {
  opacity: 1;
}

.history-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding-left: 20px;
  padding-top: 4px;
}

.history-time {
  font-size: 13px;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 1;
  min-width: 0;
  margin-right: 2px;
}

.history-score {
  flex-shrink: 0;
  font-weight: 700;
  font-size: 13px;
  padding: 2px 10px;
  border-radius: 20px;
  line-height: 1.5;
  letter-spacing: 0.3px;
  transition: all 0.2s ease;
}

.history-score.score-high {
  color: #065f46;
  background: linear-gradient(135deg, #d1fae5, #a7f3d0);
}

.history-score.score-low {
  color: #991b1b;
  background: linear-gradient(135deg, #fee2e2, #fecaca);
}

.history-item:hover .history-score.score-high {
  box-shadow: 0 2px 6px rgba(16, 185, 129, 0.2);
}

.history-item:hover .history-score.score-low {
  box-shadow: 0 2px 6px rgba(239, 68, 68, 0.2);
}

.history-score.score-none {
  color: #94a3b8;
  background: #f1f5f9;
  font-weight: 500;
}

.history-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
}

/* ======= Main Content ======= */
.quiz-main {
  order: 1;
  flex: 1;
  min-width: 0;
  height: 100%;
  overflow-y: auto;
  background: #ffffff;
  border: 1px solid var(--surface-100, #f1f5f9);
  border-radius: var(--radius-xl, 16px);
  padding: 24px;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.05));
}

.quiz-main::-webkit-scrollbar {
  width: 4px;
}

.quiz-main::-webkit-scrollbar-track {
  background: transparent;
}

.quiz-main::-webkit-scrollbar-thumb {
  background: var(--surface-200, #e2e8f0);
  border-radius: 4px;
}

/* ======= Toolbar ======= */
.quiz-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 20px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--surface-100, #f1f5f9);
  gap: 12px;
  flex-wrap: wrap;
}

.quiz-toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.count-control {
  display: flex;
  align-items: center;
  gap: 8px;
}

.count-label {
  font-size: 14px;
  color: var(--surface-500, #64748b);
  font-weight: 500;
}

.quiz-toolbar .el-button--primary {
  background: linear-gradient(135deg, var(--primary-500, #6366f1), var(--primary-600, #4f46e5));
  border: none;
  border-radius: var(--radius-md, 8px);
  height: 36px;
  padding: 0 20px;
  font-weight: 500;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.3);
  transition: all 0.2s ease;
}

.quiz-toolbar .el-button--primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4);
}

/* ======= Title Bar ======= */
.quiz-title-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--surface-100, #f1f5f9);
}

.quiz-title-bar h2 {
  font-size: 18px;
  font-weight: 700;
  color: var(--surface-900, #0f172a);
  margin: 0;
}

/* ======= Question Card ======= */
.question-card {
  background: var(--surface-50, #f8fafc);
  border: 1px solid var(--surface-100, #f1f5f9);
  border-radius: var(--radius-lg, 12px);
  padding: 20px 24px;
  margin-bottom: 16px;
  transition: all 0.2s ease;
}

.question-card:hover {
  border-color: var(--primary-200, #c7d2fe);
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.05));
}

.question-heading {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.question-number {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--primary-500, #6366f1), var(--primary-600, #4f46e5));
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  flex-shrink: 0;
  margin-top: 1px;
}

.question-heading h3 {
  flex: 1;
  font-size: 15px;
  font-weight: 600;
  color: var(--surface-800, #1e293b);
  margin: 0;
  line-height: 1.6;
}

.question-tags {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
  flex-wrap: wrap;
}

/* ======= Options ======= */
.question-options {
  padding: 4px 0 4px 40px;
}

.option-item {
  display: flex;
  margin-bottom: 10px;
  margin-right: 0;
  padding: 10px 14px;
  border-radius: var(--radius-md, 8px);
  border: 1px solid var(--surface-100, #f1f5f9);
  background: #ffffff;
  transition: all 0.2s ease;
  width: 100%;
}

.option-item:hover {
  border-color: var(--primary-200, #c7d2fe);
  background: #eff6ff;
}

:deep(.el-radio)  { margin-right: 0; }
:deep(.el-checkbox) { margin-right: 0; }

.option-item:last-child {
  margin-bottom: 0;
}

.fill-input {
  padding: 0;
}

/* ======= Hint Collapse ======= */
:deep(.hint-collapse) {
  margin-top: 12px;
  margin-left: 40px;
}

:deep(.hint-collapse .el-collapse-item__header) {
  font-size: 14px;
  font-weight: 500;
  color: var(--surface-500, #64748b);
  padding-left: 8px;
  height: 36px;
  border-bottom: none;
}

:deep(.hint-collapse .el-collapse-item__wrap) {
  border-bottom: none;
}

:deep(.hint-collapse .el-collapse-item__content) {
  font-size: 14px;
  color: var(--surface-600, #475569);
  line-height: 1.6;
  padding: 4px 12px 12px;
}

/* ======= Answer Explain ======= */
.answer-explain {
  margin-top: 14px;
  margin-left: 40px;
  padding: 14px 16px;
  background: #ffffff;
  border: 1px solid var(--surface-100, #f1f5f9);
  border-radius: var(--radius-md, 8px);
  border-left: 3px solid var(--primary-500, #6366f1);
}

.answer-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 14px;
  line-height: 1.5;
}

.answer-row:last-child {
  margin-bottom: 0;
}

.answer-label {
  flex-shrink: 0;
  min-width: 64px;
  font-weight: 600;
  color: var(--surface-600, #475569);
  font-size: 14px;
}

.answer-value {
  color: var(--surface-700, #334155);
  flex: 1;
}

.answer-ref {
  color: var(--primary-600, #4f46e5);
  font-weight: 500;
}

.answer-row-explain .answer-value {
  color: var(--surface-600, #475569);
  line-height: 1.7;
}

/* ======= Score Summary ======= */
.score-summary-card {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 28px 32px;
  background: linear-gradient(135deg, #f8faff, #ffffff);
  border: 1px solid var(--surface-100, #f1f5f9);
  border-radius: var(--radius-xl, 16px);
  margin-bottom: 16px;
}

.score-circle {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.score-pass {
  background: linear-gradient(135deg, #d1fae5, #a7f3d0);
  color: #059669;
}

.score-fail {
  background: linear-gradient(135deg, #fee2e2, #fecaca);
  color: #dc2626;
}

.score-number {
  font-size: 32px;
  font-weight: 800;
  line-height: 1;
}

.score-unit {
  font-size: 13px;
  font-weight: 500;
  opacity: 0.7;
}

.score-info h3 {
  font-size: 18px;
  font-weight: 700;
  color: var(--surface-800, #1e293b);
  margin: 0 0 6px;
}

.score-info p {
  font-size: 14px;
  color: var(--surface-500, #64748b);
  margin: 0;
  line-height: 1.6;
}

.mastery-change-panel {
  margin-bottom: 16px;
  padding: 16px 18px;
  border: 1px solid #cbd5e1;
  border-left: 4px solid #2563eb;
  border-radius: 8px;
  background: #ffffff;
}

.result-panel-title {
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
}

.mastery-change-row {
  display: grid;
  grid-template-columns: minmax(120px, 1fr) auto auto minmax(160px, 2fr);
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-top: 1px solid #e2e8f0;
}

.mastery-change-row span,
.mastery-change-row small {
  color: #64748b;
}

.quiz-replanning {
  margin-bottom: 16px;
}

.quiz-replanning p {
  margin: 4px 0;
}

/* ======= Evaluation ======= */
.quiz-evaluation {
  margin-top: 0;
  margin-bottom: 16px;
}

.quiz-evaluation :deep(.el-alert__content) {
  width: 100%;
}

.quiz-evaluation :deep(.markdown) {
  font-size: 14px;
  line-height: 1.7;
  color: var(--surface-600, #475569);
  margin-top: 8px;
}

.evaluation-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--surface-600, #475569);
  margin-top: 8px;
}

.evaluation-loading .is-loading {
  animation: rotating 1.2s linear infinite;
}

.innovation-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 16px;
}

.quiz-trust-stack {
  margin-top: 0;
}

.innovation-loading-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 18px;
  border-radius: 14px;
  border: 1px dashed rgba(99, 102, 241, 0.38);
  background: linear-gradient(135deg, rgba(248, 250, 252, 0.96), rgba(238, 242, 255, 0.92));
  box-shadow: 0 12px 28px rgba(79, 70, 229, 0.08);
}

.innovation-loading-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 12px;
  color: #3b82f6;
  background: rgba(99, 102, 241, 0.12);
  flex: 0 0 auto;
}

.innovation-loading-icon .el-icon {
  font-size: 22px;
}

.innovation-loading-text strong {
  display: block;
  font-size: 15px;
  color: #1e293b;
  margin-bottom: 4px;
}

.innovation-loading-text p {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: #64748b;
}

.innovation-error {
  border-radius: 12px;
}

@keyframes rotating {
  to { transform: rotate(360deg); }
}

/* ======= Quiz Generation Progress ======= */
.quiz-generating {
  margin: 0 0 18px;
  padding: 18px 20px;
  border-radius: 16px;
  border: 1px solid rgba(199, 210, 254, 0.72);
  background:
    radial-gradient(circle at 92% 0%, rgba(14, 165, 233, 0.12), transparent 28%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.96));
  box-shadow: 0 14px 34px rgba(79, 70, 229, 0.1);
}
.qg-header {
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
.qg-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary-500, #6366f1);
  animation: qgPulse 1.4s ease-in-out infinite;
}
@keyframes qgPulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.8); }
}
.qg-steps {
  display: flex;
  align-items: stretch;
  gap: 10px;
  min-width: 0;
}
.qg-step {
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
.qg-step.running {
  border-color: rgba(129, 140, 248, 0.58);
  background: rgba(238, 242, 255, 0.82);
}
.qg-step.done {
  border-color: rgba(16, 185, 129, 0.38);
  background: rgba(236, 253, 245, 0.78);
}
.qg-step-indicator {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  position: relative;
  z-index: 1;
}
.step-pending-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--surface-200, #e2e8f0);
  transition: all 0.3s ease;
}
.qg-step.running .step-pending-dot { background: var(--primary-400, #818cf8); }
.step-running-icon { color: var(--primary-500, #6366f1); }
.step-done-icon { color: #10b981; }
.qg-step-body {
  flex: 1;
  min-width: 0;
}
.qg-step-body strong {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-800, #1e293b);
}
.qg-step-body span {
  display: block;
  font-size: 13px;
  color: var(--surface-400, #94a3b8);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.qg-step-tail {
  position: absolute;
  left: calc(100% - 1px);
  top: 50%;
  width: 12px;
  height: 2px;
  transform: translateY(-50%);
  z-index: 0;
  pointer-events: none;
}
.qg-step-tail .tail-line {
  width: 100%;
  height: 2px;
  background: var(--surface-200, #e2e8f0);
  transition: background 0.3s ease;
}
.qg-step-tail .tail-line.active {
  background: #10b981;
}
.qg-progress {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--surface-100, #f1f5f9);
  font-size: 14px;
  color: var(--primary-600, #4f46e5);
  display: flex;
  align-items: center;
  gap: 6px;
}

/* ======= Readonly Alert ======= */
.quiz-readonly-alert {
  margin-bottom: 0;
}

.weak-points-panel {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-md, 8px);
  background: #fff7ed;
  border: 1px solid #fed7aa;
}

.weak-points-label {
  font-size: 14px;
  font-weight: 700;
  color: #c2410c;
  margin-right: 2px;
}

/* ======= Submit Bar ======= */
.submit-bar {
  text-align: center;
  padding: 20px 0 8px;
}

.submit-bar .el-button--primary {
  background: linear-gradient(135deg, var(--primary-500, #6366f1), var(--primary-600, #4f46e5));
  border: none;
  border-radius: var(--radius-md, 8px);
  padding: 0 32px;
  height: 44px;
  font-size: 15px;
  font-weight: 600;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.3);
  transition: all 0.2s ease;
}

.submit-bar .el-button--primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4);
}

/* ======= Empty State ======= */
.quiz-empty {
  text-align: center;
  padding: 80px 20px;
}

.quiz-empty-icon {
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

.quiz-empty h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--surface-700, #334155);
  margin: 0 0 8px;
}

.quiz-empty p {
  font-size: 14px;
  color: var(--surface-400, #94a3b8);
  margin: 0;
}

/* ======= Header Badges ======= */
.quiz-header-badges {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  position: relative;
  z-index: 1;
  flex-wrap: wrap;
}

/* ======= Stat Cards ======= */
.quiz-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  flex-shrink: 0;
  margin-bottom: 24px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
  background: #ffffff;
  border: 1px solid #eef2f6;
  border-radius: 14px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  transition: all 0.25s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 14px rgba(0,0,0,0.06);
  border-color: #bfdbfe;
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-value {
  font-size: 20px;
  font-weight: 800;
  color: #0f172a;
  line-height: 1.2;
}

.stat-label {
  font-size: 14px;
  color: #64748b;
  font-weight: 500;
}

/* ======= Enhanced Empty State ======= */
.quiz-empty {
  text-align: center;
  padding: 60px 20px;
}

.quiz-empty-icon {
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

.quiz-empty h3 {
  font-size: 20px;
  font-weight: 700;
  color: #1e293b;
  margin: 0 0 10px;
}

.quiz-empty-desc {
  font-size: 14px;
  color: #94a3b8;
  margin: 0 auto 28px;
  max-width: 480px;
  line-height: 1.7;
}

.quiz-quick-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}

.quiz-quick-actions .el-button {
  border-radius: 9999px;
  padding: 8px 20px;
  font-weight: 500;
  border-color: #e2e8f0;
  color: #475569;
  transition: all 0.2s ease;
}

.quiz-quick-actions .el-button:hover {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #3b82f6;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.15);
}

/* ======= Responsive ======= */
@media (max-width: 1100px) {
  .quiz-stats {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 900px) {
  .quiz-workbench {
    flex-direction: column;
    height: auto;
    min-height: calc(100vh - 96px);
  }
  .quiz-history {
    width: 100%;
    max-height: 260px;
    padding: 18px 14px;
  }
  .quiz-history:hover { width: 100%; padding: 18px 14px; }
  .quiz-history:not(:hover) .history-header { justify-content: flex-start; padding: 0 6px 14px; }
  .quiz-history:not(:hover) .history-header span,
  .quiz-history:not(:hover) .history-list { opacity: 1; pointer-events: auto; }
  .quiz-main {
    min-height: calc(100vh - 220px);
  }
  .question-heading {
    flex-direction: column;
    gap: 8px;
  }
  .question-options {
    padding-left: 0;
  }
  :deep(.hint-collapse) {
    margin-left: 0;
  }
  .answer-explain {
    margin-left: 0;
  }
  .quiz-header-badges {
    display: none;
  }
  .quiz-quick-actions {
    flex-direction: column;
    align-items: center;
  }
  .quiz-stats {
    grid-template-columns: repeat(2, 1fr);
  }
  .qg-steps {
    flex-direction: column;
  }
  .qg-step {
    align-items: flex-start;
    padding: 10px 12px;
  }
  .qg-step-tail {
    left: 23px;
    top: 36px;
    bottom: -11px;
    width: 2px;
    height: auto;
    transform: none;
  }
  .qg-step-tail .tail-line {
    width: 2px;
    height: 100%;
  }
  .qg-step-body span {
    white-space: normal;
  }
}

@media (max-width: 600px) {
  .quiz-header {
    padding: 18px 20px;
  }
  .quiz-main {
    padding: 16px;
  }
  .quiz-toolbar {
    flex-direction: column;
    align-items: stretch;
  }
  .quiz-toolbar-left {
    flex-direction: column;
    align-items: stretch;
  }
  .quiz-toolbar-left .el-select,
  .quiz-toolbar-left .el-input {
    width: 100% !important;
  }
  .score-summary-card {
    flex-direction: column;
    text-align: center;
    padding: 24px 20px;
  }
  .mastery-change-row {
    grid-template-columns: minmax(0, 1fr) auto auto;
  }
  .mastery-change-row small {
    grid-column: 1 / -1;
  }
  .question-card {
    padding: 16px;
  }
}
</style>
