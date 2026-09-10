<template>
  <!-- 右下角悬浮语音助手：待机监听「小智同学」唤醒，唤醒后解析页面跳转指令 -->
  <div class="voice-assistant" :class="{ 'is-open': panelOpen }">
    <transition name="va-fade">
      <div v-if="panelOpen" class="va-panel" role="dialog" aria-label="语音助手">
        <div class="va-head">
          <span class="va-title">
            <span class="va-dot" :class="statusClass"></span>
            语音助手
          </span>
          <span class="va-stage">{{ stateLabel }}</span>
          <button class="va-close" aria-label="关闭语音助手" @click="closePanel">&times;</button>
        </div>

        <div class="va-body">
          <!-- 语音监听区 -->
          <div class="va-listen">
            <el-button
              :type="isRunning ? 'danger' : 'primary'"
              :loading="starting"
              class="va-listen-btn"
              @click="toggleListening"
            >
              {{ isRunning ? '关闭监听' : '开启监听' }}
            </el-button>
            <span class="va-listen-tip">{{ listenTip }}</span>
          </div>

          <p v-if="!voiceEnabled" class="va-warn">
            后端未配置 MiMo 语音服务，只能使用下方文字输入。
          </p>

          <div v-if="micError" class="va-warn">{{ micError }}</div>

          <!-- 实时识别文字 -->
          <div v-if="isRunning" class="va-heard">
            <span class="va-heard-label">听到</span>
            <span class="va-heard-text">{{ heardText || '…' }}</span>
          </div>

          <div v-if="lastResult" class="va-result" :class="`va-result--${lastResult.kind}`">
            {{ lastResult.text }}
          </div>

          <!-- 文字模拟（调试用，不依赖麦克风） -->
          <el-input
            v-model="inputText"
            placeholder="输入指令或问题，如：深度学习是什么"
            clearable
            :disabled="replying"
            :aria-label="'语音助手输入'"
            @keyup.enter="runCommand(inputText)"
          />

          <div class="va-actions">
            <el-button
              type="primary"
              :loading="replying"
              :disabled="!inputText.trim()"
              @click="runCommand(inputText)"
            >
              发送
            </el-button>
            <el-button text @click="clearLog">清空记录</el-button>
          </div>

          <div class="va-quick">
            <span class="va-quick-label">快捷指令</span>
            <div class="va-quick-list">
              <el-tag
                v-for="sample in SAMPLES"
                :key="sample"
                class="va-quick-tag"
                size="small"
                effect="plain"
                @click="runCommand(sample)"
              >
                {{ sample }}
              </el-tag>
            </div>
          </div>

          <div v-if="history.length" class="va-history">
            <div v-for="(item, i) in history" :key="i" class="va-history-item">
              <span class="va-history-in">{{ item.input }}</span>
              <span class="va-history-out" :class="`is-${item.kind}`">{{ item.reply }}</span>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <button
      class="va-fab"
      :class="{ 'is-listening': isRunning }"
      :aria-label="panelOpen ? '收起语音助手' : '打开语音助手'"
      :aria-expanded="panelOpen"
      @click="togglePanel"
    >
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 2a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3z" />
        <path d="M19 10v1a7 7 0 0 1-14 0v-1" />
        <path d="M12 19v3" />
      </svg>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { navigateToPage } from '../services/pageNavigation'
import { parsePageCommand } from '../services/voiceCommandParser'
import { useVoiceRecorder } from '../composables/useVoiceRecorder'
import { useWakeWord, type VoiceState } from '../composables/useWakeWord'
import { askVoiceAssistant, fetchVoiceStatus, transcribeChunk } from '../api/voice'
import { speak, stopSpeaking } from '../services/speech'

type ResultKind = 'navigate' | 'question' | 'unknown'

interface HistoryItem {
  input: string
  reply: string
  kind: ResultKind
}

const SAMPLES = ['打开测评', '查看学习路径', '打开思维导图', '深度学习是什么', '它能做什么']

const STATE_LABELS: Record<VoiceState, string> = {
  idle: '未开启',
  sleeping: '待机 · 说「小智同学」',
  waking: '已唤醒',
  listening: '请说指令',
  executing: '执行中',
  speaking: '播报中',
}

const panelOpen = ref(false)
const inputText = ref('')
const history = ref<HistoryItem[]>([])
const lastResult = ref<{ text: string; kind: ResultKind } | null>(null)

const voiceEnabled = ref(false)
const starting = ref(false)
const replying = ref(false)
const micError = ref('')
const heardText = ref('')
let activeChatController: AbortController | null = null
let asrGeneration = 0
let asrSequence = 0
let nextAsrResult = 0
const asrControllers = new Set<AbortController>()
const pendingAsrResults = new Map<number, { text: string; isNoise: boolean } | null>()

