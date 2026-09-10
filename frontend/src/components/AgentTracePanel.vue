<template>
  <section class="trace-panel">
    <header class="trace-header">
      <div>
        <strong>Agent 执行记录</strong>
        <span v-if="run">#{{ run.id }} · {{ taskLabel(run.task_type) }}</span>
      </div>
      <el-tag v-if="run" :type="statusType(run.status)" effect="plain">
        {{ statusLabel(run.status) }}
      </el-tag>
    </header>
    <el-empty v-if="!run" description="执行任务后将在这里显示真实步骤" :image-size="54" />
    <el-timeline v-else class="trace-timeline">
      <el-timeline-item
        v-for="step in run.steps || []"
        :key="step.id"
        :type="statusType(step.status)"
        :timestamp="formatTime(step.completed_at || step.created_at)"
      >
        <div class="trace-step">
          <div class="trace-step-title">
            <strong>{{ step.agent_name }}</strong>
            <el-tag size="small" :type="statusType(step.status)">
              {{ statusLabel(step.status) }}
            </el-tag>
          </div>
          <p>{{ step.action }}</p>
          <span>使用证据 {{ step.evidence_count || 0 }} 条</span>
          <el-collapse v-if="hasDetails(step)">
            <el-collapse-item title="查看输入与输出" :name="step.id">
              <pre>{{ formatJson({ input: step.input, output: step.output }) }}</pre>
            </el-collapse-item>
          </el-collapse>
          <el-alert
            v-if="step.error_message"
            :title="step.error_message"
            type="error"
            :closable="false"
          />
        </div>
      </el-timeline-item>
    </el-timeline>
  </section>
</template>

<script setup lang="ts">
defineProps<{ run?: any | null }>()

function statusType(status: string) {
  if (status === 'passed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'revised') return 'warning'
  return 'primary'
}

function statusLabel(status: string) {
  return ({
    running: '执行中',
    passed: '通过',
    failed: '失败',
    revised: '已调整',
    skipped: '已跳过',
  } as Record<string, string>)[status] || status
}

function taskLabel(type: string) {
  return ({
    remediation_plan: '补救计划',
    adaptive_exam: '自适应测评',
  } as Record<string, string>)[type] || type
}

function formatTime(value?: string) {
  if (!value) return ''
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function hasDetails(step: any) {
  return Object.keys(step.input || {}).length || Object.keys(step.output || {}).length
}

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2)
}
</script>

<style scoped>
.trace-panel { border: 1px solid #e2e8f0; background: #fff; padding: 18px; border-radius: 6px; }
.trace-header { display: flex; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.trace-header > div { display: flex; align-items: center; gap: 10px; min-width: 0; }
.trace-header strong { color: #172033; font-size: 15px; }
.trace-header span { color: #64748b; font-size: 12px; }
.trace-timeline { padding: 4px 0 0 4px; }
.trace-step { padding-bottom: 4px; }
.trace-step-title { display: flex; align-items: center; gap: 8px; }
.trace-step p { margin: 6px 0 4px; color: #334155; font-size: 13px; }
.trace-step > span { color: #64748b; font-size: 12px; }
.trace-step pre { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; color: #475569; }
:deep(.el-collapse) { margin-top: 8px; border: 0; }
:deep(.el-collapse-item__header) { height: 32px; font-size: 12px; color: #64748b; border: 0; }
:deep(.el-collapse-item__wrap) { border: 0; }
</style>
