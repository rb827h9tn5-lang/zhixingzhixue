import { reactive } from 'vue'

export interface StreamState {
  active: boolean
  title: string
  content: string
  sections: Record<number, string>
  progress: string
  type: string
  done: boolean
}

function defaultStreamState(): StreamState {
  return {
    active: false,
    title: '',
    content: '',
    sections: {} as Record<number, string>,
    progress: '',
    type: '',
    done: false,
  }
}

/** 每种资源类型独立的流式状态 */
export const streamingStates = reactive<Record<string, StreamState>>({})

function ensureState(type: string): StreamState {
  if (!streamingStates[type]) {
    streamingStates[type] = defaultStreamState()
  }
  return streamingStates[type]
}

export function activateProgress(type: string, progress = '正在准备生成...') {
  const state = ensureState(type)
  state.active = true
  state.type = type
  state.title = ''
  state.content = ''
  state.sections = {}
  state.progress = progress
  state.done = false
}

const POLL_INTERVAL = 2000
const MAX_POLL_TIME = 300000

export function pollGenerationStatus(
  type: string,
  startedAt: string,
  checkStatus: (type: string, startedAt: string) => Promise<{ status: string; resource?: any }>,
  onComplete: (resource: any) => void,
  onTimeout: () => void,
): { stop: () => void } {
  const startTime = Date.now()
  const timer = setInterval(async () => {
    if (Date.now() - startTime > MAX_POLL_TIME) {
      clearInterval(timer)
      onTimeout()
      return
    }
    try {
      const result = await checkStatus(type, startedAt)
      if (result.status === 'completed') {
        clearInterval(timer)
        onComplete(result.resource)
      }
    } catch {
      // 轮询请求失败则静默跳过，下次继续
    }
  }, POLL_INTERVAL)
  return { stop: () => clearInterval(timer) }
}
