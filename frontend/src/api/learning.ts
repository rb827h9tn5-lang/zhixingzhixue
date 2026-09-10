import { authHttp, http } from './http'

function apiTimeoutMs(): number {
  const value = import.meta.env.VITE_API_TIMEOUT_MS
  return value ? parseInt(value, 10) : 300000
}

function abortWithTimeout(ms: number): AbortSignal {
  if (typeof AbortSignal.timeout === 'function') {
    return AbortSignal.timeout(ms)
  }
  const controller = new AbortController()
  setTimeout(() => controller.abort(), ms)
  return controller.signal
}

function combineSignals(s1: AbortSignal, s2: AbortSignal): AbortSignal {
  const controller = new AbortController()
  const onAbort = () => controller.abort()
  s1.addEventListener('abort', onAbort)
  s2.addEventListener('abort', onAbort)
  if (s1.aborted || s2.aborted) controller.abort()
  return controller.signal
}

export type ResourceType =
  | 'course_document'
  | 'mind_map'
  | 'exercise_bank'
  | 'extension_reading'
  | 'coding_case'
  | 'multimedia_video'
  | 'ppt_deck'

export type CodeLanguage = 'python' | 'c'

export interface CodeRuntime {
  id: CodeLanguage
  label: string
  version: string
  available: boolean
}

export interface CodeRuntimeResponse {
  status: 'ready' | 'partial' | 'unavailable'
  languages: CodeRuntime[]
  message?: string
}

export type CodeExecutionStatus =
  | 'success'
  | 'compile_error'
  | 'runtime_error'
  | 'timeout'

export interface CodeExecutionRequest {
  language: CodeLanguage
  code: string
  stdin: string
  timeout_ms?: number
}

export interface CodeExecutionResult {
  status: CodeExecutionStatus
  language: CodeLanguage
  version: string
  stdout: string
  stderr: string
  compile_output: string
  exit_code: number | null
  signal: string | null
  duration_ms: number
  truncated: boolean
}

export interface CodeErrorAnalysisRequest {
  language: CodeLanguage
  code: string
  status: Exclude<CodeExecutionStatus, 'success'>
  compile_output: string
  stderr: string
  exit_code: number | null
  signal: string | null
}

export interface CodeErrorAnalysis {
  summary: string
  explanation: string
  suggestions: string[]
  corrected_code: string
  model: string
}

export type DigitalHumanLessonStatus = 'wrong' | 'partial' | 'summary'

export interface DigitalHumanLesson {
  question_id: string
  question_number: number | string
  concept: string
  status: DigitalHumanLessonStatus
  question_summary: string
  user_answer: string
  reference_answer: string
  explanation: string
  mistake_reason: string
  reasoning_steps: string[]
  memory_tip: string
  speech_text: string
  script_provider?: string
}

export interface DigitalHumanVoice {
  id: string
  label: string
  gender: string
}

export interface DigitalHumanStatus {
  enabled: boolean
  script_model: string
  tts_configured: boolean
  tts_model: string
  default_voice: string
  voices: DigitalHumanVoice[]
}

export interface DigitalHumanPrepareResponse {
  status: 'ready'
  result_id: number
  lessons: DigitalHumanLesson[]
  script_provider: string
  cached: boolean
  warning: string
}

export interface DigitalHumanSubtitle {
  start: number
  end: number
  text: string
}

export interface DigitalHumanSpeechResponse {
  audio_url: string
  duration_ms: number
  provider: string
  model: string
  from_cache: boolean
  voice: string
  subtitles: DigitalHumanSubtitle[]
}

export const resourceOptions: Array<{ label: string; value: ResourceType }> = [
  { label: '讲解文档', value: 'course_document' },
  { label: '思维导图', value: 'mind_map' },
  { label: '练习题库', value: 'exercise_bank' },
  { label: '拓展阅读', value: 'extension_reading' },
  { label: '实操案例', value: 'coding_case' },
  { label: '教学视频', value: 'multimedia_video' },
  { label: 'PPT生成', value: 'ppt_deck' },
]

