<template>
  <div class="code-workbench">
    <header class="code-toolbar">
      <div class="language-control">
        <el-radio-group v-model="language" size="small">
          <el-radio-button value="python">Python</el-radio-button>
          <el-radio-button value="c">C</el-radio-button>
        </el-radio-group>
      </div>

      <div class="toolbar-status" :class="`is-${sandboxStatus}`">
        <span class="sandbox-dot"></span>
        <span>{{ sandboxLabel }}</span>
        <span v-if="currentRuntime" class="runtime-version">
          {{ currentRuntime.label }} {{ currentRuntime.version }}
        </span>
        <el-tooltip content="重新检测沙箱">
          <el-button
            text
            circle
            :icon="Refresh"
            :loading="runtimesLoading"
            aria-label="重新检测沙箱"
            @click="loadRuntimes"
          />
        </el-tooltip>
      </div>

      <div class="toolbar-actions">
        <el-select v-model="timeoutMs" size="small" class="timeout-select" aria-label="运行超时">
          <el-option label="1 秒" :value="1000" />
          <el-option label="3 秒" :value="3000" />
          <el-option label="5 秒" :value="5000" />
        </el-select>
        <el-tooltip content="复制代码">
          <el-button circle :icon="CopyDocument" aria-label="复制代码" @click="copyCode" />
        </el-tooltip>
        <el-tooltip content="恢复默认代码">
          <el-button circle :icon="RefreshRight" aria-label="恢复默认代码" @click="resetCode" />
        </el-tooltip>
        <el-button
          type="primary"
          :loading="running"
          :disabled="runDisabled"
          @click="runCode"
        >
          <el-icon><VideoPlay /></el-icon>
          运行代码
        </el-button>
      </div>
    </header>

    <div class="code-layout">
      <section class="editor-panel">
        <div class="panel-heading editor-heading">
          <span>{{ language === 'python' ? 'main.py' : 'main.c' }}</span>
          <span>{{ code.length.toLocaleString() }} / 50,000</span>
        </div>
        <div class="editor-body">
          <CodeEditor v-model="code" :language="language" @run="runCode" />
        </div>
      </section>

      <aside class="io-panel">
        <section class="stdin-panel">
          <div class="panel-heading">
            <span>标准输入</span>
            <el-button v-if="stdin" text size="small" @click="stdin = ''">清空</el-button>
          </div>
          <el-input
            v-model="stdin"
            class="stdin-input"
            type="textarea"
            resize="none"
            maxlength="10000"
            aria-label="标准输入"
          />
        </section>

        <section class="output-panel">
          <div class="panel-heading output-heading">
            <span>运行结果</span>
            <el-tooltip v-if="result || serviceError" content="清空结果">
              <el-button
                text
                circle
                :icon="Delete"
                aria-label="清空运行结果"
                @click="clearOutput"
              />
            </el-tooltip>
          </div>

          <div v-if="running" class="output-state">
            <el-icon class="is-loading" :size="22"><Loading /></el-icon>
            <span>正在沙箱中运行</span>
          </div>

          <div v-else-if="serviceError" class="service-error" role="alert">
            <el-icon :size="20"><WarningFilled /></el-icon>
            <div>
              <strong>{{ serviceErrorTitle }}</strong>
              <p>{{ serviceError }}</p>
            </div>
          </div>

          <div v-else-if="result" class="result-content">
            <div class="result-meta">
              <span class="result-status" :class="`is-${result.status}`">
                <el-icon>
                  <CircleCheck v-if="result.status === 'success'" />
                  <WarningFilled v-else />
                </el-icon>
                {{ statusLabel }}
              </span>
              <span>{{ result.duration_ms }} ms</span>
              <span>退出码 {{ result.exit_code ?? '-' }}</span>
              <span v-if="result.signal">信号 {{ result.signal }}</span>
              <span v-if="result.truncated" class="truncated-note">输出已截断</span>
              <el-tooltip
                v-if="result.status !== 'success'"
                content="将本次代码和错误信息发送给 MiMo"
              >
                <el-button
                  class="ai-analyze-button"
                  type="primary"
                  plain
                  size="small"
                  :icon="MagicStick"
                  :loading="analysisLoading"
                  @click="analyzeError"
                >
                  AI 分析
                </el-button>
              </el-tooltip>
            </div>
            <pre :class="{ 'is-error': result.status !== 'success' }">{{ outputText }}</pre>

            <section
              v-if="analysisLoading || analysisError || analysis"
              class="ai-analysis-panel"
              aria-live="polite"
            >
              <div v-if="analysisLoading" class="ai-analysis-state">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>MiMo 正在分析错误</span>
              </div>

              <div v-else-if="analysisError" class="ai-analysis-error" role="alert">
                <el-icon><WarningFilled /></el-icon>
                <span>{{ analysisError }}</span>
              </div>

              <template v-else-if="analysis">
                <div class="ai-analysis-heading">
                  <span>
                    <el-icon><MagicStick /></el-icon>
                    MiMo 错误分析
                  </span>
                  <span>{{ analysis.model }}</span>
                </div>
                <strong class="analysis-summary">{{ analysis.summary }}</strong>
                <p class="analysis-explanation">{{ analysis.explanation }}</p>
                <ol v-if="analysis.suggestions.length" class="analysis-suggestions">
                  <li v-for="item in analysis.suggestions" :key="item">{{ item }}</li>
                </ol>

                <div v-if="analysis.corrected_code" class="corrected-code">
                  <div class="corrected-code-toolbar">
                    <span>建议修改后的完整代码</span>
                    <div>
                      <el-tooltip content="复制修正代码">
                        <el-button
                          text
                          circle
                          :icon="CopyDocument"
                          aria-label="复制修正代码"
                          @click="copyCorrectedCode"
                        />
                      </el-tooltip>
                      <el-button
                        type="primary"
                        size="small"
                        :icon="Check"
                        @click="applyCorrectedCode"
                      >
                        应用修正
                      </el-button>
                    </div>
                  </div>
                  <pre>{{ analysis.corrected_code }}</pre>
                </div>
              </template>
            </section>
          </div>

          <div v-else class="output-state is-empty">
            <span>运行代码后在这里查看输出</span>
          </div>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Check,
  CircleCheck,
  CopyDocument,
  Delete,
  Loading,
  MagicStick,
  Refresh,
  RefreshRight,
  VideoPlay,
  WarningFilled,
} from '@element-plus/icons-vue'

