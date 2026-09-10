import { computed, type Ref } from 'vue'

const subTypeLabels: Record<string, string> = {
  course_document: '讲解文档',
  mind_map: '思维导图',
  exercise_bank: '练习题库',
  extension_reading: '拓展阅读',
  coding_case: '实操案例',
  multimedia_video: '教学视频',
  ppt_deck: 'PPT生成',
}

const menuLabels: Record<string, string> = {
  dashboard: '总览',
  profile: '个人画像',
  path: '学习路径',
  resources: '知识学习',
  quiz: '测评评估',
  tutor: '智能辅导',
  knowledge: '知识库管理',
}

export function useBreadcrumb(activeMenu: Ref<string>, resourceSubType: Ref<string>) {
  const breadcrumbItems = computed(() => {
    const items: Array<{ label: string }> = []

    if (activeMenu.value === 'resources') {
      items.push({ label: '知识学习' })
      const subLabel = subTypeLabels[resourceSubType.value]
      if (subLabel) {
        items.push({ label: subLabel })
      }
    } else {
      const label = menuLabels[activeMenu.value]
      if (label) {
        items.push({ label })
      }
    }

    return items
  })

  return { breadcrumbItems }
}