/** 唤醒词状态机：负责待机/唤醒/命令模式的切换与防误唤醒 */
const wake = useWakeWord({
  onWake: () => {
    speak('在的')
    heardText.value = ''
  },
  onCommand: (text) => {
    runCommand(text, true)
  },
})

/** 录音层：AudioWorklet 采 16k PCM，按 2 秒切成 WAV 分片 */
const recorder = useVoiceRecorder({
  onChunk: async (wav) => {
    const generation = asrGeneration
    const sequence = asrSequence++
    const controller = new AbortController()
    asrControllers.add(controller)
    try {
      const { text, is_noise } = await transcribeChunk(wav, controller.signal)
      if (generation !== asrGeneration) return
      pendingAsrResults.set(sequence, { text, isNoise: is_noise })
    } catch (e) {
      if (generation !== asrGeneration) return
      pendingAsrResults.set(sequence, null)
      // 单片识别失败不打断整体监听
      if (!controller.signal.aborted) console.warn('[voice] 识别失败', e)
    } finally {
      asrControllers.delete(controller)
      if (generation === asrGeneration) drainAsrResults()
    }
  },
  onError: (msg) => {
    micError.value = msg
    stopListening()
  },
})

// 播报和唤醒过渡期挂起音频上行，避免播报声被识别成新指令（方案规则 3）。
// 用 watch 而不是回调，可以避开 wake 与 recorder 的相互引用。
watch(
  () => wake.state.value,
  (s) => {
    if (s === 'speaking' || s === 'waking') recorder.pauseUplink()
    else if (s === 'sleeping' || s === 'listening') recorder.resumeUplink()
  },
)

const isRunning = computed(() => wake.state.value !== 'idle')
const stateLabel = computed(() => replying.value ? '思考中' : STATE_LABELS[wake.state.value])
const statusClass = computed(() => {
  const s = wake.state.value
  if (s === 'idle') return 'is-idle'
  if (s === 'sleeping') return 'is-standby'
  return 'is-ready'
})
const listenTip = computed(() => {
  if (!isRunning.value) return '开启后持续监听唤醒词'
  if (wake.state.value === 'sleeping') return '说「小智同学」唤醒我'
  return '正在命令模式，10 秒无指令自动待机'
})

onMounted(async () => {
  try {
    const status = await fetchVoiceStatus()
    voiceEnabled.value = status.enabled
  } catch {
    voiceEnabled.value = false
  }
})

onUnmounted(() => {
  stopListening()
})

function togglePanel() {
  panelOpen.value = !panelOpen.value
}

function closePanel() {
  panelOpen.value = false
}

async function toggleListening() {
  if (isRunning.value) stopListening()
  else await startListening()
}

async function startListening() {
  micError.value = ''
  starting.value = true
  resetAsrPipeline()
  try {
    await recorder.start()
    wake.begin()
  } catch (e) {
    micError.value = e instanceof Error ? e.message : '无法开启麦克风'
  } finally {
    starting.value = false
  }
}

function stopListening() {
  resetAsrPipeline()
  activeChatController?.abort()
  activeChatController = null
  replying.value = false
  recorder.stop()
  wake.end()
  stopSpeaking()
  heardText.value = ''
}

/** ASR 请求可以并发以降低延迟，但识别文字必须按录音顺序交给唤醒状态机。 */
function drainAsrResults() {
  while (pendingAsrResults.has(nextAsrResult)) {
    const result = pendingAsrResults.get(nextAsrResult)
    pendingAsrResults.delete(nextAsrResult)
    nextAsrResult++
    if (!result || result.isNoise || !result.text) continue
    heardText.value = result.text
    wake.handleText(result.text)
  }
}

function resetAsrPipeline() {
  asrGeneration++
  asrSequence = 0
  nextAsrResult = 0
  pendingAsrResults.clear()
  asrControllers.forEach(controller => controller.abort())
  asrControllers.clear()
}

function clearLog() {
  history.value = []
  lastResult.value = null
}

/**
 * 指令入口。文字输入和语音识别结果共用这条路径。
 * fromVoice 为 true 时会播报结果并通知状态机执行完毕。
 */
