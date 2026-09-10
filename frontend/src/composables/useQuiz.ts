import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api/learning'
import { getErrorMessage } from './useUtils'

// 模块级共享状态 —— 历史记录
const quizHistoryRecords = ref<any[]>([])

export function useQuiz() {
  // 组件级独立状态 —— 每个组件各自维护
  const quizLoading = ref(false)
  const quizDraftRecordId = ref<number | null>(null)
  const quizDraftCategory = ref<'exercise' | 'evaluation'>('exercise')
  const quizDraftSaveState = ref<'idle' | 'dirty' | 'saving' | 'saved' | 'failed'>('idle')
  const quizDraftSavedAt = ref('')
  const quizForm = reactive({ difficulty: 'intermediate', focus: '', count: 8 })
  const quizContent = ref('')
  const structuredQuiz = ref<any | null>(null)
  const quizAnswers = reactive<Record<string, string | string[]>>({})
  const quizResult = ref<any | null>(null)
  const selectedQuizRecord = ref<any | null>(null)
  let draftSaveTimer: ReturnType<typeof setTimeout> | null = null
  let activeDraftSave: Promise<boolean> | null = null

  const exerciseHistoryRecords = computed(() => quizHistoryRecords.value.filter((item) => item.category === 'exercise'))
  const evaluationHistoryRecords = computed(() => quizHistoryRecords.value.filter((item) => item.category === 'evaluation'))

  function getQuizDetail(id: number) {
    return quizResult.value?.details?.find((item: any) => item.id === id)
  }

  function quizRecordTitle(record: any) {
    return record.quiz_content || '未命名答题记录'
  }

  function isQuestionAnswered(question: any) {
    const value = quizAnswers[String(question.id)]
    if (Array.isArray(value)) return value.length > 0
    return Boolean(String(value || '').trim())
  }

  function resetQuizAnswers(questions: any[]) {
    Object.keys(quizAnswers).forEach((key) => delete quizAnswers[key])
    questions.forEach((question: any) => {
      quizAnswers[String(question.id)] = question.type === 'multiple_choice' ? [] : ''
    })
  }

  function questionTypeLabel(type: string) {
    return {
      single_choice: '单选题',
      multiple_choice: '多选题',
      true_false: '判断题',
      fill_blank: '填空题',
      short_answer: '简答题',
    }[type] || '题目'
  }

  function optionLabel(index: number, option: string) {
    const letter = optionValue(index)
    const text = String(option || '').trim()
    return new RegExp(`^${letter}\\s*[.、．)]\\s*`, 'i').test(text) ? text : `${letter}. ${text}`
  }

  function optionValue(index: number) {
    return String.fromCharCode(65 + index)
  }

  function stripOptionPrefix(value: string) {
    return String(value || '').replace(/^\s*[A-Za-z]\s*[.、．)]\s*/, '').trim()
  }

  function normalizeChoiceAnswer(question: any, value: unknown) {
    const text = String(value || '').trim()
    if (!text) return ''

    const direct = text.match(/^\s*([A-Za-z])(?:\s*[.、．)]|\s*$)/)
    if (direct) return direct[1].toUpperCase()

    const normalized = stripOptionPrefix(text)
    const options = question?.options || []
    for (let index = 0; index < options.length; index += 1) {
      const optionText = String(options[index] || '').trim()
      if (text === optionText || normalized === stripOptionPrefix(optionText)) {
        return optionValue(index)
      }
    }
    return text
  }

  function normalizeSubmittedAnswers(quiz: any, submitted: Record<string, any>) {
    const normalized: Record<string, string | string[]> = {}
    const questions = quiz?.questions || []
    questions.forEach((question: any) => {
      const key = String(question.id)
      const value = submitted?.[key] ?? submitted?.[question.id]
      if (question.type === 'multiple_choice') {
        const values = Array.isArray(value)
          ? value
          : String(value || '').split(/[,，、/；;]\s*/).filter(Boolean)
        normalized[key] = values.map((item) => normalizeChoiceAnswer(question, item)).filter(Boolean)
      } else if (question.options?.length || question.type === 'single_choice' || question.type === 'true_false') {
        normalized[key] = normalizeChoiceAnswer(question, value)
      } else {
        normalized[key] = String(value || '')
      }
    })
    return normalized
  }

  function answerStatusLabel(status?: string) {
    return {
      correct: '正确',
      partial: '部分正确',
      wrong: '错误',
    }[status || ''] || '未判定'
  }

  function answerStatusType(status?: string) {
    return {
      correct: 'success',
      partial: 'warning',
      wrong: 'danger',
    }[status || ''] || 'info'
  }

  async function generateExerciseBank() {
    if (quizLoading.value) return
    quizLoading.value = true
    try {
      const { data } = await api.generateQuiz({ focus: quizForm.focus, count: quizForm.count, structured: true })
      if (draftSaveTimer) clearTimeout(draftSaveTimer)
      quizDraftRecordId.value = null
      structuredQuiz.value = data.quiz
      quizResult.value = null
      selectedQuizRecord.value = null
      resetQuizAnswers(data.quiz.questions || [])
      quizDraftCategory.value = 'exercise'
      // 自动保存草稿到后端，切换页面后仍可查看
      try {
        const draftRes = await api.saveQuizDraft({ quiz: data.quiz, category: 'exercise' })
        quizDraftRecordId.value = draftRes.data.record.id
        markDraftSaved()
      } catch {
        quizDraftSaveState.value = 'failed'
        ElMessage.warning('题目已生成，但草稿暂未保存；填写答案后将自动重试')
      }
      ElMessage.success('题目已生成')
      return data.quiz
    } catch (error) {
      ElMessage.error(getErrorMessage(error))
    } finally {
      quizLoading.value = false
    }
  }

  async function generateQuizWithDifficulty(focus: string, count: number, difficulty: string) {
    if (quizLoading.value) return
    quizLoading.value = true
    try {
      const { data } = await api.generateQuiz({ focus, count, difficulty, structured: true })
      if (draftSaveTimer) clearTimeout(draftSaveTimer)
      quizDraftRecordId.value = null
      structuredQuiz.value = data.quiz
      quizContent.value = ''
      quizResult.value = null
      selectedQuizRecord.value = null
      resetQuizAnswers(data.quiz.questions || [])
      quizDraftCategory.value = 'evaluation'
      // 自动保存草稿到后端，切换页面后仍可查看
      try {
        const draftRes = await api.saveQuizDraft({ quiz: data.quiz, category: 'evaluation' })
        quizDraftRecordId.value = draftRes.data.record.id
        markDraftSaved()
      } catch {
        quizDraftSaveState.value = 'failed'
        ElMessage.warning('题目已生成，但草稿暂未保存；填写答案后将自动重试')
      }
      ElMessage.success('题目已生成')
      return data.quiz
    } catch (error) {
      ElMessage.error(getErrorMessage(error))
    } finally {
      quizLoading.value = false
    }
  }

  async function submitStructuredQuiz(onSuccess?: () => Promise<void>, category = 'exercise') {
    // 防止模板中不带括号调用传入的事件对象被误作为回调
    const callback = typeof onSuccess === 'function' ? onSuccess : undefined
    if (!structuredQuiz.value) {
      ElMessage.warning('请先生成题目')
      return
    }
    const unanswered = structuredQuiz.value.questions.some((q: any) => !isQuestionAnswered(q))
    if (unanswered) {
      ElMessage.warning('请先完成所有题目')
      return
    }
    if (quizLoading.value) return
    quizLoading.value = true
    try {
      const draftSaved = await saveQuizDraftAnswers(false)
      if (!draftSaved) {
        ElMessage.error('答案尚未保存，请检查网络后重试')
        return
      }
      const { data } = await api.submitStructuredQuiz({
        quiz: structuredQuiz.value,
        answers: { ...quizAnswers },
        record_id: quizDraftRecordId.value,
        category,
      })
      quizResult.value = {
        ...data.result,
        mastery_changes: data.mastery_changes || [],
        replanning: data.replanning || null,
        question_knowledge_point_coverage: data.question_knowledge_point_coverage,
      }
      // 提交成功后绑定到记录，视图进入只读模式，防止重复提交
      selectedQuizRecord.value = data.record
      quizDraftRecordId.value = null
      markDraftSaved()
      await loadQuizHistory()
      // 提交完成释放 loading，避免 AI 评价期间锁住"生成题目"按钮
      quizLoading.value = false
      if (callback) await callback()
      ElMessage.success('答案已提交')
    } catch (error) {
      ElMessage.error(getErrorMessage(error))
    } finally {
      quizLoading.value = false
    }
  }

  async function saveQuizDraftAnswers(showMessage = true): Promise<boolean> {
    if (!structuredQuiz.value || selectedQuizRecord.value || quizResult.value) return true
    if (draftSaveTimer) {
      clearTimeout(draftSaveTimer)
      draftSaveTimer = null
    }
    if (activeDraftSave) await activeDraftSave

    const request = persistQuizDraft(showMessage)
    activeDraftSave = request
    try {
      return await request
    } finally {
      if (activeDraftSave === request) activeDraftSave = null
    }
  }

  async function persistQuizDraft(showMessage: boolean): Promise<boolean> {
    quizDraftSaveState.value = 'saving'
    try {
      if (!quizDraftRecordId.value) {
        const draftResponse = await api.saveQuizDraft({
          quiz: structuredQuiz.value,
          category: quizDraftCategory.value,
        })
        quizDraftRecordId.value = draftResponse.data.record.id
      }
      const recordId = quizDraftRecordId.value
      if (!recordId) throw new Error('草稿编号无效，请重新生成题目')
      await api.updateQuizDraft(recordId, {
        answers: { ...quizAnswers },
      })
      markDraftSaved()
      if (showMessage) ElMessage.success('答题进度已保存')
      return true
    } catch (error) {
      quizDraftSaveState.value = 'failed'
      if (showMessage) ElMessage.error(getErrorMessage(error))
      return false
    }
  }

  function markDraftSaved() {
    quizDraftSaveState.value = 'saved'
    quizDraftSavedAt.value = new Date().toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  const quizDraftSaveLabel = computed(() => {
    if (quizDraftSaveState.value === 'dirty') return '有未保存修改'
    if (quizDraftSaveState.value === 'saving') return '正在保存'
    if (quizDraftSaveState.value === 'failed') return '保存失败'
    if (quizDraftSaveState.value === 'saved') {
      return quizDraftSavedAt.value ? `${quizDraftSavedAt.value} 已保存` : '已保存'
    }
    return '等待作答'
  })

  async function loadQuizHistory() {
    const { data } = await api.quizHistory()
    quizHistoryRecords.value = data.history || []
  }

  async function loadQuizHistoryByCategory(category?: string) {
    const { data } = await api.quizHistory(category)
    quizHistoryRecords.value = data.history || []
  }

  function selectQuizHistory(record: any) {
    const payload = record.answers || {}
    const quiz = payload.quiz
    if (!quiz?.questions?.length) {
      ElMessage.warning('旧记录未保存题目详情，只能查看分数和总结')
      selectedQuizRecord.value = record
      structuredQuiz.value = null
      quizResult.value = { score: record.score, details: [], summary: record.analysis || record.quiz_content }
      return
    }

    // 检测是否为草稿记录（未提交答案的草稿 submitted 为空对象）
    const completed = payload.completed === true || (payload.details || []).length > 0

    if (!completed) {
      // 草稿记录：加载题目但不锁定为只读，让用户可以继续作答
      structuredQuiz.value = quiz
      quizResult.value = null
      selectedQuizRecord.value = null
      quizDraftRecordId.value = record.id  // 关联该草稿记录，提交时更新
      quizDraftCategory.value = record.category === 'evaluation' ? 'evaluation' : 'exercise'
      resetQuizAnswers(quiz.questions || [])
      Object.assign(quizAnswers, normalizeSubmittedAnswers(quiz, payload.submitted || {}))
      markDraftSaved()
      ElMessage.info('已加载草稿题目，请继续作答')
    } else {
      // 已提交的记录：只读模式，显示得分和解析
      quizDraftRecordId.value = null
      selectedQuizRecord.value = record
      structuredQuiz.value = quiz
      quizResult.value = {
        score: record.score,
        details: payload.details || [],
        summary: record.analysis || record.quiz_content,
        evaluation: payload.evaluation || null,
        weak_points: payload.weak_points || [],
        mastery_changes: payload.mastery_changes || [],
        replanning: payload.replanning || null,
      }
      resetQuizAnswers(quiz.questions || [])
      Object.assign(quizAnswers, normalizeSubmittedAnswers(quiz, payload.submitted || payload))
      markDraftSaved()
    }
  }

  async function renameQuizRecord(record: any) {
    try {
      const { value } = await ElMessageBox.prompt('请输入新的答题记录名称', '重命名答题记录', {
        confirmButtonText: '保存',
        cancelButtonText: '取消',
        inputValue: quizRecordTitle(record),
        inputValidator: (v: string) => Boolean(v.trim()) || '名称不能为空'
      })
      const { data } = await api.renameQuizHistory(record.id, value.trim())
      Object.assign(record, data.record)
      if (selectedQuizRecord.value?.id === record.id) selectedQuizRecord.value = record
      ElMessage.success('记录已重命名')
    } catch {
      // 用户取消时不提示错误。
    }
  }

  async function deleteQuizRecord(record: any, onSuccess?: () => Promise<void>) {
    try {
      await ElMessageBox.confirm(`确定删除"${quizRecordTitle(record)}"吗？`, '删除答题记录', {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      })
      await api.deleteQuizHistory(record.id)
      if (quizDraftRecordId.value === record.id) {
        quizDraftRecordId.value = null
        structuredQuiz.value = null
        quizResult.value = null
        resetQuizAnswers([])
      }
      if (selectedQuizRecord.value?.id === record.id) {
        selectedQuizRecord.value = null
        structuredQuiz.value = null
        quizResult.value = null
        resetQuizAnswers([])
      }
      await loadQuizHistory()
      if (onSuccess) await onSuccess()
      ElMessage.success('记录已删除')
    } catch {
      // 用户取消时不提示错误。
    }
  }

  watch(quizAnswers, () => {
    if (!structuredQuiz.value || selectedQuizRecord.value || quizResult.value) return
    quizDraftSaveState.value = 'dirty'
    if (draftSaveTimer) clearTimeout(draftSaveTimer)
    draftSaveTimer = setTimeout(() => {
      void saveQuizDraftAnswers(false)
    }, 700)
  }, { deep: true })

  return {
    quizLoading,
    quizDraftRecordId,
    quizDraftSaveState,
    quizDraftSaveLabel,
    quizForm,
    quizContent,
    structuredQuiz,
    quizAnswers,
    quizResult,
    quizHistoryRecords,
    exerciseHistoryRecords,
    evaluationHistoryRecords,
    selectedQuizRecord,
    getQuizDetail,
    quizRecordTitle,
    questionTypeLabel,
    optionLabel,
    optionValue,
    answerStatusLabel,
    answerStatusType,
    generateExerciseBank,
    generateQuiz: generateQuizWithDifficulty,
    submitStructuredQuiz,
    saveQuizDraftAnswers,
    loadQuizHistory,
    loadQuizHistoryByCategory,
    selectQuizHistory,
    renameQuizRecord,
    deleteQuizRecord,
    resetQuizAnswers,
  }
}