export const api = {
  register: (data: unknown) => authHttp.post('/api/auth/register', data),
  login: (data: unknown) => authHttp.post('/api/auth/login', data),
  me: () => http.get('/api/auth/me'),
  getCodeRuntimes: () =>
    http.get<CodeRuntimeResponse>('/api/code/runtimes', { timeout: 8000 }),
  executeCode: (data: CodeExecutionRequest) =>
    http.post<CodeExecutionResult>('/api/code/execute', data, { timeout: 20000 }),
  analyzeCodeError: (data: CodeErrorAnalysisRequest) =>
    http.post<CodeErrorAnalysis>('/api/code/analyze-error', data, { timeout: 60000 }),
  getDigitalHumanStatus: () =>
    http.get<DigitalHumanStatus>('/api/digital-human/status', { timeout: 8000 }),
  prepareDigitalHuman: (resultId: number, regenerate = false) =>
    http.post<DigitalHumanPrepareResponse>(
      `/api/quiz/${resultId}/digital-human/prepare`,
      { regenerate },
      { timeout: 90000 },
    ),
  synthesizeDigitalHumanSpeech: (
    resultId: number,
    questionId: string,
    voice: string,
  ) =>
    http.post<DigitalHumanSpeechResponse>(
      `/api/quiz/${resultId}/digital-human/questions/${encodeURIComponent(questionId)}/speech`,
      { voice },
      { timeout: 40000 },
    ),
  dashboard: () => http.get('/api/dashboard'),
  getProfile: () => http.get('/api/profile'),
  updateProfile: (data: unknown) => http.post('/api/profile/dialogue', data),
  draftProfileIntake: (data: unknown) => http.post('/api/profile/intake/draft', data),
  confirmProfileIntake: (data: unknown) => http.post('/api/profile/intake/confirm', data),
  getProfileVersions: () => http.get('/api/profile/versions'),
  getProfileEvidence: (dimension = '') =>
    http.get(`/api/profile/evidence${dimension ? `?dimension=${encodeURIComponent(dimension)}` : ''}`),
  getMastery: (includeEvidence = false) =>
    http.get(`/api/mastery?include_evidence=${includeEvidence ? 'true' : 'false'}`),
  getMasteryDetail: (knowledgePointId: number) =>
    http.get(`/api/mastery/${knowledgePointId}`),
  getDiagnosis: () => http.get('/api/diagnosis'),
  getDiagnosisDetail: (knowledgePointId: number) =>
    http.get(`/api/diagnosis/${knowledgePointId}`),
  getGrowthReport: (days: number | 'all' = 30) =>
    http.get(`/api/growth-report?days=${days}`),
  createRemediationPlan: (knowledgePointId?: number) =>
    http.post('/api/remediation-plans', {
      knowledge_point_id: knowledgePointId,
    }),
  getRemediationPlans: () => http.get('/api/remediation-plans'),
  startRemediationPlan: (planId: number) =>
    http.post(`/api/remediation-plans/${planId}/start`),
  createAdaptiveExam: (data: {
    duration_minutes: number
    goal: 'diagnosis' | 'reinforcement' | 'mock' | 'comprehensive' | 'transfer'
    difficulty: string
    course_id?: number
    knowledge_point_id?: number
  }) => http.post('/api/adaptive-exams', data),
  getAdaptiveExams: () => http.get('/api/adaptive-exams'),
  getAdaptiveExam: (examId: number) =>
    http.get(`/api/adaptive-exams/${examId}`),
  submitAdaptiveExam: (
    examId: number,
    answers: Record<string, unknown>,
    reasoningSteps: Record<string, unknown> = {},
    selfConfidence: Record<string, unknown> = {},
  ) => http.post(`/api/adaptive-exams/${examId}/submit`, {
    answers,
    reasoning_steps: reasoningSteps,
    self_confidence: selfConfidence,
  }),
  getCognitiveDiagnoses: (assessmentId: number) =>
    http.get(`/api/cognitive-diagnoses/${assessmentId}`),
  getMisconceptions: (knowledgePointId?: number) =>
    http.get(
      `/api/misconceptions${
        knowledgePointId ? `?knowledge_point_id=${knowledgePointId}` : ''
      }`,
    ),
  selectTeachingStrategy: (knowledgePointId?: number) =>
    http.post('/api/teaching-strategies/select', {
      knowledge_point_id: knowledgePointId,
    }),
  getCurrentTeachingStrategy: () =>
    http.get('/api/teaching-strategies/current'),
  getTeachingStrategyHistory: (limit = 30) =>
    http.get(`/api/teaching-strategies/history?limit=${limit}`),
  getTeachingInterventions: (limit = 30) =>
    http.get(`/api/teaching-interventions?limit=${limit}`),
  createTransferAssessment: (data: {
    knowledge_point_id?: number
    course_id?: number
    duration_minutes?: number
    difficulty?: string
  }) => http.post('/api/transfer-assessments', data),
  getMasteryDimensions: (knowledgePointId: number) =>
    http.get(`/api/mastery-dimensions/${knowledgePointId}`),
  getCapabilityGate: (knowledgePointId: number) =>
    http.get(`/api/capability-gates/${knowledgePointId}`),
  getMetacognitiveCalibration: () =>
    http.get('/api/metacognitive-calibration'),
  explainDecision: (data: {
    decision_type: 'remediation' | 'next_learning' | 'path_change' | 'resource' | 'exam_question'
    knowledge_point_id?: number
    node_id?: number
    path_version_id?: number
    exam_id?: number
  }) => http.post('/api/decision-explanations', data),
  getAgentRuns: (taskType = '', limit = 20) =>
    http.get(
      `/api/agent-runs?limit=${limit}${
        taskType ? `&task_type=${encodeURIComponent(taskType)}` : ''
      }`,
    ),
  getAgentRun: (runId: number) => http.get(`/api/agent-runs/${runId}`),
  getLearningEvents: (knowledgePointId?: number, limit = 100) =>
    http.get(
      `/api/learning-events?limit=${limit}${
        knowledgePointId ? `&knowledge_point_id=${knowledgePointId}` : ''
      }`,
    ),
  planPath: () => http.post('/api/path/plan'),
  latestPath: () => http.get('/api/path/latest'),
  getPathVersions: () => http.get('/api/path/versions'),
  getPathVersionDiff: (fromVersionId: number, toVersionId: number) =>
    http.get(`/api/path/versions/${fromVersionId}/diff/${toVersionId}`),
  getLatestPathDiff: () => http.get('/api/path/latest-diff'),
  openPathNode: (nodeId: number) => http.post(`/api/path/nodes/${nodeId}/open`),
  completePathNode: (nodeId: number) => http.post(`/api/path/nodes/${nodeId}/complete`),
  getAutoResourceStatus: (since: string) => http.get(`/api/resources/auto-status?since=${encodeURIComponent(since)}`),
  generateResourceAsync: (type: ResourceType, extraInput = '') => http.post('/api/resources/generate-async', { type, extra_input: extraInput }),
  getAsyncGenerationStatus: (type: string, startedAt: string) => http.get(`/api/resources/generate-async-status?type=${type}&started_at=${encodeURIComponent(startedAt)}`),
  listResources: () => http.get('/api/resources'),
  generateResources: (types: ResourceType[], extraInput = '') => http.post('/api/resources/generate', { types, extra_input: extraInput }),
  generateResource: (type: ResourceType, extraInput = '') => http.post('/api/resources/generate', { type, extra_input: extraInput }),
  generateResourceStream: (type: ResourceType, extraInput: string, onEvent: (event: string, data: any) => void, signal?: AbortSignal) => {
    const token = localStorage.getItem('study_token')
    const apiBase = import.meta.env.VITE_API_BASE_URL || ''
    const timeoutSignal = abortWithTimeout(apiTimeoutMs())
    const combinedSignal = signal ? combineSignals(signal, timeoutSignal) : timeoutSignal
    return fetch(`${apiBase}/api/resources/generate-stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ type, extra_input: extraInput }),
      signal: combinedSignal,
    }).then(async (response) => {
      if (response.status === 401 || response.status === 422) {
        localStorage.removeItem('study_token')
        window.dispatchEvent(new Event('auth-expired'))
        throw new Error('登录状态已失效，请重新登录')
      }
      if (!response.ok) {
        const text = await response.text()
        throw new Error(text || `请求失败：${response.status}`)
      }
      const reader = response.body?.getReader()
      if (!reader) throw new Error('浏览器不支持流式响应')
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let boundary = buffer.indexOf('\n\n')
        while (boundary >= 0) {
          const rawEvent = buffer.slice(0, boundary)
          buffer = buffer.slice(boundary + 2)
          const lines = rawEvent.split('\n')
          const eventLine = lines.find((l) => l.startsWith('event:'))
          const dataLine = lines.find((l) => l.startsWith('data:'))
          const eventName = eventLine?.replace('event:', '').trim() || 'message'
          let payload = {}
          try { payload = JSON.parse(dataLine?.replace('data:', '').trim() || '{}') } catch { payload = {} }
          onEvent(eventName, payload)
          boundary = buffer.indexOf('\n\n')
        }
      }
      if (buffer.trim()) {
        const lines = buffer.trim().split('\n')
        const eventLine = lines.find((l) => l.startsWith('event:'))
        const dataLine = lines.find((l) => l.startsWith('data:'))
        const eventName = eventLine?.replace('event:', '').trim() || 'message'
        let payload = {}
        try { payload = JSON.parse(dataLine?.replace('data:', '').trim() || '{}') } catch { payload = {} }
        onEvent(eventName, payload)
      }
    })
  },
  renameResource: (id: number, title: string) => http.patch(`/api/resources/${id}`, { title }),
  deleteResource: (id: number) => http.delete(`/api/resources/${id}`),
  generateQuiz: (data: unknown) => http.post('/api/quiz/generate', data),
  saveQuizDraft: (data: unknown) => http.post('/api/quiz/save-draft', data),
  updateQuizDraft: (resultId: number, data: unknown) =>
    http.patch(`/api/quiz/${resultId}/draft`, data, { timeout: 12000 }),
  submitStructuredQuiz: (data: unknown) =>
    http.post('/api/quiz/submit-structured', data, { timeout: 30000 }),
  evaluateQuiz: (data: unknown) => http.post('/api/quiz/evaluate', data),
  quizHistory: (category?: string) => http.get(`/api/quiz/history${category ? `?category=${category}` : ''}`),
  renameQuizHistory: (id: number, title: string) => http.patch(`/api/quiz/history/${id}`, { title }),
  deleteQuizHistory: (id: number) => http.delete(`/api/quiz/history/${id}`),
  generateCase: (extraInput = '') => http.post('/api/case/generate', { extra_input: extraInput }),
  submitCase: (data: unknown) => http.post('/api/case/submit', data),
  getCaseRecord: (resourceId: number) => http.get(`/api/case/record?resource_id=${resourceId}`),
  generateVideoScript: (extraInput = '') => http.post('/api/multimedia/video-script', { extra_input: extraInput }),
  generateAnimationStoryboard: (extraInput = '') => http.post('/api/multimedia/animation-storyboard', { extra_input: extraInput }),
  multimediaHistory: () => http.get('/api/multimedia/history'),
  submitQuiz: (data: unknown) => http.post('/api/quiz/submit', data),
  evaluate: (data: unknown) => http.post('/api/evaluation', data),
  askTutor: (data: unknown) => http.post('/api/tutor/ask', data),
  listCourses: () => http.get('/api/knowledge/courses'),
  getCourse: (id: number) => http.get(`/api/knowledge/courses/${id}`),
  importBuiltinCourse: () => http.post('/api/knowledge/courses/import-builtin'),
  loadBuiltinKnowledge: () => http.post('/api/knowledge/courses/import-builtin'),
  listDocuments: () => http.get('/api/knowledge/documents'),
  renameDocument: (id: number, title: string) => http.patch(`/api/knowledge/documents/${id}`, { title }),
  deleteDocument: (id: number) => http.delete(`/api/knowledge/documents/${id}`),
  uploadTextDocument: (data: unknown) => http.post('/api/knowledge/upload', data),
  uploadFileDocument: (file: File, title = '', onProgress?: (percent: number) => void, courseId?: number) => {
    const formData = new FormData()
    formData.append('file', file)
    if (title) formData.append('title', title)
    if (courseId) formData.append('course_id', String(courseId))
    return http.post('/api/knowledge/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress
        ? (e) => { if (e.total) onProgress(Math.round((e.loaded / e.total) * 100)) }
        : undefined,
    })
  },
  queryKnowledge: (question: string) => http.post('/api/knowledge/query', { question }),
  reindexDocument: (id: number) => http.post(`/api/knowledge/reindex/${id}`),
  getRecommendedTasks: (refresh = false) => http.get(`/api/tasks/recommended${refresh ? '?refresh=1' : ''}`),
  logTaskAction: (action: string, subType?: string) => http.post('/api/tasks/log-action', { action, sub_type: subType }),
  resetTasks: () => http.post('/api/tasks/reset'),
  searchBiliVideo: (keyword: string, limit = 5, cookie = '') => http.post('/api/resources/search-bili', { keyword, limit, cookie }),
  getChatConversations: () => http.get('/api/chat-conversations'),
  createChatConversation: (data: unknown) => http.post('/api/chat-conversations', data),
  updateChatConversation: (id: number, data: unknown) => http.patch(`/api/chat-conversations/${id}`, data),
  deleteChatConversation: (id: number) => http.delete(`/api/chat-conversations/${id}`),

  getPptThemes: () => http.get('/api/ppt/themes'),
  createPptOutline: (data: unknown) => http.post('/api/ppt/outline', data),
  generatePpt: (data: unknown) => http.post('/api/ppt/generate', data),
  getPptProgress: (sid: string) => http.get(`/api/ppt/progress/${sid}`),
  generatePptContent: (data: unknown) => http.post('/api/ppt/generate-content', data),
  createPptBySid: (data: unknown) => http.post('/api/ppt/create-by-sid', data),
  createPptByOutline: (data: unknown) => http.post('/api/ppt/create-by-outline', data),
  quickCreatePpt: (data: unknown) => http.post('/api/ppt/quick-create', data),
  pptHistory: () => http.get('/api/ppt/history'),
  savePptHistory: (data: unknown) => http.post('/api/ppt/history', data),
  deletePptHistory: (id: number) => http.delete(`/api/ppt/history/${id}`),
  outlineFromDoc: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return http.post('/api/ppt/outline-from-doc', formData)
  },
}
