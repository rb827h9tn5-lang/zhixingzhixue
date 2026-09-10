<template>
  <div class="ppt-workbench">
    <transition name="ppt-agent-slide">
      <section v-if="step === 'generating'" class="ppt-agent-collab-section">
        <div class="ppt-agent-collab-header">
          <el-icon class="is-loading" :size="18"><Loading /></el-icon>
          <span>正在生成 PPT</span>
        </div>
        <div class="ppt-agent-collab-progress">
          <span>{{ progressText || '正在准备生成...' }}</span>
          <el-progress :percentage="progress" :stroke-width="6" :show-text="false" :striped="true" striped-flow />
          <span v-if="showTiming" class="live-timer">已耗时 {{ formatDuration(liveElapsed) }}</span>
        </div>
      </section>
    </transition>

    <transition name="ppt-agent-slide">
      <section v-if="step === 'completed'" class="ppt-result-banner done">
        <div class="ppt-result-main">
          <el-icon :size="18"><CircleCheckFilled /></el-icon>
          <span>PPT 生成完成</span>
          <span v-if="showTiming && generationDuration" style="margin-left:12px;font-size:12px;color:#3b82f6;background:#eff6ff;border:1px solid #bfdbfe;border-radius:12px;padding:1px 10px;white-space:nowrap;">生成耗时 {{ formatDuration(generationDuration) }}</span>
        </div>
        <div class="ppt-result-actions">
          <el-button type="success" size="small" @click="downloadPpt"><el-icon><Download /></el-icon>下载 PPT</el-button>
          <el-button size="small" @click="copyLink">复制链接</el-button>
          <el-button size="small" text @click="resetAll">重新生成</el-button>
        </div>
      </section>
    </transition>

    <transition name="ppt-agent-slide">
      <section v-if="step === 'error'" class="ppt-result-banner error">
        <div class="ppt-result-main">
          <el-icon :size="18"><WarningFilled /></el-icon>
          <span>{{ errorMessage }}</span>
        </div>
        <el-button type="primary" size="small" @click="retry">重试</el-button>
      </section>
    </transition>

    <div class="ppt-workbench-body">

      <!-- ======= 中栏：主操作区 ======= -->
      <main class="ppt-center">
      <!-- 模式标签 -->
      <el-tabs v-model="mode" class="ppt-mode-tabs">
        <!-- ===== 快速生成 ===== -->
        <el-tab-pane label="快速生成" name="quick">
          <div class="quick-gen-panel">
            <div class="selected-template-info" v-if="selectedTemplate">
              <img v-if="selectedTemplate.thumbnail" :src="selectedTemplate.thumbnail" class="sel-template-thumb" @error="selectedTemplate && (selectedTemplate.thumbnail = '')" />
              <div class="sel-template-name">已选模板：<strong>{{ selectedTemplate.label }}</strong></div>
              <el-button size="small" text @click="openTemplateDialog">更换</el-button>
            </div>
            <div v-else class="selected-template-info no-template">
              <el-icon><WarningFilled /></el-icon>
              <span>请选择模板</span>
              <el-button size="small" @click="openTemplateDialog" style="margin-left:auto">选择模板</el-button>
            </div>

            <el-form label-position="top" class="ppt-form">
              <el-form-item label="PPT 主题">
                <el-input
                  v-model="topic"
                  type="textarea"
                  :rows="4"
                  maxlength="2000"
                  show-word-limit
                  placeholder="输入 PPT 主题，如「深度学习讲解」"
                  :disabled="step === 'generating'"
                />
              </el-form-item>
              <el-form-item label="语言">
                  <el-select v-model="language" class="ppt-select" :disabled="step === 'generating'">
                    <el-option v-for="lang in languages" :key="lang.value" :label="lang.label" :value="lang.value" />
                  </el-select>
                </el-form-item>
              <!-- <el-form-item label="PPT 页数">
                <div class="page-slider-wrapper">
                  <el-slider v-model="pageCount" :min="1" :max="30" :step="1" show-stops size="small" class="page-slider" :disabled="step === 'generating'" />
                  <span class="page-count-display">{{ pageCount }}页</span>
                </div>
              </el-form-item> -->
              <el-button
                type="primary"
                size="large"
                class="ppt-primary-btn"
                :loading="step === 'generating' && mode === 'quick'"
                :disabled="!pptEnabled || !topic.trim() || !selectedTemplate || step === 'generating'"
                @click="quickGenerate"
              >
                {{ step === 'generating' && mode === 'quick' ? '正在生成…' : '一键生成 PPT' }}
              </el-button>

              <!-- 高级选项 -->
              <el-collapse class="ppt-advanced-collapse" v-model="advancedCollapseActive">
                <el-collapse-item title="高级选项" name="advanced">
                  <el-form-item label="作者">
                    <el-input v-model="author" placeholder="默认：讯飞智文" size="small" :disabled="step === 'generating'" maxlength="50" show-word-limit />
                  </el-form-item>
                  <div class="ppt-advanced-checks">
                    <el-checkbox v-model="isCardNote" :disabled="step === 'generating'">生成演讲备注</el-checkbox>
                    <el-checkbox v-model="isFigure" :disabled="step === 'generating'">自动配图</el-checkbox>
                    <el-checkbox v-model="search" :disabled="step === 'generating'">联网搜索</el-checkbox>
                  </div>
                  <div v-if="isFigure" style="margin-top:8px">
                    <el-select v-model="aiImage" placeholder="配图类型" size="small" :disabled="step === 'generating'" style="width:100%">
                      <el-option label="普通配图（20% 正文配图）" value="normal" />
                      <el-option label="高级配图（50% 正文配图）" value="advanced" />
                    </el-select>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </el-form>
          </div>
        </el-tab-pane>

        <!-- ===== 大纲定制 ===== -->
        <el-tab-pane label="大纲定制" name="outline">
          <div class="outline-panel">
            <!-- 已选模板 -->
            <div class="selected-template-info" v-if="selectedTemplate">
              <img v-if="selectedTemplate.thumbnail" :src="selectedTemplate.thumbnail" class="sel-template-thumb" @error="selectedTemplate && (selectedTemplate.thumbnail = '')" />
              <div class="sel-template-name">已选模板：<strong>{{ selectedTemplate.label }}</strong></div>
              <el-button size="small" text @click="openTemplateDialog">更换</el-button>
            </div>
            <div v-else class="selected-template-info no-template">
              <el-icon><WarningFilled /></el-icon>
              <span>请选择模板</span>
              <el-button size="small" @click="openTemplateDialog" style="margin-left:auto">选择模板</el-button>
            </div>

            <!-- 已有大纲时：展示大纲编辑 + 下一步操作 -->
            <template v-if="typeof outline === 'string' && outline.trim()">
              <div class="outline-editor">
                <div class="outline-editor-header">
                  <span class="outline-editor-title"><el-icon><Collection /></el-icon> 大纲内容（可编辑）</span>
                  <el-button size="small" text @click="resetOutline">重新生成大纲</el-button>
                </div>
                <el-input
                  v-model="outline"
                  type="textarea"
                  :rows="12"
                  class="outline-textarea"
                  :disabled="step === 'generating'"
                />
              </div>

              <el-button
                type="primary"
                size="large"
                class="ppt-primary-btn outline-submit-btn"
                :loading="step === 'generating' && mode === 'outline'"
                :disabled="step === 'generating'"
                @click="outlineGenerate"
              >
                {{ step === 'generating' && mode === 'outline' ? '正在生成…' : '基于大纲生成 PPT' }}
              </el-button>

              <!-- 高级选项 -->
              <el-collapse class="ppt-advanced-collapse" v-model="advancedCollapseActive">
                <el-collapse-item title="高级选项" name="advanced">
                  <el-form-item label="作者">
                    <el-input v-model="author" placeholder="默认：讯飞智文" size="small" :disabled="step === 'generating'" maxlength="50" show-word-limit />
                  </el-form-item>
                  <!-- <el-form-item label="页数">
                    <div class="page-slider-wrapper">
                      <el-slider v-model="pageCount" :min="1" :max="30" :step="1" show-stops size="small" class="page-slider" :disabled="step === 'generating'" />
                      <span class="page-count-display">{{ pageCount }}页</span>
                    </div>
                  </el-form-item> -->
                  <div class="ppt-advanced-checks">
                    <el-checkbox v-model="isCardNote" :disabled="step === 'generating'">生成演讲备注</el-checkbox>
                    <el-checkbox v-model="isFigure" :disabled="step === 'generating'">自动配图</el-checkbox>
                    <el-checkbox v-model="search" :disabled="step === 'generating'">联网搜索</el-checkbox>
                  </div>
                  <div v-if="isFigure" style="margin-top:8px">
                    <el-select v-model="aiImage" placeholder="配图类型" size="small" :disabled="step === 'generating'" style="width:100%">
                      <el-option label="普通配图（20% 正文配图）" value="normal" />
                      <el-option label="高级配图（50% 正文配图）" value="advanced" />
                    </el-select>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </template>

            <!-- 没有大纲时：展示生成工具 -->
            <template v-else>
              <el-tabs v-model="outlineMode" class="outline-sub-tabs">
                <el-tab-pane label="自动生成大纲" name="auto">
                  <div class="outline-auto-form">
                    <el-input
                      v-model="autoTopic"
                      placeholder="输入 PPT 主题或要求"
                      :disabled="step === 'generating'"
                      clearable
                    />
                    <el-button
                      type="primary"
                      :loading="outlineLoading === 'auto'"
                      :disabled="!autoTopic.trim() || step === 'generating'"
                      @click="generateOutline"
                    >生成大纲</el-button>
                  </div>
                </el-tab-pane>
                <el-tab-pane label="上传文档生成大纲" name="doc">
                  <div
                    class="upload-zone"
                    :class="{ 'upload-dragover': dragOver }"
                    @dragover.prevent="dragOver = true"
                    @dragleave.prevent="dragOver = false"
                    @drop.prevent="onDocDrop"
                  >
                    <el-icon :size="36" class="upload-icon"><UploadFilled /></el-icon>
                    <p v-if="!uploadLoading">拖拽 .docx / .pdf 文件到此处，或点击选择</p>
                    <p v-else><el-icon class="is-loading"><Loading /></el-icon> 正在解析文档...</p>
                    <el-button size="small" @click="triggerUpload" :disabled="uploadLoading">选择文件</el-button>
                    <input ref="fileInputRef" type="file" accept=".docx,.pdf" style="display:none" @change="onFileChange" />
                  </div>
                </el-tab-pane>
              </el-tabs>

              <!-- 当前没有大纲时的引导提示 -->
              <div class="outline-empty-hint">
                <el-icon :size="32" color="#a0aec0"><Collection /></el-icon>
                <p>请先生成大纲，然后编辑并生成 PPT</p>
              </div>
            </template>
          </div>
        </el-tab-pane>
      </el-tabs>
      </main>

      <!-- ======= 右栏：PPT 历史记录（悬浮展开） ======= -->
      <aside class="ppt-right">
        <div class="ppt-history">
        <div class="ppt-history-header">
          <h3>PPT 历史记录</h3>
          <el-button :icon="Refresh" text circle size="small" @click="loadPptHistory" />
        </div>
        <div v-if="pptHistory.length === 0" class="ppt-history-empty">暂无历史记录</div>
        <div v-else class="ppt-history-list">
          <div
            v-for="item in pptHistory"
            :key="item.id"
            class="ppt-history-item"
            :class="{ disabled: !item.local_url && !item.remote_url }"
            @click="openPptRecord(item)"
          >
            <div class="ppt-history-main">
              <strong>{{ item.title }}</strong>
              <span>{{ formatPptTime(item.created_at) }}</span>
            </div>
            <div class="ppt-history-actions">
              <el-button :icon="Download" text circle size="small" @click.stop="openPptRecord(item)" />
              <el-button :icon="Delete" text circle size="small" type="danger" @click.stop="deletePptRecord(item)" />
            </div>
          </div>
        </div>
      </div>
      </aside>
    </div>

  </div>

  <!-- 模板选择弹窗 -->
  <el-dialog v-model="templateDialogVisible" title="选择模板" width="520px" align-center>
    <el-input v-model="templateSearch" placeholder="搜索模板..." size="small" clearable prefix-icon="Search" style="margin-bottom:14px" />
    <div v-if="templates.length === 0" style="text-align:center;padding:40px 0;color:#94a3b8">
      <el-icon class="is-loading" :size="24"><Loading /></el-icon>
      <p style="margin-top:8px">加载模板中...</p>
    </div>
    <div v-else class="template-grid" style="max-height:400px;overflow-y:auto">
      <div
        v-for="t in filteredTemplates"
        :key="t.value"
        class="template-card"
        :class="{ selected: selectedTemplateId === t.value }"
        @click="selectTemplateInDialog(t)"
      >
        <div class="template-thumb-wrap">
          <img v-if="t.thumbnail" :src="t.thumbnail" :alt="t.label" class="template-thumb" @error="t.thumbnail = ''" />
          <div v-else class="template-thumb-placeholder">
            <el-icon :size="28"><Collection /></el-icon>
          </div>
          <div class="template-preview-overlay" @click.stop="previewTemplate(t)">
            <el-icon :size="18"><ZoomIn /></el-icon>
          </div>
        </div>
        <div class="template-info">
          <span class="template-name">{{ t.label }}</span>
          <span class="template-tag">{{ t.value === 'auto' ? '智能' : '风格' }}</span>
        </div>
      </div>
    </div>
  </el-dialog>

  <!-- 模板预览弹窗 -->
  <el-dialog v-model="previewDialogVisible" :title="previewImgLabel" width="480px" align-center>
    <img v-if="previewImgUrl" :src="previewImgUrl" :alt="previewImgLabel" style="width:100%;border-radius:8px;display:block" @error="previewDialogVisible = false" />
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  CircleCheckFilled, Collection, DArrowRight, Delete, Download, Loading, Refresh, UploadFilled, WarningFilled, ZoomIn,
} from '@element-plus/icons-vue'
import { api } from '../api/learning'

