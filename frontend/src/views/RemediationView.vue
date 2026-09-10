<template>
  <section class="remediation-page">
    <header class="page-head">
      <div>
        <h2>一键补救计划</h2>
        <p>先修知识、课程材料、即时练习和复测组成可执行闭环</p>
      </div>
      <div class="head-actions">
        <el-select v-model="selectedPointId" placeholder="选择薄弱知识点" filterable>
          <el-option
            v-for="item in targets"
            :key="item.knowledge_point_id"
            :label="`${item.name} · ${masteryText(item.mastery_score)}`"
            :value="item.knowledge_point_id"
          />
        </el-select>
        <el-button type="primary" :loading="creating" @click="createPlan">生成补救计划</el-button>
      </div>
    </header>

    <div v-if="currentPlan" class="plan-summary">
      <div>
        <span>当前目标</span>
        <strong>{{ currentPlan.target_knowledge_point }}</strong>
      </div>
      <div>
        <span>掌握度</span>
        <strong>{{ masteryText(currentPlan.initial_mastery) }} → {{ masteryText(currentPlan.target_mastery) }}</strong>
      </div>
      <div>
        <span>预计用时</span>
        <strong>{{ currentPlan.estimated_minutes }} 分钟</strong>
      </div>
      <div>
        <span>路径版本</span>
        <strong>v{{ currentPlan.path_version_number }}</strong>
      </div>
      <div class="summary-action">
        <el-button
          type="success"
          :loading="starting"
          :disabled="currentPlan.status === 'completed'"
          @click="startPlan"
        >
          {{ currentPlan.status === 'active' ? '继续补救' : currentPlan.status === 'completed' ? '已达成目标' : '开始学习' }}
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="currentPlan"
      :title="currentPlan.reason"
      type="warning"
      :closable="false"
      show-icon
      class="reason-band"
    />

    <div class="workspace">
      <section class="steps-panel">
        <header class="panel-head">
          <div>
            <strong>执行步骤</strong>
            <span>节点状态与学习路径实时同步</span>
          </div>
          <el-button v-if="currentPlan" link type="primary" @click="showWhy">为什么这样安排？</el-button>
        </header>
        <el-empty v-if="!currentPlan" description="选择薄弱知识点并生成补救计划" />
        <div v-else class="step-list">
          <article v-for="step in currentPlan.steps" :key="step.id" class="plan-step">
            <div class="step-index">{{ step.step_order }}</div>
            <div class="step-body">
              <header>
                <strong>{{ step.title }}</strong>
                <el-tag :type="stepType(step)" effect="plain">{{ statusLabel(step.status) }}</el-tag>
              </header>
              <p>{{ step.reason }}</p>
              <div class="step-meta">
                <span>{{ step.estimated_minutes }} 分钟</span>
                <span v-if="step.resource?.resource">{{ step.resource.resource.title }}</span>
              </div>
            </div>
          </article>
        </div>
      </section>

      <aside class="history-panel">
        <header class="panel-head">
          <div><strong>历史计划</strong><span>保留每次补救版本</span></div>
          <el-button :icon="Refresh" circle @click="load" />
        </header>
        <button
          v-for="plan in plans"
          :key="plan.id"
          class="history-item"
          :class="{ active: currentPlan?.id === plan.id }"
          @click="selectPlan(plan)"
        >
          <span>{{ plan.target_knowledge_point }}</span>
          <small>v{{ plan.path_version_number }} · {{ statusLabel(plan.status) }}</small>
        </button>
      </aside>
    </div>

    <AgentTracePanel :run="agentRun" class="trace-space" />

    <el-drawer v-model="whyVisible" title="决策依据" size="460px">
      <template v-if="explanation">
        <h3>{{ explanation.decision }}</h3>
        <h4>原因</h4>
        <ul><li v-for="item in explanation.reasons" :key="item">{{ item }}</li></ul>
        <h4>触发条件</h4>
        <p>{{ explanation.trigger }}</p>
        <h4>可选动作</h4>
        <ul><li v-for="item in explanation.alternatives" :key="item">{{ item }}</li></ul>
      </template>
    </el-drawer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import AgentTracePanel from '../components/AgentTracePanel.vue'
import { api } from '../api/learning'
import { getErrorMessage } from '../composables/useUtils'

const diagnosis = ref<any>(null)
const plans = ref<any[]>([])
const currentPlan = ref<any>(null)
const selectedPointId = ref<number>()
const agentRun = ref<any>(null)
const creating = ref(false)
const starting = ref(false)
const whyVisible = ref(false)
const explanation = ref<any>(null)

const targets = computed(() => diagnosis.value?.weakness_ranking || [])

