import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { api } from '../api/learning'
import type {
  DigitalHumanLesson,
  DigitalHumanSpeechResponse,
  DigitalHumanStatus,
  DigitalHumanSubtitle,
  DigitalHumanVoice,
} from '../api/learning'
import {
  pauseSpeaking,
  resumeSpeaking,
  speak,
  speechSupported,
  stopSpeaking,
} from '../services/speech'

export type DigitalHumanPlayerStatus =
  | 'idle'
  | 'loading'
  | 'ready'
  | 'playing'
  | 'paused'
  | 'failed'

interface CachedSpeech {
  data: DigitalHumanSpeechResponse
  absoluteUrl: string
}

type QuickSpeechResult =
  | { kind: 'ready'; speech: CachedSpeech }
  | { kind: 'error'; error: unknown }
  | { kind: 'timeout' }

const QUICK_TTS_WAIT_MS = 2500

export function useDigitalHuman(resultId: Ref<number>) {
  const status = ref<DigitalHumanPlayerStatus>('idle')
  const lessons = ref<DigitalHumanLesson[]>([])
  const currentIndex = ref(0)
  const errorMessage = ref('')
  const warningMessage = ref('')
  const scriptProvider = ref('')
  const voices = ref<DigitalHumanVoice[]>([])
  const voice = ref('冰糖')
  const rate = ref(1)
  const progress = ref(0)
  const durationMs = ref(0)
  const subtitles = ref<DigitalHumanSubtitle[]>([])
  const subtitleText = ref('')
  const ttsConfigured = ref(false)
  const ttsUnavailable = ref(false)
  const usingBrowserVoice = ref(false)
  const speechCache = new Map<string, CachedSpeech>()
  const pendingSpeech = new Map<string, Promise<CachedSpeech>>()

  let audio: HTMLAudioElement | null = null
  let animationFrame = 0
  let browserAnimationStarted = 0

  const currentLesson = computed(() => lessons.value[currentIndex.value] || null)
  const hasPrevious = computed(() => currentIndex.value > 0)
  const hasNext = computed(() => currentIndex.value < lessons.value.length - 1)

  async function loadStatus() {
    try {
      const response = await api.getDigitalHumanStatus()
      const data = response.data as DigitalHumanStatus
      ttsConfigured.value = data.tts_configured
      voices.value = data.voices || []
      voice.value = data.default_voice || voices.value[0]?.id || '冰糖'
      if (!data.enabled) {
        status.value = 'failed'
        errorMessage.value = '数字人功能未启用'
      }
    } catch (error) {
      warningMessage.value = error instanceof Error ? error.message : '无法读取数字人配置'
      voices.value = [
        { id: '冰糖', label: '冰糖', gender: '女声' },
        { id: '茉莉', label: '茉莉', gender: '女声' },
        { id: '苏打', label: '苏打', gender: '男声' },
        { id: '白桦', label: '白桦', gender: '男声' },
      ]
    }
  }

  async function prepare(regenerate = false) {
    if (!resultId.value || status.value === 'loading') return
    stop()
    status.value = 'loading'
    errorMessage.value = ''
    warningMessage.value = ''
    try {
      const response = await api.prepareDigitalHuman(resultId.value, regenerate)
      lessons.value = response.data.lessons || []
      scriptProvider.value = response.data.script_provider || ''
      warningMessage.value = response.data.warning || ''
      currentIndex.value = 0
      status.value = lessons.value.length ? 'ready' : 'failed'
      if (!lessons.value.length) errorMessage.value = '没有生成可播放的讲解'
    } catch (error) {
      status.value = 'failed'
      errorMessage.value = error instanceof Error ? error.message : '数字人讲解生成失败'
    }
  }

  async function play() {
    const lesson = currentLesson.value
    if (!lesson) return
    if (status.value === 'paused') {
      resume()
      return
    }
    errorMessage.value = ''

    const cacheKey = `${resultId.value}:${voice.value}:${lesson.question_id}`
    const cached = speechCache.get(cacheKey)
    if (cached && !ttsUnavailable.value) {
      playAudio(cached)
      return
    }
    if (!ttsUnavailable.value && ttsConfigured.value) {
      status.value = 'loading'
      const request = requestSpeech(cacheKey, lesson)
      const quickResult = await waitForQuickSpeech(request)
      if (quickResult.kind === 'ready') {
        playAudio(quickResult.speech)
        return
      }
      if (quickResult.kind === 'error') {
        ttsUnavailable.value = true
        warningMessage.value = `${quickResult.error instanceof Error ? quickResult.error.message : 'MiMo TTS 暂时不可用'}，已切换为浏览器语音`
      } else {
        warningMessage.value = 'MiMo TTS 正在后台生成，先使用浏览器语音'
        void request
          .then(() => {
            warningMessage.value = 'MiMo TTS 音频已缓存，下次播放将使用云端音色'
          })
          .catch((error) => {
            ttsUnavailable.value = true
            warningMessage.value = `${error instanceof Error ? error.message : 'MiMo TTS 暂时不可用'}，已继续使用浏览器语音`
          })
      }
    }
    playWithBrowserVoice(lesson.speech_text)
  }

  function requestSpeech(cacheKey: string, lesson: DigitalHumanLesson): Promise<CachedSpeech> {
    const existing = pendingSpeech.get(cacheKey)
    if (existing) return existing

    const request = api.synthesizeDigitalHumanSpeech(
      resultId.value,
      lesson.question_id,
      voice.value,
    ).then((response) => {
      const cachedSpeech: CachedSpeech = {
        data: response.data,
        absoluteUrl: absoluteApiUrl(response.data.audio_url),
      }
      speechCache.set(cacheKey, cachedSpeech)
      return cachedSpeech
    }).finally(() => {
      pendingSpeech.delete(cacheKey)
    })

    pendingSpeech.set(cacheKey, request)
    return request
  }

  function waitForQuickSpeech(request: Promise<CachedSpeech>): Promise<QuickSpeechResult> {
    return Promise.race([
      request
        .then(speech => ({ kind: 'ready', speech }) as const)
        .catch(error => ({ kind: 'error', error }) as const),
      new Promise<{ kind: 'timeout' }>(resolve => {
        window.setTimeout(() => resolve({ kind: 'timeout' }), QUICK_TTS_WAIT_MS)
      }),
    ])
  }

  function playAudio(cached: CachedSpeech) {
    destroyAudio()
    usingBrowserVoice.value = false
    subtitles.value = cached.data.subtitles || []
    durationMs.value = cached.data.duration_ms || 0
    audio = new Audio()
    audio.crossOrigin = 'anonymous'
    audio.src = cached.absoluteUrl
    audio.playbackRate = rate.value
    audio.preload = 'auto'
    audio.ontimeupdate = updateAudioProgress
    audio.onended = finishPlayback
    audio.onerror = () => {
      warningMessage.value = '云端音频加载失败，已切换为浏览器语音'
      ttsUnavailable.value = true
      playWithBrowserVoice(currentLesson.value?.speech_text || '')
    }
    audio.play()
      .then(() => {
        status.value = 'playing'
      })
      .catch(() => {
        warningMessage.value = '浏览器阻止了音频播放，请再次点击播放'
        status.value = 'ready'
      })
  }

  function playWithBrowserVoice(text: string) {
    destroyAudio()
    stopSpeaking()
    usingBrowserVoice.value = true
    subtitles.value = []
    subtitleText.value = text
    progress.value = 0
    durationMs.value = Math.min(60000, Math.max(3000, text.length * 190))
    if (!speechSupported()) {
      status.value = 'failed'
      errorMessage.value = '当前浏览器不支持语音播放，请阅读下方文字讲解'
      return
    }
    status.value = 'playing'
    browserAnimationStarted = performance.now()
    animateBrowserVoice()
    speak(text, finishPlayback, rate.value)
  }

  function pause() {
    if (status.value !== 'playing') return
    if (usingBrowserVoice.value) pauseSpeaking()
    else audio?.pause()
    status.value = 'paused'
    cancelAnimationFrame(animationFrame)
  }

  function resume() {
    if (status.value !== 'paused') return
    if (usingBrowserVoice.value) {
      resumeSpeaking()
      status.value = 'playing'
      animateBrowserVoice()
      return
    }
    audio?.play().then(() => {
      status.value = 'playing'
    }).catch(() => {
      status.value = 'ready'
    })
  }

  function replay() {
    if (usingBrowserVoice.value) {
      playWithBrowserVoice(currentLesson.value?.speech_text || '')
      return
    }
    if (audio) {
      audio.currentTime = 0
      audio.play().then(() => {
        status.value = 'playing'
      })
      return
    }
    play()
  }

  function stop() {
    destroyAudio()
    stopSpeaking()
    usingBrowserVoice.value = false
    progress.value = 0
    subtitleText.value = ''
    if (lessons.value.length) status.value = 'ready'
  }

  function selectLesson(index: number) {
    if (index < 0 || index >= lessons.value.length || index === currentIndex.value) return
    stop()
    currentIndex.value = index
    warningMessage.value = ''
  }

  function previous() {
    if (hasPrevious.value) selectLesson(currentIndex.value - 1)
  }

  function next() {
    if (hasNext.value) selectLesson(currentIndex.value + 1)
  }

  function setRate(value: number) {
    rate.value = value
    if (audio) audio.playbackRate = value
    if (usingBrowserVoice.value && status.value === 'playing') {
      playWithBrowserVoice(currentLesson.value?.speech_text || '')
    }
  }

  function setVoice(value: string) {
    if (voice.value === value) return
    stop()
    voice.value = value
    ttsUnavailable.value = false
  }

  function updateAudioProgress() {
    if (!audio) return
    const currentMs = audio.currentTime * 1000
    const total = audio.duration * 1000 || durationMs.value
    progress.value = total ? Math.min(100, currentMs / total * 100) : 0
    const active = subtitles.value.find(
      item => currentMs >= item.start && currentMs < item.end,
    )
    subtitleText.value = active?.text || currentLesson.value?.speech_text || ''
  }

  function animateBrowserVoice() {
    if (status.value !== 'playing') return
    const elapsed = (performance.now() - browserAnimationStarted) / 1000
    if (durationMs.value) {
      progress.value = Math.min(96, elapsed * 1000 / durationMs.value * 100)
    }
    animationFrame = requestAnimationFrame(animateBrowserVoice)
  }

  function finishPlayback() {
    cancelAnimationFrame(animationFrame)
    progress.value = 100
    status.value = 'ready'
  }

  function destroyAudio() {
    cancelAnimationFrame(animationFrame)
    if (audio) {
      audio.pause()
      audio.src = ''
      audio.load()
      audio = null
    }
  }

  function reset() {
    stop()
    lessons.value = []
    currentIndex.value = 0
    errorMessage.value = ''
    warningMessage.value = ''
    scriptProvider.value = ''
    status.value = 'idle'
    speechCache.clear()
    ttsUnavailable.value = false
  }

  watch(resultId, reset)
  onBeforeUnmount(() => {
    destroyAudio()
    stopSpeaking()
  })

  return {
    status,
    lessons,
    currentIndex,
    currentLesson,
    errorMessage,
    warningMessage,
    scriptProvider,
    voices,
    voice,
    rate,
    progress,
    subtitleText,
    ttsConfigured,
    usingBrowserVoice,
    hasPrevious,
    hasNext,
    loadStatus,
    prepare,
    play,
    pause,
    resume,
    replay,
    stop,
    previous,
    next,
    selectLesson,
    setRate,
    setVoice,
  }
}

function absoluteApiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path
  const base = import.meta.env.VITE_API_BASE_URL || window.location.origin
  return new URL(path, base.endsWith('/') ? base : `${base}/`).toString()
}
