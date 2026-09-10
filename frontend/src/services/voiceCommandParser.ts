/**
 * 语音/文字指令解析。
 *
 * 第一阶段只做本地关键词匹配，不调用大模型：命中页面白名单就跳转，
 * 否则视为普通学习问题交给智能辅导。
 */
import { PAGE_TARGETS } from './pageNavigation'

export type CommandType = 'navigate' | 'question' | 'unknown'

export interface ParsedCommand {
  matched: boolean
  type: CommandType
  pageKey?: string
  pageName?: string
  /** 命中的关键词，便于调试和界面展示 */
  keyword?: string
  /** 归一化后的文本 */
  normalized: string
}

/** 去掉标点和空白并转小写，抵消识别结果里的标点差异 */
export function normalizeVoiceText(input: string): string {
  return (input || '')
    .replace(/[\p{P}\p{S}\s]/gu, '')
    .toLowerCase()
}

/**
 * 疑问表达。命中这些词时优先当作学习提问，避免「什么是思维导图」
 * 这类问句因为包含页面名而被误判成跳转。
 */
const QUESTION_MARKERS = [
  '什么是', '是什么', '为什么', '怎么理解', '如何理解', '解释一下',
  '讲一下', '讲讲', '介绍一下', '区别', '原理', '帮我制定', '怎么办',
]

function looksLikeQuestion(normalized: string): boolean {
  return QUESTION_MARKERS.some(marker => normalized.includes(normalizeVoiceText(marker)))
}

/**
 * 解析页面跳转指令。
 *
 * 采用「最长关键词优先」：同一句话可能同时命中多个页面的关键词
 * （例如「练习题库」也包含「题」），取匹配长度最长的一条更准确。
 */
export function parsePageCommand(input: string): ParsedCommand {
  const text = normalizeVoiceText(input)

  if (!text) {
    return { matched: false, type: 'unknown', normalized: text }
  }

  let best: { pageKey: string; pageName: string; keyword: string; length: number } | null = null

  for (const [pageKey, config] of Object.entries(PAGE_TARGETS)) {
    for (const keyword of config.keywords) {
      const normalizedKeyword = normalizeVoiceText(keyword)
      if (!normalizedKeyword || !text.includes(normalizedKeyword)) continue

      if (!best || normalizedKeyword.length > best.length) {
        best = {
          pageKey,
          pageName: config.name,
          keyword,
          length: normalizedKeyword.length,
        }
      }
    }
  }

  // 提问句即使命中页面名也不跳转，交给智能辅导
  if (best && looksLikeQuestion(text)) {
    return { matched: false, type: 'question', normalized: text }
  }

  if (best) {
    return {
      matched: true,
      type: 'navigate',
      pageKey: best.pageKey,
      pageName: best.pageName,
      keyword: best.keyword,
      normalized: text,
    }
  }

  return {
    matched: false,
    type: looksLikeQuestion(text) ? 'question' : 'unknown',
    normalized: text,
  }
}