// ===== 状态定义 =====
const templates = ref<Array<{ value: string; label: string; thumbnail?: string }>>([])
const pptEnabled = ref(false)
const templateSearch = ref('')
const selectedTemplateId = ref('auto')

const mode = ref('quick')
const outlineMode = ref('auto')

const topic = ref('')
const language = ref('cn')
const author = ref('')
const pageCount = ref(20)

const autoTopic = ref('')
const advancedCollapseActive = ref(['advanced'])
const outline = ref('')
const rawOutline = ref<Record<string, unknown> | null>(null)
const outlineLoading = ref<'auto' | 'doc' | ''>('')
const outlineSid = ref('')

const isCardNote = ref(false)
const isFigure = ref(false)
const aiImage = ref('')
const search = ref(false)

const step = ref<'idle' | 'generating' | 'completed' | 'error'>('idle')
const sid = ref('')
const progress = ref(0)
const progressText = ref('')
const errorMessage = ref('')
const pptUrl = ref('')
const startTime = ref(0)
const generationDuration = ref<number | null>(null)
const liveElapsed = ref(0)
let liveTimerInterval: ReturnType<typeof setInterval> | null = null
const templateDialogVisible = ref(false)
const previewDialogVisible = ref(false)
const previewImgUrl = ref('')
const previewImgLabel = ref('')

