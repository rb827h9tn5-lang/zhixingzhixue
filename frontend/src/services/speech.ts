/**
 * 语音播报。第一版用浏览器自带的 speechSynthesis，
 * 后续可替换为 MiMo TTS（mimo-v2.5-tts）而不改调用方。
 */

export function speechSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

/**
 * 播报一段文字。
 *
 * @param onDone 播报结束（或失败）后的回调。调用方靠它把状态机从
 *               speaking 切回 listening，所以即使播报失败也必须触发。
 */
export function speak(text: string, onDone?: () => void, rate = 1): void {
  if (!text) {
    onDone?.()
    return
  }

  if (!speechSupported()) {
    onDone?.()
    return
  }

  try {
    window.speechSynthesis.cancel()

    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'zh-CN'
    utterance.rate = rate

    let finished = false
    const finish = () => {
      if (finished) return
      finished = true
      onDone?.()
    }

    utterance.onend = finish
    utterance.onerror = finish

    // 兜底：个别浏览器不触发 onend，避免状态机卡在 speaking
    const fallbackMs = Math.min(60000, 1800 + text.length * 190 / Math.max(0.5, rate))
    setTimeout(finish, fallbackMs)

    window.speechSynthesis.speak(utterance)
  } catch {
    onDone?.()
  }
}

export function stopSpeaking(): void {
  if (!speechSupported()) return
  try {
    window.speechSynthesis.cancel()
  } catch {
    /* 忽略：播报停止失败不影响主流程 */
  }
}

export function pauseSpeaking(): void {
  if (!speechSupported()) return
  try {
    window.speechSynthesis.pause()
  } catch {
    /* 暂停失败时保留当前播放状态。 */
  }
}

export function resumeSpeaking(): void {
  if (!speechSupported()) return
  try {
    window.speechSynthesis.resume()
  } catch {
    /* 恢复失败时由调用方重新播放。 */
  }
}
