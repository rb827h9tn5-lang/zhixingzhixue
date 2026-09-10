/**
 * 语音采集 AudioWorklet。
 *
 * 为什么不用 MediaRecorder：MiMo 的 ASR 接口只接受 WAV（实测 mp3/webm/ogg/pcm16
 * 全部返回 400 "音频格式转换失败"），而 MediaRecorder 在浏览器里产出的是
 * webm/opus。所以这里取原始 PCM 浮点数据，交给主线程重采样并自己封 WAV 头。
 *
 * 本处理器只做两件事：把每个渲染块的单声道数据发给主线程，并附带音量值用于界面动效。
 */
class VoiceRecorderProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0]
    if (!input || input.length === 0) {
      return true
    }

    const channel = input[0]
    if (!channel || channel.length === 0) {
      return true
    }

    // 复制一份再发送：底层缓冲区会被复用，直接传引用会读到后续数据
    const samples = new Float32Array(channel.length)
    samples.set(channel)

    // 均方根音量，供界面显示说话强度
    let sum = 0
    for (let i = 0; i < samples.length; i += 1) {
      sum += samples[i] * samples[i]
    }
    const level = Math.sqrt(sum / samples.length)

    this.port.postMessage({ samples, level }, [samples.buffer])

    return true
  }
}

registerProcessor('voice-recorder-processor', VoiceRecorderProcessor)