import { api } from '../api/learning'
import type {
  CodeErrorAnalysis,
  CodeExecutionResult,
  CodeLanguage,
  CodeRuntime,
} from '../api/learning'
import CodeEditor from '../components/CodeEditor.vue'

const templates: Record<CodeLanguage, string> = {
  python: `name = input().strip() or "World"
print(f"Hello, {name}!")
`,
  c: `#include <stdio.h>

int main(void) {
    char name[64] = "World";
    if (scanf("%63s", name) != 1) {
        snprintf(name, sizeof(name), "World");
    }
    printf("Hello, %s!\\n", name);
    return 0;
}
`,
}

const language = ref<CodeLanguage>('python')
const codeByLanguage = reactive<Record<CodeLanguage, string>>({
  python: localStorage.getItem('online_code_python') || templates.python,
  c: localStorage.getItem('online_code_c') || templates.c,
})
const code = computed({
  get: () => codeByLanguage[language.value],
  set: (value: string) => {
    codeByLanguage[language.value] = value
  },
})

const stdin = ref('Codex')
const timeoutMs = ref(3000)
const running = ref(false)
const runtimesLoading = ref(false)
const runtimes = ref<CodeRuntime[]>([])
const sandboxStatus = ref<'loading' | 'ready' | 'partial' | 'unavailable'>('loading')
const sandboxMessage = ref('')
const result = ref<CodeExecutionResult | null>(null)
const serviceError = ref('')
const submittedCode = ref('')
const analysisLoading = ref(false)
const analysis = ref<CodeErrorAnalysis | null>(null)
const analysisError = ref('')

const currentRuntime = computed(() =>
  runtimes.value.find(item => item.id === language.value),
)