async function load() {
  try {
    const [diagnosisRes, plansRes] = await Promise.all([
      api.getDiagnosis(),
      api.getRemediationPlans(),
    ])
    diagnosis.value = diagnosisRes.data.diagnosis
    plans.value = plansRes.data.plans || []
    if (!selectedPointId.value) {
      selectedPointId.value = diagnosis.value?.recommended_target?.knowledge_point_id
    }
    if (!currentPlan.value && plans.value.length) selectPlan(plans.value[0])
    else if (currentPlan.value) {
      const fresh = plans.value.find(item => item.id === currentPlan.value.id)
      if (fresh) currentPlan.value = fresh
    }
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}

async function selectPlan(plan: any) {
  currentPlan.value = plan
  selectedPointId.value = plan.target_knowledge_point_id
  agentRun.value = null
  if (plan.agent_run_id) {
    try {
      const { data } = await api.getAgentRun(plan.agent_run_id)
      agentRun.value = data.run
    } catch { /* plan remains usable */ }
  }
}

async function createPlan() {
  if (!selectedPointId.value) {
    ElMessage.warning('请先选择一个薄弱知识点')
    return
  }
  creating.value = true
  try {
    const { data } = await api.createRemediationPlan(selectedPointId.value)
    currentPlan.value = data.plan
    agentRun.value = data.agent_run
    ElMessage.success(data.reused ? '已复用未完成计划' : '补救计划已生成并通过校验')
    await load()
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    creating.value = false
  }
}

async function startPlan() {
  if (!currentPlan.value) return
  starting.value = true
  try {
    const { data } = await api.startRemediationPlan(currentPlan.value.id)
    currentPlan.value = data.plan
    ElMessage.success(data.current_node ? `已进入：${data.current_node.knowledge_point}` : '补救计划已完成')
    window.dispatchEvent(new CustomEvent('navigate-to', { detail: 'path' }))
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    starting.value = false
  }
}

async function showWhy() {
  if (!currentPlan.value) return
  try {
    const { data } = await api.explainDecision({
      decision_type: 'remediation',
      knowledge_point_id: currentPlan.value.target_knowledge_point_id,
    })
    explanation.value = data.explanation
    whyVisible.value = true
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}

function masteryText(value: unknown) {
  return value === null || value === undefined ? '未测评' : `${Math.round(Number(value) * 100) / 100}%`
}
function statusLabel(status: string) {
  return ({ ready: '待开始', active: '进行中', completed: '已完成', adjusted: '已调整', locked: '待解锁', learning: '学习中', remediation: '补救中' } as any)[status] || status
}
function stepType(step: any) {
  if (step.status === 'completed') return 'success'
  if (step.step_type === 'assessment') return 'warning'
  if (['learning', 'remediation', 'ready'].includes(step.status)) return 'primary'
  return 'info'
}

onMounted(load)
</script>

<style scoped>
.remediation-page { max-width: 1240px; margin: 0 auto; color: #172033; }
.page-head, .panel-head, .plan-step header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.page-head { padding: 4px 0 18px; }
.page-head h2 { margin: 0 0 6px; font-size: 22px; }
.page-head p, .panel-head span { margin: 0; color: #64748b; font-size: 13px; }
.head-actions { display: flex; gap: 10px; }
.head-actions .el-select { width: 260px; }
.plan-summary { display: grid; grid-template-columns: repeat(4, 1fr) auto; background: #fff; border: 1px solid #e2e8f0; border-radius: 6px; }
.plan-summary > div { padding: 16px; border-right: 1px solid #e2e8f0; }
.plan-summary > div:last-child { border: 0; }
.plan-summary span { display: block; color: #64748b; font-size: 12px; margin-bottom: 5px; }
.plan-summary strong { font-size: 15px; }
.summary-action { display: flex; align-items: center; }
.reason-band { margin: 14px 0; }
.workspace { display: grid; grid-template-columns: minmax(0, 1fr) 250px; gap: 14px; align-items: start; }
.steps-panel, .history-panel { border: 1px solid #e2e8f0; background: #fff; border-radius: 6px; overflow: hidden; }
.panel-head { padding: 15px 17px; border-bottom: 1px solid #e2e8f0; }
.panel-head > div { display: grid; gap: 3px; }
.step-list { padding: 6px 18px 16px; }
.plan-step { display: grid; grid-template-columns: 34px 1fr; gap: 12px; padding: 16px 0; border-bottom: 1px solid #eef2f7; }
.plan-step:last-child { border: 0; }
.step-index { width: 30px; height: 30px; display: grid; place-items: center; border-radius: 50%; background: #eff6ff; color: #2563eb; font-weight: 700; }
.step-body p { margin: 7px 0; color: #475569; font-size: 13px; line-height: 1.6; }
.step-meta { display: flex; gap: 16px; color: #64748b; font-size: 12px; }
.history-item { width: 100%; border: 0; border-bottom: 1px solid #eef2f7; background: #fff; padding: 13px 16px; text-align: left; cursor: pointer; }
.history-item:hover, .history-item.active { background: #f8fafc; }
.history-item span, .history-item small { display: block; }
.history-item span { color: #334155; font-weight: 600; margin-bottom: 4px; }
.history-item small { color: #64748b; }
.trace-space { margin-top: 14px; }
h4 { margin: 22px 0 8px; }
li, .el-drawer p { color: #475569; line-height: 1.7; }
@media (max-width: 900px) {
  .page-head { align-items: flex-start; }
  .head-actions { flex-direction: column; }
  .plan-summary { grid-template-columns: repeat(2, 1fr); }
  .workspace { grid-template-columns: 1fr; }
}
</style>
