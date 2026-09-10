import type { Ref } from 'vue'
import { ref } from 'vue'
import MarkdownIt from 'markdown-it'
import { ElMessage } from 'element-plus'
import { useSessionStore } from '../stores/session'

function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function installCodeCopyHandler(): void {
  if (typeof document === 'undefined') return

  const marker = 'data-study-code-copy-handler'
  if (document.documentElement.hasAttribute(marker)) return
  document.documentElement.setAttribute(marker, 'true')

  document.addEventListener('click', async (event) => {
    const target = event.target
    if (!(target instanceof Element)) return

    const button = target.closest<HTMLButtonElement>('.code-copy-btn[data-code]')
    if (!button) return

    try {
      await navigator.clipboard.writeText(decodeURIComponent(button.dataset.code || ''))
      button.classList.add('copied')
      window.setTimeout(() => button.classList.remove('copied'), 2000)
    } catch {
      ElMessage.error('复制失败，请手动选择代码')
    }
  })
}

installCodeCopyHandler()

export function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : '操作失败，请检查后端服务是否正常运行'
}

export async function runAction(loadingRef: Ref<boolean>, action: () => Promise<void>, successMessage = '') {
  if (loadingRef.value) return
  loadingRef.value = true
  try {
    await action()
    if (successMessage) ElMessage.success(successMessage)
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    loadingRef.value = false
  }
}

const md = new MarkdownIt({
  html: false, linkify: true, breaks: true,
  highlight: (str: string, lang: string) => {
    const language = lang || 'text'
    const escaped = escapeHtml(str)
    const encoded = encodeURIComponent(str)
    const safeLanguage = escapeHtml(language)
    return `<div class="code-block-wrap">
      <div class="code-block-header">
        <div class="code-dots">
          <span class="dot dot-red"></span>
          <span class="dot dot-yellow"></span>
          <span class="dot dot-green"></span>
        </div>
        <span class="code-lang-label">${safeLanguage}</span>
        <button type="button" class="code-copy-btn" data-code="${escapeHtml(encoded)}">复制</button>
      </div>
      <pre class="code-block-body"><code>${escaped}</code></pre>
    </div>`
  },
})

function stripHtmlTags(value: string): string {
  return String(value || '').replace(/<[^>]*>/g, '').trim()
}

function extractDetailsBlocks(content: string): { content: string; blocks: string[] } {
  const blocks: string[] = []
  const nextContent = String(content || '').replace(
    /<details(?:\s[^>]*)?>\s*<summary(?:\s[^>]*)?>([\s\S]*?)<\/summary>([\s\S]*?)<\/details>/gi,
    (_match, rawSummary: string, rawBody: string) => {
      const summary = escapeHtml(stripHtmlTags(rawSummary) || '查看详情')
      const bodyHtml = postProcessMarkdown(md.render(String(rawBody || '').trim()))
      const index = blocks.push(
        `<details class="markdown-details"><summary>${summary}</summary><div class="markdown-details-body">${bodyHtml}</div></details>`
      ) - 1
      return `\n\n@@DETAILS_BLOCK_${index}@@\n\n`
    }
  )
  return { content: nextContent, blocks }
}

function restoreDetailsBlocks(html: string, blocks: string[]): string {
  return html
    .replace(/<p>@@DETAILS_BLOCK_(\d+)@@<\/p>/g, (_match, index: string) => blocks[Number(index)] || '')
    .replace(/@@DETAILS_BLOCK_(\d+)@@/g, (_match, index: string) => blocks[Number(index)] || '')
}

function normalizeHeadingText(value: string): string {
  return stripHtmlTags(value).replace(/\s+/g, '').replace(/[：:，,。.!！?？、.．]/g, '').trim()
}

