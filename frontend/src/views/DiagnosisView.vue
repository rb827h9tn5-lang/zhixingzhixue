<template>
  <section class="decision-page">
    <header class="page-head">
      <div>
        <h2>AI 学习诊断中心</h2>
        <p>依据你的答题、学习行为、知识结构和路径版本生成实时诊断</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新诊断</el-button>
    </header>

    <el-alert
      v-if="diagnosis"
      class="summary-band"
      :title="diagnosis.summary"
      type="success"
      :closable="false"
      show-icon
    />

    <div v-if="diagnosis" class="metric-strip">
      <div><span>诊断覆盖</span><strong>{{ percent(diagnosis.overall.coverage) }}%</strong></div>
      <div><span>平均掌握度</span><strong>{{ value(diagnosis.overall.average_mastery) }}%</strong></div>
      <div><span>稳定掌握</span><strong>{{ diagnosis.overall.stable_count }}</strong></div>
      <div><span>重点补强</span><strong class="danger">{{ diagnosis.overall.focus_count }}</strong></div>
      <div><span>尚未测评</span><strong>{{ diagnosis.overall.unknown_count }}</strong></div>
    </div>

    <section v-if="strategy || misconceptions.length" class="cognition-panel">
      <header class="panel-head">
        <div>
          <strong>认知误区与当前教学策略</strong>
          <span>误区必须由真实过程错误重复支持，首次出现只标记为待确认</span>
        </div>
        <el-tag v-if="strategy" type="primary" effect="dark">{{ strategy.strategy_label }}</el-tag>
      </header>
      <div v-if="strategy" class="strategy-strip">
        <div>
          <span>当前策略</span>
          <strong>{{ strategy.strategy_label }}</strong>
        </div>
        <div>
          <span>选择依据</span>
          <div class="tag-list">
            <el-tag v-for="reason in strategy.reason_codes" :key="reason" effect="plain">{{ reason }}</el-tag>
          </div>
        </div>
        <div>
          <span>教学动作</span>
          <ol><li v-for="action in strategy.action_labels" :key="action">{{ action }}</li></ol>
        </div>
      </div>
      <el-table :data="misconceptions" row-key="id">
        <el-table-column prop="misconception.name" label="误区" min-width="220" />
        <el-table-column prop="misconception.knowledge_point" label="根因知识点" min-width="160" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="misconceptionType(row.status)" effect="plain">{{ misconceptionLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="evidence_count" label="证据数" width="90" />
        <el-table-column label="影响范围" min-width="190">
          <template #default="{ row }">
            {{ row.affected_knowledge_points?.map((item: any) => item.name).join('、') || '当前知识点' }}
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section v-if="diagnosis" class="knowledge-map">
      <header class="panel-head">
        <div>
          <strong>知识掌握地图</strong>
          <span>按课程章节展示全部知识点，点击可查看真实证据</span>
        </div>
      </header>
      <div class="chapter-grid">
        <article v-for="chapter in diagnosis.knowledge_map" :key="chapter.chapter_id">
          <header>
            <strong>{{ chapter.chapter }}</strong>
            <span>{{ chapter.course }}</span>
          </header>
          <button
            v-for="point in chapter.knowledge_points"
            :key="point.knowledge_point_id"
            @click="selectPoint(point)"
          >
            <span class="state-dot" :class="point.state"></span>
            <span>{{ point.name }}</span>
            <strong>{{ value(point.mastery_score) }}%</strong>
          </button>
        </article>
      </div>
    </section>

    <div class="diagnosis-layout">
      <section class="main-panel">
        <header class="panel-head">
          <div>
            <strong>薄弱项与学习优先级</strong>
            <span>排序由后端掌握度、错误次数和证据状态决定</span>
          </div>
          <el-button
            type="primary"
            :icon="FirstAidKit"
            :loading="creating"
            :disabled="!diagnosis?.recommended_target"
            @click="createPlan(diagnosis.recommended_target.knowledge_point_id)"
          >
            一键生成补救计划
          </el-button>
        </header>
        <el-table
          :data="diagnosis?.weakness_ranking || []"
          row-key="knowledge_point_id"
          highlight-current-row
          @current-change="selectPoint"
        >
          <el-table-column type="index" label="优先级" width="72" />
          <el-table-column prop="name" label="知识点" min-width="180" />
          <el-table-column prop="chapter" label="章节" min-width="150" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="stateType(row.state)" effect="plain">{{ stateLabel(row.state) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="掌握度" width="130">
            <template #default="{ row }">{{ value(row.mastery_score) }}%</template>
          </el-table-column>
          <el-table-column label="证据" width="90">
            <template #default="{ row }">{{ row.evidence_count }} 条</template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button link type="primary" @click.stop="createPlan(row.knowledge_point_id)">补救</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty
          v-if="diagnosis && !diagnosis.weakness_ranking.length"
          description="当前没有待处理知识点"
        />
      </section>

      <aside class="detail-panel">
        <template v-if="detail">
          <header>
            <div>
              <strong>{{ detail.knowledge_point.name }}</strong>
              <span>{{ detail.knowledge_point.code }}</span>
            </div>
            <el-tag :type="stateType(detail.diagnosis_state)">
              {{ stateLabel(detail.diagnosis_state) }}
            </el-tag>
          </header>
          <div class="mastery-line">
            <span>当前掌握度</span>
            <strong>{{ value(detail.mastery.mastery_score) }}%</strong>
          </div>
          <el-progress
            :percentage="detail.mastery.mastery_score || 0"
            :show-text="false"
            :stroke-width="8"
          />
          <h3>诊断原因</h3>
          <ul><li v-for="item in detail.reasons" :key="item">{{ item }}</li></ul>
          <h3>掌握度证据</h3>
          <div v-if="detail.mastery.evidence?.length" class="evidence-list">
            <div v-for="item in detail.mastery.evidence.slice(0, 6)" :key="item.id">
              <strong>{{ item.old_score }}% → {{ item.new_score }}%</strong>
              <span>{{ item.description || item.evidence_type }}</span>
            </div>
          </div>
          <span v-else class="muted">尚无 MasteryEvidence</span>
          <h3>薄弱先修知识</h3>
          <div v-if="detail.weak_prerequisites.length" class="tag-list">
            <el-tag
              v-for="item in detail.weak_prerequisites"
              :key="item.knowledge_point_id"
              type="warning"
              effect="plain"
            >{{ item.name }} · {{ value(item.mastery_score) }}%</el-tag>
          </div>
          <span v-else class="muted">未发现薄弱先修项</span>
          <h3>建议动作</h3>
          <ol><li v-for="item in detail.recommendations" :key="item">{{ item }}</li></ol>
        </template>
        <el-empty v-else description="点击左侧知识点查看诊断依据" :image-size="62" />
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { FirstAidKit, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/learning'
import { getErrorMessage } from '../composables/useUtils'

const loading = ref(false)
const creating = ref(false)
const diagnosis = ref<any>(null)
const detail = ref<any>(null)
const misconceptions = ref<any[]>([])
const strategy = ref<any>(null)

async function load() {
  loading.value = true
  try {
    const [{ data }, misconceptionRes, strategyRes] = await Promise.all([
      api.getDiagnosis(),
      api.getMisconceptions(),
      api.getCurrentTeachingStrategy(),
    ])
    diagnosis.value = data.diagnosis
    misconceptions.value = misconceptionRes.data.misconceptions || []
    strategy.value = strategyRes.data.strategy || null
    const target = data.diagnosis?.recommended_target
    if (target) await selectPoint(target)
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    loading.value = false
  }
}

async function selectPoint(row: any) {
  if (!row?.knowledge_point_id) return
  try {
    const { data } = await api.getDiagnosisDetail(row.knowledge_point_id)
    detail.value = data.detail
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}

async function createPlan(knowledgePointId: number) {
  creating.value = true
  try {
    const { data } = await api.createRemediationPlan(knowledgePointId)
    ElMessage.success(data.reused ? '已打开现有补救计划' : '补救计划已生成')
    window.dispatchEvent(new CustomEvent('navigate-to', { detail: 'remediation' }))
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    creating.value = false
  }
}

function value(input: unknown) {
  return input === null || input === undefined ? '--' : Math.round(Number(input) * 100) / 100
}
function percent(input: unknown) { return Math.round(Number(input || 0) * 100) }
function stateLabel(state: string) {
  return ({ stable: '稳定掌握', consolidate: '待巩固', focus: '重点补强', unknown: '未测评' } as any)[state] || state
}
function stateType(state: string) {
  return ({ stable: 'success', consolidate: 'warning', focus: 'danger', unknown: 'info' } as any)[state] || 'info'
}
function misconceptionLabel(status: string) {
  return ({ suspected: '待确认', confirmed: '已确认', improving: '改善中', resolved: '已解决' } as any)[status] || status
}
function misconceptionType(status: string) {
  return ({ suspected: 'warning', confirmed: 'danger', improving: 'primary', resolved: 'success' } as any)[status] || 'info'
}

onMounted(load)
</script>

<style scoped>
.decision-page { max-width: 1280px; margin: 0 auto; color: #172033; }
.page-head, .panel-head, .detail-panel header { display: flex; align-items: center; justify-content: space-between; gap: 18px; }
.page-head { padding: 4px 0 18px; }
.page-head h2 { margin: 0 0 6px; font-size: 22px; }
.page-head p, .panel-head span, .detail-panel header span, .muted { margin: 0; color: #64748b; font-size: 13px; }
.summary-band { margin-bottom: 14px; }
.metric-strip { display: grid; grid-template-columns: repeat(5, 1fr); border: 1px solid #e2e8f0; background: #fff; border-radius: 6px; margin-bottom: 16px; }
.metric-strip > div { padding: 16px 18px; border-right: 1px solid #e2e8f0; }
.metric-strip > div:last-child { border: 0; }
.metric-strip span { display: block; color: #64748b; font-size: 12px; margin-bottom: 6px; }
.metric-strip strong { font-size: 23px; }
.danger { color: #dc2626; }
.diagnosis-layout { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 16px; align-items: start; }
.main-panel, .detail-panel, .cognition-panel { border: 1px solid #e2e8f0; background: #fff; border-radius: 6px; }
.cognition-panel { margin-bottom: 16px; overflow: hidden; }
.strategy-strip { display: grid; grid-template-columns: 160px 1fr 1fr; gap: 18px; padding: 16px 18px; border-bottom: 1px solid #e2e8f0; }
.strategy-strip > div { display: grid; gap: 7px; align-content: start; }
.strategy-strip > div > span { color: #64748b; font-size: 12px; }
.strategy-strip ol { margin: 0; padding-left: 20px; color: #475569; font-size: 13px; line-height: 1.7; }
.knowledge-map { margin-bottom: 16px; }
.knowledge-map > .panel-head { padding-left: 0; padding-right: 0; border: 0; }
.chapter-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.chapter-grid article { border: 1px solid #e2e8f0; background: #fff; border-radius: 6px; overflow: hidden; }
.chapter-grid article > header { display: grid; gap: 3px; padding: 13px 14px; border-bottom: 1px solid #e2e8f0; }
.chapter-grid article > header span { color: #64748b; font-size: 12px; }
.chapter-grid button { width: 100%; display: grid; grid-template-columns: 10px 1fr auto; align-items: center; gap: 8px; padding: 10px 14px; border: 0; border-bottom: 1px solid #eef2f7; background: #fff; text-align: left; cursor: pointer; color: #334155; }
.chapter-grid button:last-child { border-bottom: 0; }
.chapter-grid button:hover { background: #f8fafc; }
.chapter-grid button > strong { font-size: 12px; }
.state-dot { width: 8px; height: 8px; border-radius: 50%; background: #94a3b8; }
.state-dot.stable { background: #16a34a; }
.state-dot.consolidate { background: #d97706; }
.state-dot.focus { background: #dc2626; }
.evidence-list { display: grid; gap: 7px; }
.evidence-list > div { display: grid; gap: 2px; padding: 8px 10px; background: #f8fafc; border-left: 3px solid #60a5fa; }
.evidence-list strong { font-size: 12px; }
.evidence-list span { color: #64748b; font-size: 12px; }
.panel-head { padding: 16px 18px; border-bottom: 1px solid #e2e8f0; }
.panel-head > div { display: grid; gap: 4px; }
.detail-panel { padding: 18px; position: sticky; top: 76px; }
.detail-panel header > div { display: grid; gap: 3px; }
.mastery-line { display: flex; justify-content: space-between; margin: 20px 0 8px; color: #64748b; }
.mastery-line strong { color: #172033; font-size: 21px; }
.detail-panel h3 { font-size: 13px; margin: 22px 0 10px; }
.detail-panel ul, .detail-panel ol { margin: 0; padding-left: 20px; color: #475569; font-size: 13px; line-height: 1.8; }
.tag-list { display: flex; gap: 6px; flex-wrap: wrap; }
@media (max-width: 900px) {
  .metric-strip { grid-template-columns: repeat(2, 1fr); }
  .chapter-grid { grid-template-columns: 1fr; }
  .strategy-strip { grid-template-columns: 1fr; }
  .metric-strip > div { border-bottom: 1px solid #e2e8f0; }
  .diagnosis-layout { grid-template-columns: 1fr; }
  .detail-panel { position: static; }
}
</style>
