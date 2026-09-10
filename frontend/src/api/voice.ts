import { http } from './http'

export interface VoiceStatus {
  enabled: boolean
  model: string
  dialogue_enabled: boolean
  dialogue_model: string
  chunk_ms: number
  sample_rate: number
}

export interface TranscribeResult {
  text: string
  is_noise: boolean
}

export interface VoiceDialogueTurn {
  user: string
  assistant: string
}

export interface VoiceChatResult {
  answer: string
}

/** 开启监听前先查后端是否配置了 MiMo，避免白白申请麦克风权限 */
export async function fetchVoiceStatus(): Promise<VoiceStatus> {
  const { data } = await http.get<VoiceStatus>('/api/voice/status')
  return data
}

/**
 * 上传一段 WAV 分片做识别。
 *
 * 走后端代理，MiMo API Key 不会出现在浏览器里。
 */
export async function transcribeChunk(wav: Blob, signal?: AbortSignal): Promise<TranscribeResult> {
  const form = new FormData()
  form.append('audio', wav, 'chunk.wav')

  const { data } = await http.post<TranscribeResult>('/api/voice/transcribe', form, {
    signal,
    // 单片识别实测 4~7 秒，给足超时但不用全局的 5 分钟
    timeout: 30000,
  })
  return data
}

/** 普通问句走简短对话接口；页面跳转仍由前端本地解析，不会发给大模型。 */
export async function askVoiceAssistant(
  question: string,
  history: VoiceDialogueTurn[],
  signal?: AbortSignal,
): Promise<VoiceChatResult> {
  const { data } = await http.post<VoiceChatResult>('/api/voice/chat', {
    question,
    history,
  }, {
    signal,
    timeout: 30000,
  })
  return data
}
