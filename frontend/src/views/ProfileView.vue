<template>
  <section class="profile-page">
    <!-- Hero Banner -->
    <div class="profile-hero">
      <div class="hero-bg-accent"></div>
      <div class="hero-content">
        <div class="hero-left">
          <div class="hero-avatar">
            <el-icon :size="28"><UserFilled /></el-icon>
          </div>
          <div class="hero-text">
            <h1 class="hero-title">对话式学生画像</h1>
            <p class="hero-desc">基于学习过程，动态构建你的个性化学习画像</p>
          </div>
        </div>
        <el-button type="primary" :icon="MagicStick" :loading="draftLoading" @click="analyzeProfile">
          整理画像草稿
        </el-button>
      </div>
    </div>

    <!-- Form Card -->
    <div class="profile-card">
      <div class="intake-section">
        <div class="form-section-title">
          <span class="section-dot"></span>
          AI 学习建档助手
          <el-tag v-if="currentVersion" size="small" effect="plain">当前 v{{ currentVersion }}</el-tag>
        </div>
        <el-input
          v-model="dialogue"
          type="textarea"
          :rows="4"
          resize="vertical"
          placeholder="例如：我是计算机专业学生，一个月后参加考试，基础一般，每周能学习 7 小时，更喜欢图解和代码实践，目前对递归比较薄弱。"
        />
        <div class="intake-actions">
          <span>AI 只整理你明确提供的信息，确认前不会写入画像。</span>
          <el-button :icon="MagicStick" :loading="draftLoading" @click="analyzeProfile">生成草稿</el-button>
        </div>
        <div v-if="profileDraft" class="draft-notice">
          <div>
            <strong>待确认画像</strong>
            <span>{{ extractionLabel }} · {{ draftChanges.length }} 个字段有变化</span>
          </div>
          <el-button text :icon="Close" @click="cancelDraft">取消草稿</el-button>
        </div>
      </div>

      <el-form label-position="top">
        <!-- Section: 用户填写 -->
        <div class="form-section">
          <div class="form-section-title">
            <span class="section-dot"></span>
            用户填写
          </div>
          <el-row :gutter="20">
            <el-col :xs="24" :sm="12" :md="8">
              <el-form-item label="课程主题">
                <el-input v-model="profileForm.topic" :prefix-icon="Notebook" placeholder="例如：人工智能导论" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12" :md="8">
              <el-form-item label="专业方向">
                <el-input v-model="profileForm.major" :prefix-icon="School" placeholder="例如：计算机科学与技术" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12" :md="8">
              <el-form-item label="可用时间">
                <el-input v-model="profileForm.time_availability" :prefix-icon="Clock" placeholder="例如：3-5 hours per week" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :xs="24" :sm="12" :md="8">
              <el-form-item label="学习目标">
                <el-input v-model="profileForm.learning_goal" :prefix-icon="Flag" placeholder="描述你的学习目标" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12" :md="8">
              <el-form-item label="实践水平">
                <el-select v-model="profileForm.practice_level" style="width: 100%">
                  <el-option label="入门" value="beginner" />
                  <el-option label="中级" value="intermediate" />
                  <el-option label="进阶" value="advanced" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12" :md="8">
              <el-form-item label="每周学习分钟">
                <el-input-number v-model="profileForm.weekly_time_minutes" :min="1" :max="10080" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <div class="confirm-row">
            <span v-if="!profileDraft">修改字段后确认，会保存一个有证据的新版本。</span>
            <span v-else>请检查 AI 草稿，可继续修改后再确认。</span>
            <el-button type="primary" :icon="Check" :loading="confirmLoading" @click="confirmProfile">
              确认并保存
            </el-button>
          </div>
        </div>

        <!-- Section: 系统动态更新 -->
        <div class="form-section form-section-last">
          <div class="form-section-title">
            <span class="section-dot section-dot--green"></span>
            系统动态更新
            <el-tag size="small" effect="plain" type="info" round>根据你的学习行为自动调整</el-tag>
          </div>
          <div class="profile-grid">
            <div class="profile-card-item">
              <div class="card-accent"></div>
              <div class="card-body">
                <span class="card-label">知识水平</span>
                <span class="card-value" :title="formatKnowledgeLevel(profileDisplay.knowledge_level)">{{ formatKnowledgeLevel(profileDisplay.knowledge_level) }}</span>
              </div>
            </div>
            <div class="profile-card-item">
              <div class="card-accent"></div>
              <div class="card-body">
                <span class="card-label">学习风格</span>
                <span class="card-value" :title="formatLearningStyle(profileDisplay.learning_style)">{{ formatLearningStyle(profileDisplay.learning_style) }}</span>
              </div>
            </div>
            <div class="profile-card-item">
              <div class="card-accent"></div>
              <div class="card-body">
                <span class="card-label">认知偏好</span>
                <span class="card-value" :title="profileDisplay.cognitive_preference || '暂无数据'">{{ profileDisplay.cognitive_preference || '暂无数据' }}</span>
              </div>
            </div>
            <div class="profile-card-item">
              <div class="card-accent"></div>
              <div class="card-body">
                <span class="card-label">过往经验</span>
                <span class="card-value" :title="profileDisplay.prior_experience || '暂无数据'">{{ profileDisplay.prior_experience || '暂无数据' }}</span>
              </div>
            </div>
            <div class="profile-card-item">
              <div class="card-accent"></div>
              <div class="card-body">
                <span class="card-label">学习动机</span>
                <span class="card-value" :title="profileDisplay.motivation_driver || '暂无数据'">{{ profileDisplay.motivation_driver || '暂无数据' }}</span>
              </div>
            </div>
            <div class="profile-card-item">
              <div class="card-accent"></div>
              <div class="card-body">
                <span class="card-label">参与习惯</span>
                <span class="card-value" :title="profileDisplay.engagement_pattern || '暂无数据'">{{ profileDisplay.engagement_pattern || '暂无数据' }}</span>
              </div>
            </div>
            <div class="profile-card-item profile-card-item--wide">
              <div class="card-accent card-accent--danger"></div>
              <div class="card-body">
                <span class="card-label">薄弱知识点</span>
                <div class="card-tags" v-if="profileDisplay.weakPoints.length" :title="profileDisplay.weakPoints.join('、')">
                  <el-tag v-for="tag in profileDisplay.weakPoints" :key="tag" size="small" type="danger" effect="plain" round>{{ tag }}</el-tag>
                </div>
                <span class="card-value" v-else>暂无数据</span>
              </div>
            </div>
          </div>
        </div>
      </el-form>
    </div>

    <section class="mastery-section">
      <div class="history-header">
        <div>
          <h2>知识点掌握度</h2>
          <p>
            已评估 {{ masterySummary.assessed || 0 }} /
            {{ masterySummary.total_knowledge_points || 0 }} 个知识点
          </p>
        </div>
        <el-button :icon="Refresh" circle aria-label="刷新掌握度" @click="loadMastery" />
      </div>
      <el-collapse v-if="masteryItems.length" class="mastery-list">
        <el-collapse-item
          v-for="item in masteryItems"
          :key="item.knowledge_point_id"
          :name="item.knowledge_point_id"
        >
          <template #title>
            <div class="mastery-title">
              <div>
                <strong>{{ item.knowledge_point }}</strong>
                <span>{{ item.knowledge_point_code }}</span>
              </div>
              <el-tag
                size="small"
                :type="masteryTagType(item)"
                effect="plain"
              >
                {{ masteryStateLabel(item) }}
              </el-tag>
              <el-progress
                class="mastery-progress"
                :percentage="item.mastery_score == null ? 0 : Math.round(item.mastery_score)"
                :stroke-width="7"
                :show-text="item.mastery_score != null"
              />
            </div>
          </template>
          <div v-if="item.evidence?.length" class="mastery-evidence">
            <div v-for="evidence in item.evidence" :key="evidence.id" class="mastery-evidence-row">
              <el-tag size="small" effect="plain">{{ eventTypeLabel(evidence.event_type) }}</el-tag>
              <span>{{ evidence.description || '学习事件证据' }}</span>
              <strong :class="{ positive: evidence.delta > 0, negative: evidence.delta < 0 }">
                {{ evidence.delta > 0 ? '+' : '' }}{{ evidence.delta }}
              </strong>
              <time>{{ formatDateTime(evidence.created_at) }}</time>
            </div>
          </div>
          <el-empty v-else description="尚无可用于计算掌握度的证据" :image-size="40" />
        </el-collapse-item>
      </el-collapse>
      <el-empty v-else description="课程知识点尚未建立" :image-size="48" />
    </section>

    <section class="profile-history">
      <div class="history-header">
        <div>
          <h2>真实画像演进</h2>
          <p>只展示数据库中的版本和证据，不补造历史事件。</p>
        </div>
        <el-button :icon="Refresh" circle aria-label="刷新画像版本" @click="loadHistory" />
      </div>
      <el-timeline v-if="versions.length">
        <el-timeline-item
          v-for="version in versions"
          :key="version.id"
          :timestamp="formatDateTime(version.created_at)"
          placement="top"
        >
          <div class="version-entry">
            <div class="version-title">
              <strong>v{{ version.version }}</strong>
              <span>{{ version.change_summary }}</span>
            </div>
            <div class="evidence-list">
              <div v-for="item in version.evidence || []" :key="item.id" class="evidence-row">
                <el-tag size="small" effect="plain">{{ evidenceTypeLabel(item.evidence_type) }}</el-tag>
                <strong>{{ fieldLabel(item.dimension) }}</strong>
                <span>{{ formatEvidenceChange(item) }}</span>
              </div>
            </div>
          </div>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="暂无画像版本" :image-size="48" />
    </section>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, Clock, Close, Flag, MagicStick, Notebook, Refresh, School, UserFilled } from '@element-plus/icons-vue'
