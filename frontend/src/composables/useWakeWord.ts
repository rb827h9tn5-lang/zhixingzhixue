/**
 * 唤醒词状态机。
 *
 * 对应方案第 14 节：待机只判唤醒词，唤醒后进入命令模式解析指令，
 * 超时回切待机。方案里的五条防误唤醒规则全部落在这里：
 *   1. 唤醒词用去标点后的包含匹配，不做等值判断
 *   2. 唤醒后冷却，冷却期内不参与唤醒匹配（防二次唤醒）
 *   3. 播报期间挂起音频上行（防自己唤醒自己）
 *   4. 命令模式超时回切待机
 *   5. 执行期间不接收新指令
 */
import { computed, ref } from 'vue'

export type VoiceState = 'idle' | 'sleeping' | 'waking' | 'listening' | 'executing' | 'speaking'

export const WAKE_WORDS = ['小智同学', '小智同', '晓智同学', '小智']

const COOLDOWN_MS = 600
const COMMAND_TIMEOUT_MS = 10000

/** 去掉标点和空白，抵消识别结果里「小智同学。」这类差异 */
function clean(text: string): string {
  return (text || '').replace(/[\p{P}\p{S}\s]/gu, '')
}

/**
 * 近音字分类，按「小智同学」四个音节各一组。
 *
 * MiMo 对短音频识别很不稳：同一段「小智同学」实测会被听成
 * 「小D组学」「小意长翔汉」「好意将要汉」「号义将杨汉」。
 * 逐字精确匹配会导致唤醒经常失败，所以按音节做容错匹配。
 */
const SYLLABLE_CLASSES = [
  '小晓消销肖效筱宵霄好号毫豪嚎', // xiao / hao
  '智知治指止志质制至意义易一亿d子字紫', // zhi / yi / zi / D
  '同童通桐铜将讲长常场唱组祖足族总宗', // tong / jiang / chang / zu
  '学雪血穴要杨羊阳洋汉喊寒憾些谢', // xue / yao / yang / han
]

/** 四个音节里至少命中三个就认为是唤醒词，容忍一个字听错 */
const FUZZY_THRESHOLD = 3

/** 在文本中找出近音唤醒词的位置，找不到返回 null */
function findFuzzyWake(t: string): { start: number; end: number } | null {
  const lower = t.toLowerCase()
  for (let i = 0; i + FUZZY_THRESHOLD <= lower.length; i++) {
    let score = 0
    for (let k = 0; k < SYLLABLE_CLASSES.length; k++) {
      const ch = lower[i + k]
      if (ch && SYLLABLE_CLASSES[k].includes(ch)) score++
    }
    if (score >= FUZZY_THRESHOLD) {
      return { start: i, end: i + SYLLABLE_CLASSES.length }
    }
  }
  return null
}

export function includesWakeWord(text: string): boolean {
  const t = clean(text)
  if (!t) return false
  if (WAKE_WORDS.some(w => t.includes(clean(w)))) return true
  return findFuzzyWake(t) !== null
}

/** 取唤醒词之后剩余的文字，支持「小智同学，打开测评」一句话完成唤醒+指令 */
export function stripWakeWord(text: string): string {
  const t = clean(text)

  // 先按精确别名截取，取最靠前的一个
  let cut = -1
  for (const w of WAKE_WORDS) {
    const key = clean(w)
    const idx = t.indexOf(key)
    if (idx >= 0 && (cut < 0 || idx + key.length < cut)) cut = idx + key.length
  }

  if (cut < 0) {
    const fuzzy = findFuzzyWake(t)
    if (fuzzy) cut = fuzzy.end
  }

  const rest = cut >= 0 ? t.slice(cut) : t
  // 误识别常在唤醒词后多带一两个杂字（如「小意长翔汉」的「汉」），
  // 太短的残留不可能是有效指令，直接丢掉
  return rest.length >= 2 ? rest : ''
}

export interface WakeWordCallbacks {
  /** 命中唤醒词，需要播报「在的」并挂起上行 */
  onWake: () => void
  /** 命令模式下收到有效指令文字 */
  onCommand: (text: string) => void
  /** 回到待机 */
  onSleep?: () => void
}