function stripLessonChatter(content: string): string {
  let text = String(content || '').trim()
  const chatterPatterns = [
    /^(好的|好|你好|您好)[，,！!。.\s]*(同学|同学们|这位同学)?[，,！!。.\s]*[\s\S]{0,220}?(今天|接下来|下面|我们|让我们|现在)[\s\S]{0,160}?(开始|进入|学习|讲解|看看)[^。\n]*[。\n]+/u,
    /^让我们开始(?:第一|本)?[章节节课]?.{0,40}[。\n]+/u,
    /^接下来(?:我们)?(?:开始|进入|学习|讲解).{0,80}[。\n]+/u,
  ]
  for (let i = 0; i < 3; i += 1) {
    const before = text
    for (const pattern of chatterPatterns) {
      text = text.replace(pattern, '').trim()
    }
    if (text === before) break
  }
  return text
}

function normalizeEscapedMarkdownText(content: string): string {
  const text = String(content || '')
  const escapedBreaks = (text.match(/\\r\\n|\\n|\\r/g) || []).length
  if (!escapedBreaks) return text
  const realBreaks = (text.match(/\r\n|\n|\r/g) || []).length
  if (escapedBreaks < 2 && realBreaks > escapedBreaks) return text
  return text
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\r/g, '\n')
    .replace(/\\t/g, '  ')
}