const dragOver = ref(false)
const uploadLoading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

interface PptHistoryRecord {
  id: number
  sid: string
  title: string
  local_url?: string
  remote_url?: string
  status: string
  created_at: string
}

const pptHistory = ref<PptHistoryRecord[]>([])

const languages = [
  { value: 'cn', label: '中文简体' },
  { value: 'en', label: '英语' },
  { value: 'ja', label: '日语' },
  { value: 'ru', label: '俄语' },
  { value: 'ko', label: '韩语' },
  { value: 'de', label: '德语' },
  { value: 'fr', label: '法语' },
  { value: 'pt', label: '葡萄牙语' },
  { value: 'es', label: '西班牙语' },
  { value: 'it', label: '意大利语' },
  { value: 'th', label: '泰语' },
]

let pollTimer: ReturnType<typeof setInterval> | null = null

// ===== 计算属性 =====
const filteredTemplates = computed(() => {
  if (!templateSearch.value.trim()) return templates.value
  const q = templateSearch.value.toLowerCase()
  return templates.value.filter(t => t.label.toLowerCase().includes(q))
})

const selectedTemplate = computed(() => {
  return templates.value.find(t => t.value === selectedTemplateId.value) || null
})

const showTiming = computed(() => import.meta.env.VITE_ENABLE_RESOURCE_TIMING === 'true')