export function useWakeWord(callbacks: WakeWordCallbacks) {
  const state = ref<VoiceState>('idle')
  /** 唤醒句里跟在唤醒词后面的那截，冷却结束后直接当指令用 */
  const pendingCommandText = ref('')

  let cooldownTimer: ReturnType<typeof setTimeout> | null = null
  let commandTimer: ReturnType<typeof setTimeout> | null = null

  const isActive = computed(() => state.value !== 'idle')
  const stateLabel = computed(() => {
    switch (state.value) {
      case 'sleeping': return '待机中，说「小智同学」唤醒'
      case 'waking': return '已唤醒'
      case 'listening': return '请说指令'
      case 'executing': return '正在执行'
      case 'speaking': return '播报中'
      default: return '未开启'
    }
  })

  function clearTimers() {
    if (cooldownTimer) { clearTimeout(cooldownTimer); cooldownTimer = null }
    if (commandTimer) { clearTimeout(commandTimer); commandTimer = null }
  }

  function toSleeping() {
    clearTimers()
    pendingCommandText.value = ''
    state.value = 'sleeping'
    callbacks.onSleep?.()
  }

  /** 规则 4：命令模式超时回切待机 */
  function startCommandTimeout() {
    if (commandTimer) clearTimeout(commandTimer)
    commandTimer = setTimeout(() => {
      if (state.value === 'listening') toSleeping()
    }, COMMAND_TIMEOUT_MS)
  }

  function resetCommandTimeout() {
    startCommandTimeout()
  }

  /** 规则 2：唤醒后冷却；重复唤醒词忽略，紧随其后的命令暂存 */
  function enterCommandMode() {
    state.value = 'waking'
    callbacks.onWake()
    if (cooldownTimer) clearTimeout(cooldownTimer)
    cooldownTimer = setTimeout(() => {
      cooldownTimer = null
      if (state.value !== 'waking') return
      state.value = 'listening'
      startCommandTimeout()

      // 规则：唤醒句里已经带了指令，冷却结束直接执行，不必让用户再说一次
      const carried = pendingCommandText.value
      pendingCommandText.value = ''
      if (carried) {
        state.value = 'executing'
        callbacks.onCommand(carried)
      }
    }, COOLDOWN_MS)
  }

  /**
   * 处理一段识别文字。
   * 返回 false 表示这段文字被状态机忽略（冷却/执行/播报中）。
   */
  function handleText(text: string): boolean {
    const t = clean(text)
    if (!t) return false

    // 规则 3、5：播报中和执行中不处理新文字
    if (state.value === 'speaking' || state.value === 'executing') {
      return false
    }

    // ASR 请求并发返回时，唤醒词和后续命令可能在同一时刻按序交付。
    // 冷却期只过滤重复唤醒尾音，真正的命令留到冷却结束后执行。
    if (state.value === 'waking') {
      const commandText = includesWakeWord(t) ? stripWakeWord(t) : t
      if (commandText.length >= 2) pendingCommandText.value = commandText
      return Boolean(commandText)
    }

    if (state.value === 'sleeping') {
      if (!includesWakeWord(t)) return false
      pendingCommandText.value = stripWakeWord(t)
      enterCommandMode()
      return true
    }

    if (state.value === 'listening') {
      resetCommandTimeout()
      state.value = 'executing'
      callbacks.onCommand(t)
      return true
    }

    return false
  }

  function begin() {
    state.value = 'sleeping'
  }

  function end() {
    clearTimers()
    pendingCommandText.value = ''
    state.value = 'idle'
  }

  /** 执行/播报结束后停在 listening，给用户继续下指令的窗口 */
  function backToListening() {
    if (state.value === 'idle') return
    state.value = 'listening'
    startCommandTimeout()
  }

  function setSpeaking() {
    if (state.value === 'idle') return
    state.value = 'speaking'
  }

  return {
    state,
    stateLabel,
    isActive,
    handleText,
    begin,
    end,
    backToListening,
    setSpeaking,
    toSleeping,
  }
}