function normalizeMarkdownSource(content: string): string {
  const lines = stripLessonChatter(normalizeEscapedMarkdownText(content)).replace(/\r\n/g, '\n').split('\n')
  const nonEmpty = lines.filter(line => line.trim())
  const indents = nonEmpty
    .map(line => line.match(/^[ \t]*/)?.[0].replace(/\t/g, '    ').length ?? 0)
    .filter(count => count > 0)
  const commonIndent = indents.length ? Math.min(...indents) : 0
  return lines
    .map(line => {
      const withoutCommonIndent = commonIndent ? line.replace(new RegExp(`^[ \\t]{0,${commonIndent}}`), '') : line
      return withoutCommonIndent
        .replace(/^[ \t]{1,8}(#{1,6}\s+)/, '$1')
        .replace(/^[ \t]{1,8}([*+-]\s+)/, '$1')
        .replace(/^[ \t]{1,8}(\d+[.)、]\s+)/, '$1')
    })
    .join('\n')
    .trim()
}

function renderMarkdownFragment(content: string): string {
  const details = extractDetailsBlocks(normalizeMarkdownSource(content))
  return restoreDetailsBlocks(postProcessMarkdown(md.render(details.content)), details.blocks)
}

function stripDuplicateSectionHeading(html: string, title: string): string {
  const expectedTitle = normalizeHeadingText(title)
  if (!expectedTitle) return html
  let removed = false
  return html.replace(/<h([1-4])>([\s\S]*?)<\/h\1>/i, (match, _level, heading, offset) => {
    if (removed || offset > 1200) return match
    const actualTitle = normalizeHeadingText(heading)
    if (actualTitle && (actualTitle.includes(expectedTitle) || expectedTitle.includes(actualTitle))) {
      removed = true
      return ''
    }
    return match
  })
}

function renderMarkedSections(content: string): string {
  const markerPattern = /<!--\s*MA_SECTION_START\s+index=(\d+)\s+title=([^\s>]+)\s*-->([\s\S]*?)<!--\s*MA_SECTION_END\s+index=\1\s*-->/g
  const sections = Array.from(String(content || '').matchAll(markerPattern))
  if (!sections.length) return ''

  let result = ''
  let cursor = 0
  sections.forEach((match, index) => {
    const start = match.index || 0
    const preface = content.slice(cursor, start).trim()
    if (preface) result += renderMarkdownFragment(preface)

    const sectionNo = Number(match[1]) || index + 1
    const title = decodeURIComponent(match[2] || '').trim() || `第 ${sectionNo} 节`
    const bodyHtml = stripDuplicateSectionHeading(renderMarkdownFragment(match[3] || ''), title)
    result += `<details class="markdown-section-details"><summary><span class="section-index">${sectionNo}</span><span class="section-title">${escapeHtml(title)}</span></summary><div class="markdown-section-body">${bodyHtml}</div></details>`
    cursor = start + match[0].length
  })

  const tail = content.slice(cursor).trim()
  if (tail) result += renderMarkdownFragment(tail)
  return result
}

function stripSectionMarkers(content: string): string {
  return String(content || '')
    .replace(/<!--\s*MA_SECTION_START\s+index=\d+\s+title=[^\s>]+\s*-->/g, '')
    .replace(/<!--\s*MA_SECTION_END\s+index=\d+\s*-->/g, '')
}

function getChapterHeadingKind(value: string): 'cjk' | 'arabic' | '' {
  const text = stripHtmlTags(value).replace(/\s+/g, ' ').trim()
  if (!text) return ''
  if (/^第\s*[\d一二三四五六七八九十百千万]+\s*[章节篇课部分]/.test(text)
    || /^[一二三四五六七八九十百千万]+[、.．]\s*/.test(text)) {
    return 'cjk'
  }
  if (/^\d{1,2}[、．]\s*/.test(text) || /^\d{1,2}\.\s+/.test(text)) {
    return 'arabic'
  }
  return ''
}

function collapseHeadingSections(html: string): string {
  const allHeadings = Array.from(html.matchAll(/<h([2-4])>([\s\S]*?)<\/h\1>/gi))
  const cjkHeadings = allHeadings.filter(match => getChapterHeadingKind(match[2]) === 'cjk')
  const arabicHeadings = allHeadings.filter(match => getChapterHeadingKind(match[2]) === 'arabic')
  const chapterHeadings = cjkHeadings.length >= 2 ? cjkHeadings : arabicHeadings
  const matches = chapterHeadings.length >= 2
    ? chapterHeadings
    : Array.from(html.matchAll(/<h2>([\s\S]*?)<\/h2>/gi))
  if (!matches.length) return html

  let result = html.slice(0, matches[0].index || 0)
  matches.forEach((match, index) => {
    const start = match.index || 0
    const end = index + 1 < matches.length ? (matches[index + 1].index || html.length) : html.length
    const sectionHtml = html.slice(start + match[0].length, end).trim()
    const rawTitle = chapterHeadings.length >= 2 ? match[2] : match[1]
    const title = escapeHtml(stripHtmlTags(rawTitle) || `第 ${index + 1} 节`)
    result += `<details class="markdown-section-details"><summary><span class="section-index">${index + 1}</span><span class="section-title">${title}</span></summary><div class="markdown-section-body">${sectionHtml}</div></details>`
  })
  return result
}

function postProcessMarkdown(html: string): string {
  // 将包含特定关键词的引用块转为 Callout 卡片
  html = html.replace(/<blockquote>\s*<p>(.*?)<\/p>\s*<\/blockquote>/gs, (_m, content: string) => {
    if (content.includes('为什么先讲这个') || content.startsWith('重点')) {
      return `<div class="callout-card callout-info"><div class="callout-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg></div><div class="callout-content"><p>${content}</p></div></div>`
    }
    if (content.includes('易错点') || content.includes('注意')) {
      return `<div class="callout-card callout-warning"><div class="callout-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg></div><div class="callout-content"><p>${content}</p></div></div>`
    }
    if (content.includes('代码练习') || content.includes('实践任务')) {
      return `<div class="callout-card callout-success"><div class="callout-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg></div><div class="callout-content"><p>${content}</p></div></div>`
    }
    if (content.includes('推荐下一步')) {
      return `<div class="callout-card callout-purple"><div class="callout-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg></div><div class="callout-content"><p>${content}</p></div></div>`
    }
    return `<blockquote><p>${content}</p></blockquote>`
  })

  // 将包含特定关键词的独立段落转为 Callout 卡片
  html = html.replace(/<p>((?:(?!<\/p>).)*(为什么先讲这个|易错点|代码练习|实践任务|推荐下一步|重点|注意)(?:(?!<\/p>).)*)<\/p>/gs, (_m, content: string) => {
    if (content.includes('为什么先讲这个') || content.startsWith('重点')) {
      return `<div class="callout-card callout-info"><div class="callout-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg></div><div class="callout-content"><p>${content}</p></div></div>`
    }
    if (content.includes('易错点') || content.includes('注意')) {
      return `<div class="callout-card callout-warning"><div class="callout-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg></div><div class="callout-content"><p>${content}</p></div></div>`
    }
    if (content.includes('代码练习') || content.includes('实践任务')) {
      return `<div class="callout-card callout-success"><div class="callout-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg></div><div class="callout-content"><p>${content}</p></div></div>`
    }
    if (content.includes('推荐下一步')) {
      return `<div class="callout-card callout-purple"><div class="callout-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg></div><div class="callout-content"><p>${content}</p></div></div>`
    }
    return `<p>${content}</p>`
  })

  return html
}

export function renderMarkdown(content: string, options: { collapsibleHeadings?: boolean } = {}) {
  if (!content) return ''
  if (options.collapsibleHeadings) {
    const markedHtml = renderMarkedSections(content)
    if (markedHtml) return markedHtml
  }
  const details = extractDetailsBlocks(normalizeMarkdownSource(stripSectionMarkers(content)))
  const html = restoreDetailsBlocks(postProcessMarkdown(md.render(details.content)), details.blocks)
  return options.collapsibleHeadings ? collapseHeadingSections(html) : html
}

let authExpiredShown = false

export function handleAuthExpired() {
  if (authExpiredShown) return
  authExpiredShown = true
  const session = useSessionStore()
  session.logout()
  ElMessage.warning('登录状态已失效，请重新登录')
}

export function formatDateTime(value: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value.replace('T', ' ').slice(0, 16)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function scoreText(score: number | string) {
  const numericScore = Number(score || 0)
  return `${Number.isInteger(numericScore) ? numericScore : numericScore.toFixed(1)} 分`
}

export const knowledgeLevelLabels: Record<string, string> = {
  beginner: '入门',
  intermediate: '中级',
  advanced: '高级',
}

export const learningStyleLabels: Record<string, string> = {
  mixed: '混合型',
  visual: '视觉型',
  auditory: '听觉型',
  kinesthetic: '动手实践型',
  reading_writing: '读写型',
}

export const timeAvailabilityLabels: Record<string, string> = {
  '1-2 hours per week': '每周 1-2 小时',
  '3-5 hours per week': '每周 3-5 小时',
  '6-10 hours per week': '每周 6-10 小时',
  '10+ hours per week': '每周 10 小时以上',
}

export function formatKnowledgeLevel(value: string) {
  return knowledgeLevelLabels[value] || value || '未设置'
}

export function formatLearningStyle(value: string) {
  return learningStyleLabels[value] || value || '未设置'
}

export function formatTimeAvailability(value: string) {
  return timeAvailabilityLabels[value] || value || '未设置'
}

export function formatPathMetaValue(item: { label: string; value: string }) {
  if (item.label.includes('当前基础')) return formatKnowledgeLevel(item.value)
  if (item.label.includes('学习风格')) return formatLearningStyle(item.value)
  if (item.label.includes('可投入时间')) return formatTimeAvailability(item.value)
  return item.value || '未设置'
}

export function questionTypeLabel(type: string) {
  return {
    single_choice: '单选题',
    multiple_choice: '多选题',
    true_false: '判断题',
    fill_blank: '填空题',
    short_answer: '简答题',
  }[type] || '题目'
}

export function optionLabel(index: number, option: string) {
  return `${String.fromCharCode(65 + index)}. ${option}`
}

export function answerStatusLabel(status?: string) {
  return {
    correct: '正确',
    partial: '部分正确',
    wrong: '错误',
  }[status || ''] || '未判定'
}

export function answerStatusType(status?: string) {
  return {
    correct: 'success',
    partial: 'warning',
    wrong: 'danger',
  }[status || ''] || 'info'
}

export function hashText(value: string) {
  let hash = 0
  for (let index = 0; index < value.length; index += 1) {
    hash = ((hash << 5) - hash + value.charCodeAt(index)) | 0
  }
  return Math.abs(hash).toString(36)
}

// 页面切换计数器 —— 当用户在侧边栏切换页面时自增，
// 组件通过 watch 此值来重置加载状态，避免切回页面时按钮仍被 loading 锁死
const tabSwitchCounter = ref(0)

export function notifyTabSwitch() {
  tabSwitchCounter.value++
}

export function useTabSwitch() {
  return tabSwitchCounter
}