// ===== 初始化 =====
async function loadTemplates() {
  try {
    const res = await api.getPptThemes()
    const themes = res.data.themes || []
    if (themes.length > 0) {
      templates.value = themes
    }
    pptEnabled.value = true
  } catch {
    pptEnabled.value = false
  }
}
loadTemplates()

function upsertPptRecord(record?: PptHistoryRecord | null) {
  if (!record?.id) return
  const index = pptHistory.value.findIndex(item => item.id === record.id)
  if (index >= 0) {
    pptHistory.value.splice(index, 1, record)
  } else {
    pptHistory.value.unshift(record)
  }
}

async function loadPptHistory() {
  try {
    const res = await api.pptHistory()
    pptHistory.value = res.data.records || []
  } catch {
    pptHistory.value = []
  }
}
loadPptHistory()

function formatPptTime(value: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (num: number) => String(num).padStart(2, '0')
  return `${date.getFullYear()}/${pad(date.getMonth() + 1)}/${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function formatDuration(seconds: number) {
  if (seconds == null) return ''
  if (seconds < 60) return `${Math.floor(seconds)}秒`
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}分${secs}秒`
}

function startLiveTimer() {
  stopLiveTimer()
  liveElapsed.value = 0
  const _start = Date.now()
  liveTimerInterval = setInterval(() => {
    liveElapsed.value = Math.floor((Date.now() - _start) / 1000)
  }, 1000)
}

function stopLiveTimer() {
  if (liveTimerInterval) {
    clearInterval(liveTimerInterval)
    liveTimerInterval = null
  }
}

function openPptRecord(record: PptHistoryRecord) {
  const url = record.local_url || record.remote_url || ''
  if (!url) {
    ElMessage.warning(record.status === 'generating' ? 'PPT 仍在生成中，请稍后刷新' : '该记录暂无可下载文件')
    return
  }
  window.open(url, '_blank')
}

async function deletePptRecord(record: PptHistoryRecord) {
  try {
    await api.deletePptHistory(record.id)
    pptHistory.value = pptHistory.value.filter(item => item.id !== record.id)
    ElMessage.success('PPT 历史记录已删除')
  } catch (err: any) {
    ElMessage.error((err as Error).message || '删除失败')
  }
}

async function saveCompletedPpt() {
  if (!pptUrl.value && !sid.value) return
  const title = mode.value === 'quick'
    ? topic.value.trim() || 'PPT 生成'
    : autoTopic.value.trim() || sanitizeOutline(outline.value).split('\n')[0] || 'PPT 生成'
  try {
    const res = await api.savePptHistory({
      sid: sid.value,
      ppt_url: pptUrl.value,
      title,
      template_id: selectedTemplateId.value,
    })
    upsertPptRecord(res.data.record)
  } catch {
    await loadPptHistory()
  }
}

// ===== 模板预览 =====
function openTemplateDialog() {
  templateDialogVisible.value = true
}

function selectTemplateInDialog(t: { value: string; label: string; thumbnail?: string }) {
  selectedTemplateId.value = t.value
  templateDialogVisible.value = false
}

function previewTemplate(t: { value: string; label: string; thumbnail?: string }) {
  if (!t.thumbnail) return
  previewImgUrl.value = t.thumbnail
  previewImgLabel.value = t.label
  previewDialogVisible.value = true
}

// ===== 快速生成 =====
async function quickGenerate() {
  if (!topic.value.trim() || !selectedTemplate.value) {
    ElMessage.warning('请先输入主题并选择模板')
    return
  }
  step.value = 'generating'
  mode.value = 'quick'
  progress.value = 0
  progressText.value = '正在准备数据…'
  startTime.value = Date.now()
  startLiveTimer()
  
  try {
    const res = await api.quickCreatePpt({
      template_id: selectedTemplateId.value || 'auto',
      topic: topic.value,
      language: language.value,
      author: author.value || undefined,
      is_card_note: isCardNote.value,
      is_figure: isFigure.value,
      search: search.value,
      ai_image: aiImage.value || undefined,
      page_count: pageCount.value,
    })

    sid.value = res.data.sid || ''


    if (!sid.value) throw new Error('PPT 服务未返回生成任务，请重试')
    progressText.value = '数据准备完成，正在制作幻灯片…'
    progress.value = 15
    startPolling()
  } catch (err: any) {
    step.value = 'error'
    errorMessage.value = (err as Error).message || '快速生成失败'
    ElMessage.error(errorMessage.value)
  }
}

// ===== 大纲格式化 =====
/** 将 XFYUN 结构化大纲转换为可编辑的纯文本格式 */
function formatOutline(data: unknown): string {
  if (typeof data === 'string') return data
  if (!data || typeof data !== 'object') return ''
  const obj = data as Record<string, unknown>
  const lines: string[] = []
  const chapters = obj.chapters
  if (Array.isArray(chapters)) {
    for (const ch of chapters) {
      if (typeof ch === 'object' && ch !== null) {
        const chapter = ch as Record<string, unknown>
        if (typeof chapter.chapterTitle === 'string' && chapter.chapterTitle) {
          lines.push('', chapter.chapterTitle)
        }
        const contents = chapter.chapterContents
        if (Array.isArray(contents)) {
          for (const item of contents) {
            if (typeof item === 'object' && item !== null) {
              const title = (item as Record<string, unknown>).chapterTitle
              if (typeof title === 'string' && title) lines.push('  ' + title)
            }
          }
        }
      }
    }
  }
  return lines.join('\n').trim()
}

/** 提交给 API 时精简大纲：去掉所有缩进和空白行 */
function sanitizeOutline(text: string): string {
  return text
    .split('\n')
    .map(line => line.replace(/\s+$/, ''))
    .filter(line => line.trim() !== '')
    .join('\n')
}

