/**
 * 语音助手可访问的页面白名单。
 *
 * 只有登记在此处的页面才允许被语音/文字指令打开，避免解析结果把未知
 * pageKey 传给 App.vue。pageKey 必须与 App.vue 侧边栏 el-menu-item 的
 * index 完全一致：resources_* 会被 App.vue 拆成 activeMenu='resources'
 * 加 resourceSubType。
 */
import { getTabTitle } from '../stores/tabs'

export interface PageTarget {
  /** 展示名，用于语音反馈文案 */
  name: string
  /** 命中该页面的说法，匹配时会先做归一化 */
  keywords: string[]
}

export const PAGE_TARGETS: Record<string, PageTarget> = {
  dashboard: {
    name: getTabTitle('dashboard'),
    keywords: ['打开首页', '打开总览', '回到首页', '学习总览', '看看学习情况'],
  },
  profile: {
    name: getTabTitle('profile'),
    keywords: ['打开个人画像', '查看我的画像', '我的画像', '学习画像'],
  },
  quiz: {
    name: getTabTitle('quiz'),
    keywords: ['打开测评', '进入测评', '我要做题', '我想做几道题', '测评评估'],
  },
  path: {
    name: getTabTitle('path'),
    keywords: ['打开学习路径', '查看学习路径', '查看学习路线', '学习路线', '学习路径', '看看学习路径'],
  },
  tutor: {
    name: getTabTitle('tutor'),
    keywords: ['打开智能辅导', '进入智能辅导', '智能辅导', '我要提问'],
  },
  coding: {
    name: getTabTitle('coding'),
    keywords: ['打开在线编程', '进入在线编程', '在线编程', '打开代码编辑器', '写代码'],
  },
  knowledge: {
    name: getTabTitle('knowledge'),
    keywords: ['打开知识库', '查看知识库', '知识库管理'],
  },
  resources_course_document: {
    name: getTabTitle('resources_course_document'),
    keywords: ['打开讲解文档', '查看课程文档', '讲解文档'],
  },
  resources_mind_map: {
    name: getTabTitle('resources_mind_map'),
    keywords: ['打开思维导图', '查看思维导图', '思维导图'],
  },
  resources_exercise_bank: {
    name: getTabTitle('resources_exercise_bank'),
    keywords: ['打开练习题库', '查看练习题', '练习题库'],
  },
  resources_extension_reading: {
    name: getTabTitle('resources_extension_reading'),
    keywords: ['打开拓展阅读', '查看拓展阅读', '拓展阅读'],
  },
  resources_coding_case: {
    name: getTabTitle('resources_coding_case'),
    keywords: ['打开实操案例', '查看实操案例', '实操案例', '代码案例'],
  },
  resources_multimedia_video: {
    name: getTabTitle('resources_multimedia_video'),
    keywords: ['打开教学视频', '查看教学视频', '教学视频', '找一些视频'],
  },
  resources_ppt_deck: {
    name: getTabTitle('resources_ppt_deck'),
    // 裸 'ppt' 作为兜底关键词，覆盖「我想制作一个人工智能主题的 PPT」这类自然表达。
    // 「PPT 是什么」一类问句由 looksLikeQuestion 拦截，不会误跳转。
    keywords: ['打开ppt生成', '进入ppt制作', 'ppt生成', '制作ppt', '做一个ppt', 'ppt'],
  },
}

export type PageKey = keyof typeof PAGE_TARGETS

export function isValidPageKey(key: string): boolean {
  return Object.prototype.hasOwnProperty.call(PAGE_TARGETS, key)
}

export function getPageName(key: string): string {
  return PAGE_TARGETS[key]?.name ?? key
}

/**
 * 触发页面跳转。App.vue 已监听 navigate-to，会同步 activeMenu、
 * resourceSubType 和顶部标签栏。
 *
 * 白名单外的 key 一律拒绝，返回 false 供调用方给出反馈。
 */
export function navigateToPage(pageKey: string): boolean {
  if (!isValidPageKey(pageKey)) {
    console.warn(`[pageNavigation] 拒绝跳转到未登记页面: ${pageKey}`)
    return false
  }

  window.dispatchEvent(new CustomEvent('navigate-to', { detail: pageKey }))
  return true
}