const runDisabled = computed(() =>
  running.value
  || runtimesLoading.value
  || sandboxStatus.value === 'unavailable'
  || currentRuntime.value?.available === false,
)

const sandboxLabel = computed(() => {
  if (sandboxStatus.value === 'loading') return '正在检测沙箱'
  if (sandboxStatus.value === 'ready') return '沙箱就绪'
  if (sandboxStatus.value === 'partial') return '部分运行环境可用'
  return sandboxMessage.value || '沙箱不可用'
})

const statusLabel = computed(() => {
  if (!result.value) return ''
  return {
    success: '运行成功',
    compile_error: '编译错误',
    runtime_error: '运行时错误',
    timeout: '运行超时',
  }[result.value.status]
})

const serviceErrorTitle = computed(() => {
  if (serviceError.value.includes('运行次数过多')) return '运行过于频繁'
  if (serviceError.value.includes('运行任务较多')) return '运行任务繁忙'
  if (serviceError.value.includes('过长') || serviceError.value.includes('不能为空')) {
    return '代码无法提交'
  }
  return '运行服务不可用'
})

const outputText = computed(() => {
  if (!result.value) return ''
  if (result.value.status === 'compile_error') {
    return result.value.compile_output || '编译失败，但编译器没有返回错误信息。'
  }
  const output = [result.value.stdout, result.value.stderr]
    .filter(Boolean)
    .join(result.value.stdout && result.value.stderr ? '\n' : '')
  if (output) return output
  if (result.value.status === 'timeout') return '程序运行时间超过限制，已由沙箱终止。'
  if (result.value.status === 'runtime_error') return '程序异常退出，但没有返回错误信息。'
  return '[程序没有输出]'
})

watch(
  codeByLanguage,
  value => {
    localStorage.setItem('online_code_python', value.python)
    localStorage.setItem('online_code_c', value.c)
  },
  { deep: true },
)

watch(language, () => {
  result.value = null
  serviceError.value = ''
  clearAnalysis()
})

async function loadRuntimes() {
  runtimesLoading.value = true
  sandboxMessage.value = ''
  try {
    const response = await api.getCodeRuntimes()
    runtimes.value = response.data.languages
    sandboxStatus.value = response.data.status
    sandboxMessage.value = response.data.message || ''
  } catch (error) {
    runtimes.value = []
    sandboxStatus.value = 'unavailable'
    sandboxMessage.value = error instanceof Error ? error.message : '无法连接代码沙箱'
  } finally {
    runtimesLoading.value = false
  }
}

async function runCode() {
  if (running.value || runDisabled.value) return
  if (!code.value.trim()) {
    ElMessage.warning('代码不能为空')
    return
  }

  running.value = true
  result.value = null
  serviceError.value = ''
  clearAnalysis()
  submittedCode.value = code.value
  try {
    const response = await api.executeCode({
      language: language.value,
      code: submittedCode.value,
      stdin: stdin.value,
      timeout_ms: timeoutMs.value,
    })
    result.value = response.data
  } catch (error) {
    serviceError.value = error instanceof Error ? error.message : '代码运行失败'
  } finally {
    running.value = false
  }
}

async function analyzeError() {
  if (!result.value || result.value.status === 'success' || analysisLoading.value) return

  analysisLoading.value = true
  analysis.value = null
  analysisError.value = ''
  try {
    const response = await api.analyzeCodeError({
      language: language.value,
      code: submittedCode.value || code.value,
      status: result.value.status,
      compile_output: result.value.compile_output,
      stderr: result.value.stderr,
      exit_code: result.value.exit_code,
      signal: result.value.signal,
    })
    analysis.value = response.data
  } catch (error) {
    analysisError.value = error instanceof Error ? error.message : 'AI 分析失败'
  } finally {
    analysisLoading.value = false
  }
}

async function applyCorrectedCode() {
  if (!analysis.value?.corrected_code) return
  try {
    await ElMessageBox.confirm(
      '将用 MiMo 建议的完整代码替换当前编辑器内容。',
      '应用 AI 修正',
      { type: 'warning', confirmButtonText: '应用', cancelButtonText: '取消' },
    )
    code.value = analysis.value.corrected_code
    ElMessage.success('修正代码已应用，可以重新运行验证')
  } catch {
    // 用户取消替换。
  }
}

