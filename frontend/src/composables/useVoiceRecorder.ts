/**
 * 麦克风持续采集 + 端点检测 + WAV 语句切片。
 *
 * 为什么不用 MediaRecorder：MiMo 的 ASR 接口实测只接受 WAV，
 * mp3/webm/ogg/pcm16 一律返回「音频格式转换失败」。而 MediaRecorder 在
 * 浏览器里产出的是 webm/opus，所以这里改用 AudioWorklet 取原始 PCM，
 * 在前端重采样到 16kHz 单声道后自己封 WAV 头。
 *
 * 实测最优参数：16kHz / 单声道 / 16bit。录音会保留少量前导声音，
 * 并在用户停顿后立即提交整句话，避免固定时间切片从词语中间截断。
 */
import { ref } from 'vue'

const TARGET_SAMPLE_RATE = 16000
const VOICE_THRESHOLD = 0.004
const PRE_ROLL_MS = 250
const END_SILENCE_MS = 500
const MIN_SPEECH_MS = 180
const DEFAULT_MAX_UTTERANCE_MS = 5000
/** 带版本号：AudioWorklet 模块会被浏览器单独缓存，普通刷新不一定重新拉取 */
const WORKLET_URL = '/voice-recorder-worklet.js?v=3'
const PROCESSOR_NAME = 'voice-recorder-processor'

/** Float32 [-1,1] 线性重采样到目标采样率 */
function resample(input: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate === toRate) return input
  const ratio = fromRate / toRate
  const outLength = Math.floor(input.length / ratio)
  const output = new Float32Array(outLength)
  for (let i = 0; i < outLength; i++) {
    const pos = i * ratio
    const left = Math.floor(pos)
    const right = Math.min(left + 1, input.length - 1)
    const frac = pos - left
    output[i] = input[left] * (1 - frac) + input[right] * frac
  }
  return output
}

/** Float32 PCM 封装成 16bit 单声道 WAV */
function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)

  const writeString = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i))
  }

  writeString(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)        // fmt chunk 大小
  view.setUint16(20, 1, true)         // PCM
  view.setUint16(22, 1, true)         // 单声道
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true) // 字节率
  view.setUint16(32, 2, true)         // 块对齐
  view.setUint16(34, 16, true)        // 位深
  writeString(36, 'data')
  view.setUint32(40, samples.length * 2, true)

  let offset = 44
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
    offset += 2
  }

  return new Blob([buffer], { type: 'audio/wav' })
}

/** 计算音量均方根，用于界面音量条和跳过明显的静音分片 */
function rms(samples: Float32Array): number {
  let sum = 0
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i]
  return Math.sqrt(sum / (samples.length || 1))
}

export interface VoiceRecorderOptions {
  /** 单句话允许的最长时长，默认 5000ms */
  chunkMs?: number
  /** 分片就绪回调；level 为该片音量 */
  onChunk: (wav: Blob, level: number) => void
  onError?: (message: string) => void
}