import { api } from '../api/learning'
import { formatDateTime, formatKnowledgeLevel, formatLearningStyle, getErrorMessage } from '../composables/useUtils'

const profileForm = reactive({
  topic: '人工智能导论',
  major: '计算机科学与技术',
  learning_goal: '',
  time_availability: '',
  practice_level: 'beginner',
  weekly_time_minutes: undefined as number | undefined,
})

const profileDisplay = reactive({
  knowledge_level: 'beginner',
  learning_style: 'mixed',
  cognitive_preference: '',
  prior_experience: '',
  motivation_driver: '',
  engagement_pattern: '',
  weakPoints: [] as string[],
})

const dialogue = ref('')
const draftLoading = ref(false)
const confirmLoading = ref(false)
const profileDraft = ref<any | null>(null)
const draftChanges = ref<any[]>([])
const extractionLabel = ref('')
const extractionConfidence = ref(1)
const currentVersion = ref(0)
const versions = ref<any[]>([])
const masteryItems = ref<any[]>([])
const masterySummary = ref<Record<string, number>>({})

function applyProfile(profile: any, sources: Array<Record<string, any>> = []) {
  profileForm.topic = profile.topic || '人工智能导论'
  profileForm.major = profile.major || '计算机科学与技术'
  profileForm.learning_goal = profile.learning_goal || ''
  profileForm.time_availability = profile.time_availability || ''
  profileForm.practice_level = profile.practice_level || 'beginner'
  profileForm.weekly_time_minutes = profile.weekly_time_minutes || undefined
  updateDisplay(profile, sources)
}

