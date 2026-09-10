import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface TabItem {
  key: string
  title: string
  affix: boolean
}

const STORAGE_KEY = 'openedTabs'

const TAB_TITLES: Record<string, string> = {
  dashboard: '总览',
  profile: '个人画像',
  quiz: '测评评估',
  path: '学习路径',
  diagnosis: '学习诊断',
  remediation: '补救计划',
  'adaptive-exam': '自适应测评',
  growth: '成长报告',
  tutor: '智能辅导',
  coding: '在线编程',
  knowledge: '知识库管理',
}

const SUB_LABELS: Record<string, string> = {
  course_document: '讲解文档',
  mind_map: '思维导图',
  exercise_bank: '练习题库',
  extension_reading: '拓展阅读',
  coding_case: '实操案例',
  multimedia_video: '教学视频',
  ppt_deck: 'PPT生成',
}

export function getTabTitle(key: string): string {
  if (TAB_TITLES[key]) return TAB_TITLES[key]
  for (const [st, label] of Object.entries(SUB_LABELS)) {
    if (key === `resources_${st}`) return label
  }
  return key
}

export const useTabsStore = defineStore('tabs', () => {
  const openedTabs = ref<TabItem[]>([{ key: 'dashboard', title: '总览', affix: true }])
  const activeTabKey = ref('dashboard')

  function addTab(key: string, title: string, affix = false) {
    if (!openedTabs.value.some(t => t.key === key)) {
      openedTabs.value.push({ key, title, affix })
    }
    activeTabKey.value = key
    saveTabs()
  }

  function removeTab(key: string) {
    const tab = openedTabs.value.find(t => t.key === key)
    if (!tab || tab.affix) return

    const idx = openedTabs.value.findIndex(t => t.key === key)
    const isActive = activeTabKey.value === key

    openedTabs.value = openedTabs.value.filter(t => t.key !== key)

    if (isActive && openedTabs.value.length > 0) {
      const newIdx = Math.min(idx, openedTabs.value.length - 1)
      activeTabKey.value = openedTabs.value[newIdx].key
    }

    saveTabs()
  }

  function setActiveTab(key: string) {
    activeTabKey.value = key
  }

  function saveTabs() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(openedTabs.value))
  }

  function restoreTabs() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const tabs = JSON.parse(saved) as TabItem[]
        if (tabs.length > 0) {
          openedTabs.value = tabs
          activeTabKey.value = tabs[0].key
          return
        }
      }
    } catch { /* ignore */ }
    openedTabs.value = [{ key: 'dashboard', title: '总览', affix: true }]
    activeTabKey.value = 'dashboard'
  }

  return { openedTabs, activeTabKey, addTab, removeTab, setActiveTab, saveTabs, restoreTabs }
})