async function runCommand(raw: string, fromVoice = false) {
  const text = (raw || '').trim()
  if (!text || replying.value) return

  const result = parsePageCommand(text)
  if (!fromVoice) inputText.value = ''

  if (result.matched && result.pageKey) {
    const ok = navigateToPage(result.pageKey)
    finishCommand(
      text,
      ok ? `已为你打开${result.pageName}` : `无法打开${result.pageName}`,
      'navigate',
      fromVoice,
    )
    return
  }

  const dialogueHistory = history.value
    .filter(item => item.kind === 'question')
    .slice(0, 4)
    .reverse()
    .map(item => ({ user: item.input, assistant: item.reply }))

  activeChatController?.abort()
  const controller = new AbortController()
  activeChatController = controller
  replying.value = true
  lastResult.value = { text: '正在思考…', kind: 'question' }

  try {
    const { answer } = await askVoiceAssistant(text, dialogueHistory, controller.signal)
    if (controller.signal.aborted) return
    finishCommand(text, answer, 'question', fromVoice)
  } catch (error) {
    if (controller.signal.aborted) return
    const reply = error instanceof Error ? error.message : '对话服务暂时不可用，请稍后再试'
    finishCommand(text, reply, 'unknown', fromVoice)
  } finally {
    if (activeChatController === controller) {
      activeChatController = null
      replying.value = false
    }
  }
}

function finishCommand(text: string, reply: string, kind: ResultKind, fromVoice: boolean) {
  lastResult.value = { text: reply, kind }
  history.value.unshift({ input: text, reply, kind })
  if (history.value.length > 8) history.value.pop()

  if (fromVoice && isRunning.value) {
    // 播报期间挂起上行（watch 里处理），播报结束回到命令模式继续等下一条指令
    wake.setSpeaking()
    speak(reply, () => wake.backToListening())
  }
}
</script>

<style scoped>
.voice-assistant {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 2000;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12px;
}

.va-fab {
  width: 48px;
  height: 48px;
  border: none;
  border-radius: 50%;
  background: var(--el-color-primary, #3b82f6);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.18);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.va-fab:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.24);
}

.va-fab:focus-visible {
  outline: 2px solid var(--el-color-primary, #3b82f6);
  outline-offset: 3px;
}

/* 监听中用呼吸动效明示麦克风在工作 */
.va-fab.is-listening {
  background: var(--el-color-danger, #ef4444);
  animation: va-pulse 1.8s ease-in-out infinite;
}

@keyframes va-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.45); }
  50% { box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
}

.va-panel {
  width: 320px;
  max-width: calc(100vw - 32px);
  background: #fff;
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.14);
  overflow: hidden;
}

.va-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
}

.va-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}

.va-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--el-color-info, #909399);
}

.va-dot.is-standby {
  background: var(--el-color-danger, #ef4444);
}

.va-dot.is-ready {
  background: var(--el-color-success, #10b981);
}

.va-stage {
  margin-left: auto;
  font-size: 11px;
  color: var(--el-text-color-secondary, #909399);
}

.va-close {
  border: none;
  background: transparent;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  color: var(--el-text-color-secondary, #909399);
}

.va-body {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.va-listen {
  display: flex;
  align-items: center;
  gap: 8px;
}

.va-listen-btn {
  flex-shrink: 0;
}

.va-listen-tip {
  font-size: 11px;
  line-height: 1.4;
  color: var(--el-text-color-secondary, #909399);
}

.va-warn {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--el-color-warning-light-9, #fdf6ec);
  color: var(--el-color-warning, #e6a23c);
}

.va-heard {
  font-size: 12px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--el-fill-color-light, #f5f7fa);
}

.va-heard-label {
  color: var(--el-text-color-secondary, #909399);
  margin-right: 6px;
}

.va-heard-text {
  color: var(--el-text-color-primary, #303133);
}

.va-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.va-result {
  font-size: 13px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--el-fill-color-light, #f5f7fa);
  color: var(--el-text-color-primary, #303133);
}

.va-result--navigate {
  background: var(--el-color-success-light-9, #f0f9eb);
}

.va-result--unknown {
  background: var(--el-color-warning-light-9, #fdf6ec);
}

.va-quick-label {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}

.va-quick-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.va-quick-tag {
  cursor: pointer;
}

.va-history {
  border-top: 1px dashed var(--el-border-color-lighter, #ebeef5);
  padding-top: 8px;
  max-height: 160px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.va-history-item {
  font-size: 12px;
  line-height: 1.5;
}

.va-history-in {
  color: var(--el-text-color-primary, #303133);
}

.va-history-in::before {
  content: '「';
}

.va-history-in::after {
  content: '」';
}

.va-history-out {
  margin-left: 4px;
  color: var(--el-text-color-secondary, #909399);
}

.va-history-out.is-navigate {
  color: var(--el-color-success, #10b981);
}

.va-fade-enter-active,
.va-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.va-fade-enter-from,
.va-fade-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

@media (max-width: 768px) {
  .voice-assistant {
    right: 16px;
    bottom: 76px; /* 避开移动端底部导航栏 */
  }
}
</style>