function updateDisplay(profile: any, sources: Array<Record<string, any>> = []) {
  if (profile.knowledge_level) profileDisplay.knowledge_level = profile.knowledge_level
  if (profile.learning_style) profileDisplay.learning_style = profile.learning_style
  if (profile.cognitive_preference) profileDisplay.cognitive_preference = profile.cognitive_preference
  if (profile.prior_experience) profileDisplay.prior_experience = profile.prior_experience
  if (profile.motivation_driver) profileDisplay.motivation_driver = profile.motivation_driver
  if (profile.engagement_pattern) profileDisplay.engagement_pattern = profile.engagement_pattern
  if (sources.length) {
    profileDisplay.weakPoints = sources.map(item => String(item.name || '').trim()).filter(Boolean)
  } else if (profile.weak_points) {
    profileDisplay.weakPoints = Array.isArray(profile.weak_points)
      ? profile.weak_points
      : String(profile.weak_points).split(/[;；、,，\n]/).map((s: string) => s.trim()).filter(Boolean)
  }
}

async function loadProfile() {
  try {
    const { data } = await api.getProfile()
    const p = data.profile || {}
    currentVersion.value = data.current_version?.version || 0
    applyProfile(p, data.weak_points_sources || [])
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}

async function analyzeProfile() {
  if (!dialogue.value.trim()) {
    ElMessage.warning('请先描述你的学习情况')
    return
  }
  if (draftLoading.value) return
  draftLoading.value = true
  try {
    const { data } = await api.draftProfileIntake({
      dialogue: dialogue.value,
      ...profileForm,
    })
    profileDraft.value = data.draft
    draftChanges.value = data.changes || []
    extractionConfidence.value = data.extraction?.confidence || 1
    extractionLabel.value = data.extraction?.provider === 'mimo'
      ? `MiMo ${data.extraction?.model || ''}`
      : '本地确定性抽取'
    currentVersion.value = data.current_version || currentVersion.value
    applyProfile(data.draft || {})
    ElMessage.success('画像草稿已生成，请确认后保存')
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    draftLoading.value = false
  }
}

async function confirmProfile() {
  if (confirmLoading.value) return
  confirmLoading.value = true
  const draft = {
    ...(profileDraft.value || {}),
    ...profileForm,
  }
  try {
    const { data } = await api.confirmProfileIntake({
      draft,
      dialogue: dialogue.value,
      confidence: extractionConfidence.value,
      expected_version: currentVersion.value,
    })
    applyProfile(data.profile || {}, data.weak_points_sources || [])
    currentVersion.value = data.version?.version || currentVersion.value
    cancelDraft(false)
    dialogue.value = ''
    await loadHistory()
    ElMessage.success(data.idempotent ? '画像没有变化，无需创建新版本' : `画像 v${currentVersion.value} 已保存`)
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    confirmLoading.value = false
  }
}

function cancelDraft(restore = true) {
  profileDraft.value = null
  draftChanges.value = []
  extractionLabel.value = ''
  extractionConfidence.value = 1
  if (restore) loadProfile()
}

async function loadHistory() {
  try {
    const { data } = await api.getProfileVersions()
    versions.value = data.versions || []
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}

async function loadMastery() {
  try {
    const { data } = await api.getMastery(true)
    masteryItems.value = data.mastery || []
    masterySummary.value = data.summary || {}
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}

function masteryStateLabel(item: any) {
  if (item.state === 'unassessed') return '未评估'
  if (item.state === 'insufficient_evidence') {
    return `${Math.round(item.mastery_score)}% · 证据不足`
  }
  return `${Math.round(item.mastery_score)}% · 已评估`
}

function masteryTagType(item: any) {
  if (item.state === 'unassessed') return 'info'
  if (Number(item.mastery_score) < 45) return 'danger'
  if (Number(item.mastery_score) < 70) return 'warning'
  return 'success'
}

function eventTypeLabel(type: string) {
  const labels: Record<string, string> = {
    question_correct: '答对',
    question_wrong: '答错',
    question_partial: '部分正确',
    resource_complete: '完成资源',
    hint_request: '请求提示',
    code_run: '代码通过',
    code_error: '代码错误',
  }
  return labels[type] || type
}

const FIELD_LABELS: Record<string, string> = {
  profile_snapshot: '画像快照',
  dialogue_context: '建档原话',
  topic: '课程主题',
  major: '专业方向',
  knowledge_level: '知识水平',
  learning_goal: '学习目标',
  learning_style: '学习风格',
  cognitive_preference: '认知偏好',
  prior_experience: '过往经验',
  time_availability: '可用时间',
  motivation_driver: '学习动机',
  engagement_pattern: '参与习惯',
  weak_points: '薄弱知识点',
  preferred_resource_types: '资源偏好',
  weekly_time_minutes: '每周学习时间',
  practice_level: '实践水平',
}

function fieldLabel(field: string) {
  return FIELD_LABELS[field] || field
}

function evidenceTypeLabel(type: string) {
  const labels: Record<string, string> = {
    dialogue: '建档对话',
    assessment: '测评',
    question_error: '错题',
    tutor_session: '辅导',
    learning_behavior: '学习行为',
    resource_feedback: '资源反馈',
    migration_snapshot: '初始快照',
  }
  return labels[type] || type
}

function displayValue(value: any): string {
  if (value === null || value === undefined || value === '') return '空'
  if (Array.isArray(value)) return value.join('、') || '空'
  if (typeof value === 'object') return '完整画像快照'
  return String(value)
}

function formatEvidenceChange(item: any) {
  if (item.dimension === 'profile_snapshot') return '保存迁移时的当前真实状态'
  return `${displayValue(item.old_value)} → ${displayValue(item.new_value)}`
}

onMounted(() => {
  Promise.all([loadProfile(), loadHistory(), loadMastery()])
})
</script>

<style scoped>
/* ======= Page ======= */
.profile-page {
  max-width: 960px;
  margin: 0 auto;
  animation: fadeIn 0.4s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ======= Hero Banner ======= */
.profile-hero {
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
  gap: 24px;
}

.hero-left {
  display: flex;
  align-items: center;
  gap: 18px;
  min-width: 0;
}

.hero-avatar {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  background: linear-gradient(135deg, var(--primary-500, #6366f1), var(--primary-600, #4f46e5));
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.35);
  flex-shrink: 0;
}

.hero-text { min-width: 0; }

.hero-title {
  font-size: 22px;
  font-weight: 800;
  color: var(--surface-900, #0f172a);
  margin: 0 0 6px;
  line-height: 1.25;
  letter-spacing: -0.3px;
}

.hero-desc {
  font-size: 14px;
  color: var(--surface-500, #64748b);
  margin: 0;
  line-height: 1.6;
}

/* Hero button */
.hero-content .el-button--primary {
  background: linear-gradient(135deg, #3b82f6, #3b82f6);
  border: none;
  border-radius: 10px;
  height: 42px;
  padding: 0 24px;
  font-weight: 600;
  box-shadow: 0 4px 20px rgba(99, 102, 241, 0.4);
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.hero-content .el-button--primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 30px rgba(99, 102, 241, 0.5);
}

.hero-content .el-button--primary:active {
  transform: translateY(0);
}

/* ======= Form Card ======= */
.profile-card {
  background: #ffffff;
  border: 1px solid #cbd5e1;
  border-radius: var(--radius-xl, 16px);
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.05));
  padding: 28px 28px 20px;
  transition: box-shadow 0.2s ease;
}

.profile-card:hover {
  box-shadow: var(--shadow-md, 0 4px 6px -1px rgba(0,0,0,0.07));
}

.intake-section {
  margin-bottom: 28px;
  padding-bottom: 24px;
  border-bottom: 1px solid #d1d5db;
}

.intake-actions,
.draft-notice,
.confirm-row,
.history-header,
.version-title,
.evidence-row {
  display: flex;
  align-items: center;
}

.intake-actions,
.confirm-row,
.history-header,
.draft-notice {
  justify-content: space-between;
}

.intake-actions {
  gap: 16px;
  margin-top: 10px;
}

.intake-actions span,
.confirm-row span,
.history-header p,
.draft-notice span {
  font-size: 12px;
  color: var(--surface-500, #64748b);
}

.draft-notice {
  margin-top: 14px;
  padding: 10px 12px;
  border-left: 3px solid #2563eb;
  background: #eff6ff;
}

.draft-notice > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.draft-notice strong {
  font-size: 13px;
  color: #1e3a8a;
}

.confirm-row {
  gap: 16px;
  margin-top: 4px;
  padding-top: 16px;
  border-top: 1px dashed #cbd5e1;
}

.profile-history,
.mastery-section {
  margin-top: 20px;
  padding: 20px 24px 8px;
  background: #ffffff;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
}

.mastery-title {
  width: 100%;
  min-width: 0;
  padding-right: 14px;
  display: grid;
  grid-template-columns: minmax(160px, 1fr) auto minmax(160px, 260px);
  align-items: center;
  gap: 12px;
}

.mastery-title > div {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.mastery-title span {
  color: #64748b;
  font-size: 12px;
}

.mastery-progress {
  min-width: 0;
}

.mastery-evidence {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px 0 10px;
}

.mastery-evidence-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: #475569;
}

.mastery-evidence-row time {
  color: #94a3b8;
}

.mastery-evidence-row .positive {
  color: #047857;
}

.mastery-evidence-row .negative {
  color: #b91c1c;
}

.history-header {
  margin-bottom: 20px;
}

.history-header h2 {
  margin: 0 0 3px;
  font-size: 16px;
  color: var(--surface-800, #1e293b);
}

.history-header p {
  margin: 0;
}

.version-entry {
  padding: 12px 14px;
  border: 1px solid var(--surface-200, #e2e8f0);
  border-radius: 8px;
}

.version-title {
  gap: 10px;
  margin-bottom: 10px;
}

.version-title strong {
  color: #1d4ed8;
}

.version-title span {
  font-size: 13px;
  color: var(--surface-700, #334155);
}

.evidence-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.evidence-row {
  gap: 8px;
  min-width: 0;
  font-size: 12px;
}

.evidence-row strong {
  flex-shrink: 0;
  color: var(--surface-700, #334155);
}

.evidence-row > span {
  min-width: 0;
  overflow: hidden;
  color: var(--surface-500, #64748b);
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ======= Form Sections ======= */
.form-section {
  margin-bottom: 28px;
  padding-bottom: 28px;
  border-bottom: 1px solid #d1d5db;
}

.form-section-last {
  margin-bottom: 0;
  padding-bottom: 0;
  border-bottom: none;
}

.form-section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 15px;
  font-weight: 600;
  color: var(--surface-800, #1e293b);
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px dashed #cbd5e1;
}

.section-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary-500, #6366f1);
  flex-shrink: 0;
}

.section-dot--green {
  background: #10b981 !important;
}

/* ======= Form Items ======= */
:deep(.el-form-item) {
  margin-bottom: 22px;
}

:deep(.el-form-item:last-child) {
  margin-bottom: 0;
}

:deep(.el-form-item__label) {
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-700, #334155);
  padding-bottom: 6px;
}

:deep(.el-input__wrapper),
:deep(.el-textarea__inner) {
  border-radius: var(--radius-md, 8px);
  transition: all 0.2s ease;
  box-shadow: 0 0 0 1px #cbd5e1 inset;
}

:deep(.el-input__wrapper:hover),
:deep(.el-textarea__inner:hover) {
  box-shadow: 0 0 0 1px var(--primary-300, #c7d2fe) inset;
}

:deep(.el-input__wrapper.is-focus),
:deep(.el-textarea__inner:focus) {
  box-shadow: 0 0 0 1px var(--primary-500, #6366f1) inset !important;
}

:deep(.el-input__inner) {
  padding-left: 4px;
}

/* ======= Profile Card Grid ======= */
.profile-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}

.profile-card-item {
  background: #ffffff;
  border: 1px solid #d1d5db;
  border-radius: var(--radius-lg, 12px);
  overflow: hidden;
  transition: all 0.25s ease;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.03));
  display: flex;
  flex-direction: column;
  min-height: 112px;
  max-height: 128px;
}

.profile-card-item:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md, 0 4px 6px -1px rgba(0,0,0,0.07));
}

.profile-card-item--wide {
  grid-column: span 2;
}

.card-accent {
  height: 3px;
  flex-shrink: 0;
  background: linear-gradient(90deg, #10b981, #34d399);
}

.card-accent--danger {
  background: linear-gradient(90deg, #ef4444, #f87171);
}

.card-body {
  padding: 14px 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  min-height: 0;
}

.card-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--surface-400, #94a3b8);
  line-height: 1.4;
  letter-spacing: 0.3px;
  text-transform: uppercase;
}

.card-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-800, #1e293b);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding: 2px 0;
  max-height: 54px;
  overflow: hidden;
}

/* Override el-tag inside card-tags to reduce vertical space */
.card-tags :deep(.el-tag) {
  margin: 0;
}

/* ======= Responsive ======= */
@media (max-width: 768px) {
  .mastery-title {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .mastery-progress {
    grid-column: 1 / -1;
  }
  .mastery-evidence-row {
    grid-template-columns: auto minmax(0, 1fr) auto;
  }
  .mastery-evidence-row time {
    grid-column: 2 / -1;
  }
  .hero-content {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
    padding: 24px 20px;
  }
  .hero-left {
    flex-wrap: wrap;
  }
  .hero-title {
    font-size: 18px;
  }
  .hero-avatar {
    width: 44px;
    height: 44px;
  }
  .profile-card {
    padding: 20px;
  }
  .intake-actions,
  .confirm-row {
    align-items: stretch;
    flex-direction: column;
  }
  .intake-actions .el-button,
  .confirm-row .el-button {
    width: 100%;
  }
  .profile-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .profile-card-item--wide {
    grid-column: span 2;
  }
}

@media (max-width: 480px) {
  .profile-grid {
    grid-template-columns: 1fr;
  }
  .profile-card-item--wide {
    grid-column: span 1;
  }
}
</style>