async function copyCorrectedCode() {
  if (!analysis.value?.corrected_code) return
  try {
    await navigator.clipboard.writeText(analysis.value.corrected_code)
    ElMessage.success('修正代码已复制')
  } catch {
    ElMessage.error('复制失败，请检查浏览器权限')
  }
}

async function resetCode() {
  try {
    await ElMessageBox.confirm(
      `将恢复 ${language.value === 'python' ? 'Python' : 'C'} 默认代码。`,
      '恢复默认代码',
      { type: 'warning', confirmButtonText: '恢复', cancelButtonText: '取消' },
    )
    codeByLanguage[language.value] = templates[language.value]
    clearOutput()
  } catch {
    // 用户取消恢复。
  }
}

async function copyCode() {
  try {
    await navigator.clipboard.writeText(code.value)
    ElMessage.success('代码已复制')
  } catch {
    ElMessage.error('复制失败，请检查浏览器权限')
  }
}

function clearOutput() {
  result.value = null
  serviceError.value = ''
  submittedCode.value = ''
  clearAnalysis()
}

function clearAnalysis() {
  analysisLoading.value = false
  analysis.value = null
  analysisError.value = ''
}

onMounted(loadRuntimes)
</script>

<style scoped>
.code-workbench {
  height: 100%;
  min-height: 570px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
}

.code-toolbar {
  min-height: 56px;
  display: grid;
  grid-template-columns: auto minmax(220px, 1fr) auto;
  align-items: center;
  gap: 16px;
  padding: 8px 12px;
  border-bottom: 1px solid #dcdfe6;
}

.toolbar-status,
.toolbar-actions {
  display: flex;
  align-items: center;
}

.toolbar-status {
  min-width: 0;
  gap: 7px;
  color: #606266;
  font-size: 13px;
}

.toolbar-status > span:not(.sandbox-dot) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sandbox-dot {
  width: 8px;
  height: 8px;
  flex: 0 0 8px;
  border-radius: 50%;
  background: #909399;
}

.toolbar-status.is-ready .sandbox-dot {
  background: #16a34a;
}

.toolbar-status.is-partial .sandbox-dot {
  background: #d97706;
}

.toolbar-status.is-unavailable .sandbox-dot {
  background: #dc2626;
}

.runtime-version {
  color: #909399;
}

.toolbar-actions {
  justify-content: flex-end;
  gap: 8px;
}

.timeout-select {
  width: 82px;
}

.code-layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr);
}

.editor-panel,
.stdin-panel,
.output-panel {
  min-width: 0;
  min-height: 0;
}

.editor-panel {
  display: flex;
  flex-direction: column;
  background: #161b22;
}

.panel-heading {
  height: 38px;
  flex: 0 0 38px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 12px;
  color: #303133;
  font-size: 13px;
  font-weight: 600;
  border-bottom: 1px solid #dcdfe6;
}

.editor-heading {
  color: #c9d1d9;
  background: #0d1117;
  border-bottom-color: #30363d;
}

.editor-heading span:last-child {
  color: #8b949e;
  font-weight: 400;
}

.editor-body {
  flex: 1;
  min-height: 0;
}

.io-panel {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(190px, 0.75fr) minmax(270px, 1.25fr);
  border-left: 1px solid #dcdfe6;
}

.stdin-panel,
.output-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.stdin-panel {
  border-bottom: 1px solid #dcdfe6;
}

.stdin-input {
  flex: 1;
  min-height: 0;
}

.stdin-input :deep(.el-textarea__inner) {
  height: 100%;
  min-height: 100% !important;
  padding: 12px;
  border: 0;
  border-radius: 0;
  box-shadow: none;
  resize: none;
  font: 13px/1.6 'Cascadia Code', Consolas, monospace;
}

.output-heading .el-button {
  margin-left: auto;
}

.output-state {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #606266;
  font-size: 13px;
}

.output-state.is-empty {
  color: #909399;
}

.service-error {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 10px;
  margin: 14px;
  padding: 12px;
  color: #991b1b;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
}

