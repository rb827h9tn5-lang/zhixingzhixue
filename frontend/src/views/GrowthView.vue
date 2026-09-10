<template>
  <section class="growth-page">
    <header class="page-head">
      <div>
        <h2>学习成长与效果报告</h2>
        <p>所有指标都由学习事件、测评结果和掌握度证据在后端汇总</p>
      </div>
      <div class="head-actions">
        <el-segmented v-model="days" :options="periodOptions" @change="load" />
        <el-button type="primary" :loading="loading" @click="generateReport">生成学习成效报告</el-button>
      </div>
    </header>

    <el-alert
      v-if="growth"
      :title="growth.report"
      type="success"
      :closable="false"
      show-icon
      class="report-band"
    />

    <div v-if="growth" class="metric-strip">
      <div><span>学习事件</span><strong>{{ growth.metrics.learning_event_count }}</strong></div>
      <div><span>综合正确率</span><strong>{{ display(growth.metrics.accuracy, '%') }}</strong></div>
      <div><span>掌握度平均提升</span><strong>{{ signed(growth.metrics.average_mastery_improvement) }}</strong></div>
      <div><span>完成节点</span><strong>{{ growth.metrics.completed_node_count }}</strong></div>
      <div><span>达标补救计划</span><strong>{{ growth.metrics.completed_remediation_count }}</strong></div>
      <div><span>路径调整</span><strong>{{ growth.metrics.replan_count }}</strong></div>
    </div>

    <el-alert
      v-if="growth?.current_intervention"
      class="intervention-band"
      :title="`正在执行 ${growth.current_intervention.strategy_type} 教学干预`"
      :description="growth.current_intervention.effect_statement"
      type="warning"
      :closable="false"
      show-icon
    />

    <section v-if="growth" class="strategy-panel">
      <header class="panel-head">
        <div>
          <strong>教学策略响应</strong>
          <span>这里只报告干预后观察到的变化，不把相关性表述为因果</span>
        </div>
        <el-tag v-if="growth.current_strategy" type="primary" effect="dark">
          {{ growth.current_strategy.strategy_label }}
        </el-tag>
      </header>
      <el-table :data="growth.strategy_response || []">
        <el-table-column prop="strategy_label" label="策略" min-width="160" />
        <el-table-column prop="completed_count" label="完整证据" width="100" />
        <el-table-column label="平均观察变化" width="140">
          <template #default="{ row }">{{ signed(row.average_observed_gain) }} 个百分点</template>
        </el-table-column>
        <el-table-column label="证据状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.minimum_evidence_met ? 'success' : 'info'" effect="plain">
              {{ row.minimum_evidence_met ? '达到最低门槛' : '证据不足' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="statement" label="可审计结论" min-width="280" />
      </el-table>
      <el-empty v-if="!growth.strategy_response?.length" description="完成干预后的下一次测评，才会产生策略效果证据" :image-size="52" />
    </section>

    <section v-if="growth?.metacognitive_calibration" class="calibration-panel">
      <header class="panel-head">
        <div><strong>自我判断校准</strong><span>至少两条方向一致的证据后才给出高估或低估结论</span></div>
        <el-tag effect="plain">{{ calibrationLabel(growth.metacognitive_calibration.state) }}</el-tag>
      </header>
      <div class="calibration-body">
        <div><span>平均自信度</span><strong>{{ display(growth.metacognitive_calibration.average_self_confidence, '%') }}</strong></div>
        <div><span>实际表现</span><strong>{{ display(growth.metacognitive_calibration.actual_performance, '%') }}</strong></div>
        <p>{{ growth.metacognitive_calibration.message }}</p>
      </div>
    </section>

    <section class="growth-panel">
      <header class="panel-head">
        <div>
          <strong>知识点掌握度前后对比</strong>
          <span>初始值取所选周期内第一条证据写入前的分数</span>
        </div>
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </header>
      <el-table :data="growth?.knowledge_growth || []" row-key="knowledge_point_id">
        <el-table-column prop="knowledge_point" label="知识点" min-width="190" />
        <el-table-column label="周期初始" width="110">
          <template #default="{ row }">{{ row.initial_mastery }}%</template>
        </el-table-column>
        <el-table-column label="当前掌握度" min-width="230">
          <template #default="{ row }">
            <div class="mastery-cell">
              <el-progress :percentage="row.current_mastery" :show-text="false" :stroke-width="8" />
              <strong>{{ row.current_mastery }}%</strong>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="变化" width="110">
          <template #default="{ row }">
            <el-tag :type="row.improvement > 0 ? 'success' : row.improvement < 0 ? 'danger' : 'info'" effect="plain">
              {{ signed(row.improvement) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="attempt_count" label="累计作答" width="100" />
        <el-table-column label="能力门槛" width="120">
          <template #default="{ row }">
            <el-tag effect="plain">{{ capabilityLabel(row.capability?.capability_state) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="多维掌握" width="100">
          <template #default="{ row }">
            <el-popover placement="left" width="390" trigger="click">
              <template #reference><el-button link type="primary">查看</el-button></template>
              <div class="dimension-list">
                <div v-for="(dimension, key) in row.dimensions" :key="key">
                  <span>{{ dimensionLabel(String(key)) }}</span>
                  <strong>{{ display(dimension.mastery_score, '%') }}</strong>
                  <small>{{ dimension.evidence_count }} 条证据</small>
                </div>
              </div>
            </el-popover>
          </template>
        </el-table-column>
        <el-table-column label="证据明细" width="100">
          <template #default="{ row }">
            <el-popover placement="left" width="360" trigger="click">
              <template #reference><el-button link type="primary">查看 {{ row.timeline.length }}</el-button></template>
              <div class="evidence-list">
                <div v-for="item in row.timeline" :key="item.event_id">
                  <strong>{{ item.score }}%（{{ signed(item.delta) }}）</strong>
                  <span>{{ item.description || item.evidence_type }}</span>
                  <small>{{ formatTime(item.created_at) }}</small>
                </div>
                <el-empty v-if="!row.timeline.length" description="本周期没有新增证据" :image-size="48" />
              </div>
            </el-popover>
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-if="growth && !growth.knowledge_growth.length"
        description="完成一次知识点测评后即可查看成长变化"
      />
    </section>

    <section class="score-panel">
      <header class="panel-head">
        <div><strong>测评成绩记录</strong><span>仅统计已正式提交的测评</span></div>
      </header>
      <div v-if="growth?.score_trend?.length" class="score-list">
        <div v-for="(item, index) in growth.score_trend" :key="item.result_id">
          <span>第 {{ index + 1 }} 次</span>
          <div class="score-track"><i :style="{ width: `${item.score}%` }"></i></div>
          <strong>{{ item.score }}</strong>
          <small>{{ formatTime(item.created_at) }}</small>
        </div>
      </div>
      <el-empty v-else description="暂无已提交测评" :image-size="58" />
    </section>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/learning'
import { getErrorMessage } from '../composables/useUtils'

const days = ref<number | 'all'>(30)
const periodOptions = [
  { label: '近 7 天', value: 7 },
  { label: '近 30 天', value: 30 },
  { label: '近 90 天', value: 90 },
  { label: '全部', value: 'all' },
]
const growth = ref<any>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await api.getGrowthReport(days.value)
    growth.value = data.growth
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    loading.value = false
  }
}

async function generateReport() {
  await load()
  if (growth.value) ElMessage.success('已根据真实学习数据生成效果报告')
}

function signed(value: unknown) {
  const number = Math.round(Number(value || 0) * 100) / 100
  return `${number > 0 ? '+' : ''}${number}`
}
function display(value: unknown, suffix = '') {
  return value === null || value === undefined ? '--' : `${Math.round(Number(value) * 100) / 100}${suffix}`
}
function formatTime(value: string) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '--'
}
function calibrationLabel(state: string) {
  return ({
    INSUFFICIENT_EVIDENCE: '证据不足',
    OVERCONFIDENT: '自信判断偏高',
    UNDERCONFIDENT: '自信判断偏低',
    CALIBRATED: '判断较校准',
  } as any)[state] || state
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
function dimensionLabel(dimension: string) {
  return ({
    conceptual_understanding: '概念理解',
    procedural_application: '程序性应用',
    reasoning: '推理过程',
    coding: '代码实践',
    transfer: '迁移能力',
  } as any)[dimension] || dimension
}

onMounted(load)
</script>

<style scoped>
.growth-page { max-width: 1220px; margin: 0 auto; color: #172033; }
.page-head, .panel-head { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.page-head { padding: 4px 0 18px; }
.page-head h2 { margin: 0 0 6px; font-size: 22px; }
.page-head p, .panel-head span { margin: 0; color: #64748b; font-size: 13px; }
.head-actions { display: flex; align-items: center; gap: 10px; }
.report-band { margin-bottom: 14px; }
.metric-strip { display: grid; grid-template-columns: repeat(6, 1fr); border: 1px solid #e2e8f0; background: #fff; border-radius: 6px; margin-bottom: 14px; }
.metric-strip > div { padding: 15px; border-right: 1px solid #e2e8f0; }
.metric-strip > div:last-child { border: 0; }
.metric-strip span { display: block; color: #64748b; font-size: 12px; margin-bottom: 5px; }
.metric-strip strong { font-size: 20px; }
.growth-panel, .score-panel, .strategy-panel, .calibration-panel { border: 1px solid #e2e8f0; background: #fff; border-radius: 6px; overflow: hidden; margin-bottom: 14px; }
.intervention-band { margin-bottom: 14px; }
.calibration-body { display: grid; grid-template-columns: 160px 160px 1fr; gap: 18px; align-items: center; padding: 16px 18px; }
.calibration-body > div { display: grid; gap: 4px; }
.calibration-body span { color: #64748b; font-size: 12px; }
.calibration-body strong { font-size: 20px; }
.calibration-body p { margin: 0; color: #475569; }
.dimension-list { display: grid; gap: 8px; }
.dimension-list > div { display: grid; grid-template-columns: 1fr 70px 80px; gap: 8px; padding-bottom: 7px; border-bottom: 1px solid #eef2f7; }
.dimension-list small { color: #64748b; }
.panel-head { padding: 15px 18px; border-bottom: 1px solid #e2e8f0; }
.panel-head > div { display: grid; gap: 4px; }
.mastery-cell { display: grid; grid-template-columns: 1fr 48px; align-items: center; gap: 10px; }
.evidence-list > div { display: grid; gap: 3px; padding: 9px 0; border-bottom: 1px solid #eef2f7; }
.evidence-list span, .evidence-list small { color: #64748b; font-size: 12px; }
.score-list { padding: 10px 18px 16px; }
.score-list > div { display: grid; grid-template-columns: 70px 1fr 48px 150px; align-items: center; gap: 12px; padding: 10px 0; }
.score-list span, .score-list small { color: #64748b; font-size: 12px; }
.score-track { height: 8px; background: #eef2f7; border-radius: 4px; overflow: hidden; }
.score-track i { display: block; height: 100%; background: #2563eb; border-radius: inherit; }
@media (max-width: 900px) {
  .metric-strip { grid-template-columns: repeat(2, 1fr); }
  .metric-strip > div { border-bottom: 1px solid #e2e8f0; }
  .score-list > div { grid-template-columns: 58px 1fr 40px; }
  .score-list small { display: none; }
  .calibration-body { grid-template-columns: 1fr 1fr; }
  .calibration-body p { grid-column: 1 / -1; }
}
</style>