export function useVoiceRecorder(options: VoiceRecorderOptions) {
  const recording = ref(false)
  const level = ref(0)

  let stream: MediaStream | null = null
  let context: AudioContext | null = null
  let source: MediaStreamAudioSourceNode | null = null
  let node: AudioWorkletNode | null = null

  /** 累积当前一句话的重采样样本 */
  let buffer: Float32Array[] = []
  let buffered = 0
  let speechSamples = 0
  let trailingSilenceSamples = 0
  let speechStarted = false
  /** speaking 期间挂起上行，避免播报声被当成新指令（自唤醒） */
  let paused = false

  function maxUtteranceSamples() {
    return Math.floor((TARGET_SAMPLE_RATE * (options.chunkMs ?? DEFAULT_MAX_UTTERANCE_MS)) / 1000)
  }

  function resetCapture() {
    buffer = []
    buffered = 0
    speechSamples = 0
    trailingSilenceSamples = 0
    speechStarted = false
  }

  function trimToPreRoll() {
    const keepSamples = Math.floor((TARGET_SAMPLE_RATE * PRE_ROLL_MS) / 1000)
    while (buffer.length > 1 && buffered - buffer[0].length >= keepSamples) {
      const removed = buffer.shift()
      buffered -= removed?.length ?? 0
    }
  }

  function flushUtterance() {
    if (!buffered) return
    const merged = new Float32Array(buffered)
    let offset = 0
    for (const part of buffer) {
      merged.set(part, offset)
      offset += part.length
    }
    const capturedSpeechSamples = speechSamples
    resetCapture()

    if (capturedSpeechSamples < TARGET_SAMPLE_RATE * MIN_SPEECH_MS / 1000) return
    const chunkLevel = rms(merged)
    level.value = chunkLevel
    if (paused) return
    options.onChunk(encodeWav(merged, TARGET_SAMPLE_RATE), chunkLevel)
  }

  function captureBlock(samples: Float32Array, blockLevel: number) {
    if (paused) {
      resetCapture()
      return
    }

    buffer.push(samples)
    buffered += samples.length
    const isSpeech = blockLevel >= VOICE_THRESHOLD

    if (!speechStarted) {
      if (!isSpeech) {
        trimToPreRoll()
        return
      }
      speechStarted = true
    }

    if (isSpeech) {
      speechSamples += samples.length
      trailingSilenceSamples = 0
    } else {
      trailingSilenceSamples += samples.length
    }

    const endSilenceSamples = TARGET_SAMPLE_RATE * END_SILENCE_MS / 1000
    if (trailingSilenceSamples >= endSilenceSamples || buffered >= maxUtteranceSamples()) {
      flushUtterance()
    }
  }

  async function start(): Promise<boolean> {
    if (recording.value) return true

    if (!navigator.mediaDevices?.getUserMedia) {
      options.onError?.('当前浏览器不支持麦克风采集')
      return false
    }

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      })
    } catch (err) {
      const name = (err as DOMException)?.name
      options.onError?.(
        name === 'NotAllowedError'
          ? '麦克风权限被拒绝，请在浏览器地址栏的权限设置里允许后重试'
          : '无法打开麦克风：' + ((err as Error)?.message || String(err)),
      )
      return false
    }

    try {
      context = new AudioContext()
      await context.audioWorklet.addModule(WORKLET_URL)
      source = context.createMediaStreamSource(stream)
      node = new AudioWorkletNode(context, 'voice-recorder-processor')

      const inputRate = context.sampleRate
      node.port.onmessage = (event) => {
        // worklet 发的是 { samples, level }，不是裸的 Float32Array
        const { samples, level: chunkLevel } = (event.data ?? {}) as {
          samples?: Float32Array
          level?: number
        }
        if (typeof chunkLevel === 'number') level.value = chunkLevel
        if (!samples?.length) return
        const converted = resample(samples, inputRate, TARGET_SAMPLE_RATE)
        captureBlock(converted, typeof chunkLevel === 'number' ? chunkLevel : rms(converted))
      }

      source.connect(node)
      // 不接 destination，避免把麦克风声音回放出来造成啸叫
      recording.value = true
      return true
    } catch (err) {
      options.onError?.('初始化录音失败：' + ((err as Error)?.message || String(err)))
      await stop()
      return false
    }
  }

  async function stop() {
    recording.value = false
    level.value = 0
    resetCapture()
    paused = false

    try {
      node?.port.close()
      node?.disconnect()
      source?.disconnect()
    } catch { /* ignore */ }

    // 必须停掉每个 track，否则浏览器标签页的麦克风红点不会消失
    stream?.getTracks().forEach(track => track.stop())
    if (context && context.state !== 'closed') {
      try { await context.close() } catch { /* ignore */ }
    }

    node = null
    source = null
    stream = null
    context = null
  }

  /** 播报期间挂起上行，防止自己的声音触发唤醒 */
  function pauseUplink() {
    paused = true
    resetCapture()
  }

  function resumeUplink() {
    paused = false
    resetCapture()
  }

  return { recording, level, start, stop, pauseUplink, resumeUplink }
}