// ===== 大纲生成 =====
async function generateOutline() {
  if (outlineLoading.value) return
  if (!autoTopic.value.trim()) return
  outlineLoading.value = 'auto'
  try {
    const res = await api.createPptOutline({ query: autoTopic.value, theme: selectedTemplateId.value || 'auto' })
    outlineSid.value = res.data.sid || ''
    rawOutline.value = res.data.outline || null
    outline.value = formatOutline(res.data.outline)
    if (!outline.value) {
      ElMessage.warning('大纲生成结果为空，请重试')
    }
  } catch (err: any) {
    console.error('[PPT] 大纲生成失败:', err)
    const msg = (err as Error).message || '大纲生成失败'
    ElMessage.error(msg)
    step.value = 'error'
    errorMessage.value = msg
  } finally {
    outlineLoading.value = ''
  }
}

// ===== 文档上传 =====
function triggerUpload() {
  fileInputRef.value?.click()
}

function onDocDrop(e: DragEvent) {
  dragOver.value = false
  const files = e.dataTransfer?.files
  if (files?.length) uploadFile(files[0])
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.length) uploadFile(input.files[0])
  input.value = ''
}

async function uploadFile(file: File) {
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!['pdf', 'doc', 'docx', 'txt', 'md'].includes(ext || '')) {
    ElMessage.warning('仅支持 pdf、doc、docx、txt、md 文件')
    return
  }
  uploadLoading.value = true
  try {
    const res = await api.outlineFromDoc(file)
    outlineSid.value = res.data.sid || ''
    rawOutline.value = res.data.outline || null
    outline.value = formatOutline(res.data.outline)
  } catch (err: any) {
    console.error('[PPT] 文档解析失败:', err)
    ElMessage.error((err as Error).message || '文档解析失败')
  } finally {
    uploadLoading.value = false
  }
}

// ===== 基于大纲生成 =====
async function outlineGenerate() {
  if (typeof outline.value !== 'string' || !outline.value.trim()) {
    ElMessage.warning('请先生成或编辑大纲')
    return
  }
  if (!autoTopic.value.trim() && mode.value === 'outline') {
    // 如果用户没有输入主题，用大纲的前几个字作为 query
    autoTopic.value = outline.value.split('\n')[0]?.replace(/^\d+\.\s*/, '') || 'PPT 生成'
  }
  step.value = 'generating'
  mode.value = 'outline'
  progress.value = 0
  progressText.value = '正在准备数据…'
  startTime.value = Date.now()
  startLiveTimer()

  try {
    const sanitized = sanitizeOutline(outline.value)

    // 没有 SID（来自文档上传）时，先调用 createOutline 获取 SID
    if (!outlineSid.value) {
      try {
        const queryText = autoTopic.value.trim() || sanitized.split('\n')[0] || 'PPT 生成'
        const outlineRes = await api.createPptOutline({ query: queryText, theme: selectedTemplateId.value || 'auto' })
        outlineSid.value = outlineRes.data.sid || ''
      } catch {
        throw new Error('获取大纲 SID 失败，请先生成大纲')
      }
    }

    // 后端会用本地解析或原始 JSON 大纲适配 XFYUN createPptByOutline，不再调用通用 LLM 转换。
    const res = await api.createPptBySid({
      sid: outlineSid.value,
      outline: sanitized,
      raw_outline: rawOutline.value || undefined,
      query: autoTopic.value.trim() || sanitized.split('\n')[0] || 'PPT 生成',
      author: author.value || undefined,
      theme: selectedTemplateId.value || 'auto',
      language: language.value,
      is_card_note: isCardNote.value,
      is_figure: isFigure.value,
      search: search.value,
      ai_image: aiImage.value || undefined,
      format: 'llm',
      page_count: pageCount.value,
    })
    sid.value = res.data.sid || ''
    if (!sid.value) throw new Error('PPT 服务未返回生成任务，请重试')
    progressText.value = '数据准备完成，正在制作幻灯片…'
    progress.value = 15
    startPolling()
  } catch (err: any) {
    step.value = 'error'
    errorMessage.value = (err as Error).message || 'PPT 生成失败'
    ElMessage.error(errorMessage.value)
  }
}

