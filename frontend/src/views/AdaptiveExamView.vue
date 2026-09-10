<template>
  <section class="exam-page">
    <header class="page-head">
      <div>
        <h2>掌握度自适应测评</h2>
        <p>题量与知识点配比由当前掌握度、证据置信度和测评目标共同决定</p>
      </div>
    </header>

    <section class="config-band">
      <div class="config-item">
        <span>测评目标</span>
        <el-segmented v-model="form.goal" :options="goalOptions" />
      </div>
      <div class="config-item">
        <span>时长</span>
        <el-segmented v-model="form.duration_minutes" :options="durationOptions" />
      </div>
      <div class="config-item">
        <span>难度</span>
        <el-select v-model="form.difficulty">
          <el-option label="基础" value="beginner" />
          <el-option label="中等" value="intermediate" />
          <el-option label="进阶" value="advanced" />
        </el-select>
      </div>
      <el-button type="primary" :loading="generating" @click="createExam">生成测评</el-button>
    </section>

    <section v-if="exam" class="blueprint-panel">
      <header class="panel-head">
        <div>
          <strong>组卷蓝图</strong>
          <span>{{ exam.blueprint.strategy }}</span>
        </div>
        <el-tag effect="dark">{{ exam.blueprint.question_count }} 道 · {{ exam.duration_minutes }} 分钟</el-tag>
      </header>
      <div class="allocation-list">
        <div v-for="item in exam.blueprint.allocations" :key="item.knowledge_point_id" class="allocation-row">
          <div>
            <strong>{{ item.name }}</strong>
            <span>{{ item.reason }}</span>
          </div>
          <el-tag :type="stateType(item.state)" effect="plain">{{ stateLabel(item.state) }}</el-tag>
          <strong>{{ item.question_count }} 道</strong>
        </div>
      </div>
    </section>

    <section v-if="exam?.quiz?.questions?.length" class="question-panel">
      <header class="panel-head">
        <div>
          <strong>{{ exam.quiz.title }}</strong>
          <span>所有题目均绑定知识点与当前用户课程片段</span>
        </div>
        <el-button v-if="!result" type="success" :loading="submitting" @click="submitExam">提交测评</el-button>
        <el-tag v-else :type="result.score >= 60 ? 'success' : 'danger'" effect="dark">得分 {{ result.score }}</el-tag>
      </header>
      <article v-for="(question, index) in exam.quiz.questions" :key="question.id" class="question-row">
        <header>
          <span class="question-index">{{ index + 1 }}</span>
          <div>
           <h3>{{ question.prompt }}</h3>
            <div class="question-tags">
              <el-tag size="small" effect="plain">{{ question.concept }}</el-tag>
              <el-tag size="small" type="warning" effect="plain">
                {{ transferLabel(question.transfer_level) }}
              </el-tag>
            </div>
          </div>
        </header>
        <el-radio-group v-model="answers[String(question.id)]" :disabled="Boolean(result)" class="option-list">
          <el-radio
            v-for="(option, optionIndex) in question.options"
            :key="optionIndex"
            :value="String.fromCharCode(65 + optionIndex)"
            border
          >
            {{ String.fromCharCode(65 + optionIndex) }}. {{ option }}
          </el-radio>
        </el-radio-group>
        <div class="reasoning-box">
          <div>
            <strong>你的解题过程</strong>
            <span>可按步骤说明判断依据，系统据此定位第一处错误</span>
          </div>
          <el-input
            v-model="reasoningSteps[String(question.id)]"
            :disabled="Boolean(result)"
            type="textarea"
            :rows="2"
            placeholder="例如：先识别考查概念；再从课程材料提取条件；最后比较选项"
          />
          <div class="confidence-row">
            <span>作答自信度</span>
            <el-segmented
              v-model="selfConfidence[String(question.id)]"
              :disabled="Boolean(result)"
              :options="confidenceOptions"
            />
          </div>
        </div>
        <el-alert
          v-if="result"
          :type="detailFor(question.id)?.is_correct ? 'success' : 'error'"
          :title="detailFor(question.id)?.is_correct ? '回答正确' : `正确答案：${detailFor(question.id)?.reference_answer}`"
          :description="question.explanation"
          :closable="false"
          show-icon
        />
        <div v-if="result && diagnosisFor(question.id)" class="cognitive-result">
          <header>
            <strong>认知过程诊断</strong>
            <el-tag
              :type="diagnosisFor(question.id).overall_status === 'no_error' ? 'success' : 'danger'"
              effect="plain"
            >
              {{ diagnosisStatusLabel(diagnosisFor(question.id).overall_status) }}
            </el-tag>
          </header>
          <p>{{ diagnosisFor(question.id).summary }}</p>
          <div class="step-chain">
            <div
              v-for="step in diagnosisFor(question.id).steps || []"
              :key="step.id || step.step_index"
              :class="['cognitive-step', step.error_role]"
            >
              <span>{{ step.step_index }}</span>
              <div>
                <strong>{{ step.concept }}</strong>
                <small>{{ stepStatusLabel(step.status) }} · {{ errorRoleLabel(step.error_role) }}</small>
                <p v-if="step.student">你的过程：{{ step.student }}</p>
                <p>标准过程：{{ step.expected }}</p>
                <el-popover v-if="step.course_sources?.length" width="360" trigger="click">
                  <template #reference><el-button link type="primary">查看课程依据</el-button></template>
                  <div v-for="source in step.course_sources" :key="source.chunk_id" class="source-line">
                    <strong>课程片段 #{{ source.chunk_id }}</strong>
                    <span>{{ source.excerpt }}</span>
                  </div>
                </el-popover>
              </div>
            </div>
          </div>
        </div>
      </article>
    </section>

    <section v-if="teachingStrategy || intervention?.triggered" class="strategy-panel">
      <header class="panel-head">
        <div>
          <strong>下一步教学策略</strong>
          <span>由掌握度、误区、过程错误、先修依赖和迁移证据共同选择</span>
        </div>
        <el-tag v-if="teachingStrategy" type="primary" effect="dark">
          {{ teachingStrategy.strategy_label }}
        </el-tag>
      </header>
      <div v-if="teachingStrategy" class="strategy-body">
        <div>
          <span>选择依据</span>
          <div class="tag-list">
            <el-tag v-for="reason in teachingStrategy.reason_codes" :key="reason" effect="plain">
              {{ reason }}
            </el-tag>
          </div>
        </div>
        <div>
          <span>接下来会执行</span>
          <ol><li v-for="action in teachingStrategy.action_labels" :key="action">{{ action }}</li></ol>
        </div>
        <el-alert
          v-if="teachingStrategy.switched"
          title="教学策略已根据本次新证据切换"
          type="warning"
          :closable="false"
          show-icon
        />
      </div>
      <el-alert
        v-if="intervention?.triggered"
        class="intervention-alert"
        :title="`已启动主动干预：${intervention.reason}`"
        :description="`已生成路径版本 v${intervention.path_version?.version_number || '--'}，可前往学习路径执行新任务。`"
        type="error"
        :closable="false"
        show-icon
      />
    </section>

    <section v-if="capabilityRows.length" class="capability-panel">
      <header class="panel-head">
        <div><strong>多维能力门槛</strong><span>基础掌握不等于迁移就绪，缺少证据的维度保持未知</span></div>
      </header>
      <el-table :data="capabilityRows" row-key="knowledge_point_id">
        <el-table-column prop="knowledge_point" label="知识点" min-width="160" />
        <el-table-column label="能力状态" width="150">
          <template #default="{ row }"><el-tag effect="plain">{{ capabilityLabel(row.capability_state) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="迁移掌握度" width="130">
          <template #default="{ row }">{{ masteryText(row.dimensions?.transfer?.mastery_score) }}</template>
        </el-table-column>
        <el-table-column prop="conclusion" label="结论" min-width="250" />
      </el-table>
    </section>

    <section v-if="report" class="report-panel">
      <header class="panel-head">
        <div><strong>测评后掌握度变化</strong><span>{{ report.summary }}</span></div>
      </header>
      <el-table :data="report.knowledge_point_breakdown || []">
        <el-table-column prop="knowledge_point" label="知识点" min-width="180" />
        <el-table-column prop="question_count" label="题数" width="80" />
        <el-table-column prop="accuracy" label="正确率" width="100">
          <template #default="{ row }">{{ row.accuracy }}%</template>
        </el-table-column>
        <el-table-column label="掌握度变化" min-width="180">
          <template #default="{ row }">
            {{ masteryText(row.mastery_before) }} → {{ masteryText(row.mastery_after) }}
            <el-tag v-if="row.mastery_delta !== null" size="small" :type="row.mastery_delta >= 0 ? 'success' : 'danger'">
              {{ row.mastery_delta >= 0 ? '+' : '' }}{{ row.mastery_delta }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <AgentTracePanel :run="agentRun" class="trace-space" />

    <section class="history-panel">
      <header class="panel-head">
        <div><strong>自适应测评历史</strong><span>可回看蓝图、目标和最终成绩</span></div>
        <el-button :icon="Refresh" circle @click="loadHistory" />
      </header>
      <el-table :data="history">
        <el-table-column prop="created_at" label="生成时间" min-width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="goal" label="目标" width="110">
          <template #default="{ row }">{{ goalLabel(row.goal) }}</template>
        </el-table-column>
        <el-table-column prop="duration_minutes" label="时长" width="90">
          <template #default="{ row }">{{ row.duration_minutes }} 分钟</template>
        </el-table-column>
        <el-table-column label="题数" width="80">
          <template #default="{ row }">{{ row.blueprint?.question_count || 0 }}</template>
        </el-table-column>
        <el-table-column label="成绩" width="100">
          <template #default="{ row }">{{ row.result?.score ?? '未提交' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }"><el-button link type="primary" @click="openExam(row.id)">查看</el-button></template>
        </el-table-column>
      </el-table>
    </section>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import AgentTracePanel from '../components/AgentTracePanel.vue'
import { api } from '../api/learning'
import { getErrorMessage } from '../composables/useUtils'

const form = reactive({
  goal: 'diagnosis' as 'diagnosis' | 'reinforcement' | 'mock' | 'comprehensive' | 'transfer',
  duration_minutes: 30,
  difficulty: 'intermediate',
})
const goalOptions = [
  { label: '诊断', value: 'diagnosis' },
  { label: '强化', value: 'reinforcement' },
  { label: '模拟', value: 'mock' },
  { label: '综合', value: 'comprehensive' },
  { label: '迁移', value: 'transfer' },
]
const durationOptions = [
  { label: '15 分钟', value: 15 },
  { label: '30 分钟', value: 30 },
  { label: '60 分钟', value: 60 },
]
const exam = ref<any>(null)
const answers = reactive<Record<string, string>>({})
const reasoningSteps = reactive<Record<string, string>>({})
const selfConfidence = reactive<Record<string, number>>({})
const result = ref<any>(null)
const report = ref<any>(null)
const agentRun = ref<any>(null)
const history = ref<any[]>([])
const generating = ref(false)
const submitting = ref(false)
const cognitiveDiagnoses = ref<any[]>([])
const teachingStrategy = ref<any>(null)
const intervention = ref<any>(null)
const capability = ref<Record<string, any>>({})
const capabilityRows = ref<any[]>([])
const confidenceOptions = [
  { label: '不确定', value: 25 },
  { label: '一般', value: 50 },
  { label: '较确定', value: 75 },
  { label: '很确定', value: 100 },
]

async function createExam() {
  generating.value = true
  result.value = null
  report.value = null
  Object.keys(answers).forEach(key => delete answers[key])
  Object.keys(reasoningSteps).forEach(key => delete reasoningSteps[key])
  Object.keys(selfConfidence).forEach(key => delete selfConfidence[key])
  cognitiveDiagnoses.value = []
  teachingStrategy.value = null
  intervention.value = null
  capability.value = {}
  capabilityRows.value = []
  try {
    const { data } = await api.createAdaptiveExam(form)
    exam.value = data.exam
    agentRun.value = data.agent_run
    ElMessage.success('组卷蓝图和题目已通过校验')
    await loadHistory()
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    generating.value = false
  }
}

async function submitExam() {
  if (!exam.value) return
  const missing = exam.value.quiz.questions.filter((q: any) => !answers[String(q.id)])
  if (missing.length) {
    ElMessage.warning(`还有 ${missing.length} 道题未作答`)
    return
  }
  submitting.value = true
  try {
    const { data } = await api.submitAdaptiveExam(
      exam.value.id,
      answers,
      reasoningSteps,
      selfConfidence,
    )
    result.value = data.result
    report.value = data.report
    agentRun.value = data.agent_run
    applyCognitivePayload(data)
    ElMessage.success('测评完成，掌握度和后续路径已更新')
    await loadHistory()
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    submitting.value = false
  }
}

async function loadHistory() {
  try {
    const { data } = await api.getAdaptiveExams()
    history.value = data.exams || []
  } catch { /* keep current page usable */ }
}

async function openExam(id: number) {
  try {
    const { data } = await api.getAdaptiveExam(id)
    exam.value = data.exam
    agentRun.value = data.agent_run
    const saved = data.exam.result?.answers || {}
    Object.assign(answers, saved.submitted || {})
    Object.assign(reasoningSteps, saved.reasoning_steps || {})
    Object.assign(selfConfidence, saved.self_confidence || {})
    result.value = saved.details?.length
      ? { score: data.exam.result.score, details: saved.details, summary: data.exam.result.analysis }
      : null
    report.value = saved.adaptive_report || null
    applyCognitivePayload(saved)
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}

function detailFor(id: number) {
  return result.value?.details?.find((item: any) => String(item.id) === String(id))
}
function diagnosisFor(id: number) {
  return cognitiveDiagnoses.value.find(item => String(item.question_id) === String(id))
}
function applyCognitivePayload(payload: any) {
  cognitiveDiagnoses.value = payload.cognitive_diagnoses || []
  teachingStrategy.value = payload.teaching_strategy || null
  intervention.value = payload.intervention || null
  capability.value = payload.capability || {}
  capabilityRows.value = Object.values(capability.value)
}
function masteryText(value: unknown) {
  return value === null || value === undefined ? '未测评' : `${Math.round(Number(value) * 100) / 100}%`
}
function stateLabel(state: string) {
  return ({ stable: '稳定', consolidate: '巩固', focus: '薄弱', unknown: '未测评' } as any)[state] || state
}
function stateType(state: string) {
  return ({ stable: 'success', consolidate: 'warning', focus: 'danger', unknown: 'info' } as any)[state] || 'info'
}
function goalLabel(goal: string) {
  return ({ diagnosis: '诊断', reinforcement: '强化', mock: '模拟', comprehensive: '综合', transfer: '迁移' } as any)[goal] || goal
}
function transferLabel(level: string) {
  return ({ L1: 'L1 原型', L2: 'L2 变式', L3: 'L3 迁移' } as any)[level] || '基础题'
}
function diagnosisStatusLabel(status: string) {
  return ({ no_error: '过程正确', root_error: '已定位根因', insufficient_evidence: '证据不足' } as any)[status] || status
}
function stepStatusLabel(status: string) {
  return ({ correct: '正确', incorrect: '错误', uncertain: '不确定', not_observed: '未观察到' } as any)[status] || status
}
function errorRoleLabel(role: string) {
  return ({ none: '无错误', root_error: '根因错误', derived_error: '传播错误', independent_error: '独立错误', uncertain: '待确认' } as any)[role] || role
}
function capabilityLabel(state: string) {
  return ({
    FOUNDATION_GAP: '基础缺口',
    BASIC_UNSTABLE: '基础不稳',
    BASIC_MASTERED: '基础掌握',
    APPLICATION_READY: '应用就绪',
    TRANSFER_WEAK: '迁移薄弱',
    TRANSFER_READY: '迁移就绪',
  } as any)[state] || state
}
function formatTime(value: string) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '--'
}

onMounted(loadHistory)
</script>

<style scoped>
.exam-page { max-width: 1180px; margin: 0 auto; color: #172033; }
.page-head { padding: 4px 0 18px; }
.page-head h2 { margin: 0 0 6px; font-size: 22px; }
.page-head p, .panel-head span { margin: 0; color: #64748b; font-size: 13px; }
.config-band { display: grid; grid-template-columns: 1.4fr 1fr 150px auto; align-items: end; gap: 16px; padding: 16px 18px; border: 1px solid #e2e8f0; background: #fff; border-radius: 6px; margin-bottom: 14px; }
.config-item { display: grid; gap: 8px; }
.config-item > span { color: #475569; font-size: 12px; font-weight: 600; }
.blueprint-panel, .question-panel, .report-panel, .history-panel, .strategy-panel, .capability-panel { border: 1px solid #e2e8f0; background: #fff; border-radius: 6px; margin-bottom: 14px; overflow: hidden; }
.panel-head { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 15px 18px; border-bottom: 1px solid #e2e8f0; }
.panel-head > div { display: grid; gap: 4px; }
.allocation-list { padding: 6px 18px; }
.allocation-row { display: grid; grid-template-columns: minmax(0, 1fr) 90px 54px; align-items: center; gap: 12px; padding: 12px 0; border-bottom: 1px solid #eef2f7; }
.allocation-row:last-child { border: 0; }
.allocation-row > div { display: grid; gap: 3px; }
.allocation-row span { color: #64748b; font-size: 12px; }
.question-row { padding: 20px 22px; border-bottom: 1px solid #e2e8f0; }
.question-row:last-child { border: 0; }
.question-row > header { display: grid; grid-template-columns: 30px 1fr; gap: 12px; }
.question-index { width: 28px; height: 28px; display: grid; place-items: center; background: #eff6ff; color: #2563eb; border-radius: 4px; font-weight: 700; }
.question-row h3 { margin: 2px 0 8px; font-size: 15px; line-height: 1.6; }
.question-tags, .tag-list { display: flex; flex-wrap: wrap; gap: 6px; }
.option-list { display: grid; gap: 8px; margin: 16px 0; }
.option-list .el-radio { width: 100%; height: auto; min-height: 42px; padding: 8px 12px; margin: 0; white-space: normal; }
.reasoning-box { display: grid; gap: 9px; padding: 13px; margin: 12px 0; background: #f8fafc; border-left: 3px solid #2563eb; }
.reasoning-box > div:first-child { display: grid; gap: 3px; }
.reasoning-box span, .strategy-body > div > span { color: #64748b; font-size: 12px; }
.confidence-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.cognitive-result { margin-top: 12px; padding: 14px; border: 1px solid #dbeafe; background: #f8fbff; }
.cognitive-result > header { display: flex; justify-content: space-between; align-items: center; }
.cognitive-result > p { margin: 8px 0 12px; color: #475569; font-size: 13px; }
.step-chain { display: grid; gap: 8px; }
.cognitive-step { display: grid; grid-template-columns: 28px 1fr; gap: 10px; padding: 10px; background: #fff; border-left: 3px solid #94a3b8; }
.cognitive-step.root_error { border-color: #dc2626; }
.cognitive-step.derived_error { border-color: #f59e0b; }
.cognitive-step > span { width: 25px; height: 25px; display: grid; place-items: center; background: #e2e8f0; border-radius: 50%; font-weight: 700; }
.cognitive-step > div { display: grid; gap: 3px; }
.cognitive-step small, .source-line span { color: #64748b; }
.cognitive-step p { margin: 2px 0; font-size: 12px; }
.source-line { display: grid; gap: 4px; margin-bottom: 10px; }
.strategy-body { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; padding: 16px 18px; }
.strategy-body > div { display: grid; gap: 8px; }
.strategy-body ol { margin: 0; padding-left: 20px; color: #475569; line-height: 1.8; font-size: 13px; }
.strategy-body .el-alert { grid-column: 1 / -1; }
.intervention-alert { margin: 0 18px 18px; }
.trace-space { margin-bottom: 14px; }
@media (max-width: 900px) {
  .config-band { grid-template-columns: 1fr; align-items: stretch; }
  .allocation-row { grid-template-columns: 1fr auto; }
  .allocation-row > strong { grid-column: 2; }
  .strategy-body { grid-template-columns: 1fr; }
  .confidence-row { align-items: stretch; flex-direction: column; }
}
</style>