.service-error strong {
  display: block;
  font-size: 13px;
}

.service-error p {
  margin: 4px 0 0;
  color: #b91c1c;
  font-size: 12px;
  line-height: 1.55;
}

.result-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 12px;
  overflow: auto;
}

.result-meta {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  color: #606266;
  font-size: 12px;
}

.result-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #b91c1c;
  font-weight: 600;
}

.result-status.is-success {
  color: #15803d;
}

.truncated-note {
  color: #b45309;
}

.ai-analyze-button {
  margin-left: auto;
}

.result-content pre {
  flex: 0 0 auto;
  min-height: 0;
  max-height: 260px;
  overflow: auto;
  margin: 10px 0 0;
  padding: 12px;
  color: #d1fae5;
  background: #111827;
  border: 1px solid #1f2937;
  border-radius: 6px;
  font: 13px/1.6 'Cascadia Code', Consolas, monospace;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.result-content pre.is-error {
  color: #fecaca;
}

.ai-analysis-panel {
  margin-top: 12px;
  padding-top: 12px;
  color: #303133;
  border-top: 1px solid #dcdfe6;
}

.ai-analysis-state,
.ai-analysis-error,
.ai-analysis-heading,
.ai-analysis-heading > span,
.corrected-code-toolbar,
.corrected-code-toolbar > div {
  display: flex;
  align-items: center;
}

.ai-analysis-state {
  min-height: 68px;
  justify-content: center;
  gap: 8px;
  color: #606266;
  font-size: 13px;
}

.ai-analysis-error {
  gap: 8px;
  padding: 10px;
  color: #b91c1c;
  background: #fef2f2;
  border-left: 3px solid #dc2626;
  font-size: 13px;
}

.ai-analysis-heading,
.corrected-code-toolbar {
  justify-content: space-between;
  gap: 12px;
}

.ai-analysis-heading {
  color: #303133;
  font-size: 13px;
  font-weight: 600;
}

.ai-analysis-heading > span:first-child {
  gap: 6px;
}

.ai-analysis-heading > span:last-child {
  color: #909399;
  font-size: 12px;
  font-weight: 400;
}

.analysis-summary {
  display: block;
  margin-top: 10px;
  color: #b91c1c;
  font-size: 14px;
}

.analysis-explanation {
  margin: 7px 0 0;
  color: #4b5563;
  font-size: 13px;
  line-height: 1.65;
}

.analysis-suggestions {
  margin: 8px 0 0;
  padding-left: 22px;
  color: #374151;
  font-size: 13px;
  line-height: 1.7;
}

.corrected-code {
  margin-top: 12px;
}

.corrected-code-toolbar {
  min-height: 32px;
  color: #303133;
  font-size: 13px;
  font-weight: 600;
}

.corrected-code-toolbar > div {
  gap: 6px;
}

.corrected-code pre {
  margin-top: 6px;
  max-height: 300px;
  color: #d1fae5;
}

@media (max-width: 900px) {
  .code-workbench {
    height: auto;
    min-height: calc(100vh - 130px);
    overflow: visible;
  }

  .code-toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .toolbar-status {
    order: 3;
    width: 100%;
  }

  .toolbar-actions {
    margin-left: auto;
  }

  .toolbar-actions > .el-button.is-circle {
    display: none;
  }

  .code-layout {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(430px, 55vh) minmax(520px, auto);
  }

  .io-panel {
    border-left: 0;
    border-top: 1px solid #dcdfe6;
  }

  .ai-analyze-button {
    margin-left: 0;
  }
}

@media (max-width: 540px) {
  .code-toolbar {
    align-items: stretch;
  }

  .language-control {
    width: 100%;
  }

  .language-control :deep(.el-radio-group) {
    display: flex;
    width: 100%;
  }

  .language-control :deep(.el-radio-button) {
    flex: 1;
  }

  .language-control :deep(.el-radio-button__inner) {
    width: 100%;
  }

  .toolbar-actions {
    width: 100%;
    display: grid;
    grid-template-columns: 90px 1fr;
  }

  .timeout-select {
    width: 90px;
  }
}
</style>