// ===== 轮询 =====
function startPolling() {
  stopPolling()
  const POLL_TIMEOUT = 600000
  const POLL_INTERVAL = 3000

  pollTimer = setInterval(async () => {
    if (Date.now() - startTime.value > POLL_TIMEOUT) {
      stopPolling()
      step.value = 'error'
      errorMessage.value = '生成超时，请重试'
      return
    }

    try {
      const res = await api.getPptProgress(sid.value)
      const p = Number(res.data.process || 0)
      const visualProgress = res.data.pptUrl ? 100 : Math.min(99, Math.max(p, progress.value, 12))
      progress.value = visualProgress
      upsertPptRecord(res.data.record)

      if (res.data.pptUrl || p >= 100) {
        progressText.value = '导出完成'
        progress.value = 100
        pptUrl.value = res.data.pptUrl || ''
        generationDuration.value = (Date.now() - startTime.value) / 1000
        stopLiveTimer()
        liveElapsed.value = Math.floor((Date.now() - startTime.value) / 1000)
        stopPolling()
        await saveCompletedPpt()
        await loadPptHistory()
        await nextTick()
        step.value = 'completed'
        ElMessage.success('PPT 生成完成！')
      } else if (visualProgress < 30) {
        progressText.value = '正在准备数据…'
      } else if (visualProgress < 70) {
        progressText.value = '大纲准备完成，正在制作幻灯片…'
      } else {
        progressText.value = 'PPT 制作完成，正在导出文件…'
      }
    } catch (err: any) {
      stopPolling()
      step.value = 'error'
      errorMessage.value = (err as Error).message || '查询进度失败'
      ElMessage.error(errorMessage.value)
    }
  }, POLL_INTERVAL)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// ===== 操作 =====
function downloadPpt() {
  if (pptUrl.value) window.open(pptUrl.value, '_blank')
}

function copyLink() {
  if (!pptUrl.value) return
  navigator.clipboard.writeText(pptUrl.value).then(() => {
    ElMessage.success('下载链接已复制')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

function retry() {
  step.value = 'idle'
  progress.value = 0
  errorMessage.value = ''
}

function resetOutline() {
  outline.value = ''
  rawOutline.value = null
  outlineSid.value = ''
  autoTopic.value = ''
  outlineMode.value = 'auto'
}

function resetAll() {
  stopPolling()
  stopLiveTimer()
  step.value = 'idle'
  progress.value = 0
  progressText.value = ''
  pptUrl.value = ''
  sid.value = ''
  errorMessage.value = ''
  generationDuration.value = null
  topic.value = ''
  outline.value = ''
  rawOutline.value = null
  outlineSid.value = ''
  autoTopic.value = ''
  selectedTemplateId.value = 'auto'
  isCardNote.value = false
  isFigure.value = false
  search.value = false
  aiImage.value = ''
  author.value = ''
}

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.live-timer {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  font-weight: 500;
  color: #3b82f6;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 12px;
  padding: 1px 10px;
  margin-left: 8px;
  white-space: nowrap;
  animation: timer-pulse 2s ease-in-out infinite;
}

@keyframes timer-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}
.ppt-workbench {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 16px;
  min-height: 0;
  animation: wbFadeIn 0.35s ease-out;
}
.ppt-workbench-body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 16px;
  overflow: hidden;
}
@keyframes wbFadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ===== PPT Agent Collaboration ===== */
.ppt-agent-collab-section,
.ppt-result-banner {
  flex-shrink: 0;
  border-radius: 14px;
  border: 1px solid rgba(199, 210, 254, 0.65);
  background: rgba(248, 250, 255, 0.94);
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
}

.ppt-agent-collab-section {
  padding: 12px 16px;
  position: relative;
  overflow: hidden;
}

.ppt-agent-collab-section::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, rgba(99, 102, 241, 0.05), rgba(14, 165, 233, 0.06), rgba(236, 72, 153, 0.04));
  pointer-events: none;
}

.ppt-agent-collab-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 700;
  color: var(--primary-600, #4f46e5);
  position: relative;
  z-index: 1;
}

.ppt-agent-collab-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary-400, #818cf8);
  animation: pptAgentPulse 1.5s ease-in-out infinite;
}

@keyframes pptAgentPulse {
  0%, 100% { opacity: 0.45; transform: scale(0.9); }
  50% { opacity: 1; transform: scale(1.18); }
}

.ppt-agent-steps {
  display: flex;
  align-items: center;
  gap: 10px;
  position: relative;
  z-index: 1;
}

.ppt-agent-step {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  position: relative;
}

.ppt-agent-step-indicator {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.74);
  border: 2px solid rgba(226, 232, 240, 0.9);
  flex-shrink: 0;
}

.ppt-agent-step.running .ppt-agent-step-indicator {
  border-color: var(--primary-300, #a5b4fc);
  background: #eff6ff;
}

.ppt-agent-step.done .ppt-agent-step-indicator {
  border-color: #34d399;
  background: #d1fae5;
}

.ppt-step-done-icon {
  color: #10b981;
}

.ppt-step-running-icon {
  color: var(--primary-500, #6366f1);
}

.ppt-step-pending-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--surface-300, #cbd5e1);
}

.ppt-agent-step-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ppt-agent-step-body strong {
  font-size: 13px;
  color: var(--surface-700, #334155);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ppt-agent-step-body span {
  font-size: 12px;
  color: var(--surface-400, #94a3b8);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ppt-agent-step-tail {
  position: absolute;
  right: -8px;
  top: 14px;
  width: 16px;
  height: 2px;
}

.ppt-tail-line {
  width: 100%;
  height: 100%;
  background: rgba(203, 213, 225, 0.8);
}

.ppt-tail-line.active {
  background: linear-gradient(90deg, var(--primary-300, #a5b4fc), var(--primary-400, #818cf8));
}

.ppt-agent-collab-progress {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(140px, auto) minmax(180px, 1fr) auto;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid rgba(99, 102, 241, 0.1);
  font-size: 13px;
  color: var(--primary-600, #4f46e5);
}

.ppt-progress-meta {
  color: var(--surface-400, #94a3b8);
  white-space: nowrap;
}

.ppt-result-banner {
  min-height: 46px;
  padding: 9px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.ppt-result-banner.done {
  border-color: rgba(52, 211, 153, 0.45);
  background: linear-gradient(135deg, #ecfdf5, #f8fffb);
}

.ppt-result-banner.error {
  border-color: rgba(248, 113, 113, 0.45);
  background: linear-gradient(135deg, #fef2f2, #fff7f7);
}

.ppt-result-main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-size: 14px;
  font-weight: 700;
}

.ppt-result-main span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ppt-result-banner.done .ppt-result-main {
  color: #047857;
}

.ppt-result-banner.error .ppt-result-main {
  color: #dc2626;
}

.ppt-result-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.ppt-agent-slide-enter-active {
  animation: pptAgentSlideIn 0.3s ease-out;
}

.ppt-agent-slide-leave-active {
  animation: pptAgentSlideIn 0.22s ease-in reverse;
}

@keyframes pptAgentSlideIn {
  from { opacity: 0; transform: translateY(-8px); max-height: 0; }
  to { opacity: 1; transform: translateY(0); max-height: 180px; }
}

.template-grid {
  flex: 1;
  overflow-y: auto;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  padding-right: 2px;
}
.template-grid::-webkit-scrollbar { width: 4px; }
.template-grid::-webkit-scrollbar-track { background: transparent; }
.template-grid::-webkit-scrollbar-thumb { background: var(--surface-200, #e2e8f0); border-radius: 4px; }

.template-card {
  border: 2px solid var(--surface-100, #f1f5f9);
  border-radius: var(--radius-md, 10px);
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s ease;
  background: #ffffff;
}
.template-card:hover {
  border-color: var(--primary-200, #c7d2fe);
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.1);
  transform: translateY(-1px);
}
.template-card.selected {
  border-color: var(--primary-500, #6366f1);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.15);
}

.template-thumb-wrap {
  position: relative;
}

.template-preview-overlay {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  border-radius: 6px;
  opacity: 0;
  transition: opacity 0.2s ease;
  cursor: pointer;
}
.template-card:hover .template-preview-overlay {
  opacity: 1;
}

.template-thumb {
  width: 100%;
  height: 128px;
  object-fit: cover;
  display: block;
  background: var(--surface-50, #f8fafc);
}

.template-thumb-placeholder {
  height: 128px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--surface-50, #f8fafc);
  color: var(--surface-300, #cbd5e1);
}

.template-info {
  padding: 8px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.template-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--surface-700, #334155);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.template-tag {
  font-size: 10px;
  padding: 1px 8px;
  border-radius: 10px;
  background: var(--surface-50, #f8fafc);
  color: var(--surface-400, #94a3b8);
  flex-shrink: 0;
  font-weight: 500;
}

/* ===== 中栏 ===== */
.ppt-center {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border: 1px solid var(--surface-100, #f1f5f9);
  border-radius: var(--radius-xl, 16px);
  padding: 20px 22px;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.05));
  overflow-y: auto;
}

.ppt-center::-webkit-scrollbar { width: 4px; }
.ppt-center::-webkit-scrollbar-thumb { background: var(--surface-200, #e2e8f0); border-radius: 4px; }

.ppt-mode-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.ppt-mode-tabs :deep(.el-tabs__content) {
  flex: 1;
}
.ppt-mode-tabs :deep(.el-tab-pane) {
  height: 100%;
}

.quick-gen-panel,
.outline-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.selected-template-info {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--surface-50, #f8fafc);
  border-radius: var(--radius-md, 8px);
  border: 1px solid var(--surface-100, #f1f5f9);
  font-size: 14px;
  color: var(--surface-500, #64748b);
}
.selected-template-info.no-template {
  color: var(--surface-400, #94a3b8);
}

.sel-template-thumb {
  width: 36px;
  height: 24px;
  border-radius: 4px;
  object-fit: cover;
  border: 1px solid var(--surface-200, #e2e8f0);
}

.sel-template-name strong {
  color: var(--surface-700, #334155);
}

.ppt-form .el-form-item {
  margin-bottom: 18px;
}

.ppt-form-row {
  display: flex;
  gap: 16px;
}
.ppt-form-row .el-form-item {
  flex: 1;
  min-width: 0;
}
.ppt-form-row .el-form-item:last-child {
  min-width: 240px;
}

.ppt-select {
  width: 100%;
}

.page-slider-wrapper {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
}
.page-slider {
  flex: 1;
  padding: 0 4px;
}
.page-slider :deep(.el-slider__runway) {
  margin: 12px 0;
}
.page-count-display {
  flex-shrink: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--primary-600, #4f46e5);
  min-width: 40px;
  text-align: center;
}

.ppt-modules {
  display: flex;
  gap: 20px;
  margin-bottom: 18px;
  padding: 10px 0;
}

.ppt-primary-btn {
  width: 100%;
  height: 44px;
  font-size: 15px;
  font-weight: 600;
  background: linear-gradient(135deg, var(--primary-500, #6366f1), var(--primary-600, #4f46e5));
  border: none;
  border-radius: var(--radius-md, 10px);
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.3);
  transition: all 0.2s ease;
}
.ppt-primary-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4);
}

.outline-sub-tabs :deep(.el-tabs__content) {
  padding-top: 8px;
}

.outline-auto-form {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}

.upload-zone {
  border: 2px dashed var(--surface-200, #e2e8f0);
  border-radius: var(--radius-lg, 12px);
  padding: 28px 16px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-bottom: 12px;
  background: var(--surface-50, #f8fafc);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.upload-zone:hover,
.upload-zone.upload-dragover {
  border-color: var(--primary-400, #818cf8);
  background: #eff6ff;
}
.upload-icon {
  color: var(--surface-300, #cbd5e1);
}
.upload-zone:hover .upload-icon {
  color: var(--primary-400, #818cf8);
}
.upload-zone p {
  font-size: 14px;
  color: var(--surface-400, #94a3b8);
  margin: 0;
}

.outline-editor {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.outline-editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.outline-editor-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-600, #475569);
}

.outline-textarea {
  flex: 1;
}
.outline-textarea :deep(.el-textarea__inner) {
  font-family: 'Cascadia Code', 'JetBrains Mono', monospace;
  font-size: 14px;
  line-height: 1.7;
  border-radius: var(--radius-md, 8px);
}

.outline-submit-btn {
  margin-top: 4px;
}

/* 空白引导 */
.outline-empty-hint {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 140px;
  color: var(--surface-300, #cbd5e1);
}
.outline-empty-hint p {
  margin: 0;
  font-size: 14px;
}

/* ===== 高级选项 ===== */
.ppt-advanced-collapse {
  margin-top: 12px;
  border: 1px solid var(--surface-100, #f1f5f9);
  border-radius: var(--radius-md, 8px);
  overflow: hidden;
}
.ppt-advanced-collapse :deep(.el-collapse-item__header) {
  font-size: 14px;
  font-weight: 500;
  color: var(--surface-500, #64748b);
  padding: 0 12px;
  height: 36px;
  border-bottom: none;
  background: var(--surface-50, #f8fafc);
}
.ppt-advanced-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}
.ppt-advanced-collapse :deep(.el-collapse-item__content) {
  padding: 12px 14px 16px;
}
.ppt-advanced-checks {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-top: 8px;
}

/* ===== 右栏 ===== */
.ppt-right {
  width: 44px;
  min-width: 44px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: linear-gradient(180deg, #eff6ff 0%, #f3e8ff 100%);
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 18px;
  padding: 18px 10px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
  transition: width 0.26s ease, min-width 0.26s ease, padding 0.26s ease, box-shadow 0.26s ease;
}

.ppt-right:hover {
  width: 240px;
  min-width: 240px;
  padding: 18px 14px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: -8px 0 28px rgba(99, 102, 241, 0.12), 0 10px 30px rgba(15, 23, 42, 0.06);
}

.ppt-history {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.ppt-history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  flex-shrink: 0;
}

.ppt-history-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-700, #334155);
}

.ppt-right:not(:hover) .ppt-history-header {
  justify-content: center;
  height: 100%;
  margin-bottom: 0;
}

.ppt-right:not(:hover) .ppt-history-header h3 {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  letter-spacing: 4px;
  font-size: 14px;
  font-weight: 700;
  color: #3b82f6;
  white-space: nowrap;
}

.ppt-right:not(:hover) .ppt-history-header :deep(.el-button) {
  display: none;
}

.ppt-right:not(:hover) .ppt-history-empty,
.ppt-right:not(:hover) .ppt-history-list {
  opacity: 0;
  pointer-events: none;
}

.ppt-history-empty,
.ppt-history-list,
.ppt-history-header h3 {
  transition: opacity 0.16s ease;
}

.ppt-history-empty {
  padding: 18px 8px;
  text-align: center;
  color: var(--surface-400, #94a3b8);
  font-size: 13px;
}

.ppt-history-list {
  overflow-y: auto;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-right: 2px;
}

.ppt-history-list::-webkit-scrollbar { width: 4px; }
.ppt-history-list::-webkit-scrollbar-thumb { background: var(--surface-200, #e2e8f0); border-radius: 4px; }

.ppt-history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 9px 8px;
  border-radius: var(--radius-md, 8px);
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(226, 232, 240, 0.9);
  cursor: pointer;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.ppt-history-item:hover {
  border-color: var(--primary-200, #c7d2fe);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.10);
  transform: translateY(-1px);
}

.ppt-history-item.disabled {
  opacity: 0.72;
}

.ppt-history-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ppt-history-main strong {
  font-size: 13px;
  color: var(--surface-700, #334155);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ppt-history-main span {
  font-size: 12px;
  color: var(--surface-400, #94a3b8);
}

.ppt-history-actions {
  display: flex;
  flex-shrink: 0;
  gap: 2px;
}

.ppt-innovation-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-bottom: 16px;
}

.ppt-innovation-loading {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: var(--radius-lg, 12px);
  border: 1px dashed rgba(99, 102, 241, 0.38);
  background: linear-gradient(135deg, rgba(248, 250, 252, 0.96), rgba(238, 242, 255, 0.92));
  color: var(--surface-600, #475569);
}

.ppt-innovation-loading > .el-icon {
  color: var(--primary-500, #6366f1);
  font-size: 22px;
  flex-shrink: 0;
}

.ppt-innovation-loading strong {
  display: block;
  color: var(--surface-800, #1e293b);
  font-size: 14px;
  margin-bottom: 3px;
}

.ppt-innovation-loading p {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
}

/* ===== 响应式 ===== */
@media (max-width: 1200px) {
  .ppt-workbench {
    overflow-y: auto;
  }
  .ppt-workbench-body {
    flex-direction: column;
    overflow: visible;
  }
  .ppt-agent-steps {
    flex-direction: column;
    align-items: stretch;
  }
  .ppt-agent-step {
    width: 100%;
  }
  .ppt-agent-step-tail {
    display: none;
  }
  .ppt-agent-collab-progress {
    grid-template-columns: 1fr;
    gap: 8px;
  }
  .ppt-result-banner {
    align-items: flex-start;
    flex-direction: column;
  }
  .ppt-result-actions {
    flex-wrap: wrap;
  }
  .ppt-right {
    width: 100%;
    min-width: 0;
    padding: 18px 14px;
  }
  .ppt-right:hover {
    width: 100%;
    min-width: 0;
    padding: 18px 14px;
  }
  .ppt-right:not(:hover) .ppt-history-header {
    justify-content: space-between;
    height: auto;
    margin-bottom: 10px;
  }
  .ppt-right:not(:hover) .ppt-history-header h3 {
    writing-mode: horizontal-tb;
    letter-spacing: 0;
    color: var(--surface-700, #334155);
  }
  .ppt-right:not(:hover) .ppt-history-header :deep(.el-button) {
    display: inline-flex;
  }
  .ppt-right:not(:hover) .ppt-history-empty,
  .ppt-right:not(:hover) .ppt-history-list {
    opacity: 1;
    pointer-events: auto;
  }
  .template-grid {
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  }
}
</style>
