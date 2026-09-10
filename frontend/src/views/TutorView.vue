<template>
  <section class="module tutor-module">
    <div class="chat-shell">
      <aside class="chat-sidebar">
        <el-button :icon="Plus" class="new-chat-button" @click="startNewTutorConversation">开启新对话</el-button>
        <div class="chat-list">
          <div
            v-for="conversation in tutorConversations"
            :key="conversation.id"
            class="chat-list-row"
            :class="{ active: conversation.id === activeTutorConversationId }"
          >
            <button class="chat-list-item" @click="selectTutorConversation(conversation.id)">
              <span class="chat-item-title" :title="conversation.title">{{ conversation.title }}</span>
              <span class="chat-item-time" :title="formatDateTime(conversation.created_at || '')">{{ formatDateTime(conversation.created_at || '') }}</span>
            </button>
            <el-button :icon="EditPen" size="small" text circle title="重命名对话" @click.stop="renameTutorConversation(conversation)" />
            <el-button :icon="Delete" size="small" text circle type="danger" title="删除对话" @click.stop="deleteTutorConversation(conversation)" />
          </div>
        </div>
      </aside>

      <div class="chat-main">
        <header class="chat-header">
          <div>
            <h2>{{ activeTutorConversation?.title || 'RAG 增强智能辅导' }}</h2>
            <!-- <span>结合课程知识库进行可信、可追溯的即时答疑 · 支持图片分析与文件解析</span>
            <div class="tutor-identity-line">身份：循证学习教练 · 先定位困惑，再用课程证据讲清楚，并给出可执行练习</div> -->
          </div>
          <div class="chat-header-actions">
            <div class="chat-header-badges">
              <el-tag size="small" effect="plain" round style="background:#eff6ff;color:#3b82f6;border-color:#bfdbfe;font-weight:600;">RAG增强</el-tag>
              <el-tag size="small" effect="plain" round style="background:#fdf4ff;color:#9333ea;border-color:#fae8ff;font-weight:600;">图片理解</el-tag>
              <el-tag size="small" effect="plain" round style="background:#ecfeff;color:#0891b2;border-color:#cffafe;font-weight:600;">文件解析</el-tag>
              <el-tag size="small" effect="plain" round style="background:#fff7ed;color:#ea580c;border-color:#ffedd5;font-weight:600;">内容安全检查</el-tag>
              <el-tag v-if="currentTeachingStrategy" size="small" type="primary" effect="dark">
                {{ currentTeachingStrategy.strategy_label }}
              </el-tag>
            </div>
            <el-button :icon="EditPen" size="small" @click="renameTutorConversation(activeTutorConversation ?? undefined)">重命名</el-button>
          </div>
        </header>

        <div ref="chatViewportRef" class="chat-messages">
          <div v-if="chatMessages.length === 0" class="chat-empty">
            <div class="tutor-identity-card">
              <strong>循证学习教练</strong>
              <span>我会根据你的课程资料、图片/文件和学习画像，先做问题诊断，再给出分层讲解、关键依据和下一步练习。</span>
            </div>
            <h3>开始一次学习辅导</h3>
            <p>上传图片或文件后再提问，智能辅导会自动解析并融合所有信息，逐步展示思考过程给出回答。</p>
          </div>

          <div v-for="message in chatMessages" :key="message.id" class="chat-row" :class="message.role" :data-message-id="message.id">
            <template v-if="message.role === 'assistant'">
              <div style="display:flex;flex-direction:column;align-items:flex-start;width:100%;">
                <div v-if="showTiming && message.status === 'generating'" class="live-timer" style="margin-bottom:4px;margin-left:2px;">已耗时 {{ formatDuration(liveElapsed) }}</div>
                <div v-else-if="showTiming && message.duration" class="live-timer" style="margin-bottom:4px;margin-left:2px;">回答耗时 {{ formatDuration(message.duration) }}</div>
                <div class="chat-bubble">
                <!-- ======= 生成中状态 ======= -->
                <template v-if="message.status === 'generating'">
                  <div class="assistant-msg-generating">
                    <div class="generating-header">
                      <span class="loading-spinner"></span>
                      <span class="generating-text">正在生成回答...</span>
                    </div>
                    <div v-if="message.content" class="markdown" v-html="renderMarkdown(message.content)"></div>
                    <div class="assistant-msg-actions">
                      <el-button type="info" size="small" @click.stop="stopTutorAnswer" class="stop-gen-btn">
                        <el-icon><Close /></el-icon>
                        停止生成
                      </el-button>
                      <el-button :icon="CopyDocument" size="small" text circle title="复制消息" @click.stop="copyMessage(message)" />
                      <el-button :icon="Refresh" size="small" text circle title="重新生成" @click.stop="regenerateAssistantMessage(message)" :disabled="regeneratingMessageId !== null" />
                      <el-button :icon="Delete" size="small" text circle title="删除此条消息" @click.stop="deleteChatMessage(message.id)" />
                    </div>
                  </div>
                </template>
                <!-- ======= 已停止状态 ======= -->
                <template v-else-if="message.status === 'stopped'">
                  <div class="assistant-msg-stopped">
                    <div class="stopped-header">
                      <el-tag type="info" size="small" class="stopped-tag">已停止</el-tag>
                    </div>
                    <div v-if="message.content" class="markdown" v-html="renderMarkdown(message.content)"></div>
                    <div class="assistant-msg-actions">
                      <el-button type="primary" size="small" @click.stop="continueTutorAnswer(message)" class="continue-btn">
                        <el-icon><VideoPlay /></el-icon>
                        继续生成
                      </el-button>
                      <el-button :icon="CopyDocument" size="small" text circle title="复制消息" @click.stop="copyMessage(message)" />
                      <el-button :icon="Delete" size="small" text circle title="删除此条消息" @click.stop="deleteChatMessage(message.id)" />
                    </div>
                  </div>
                </template>
                <!-- ======= 已完成/默认状态 ======= -->
                <template v-else>
                  <div class="assistant-msg-display">
                    <div v-if="regeneratingMessageId === message.id" class="regenerating-hint">正在重新生成...</div>
                    <div v-show="regeneratingMessageId !== message.id" class="markdown" v-html="renderMarkdown(message.content || '')"></div>
                    <div v-if="message.image_url" class="tutor-generated-image" style="margin-top: 12px; text-align: center;">
                      <el-image :src="message.image_url" fit="contain" style="max-width: 320px; max-height: 200px; width: auto; height: auto; border-radius: var(--radius-md); border: 1px solid var(--surface-200); cursor: pointer; box-shadow: var(--shadow-sm);" :preview-src-list="[message.image_url]" :preview-teleported="true" />
                      <div style="margin-top: 6px; font-size: 12px; color: var(--surface-400);">
                        智能生成的教学配图
                        <el-link :href="message.image_url" target="_blank" type="primary" style="margin-left: 8px;" @click.stop>查看原图</el-link>
                      </div>
                    </div>
                    <div v-if="message.video_url" class="tutor-generated-video" style="margin-top: 12px; text-align: center;">
                      <video :src="message.video_url" controls style="max-width: 100%; max-height: 400px; border-radius: var(--radius-md); border: 1px solid var(--surface-200); box-shadow: var(--shadow-sm);" :title="'智能生成的教学视频'">
                        您的浏览器不支持播放视频，请 <a :href="message.video_url" target="_blank">点击下载</a>
                      </video>
                      <div style="margin-top: 6px; font-size: 12px; color: var(--surface-400);">
                        智能生成的教学视频
                        <el-link :href="message.video_url" target="_blank" type="primary" style="margin-left: 8px;" @click.stop>下载视频</el-link>
                      </div>
                    </div>
                    <div class="assistant-msg-actions">
                      <el-button :icon="CopyDocument" size="small" text circle title="复制消息" @click.stop="copyMessage(message)" />
                      <el-button :icon="Refresh" size="small" text circle title="重新生成" @click.stop="regenerateAssistantMessage(message)" :disabled="regeneratingMessageId !== null" />
                      <el-button :icon="Delete" size="small" text circle title="删除此条消息" @click.stop="deleteChatMessage(message.id)" />
                    </div>
                  </div>
                </template>
              </div>
              </div>
            </template>
            <template v-else>
              <div class="user-message-wrapper" :class="{ 'is-editing': editingMessageId === message.id }">
                <!-- 附件卡片（完全独立，不参与编辑，不受气泡宽度影响） -->
                <div v-if="(message.images && message.images.length > 0) || (message.files && message.files.length > 0)" class="user-attachments">
                  <div v-for="(img, idx) in message.images" :key="'user-img-'+idx" class="user-attach-img" @click="previewUserImage(img)">
                    <img :src="img" class="user-attach-thumb" />
                  </div>
                  <div v-for="(file, idx) in message.files" :key="'user-file-'+idx" class="user-attach-file" @click="previewUserFile(file)">
                    <span :class="['user-attach-badge', file.type === 'application/pdf' ? 'badge-pdf' : 'badge-file']">{{ file.type === 'application/pdf' ? 'PDF' : file.name.split('.').pop()?.toUpperCase() || 'FILE' }}</span>
                    <span class="user-attach-filename" :title="file.name">{{ file.name }}</span>
                  </div>
                </div>
                <!-- 气泡容器：relative 用于按钮悬浮定位 -->
                <div class="user-bubble-container" :class="{ 'is-editing': editingMessageId === message.id }">
                  <!-- 编辑模式 -->
                  <template v-if="editingMessageId === message.id">
                    <div class="chat-bubble editing">
                      <textarea
                        ref="editTextareaRef"
                        v-model="editingContent"
                        class="edit-inline-textarea"
                        placeholder="编辑消息内容"
                        @input="autoResizeEditInput"
                      ></textarea>
                    </div>
                    <div class="edit-float-actions">
                      <button class="edit-cancel-btn" @click.stop="cancelEditMessage">取消</button>
                      <button class="edit-submit-btn" @click.stop="submitEditMessage">发送</button>
                    </div>
                  </template>
                  <!-- 普通模式 -->
                  <template v-else>
                    <div class="chat-bubble">
                      <div class="user-message-text">{{ message.content }}</div>
                    </div>
                    <div class="user-msg-actions">
                      <el-button :icon="CopyDocument" size="small" text circle title="复制消息" @click.stop="copyMessage(message)" />
                      <el-button :icon="EditPen" size="small" text circle title="编辑消息" @click.stop="startEditMessage(message)" />
                      <el-button :icon="Delete" size="small" text circle title="删除此条消息" @click.stop="deleteChatMessage(message.id)" />
                    </div>
                  </template>
                </div>
              </div>
            </template>
          </div>
        </div>

        <div
          class="chat-composer"
          @dragenter.prevent="onDragEnter"
          @dragover.prevent="onDragOver"
          @dragleave.prevent="onDragLeave"
          @drop.prevent="onDrop"
        >
          <transition name="fade">
            <div v-if="isDragOver" class="drop-overlay">
              <div class="drop-overlay-content">
                <el-icon :size="40"><Upload /></el-icon>
                <p>释放以上传图片或文件</p>
              </div>
            </div>
          </transition>
          <div v-if="tutorForm.images.length > 0 || tutorForm.files.length > 0" class="attachments-container">
            <div v-for="(img, idx) in tutorForm.images" :key="'img-'+idx" class="attachment-card">
              <img :src="img" class="attachment-thumb" />
              <div class="attachment-info">
                <div class="attachment-name">图片_{{ idx + 1 }}</div>
                <div class="attachment-size">{{ formatFileSize(Math.round((img.length * 3) / 4)) }}</div>
              </div>
              <div class="attachment-close" @click.stop="removeTutorImage(idx)">×</div>
            </div>
            <div v-for="(file, idx) in tutorForm.files" :key="'file-'+idx" class="attachment-card">
              <div v-if="file.type === 'application/pdf'" class="attachment-icon attachment-icon-pdf">PDF</div>
              <div v-else class="attachment-icon attachment-icon-file">FIL</div>
              <div class="attachment-info">
                <div class="attachment-name">{{ file.name }}</div>
                <div class="attachment-size">{{ formatFileSize(file.content ? Math.round((file.content.length * 3) / 4) : 0) }}</div>
              </div>
              <div class="attachment-close" @click.stop="removeTutorFile(idx)">×</div>
            </div>
          </div>
          <div class="composer-line">
            <div class="tutor-input-wrapper">
              <transition name="input-examples-fade">
                <section v-show="showSidebarExamples" class="input-examples-popover">
                  <div class="sidebar-examples-head">
                    <strong>可以这样问</strong>
                    <span>点击示例填入输入框</span>
                  </div>
                  <div class="sidebar-example-list">
                    <button
                      v-for="(prompt, idx) in examplePrompts"
                      :key="idx"
                      type="button"
                      class="sidebar-example-card"
                      @mousedown.prevent
                      @click="useExamplePrompt(idx)"
                    >
                      <span class="sidebar-example-label">示例 {{ idx + 1 }}</span>
                      <span class="sidebar-example-text">{{ prompt }}</span>
                    </button>
                  </div>
                </section>
              </transition>
              <el-input
                ref="tutorInputRef"
                v-model="tutorForm.question"
                type="textarea"
                resize="none"
                placeholder="输入你的学习问题，支持拖拽图片或文件到此处上传"
                class="tutor-textarea"
                @focus="handleTutorInputFocus"
                @blur="handleTutorInputBlur"
                @paste="onTutorInputPaste"
                @input="autoResizeTutorInput"
              />
            </div>
            <div class="composer-footer">
              <div class="kb-switch">
                <el-popover
                  trigger="hover"
                  placement="top-start"
                  :width="120"
                  popper-class="kb-popover"
                >
                  <template #reference>
                    <span class="kb-switch-label">
                      知识库
                      <el-tag size="small" effect="plain" class="kb-mode-tag">{{ knowledgeBaseMode === 'auto' ? '自动' : knowledgeBaseMode === 'on' ? '开启' : '关闭' }}</el-tag>
                    </span>
                  </template>
                  <div class="kb-dropdown">
                    <div
                      class="kb-dropdown-item"
                      :class="{ active: knowledgeBaseMode === 'auto' }"
                      @click="knowledgeBaseMode = 'auto'"
                    >自动</div>
                    <div
                      class="kb-dropdown-item"
                      :class="{ active: knowledgeBaseMode === 'on' }"
                      @click="knowledgeBaseMode = 'on'"
                    >开启</div>
                    <div
                      class="kb-dropdown-item"
                      :class="{ active: knowledgeBaseMode === 'off' }"
                      @click="knowledgeBaseMode = 'off'"
                    >关闭</div>
                  </div>
                </el-popover>
              </div>
              <div class="img-switch">
                <el-switch
                  v-model="enableImageGen"
                  active-text="配图"
                  inactive-text="配图"
                  size="small"
                  inline-prompt
                />
              </div>
              <div class="composer-actions">
                <el-button v-if="!loading" type="primary" :icon="ChatDotRound" class="send-button" @click="askTutor">发送</el-button>
                <el-button v-else type="info" :icon="Close" class="stop-button" @click="stopTutorAnswer">停止</el-button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElInput, ElMessage, ElMessageBox } from 'element-plus'
import { ChatDotRound, Close, CopyDocument, Delete, EditPen, Picture, Plus, Refresh, Upload, VideoPlay } from '@element-plus/icons-vue'
import { api } from '../api/learning'
import { getErrorMessage, renderMarkdown, formatDateTime } from '../composables/useUtils'

interface UploadedFile {
  name: string
  type: string
  content: string
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  thinking?: string
  openPanels?: string[]
  images?: string[]
  files?: UploadedFile[]
  image_url?: string
  video_url?: string
  status?: 'generating' | 'stopped' | 'completed'
  duration?: number
}

interface ChatConversation {
  id: number
  title: string
  messages: ChatMessage[]
  created_at?: string
}

const chatViewportRef = ref<HTMLDivElement | null>(null)
const loading = ref(false)
const currentTeachingStrategy = ref<any | null>(null)
const showTiming = computed(() => import.meta.env.VITE_ENABLE_RESOURCE_TIMING === 'true')

const liveElapsed = ref(0)
let liveTimerInterval: ReturnType<typeof setInterval> | null = null

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

function formatDuration(seconds: number) {
  if (seconds == null) return ''
  if (seconds < 60) return `${Math.floor(seconds)}秒`
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}分${secs}秒`
}
const knowledgeBaseMode = ref<'auto' | 'on' | 'off'>('off')
const enableImageGen = ref(false)
const tutorInputRef = ref<InstanceType<typeof ElInput> | null>(null)
const showSidebarExamples = ref(false)
const continueTargetMessageId = ref<string | null>(null)
const editTextareaRef = ref<HTMLTextAreaElement | null>(null)
let sidebarExamplesHideTimer: ReturnType<typeof setTimeout> | null = null
/** v-for 内 ref 会在 Vue 3 中变成数组，提取单个元素 */
function getEditTextarea(): HTMLTextAreaElement | null {
  const refs = editTextareaRef.value
  if (!refs) return null
  return Array.isArray(refs) ? (refs[0] || null) : (refs as HTMLTextAreaElement)
}
const activeTutorConversationId = ref<number | null>(null)
const streamingMessageId = ref('')
const tutorConversations = ref<ChatConversation[]>([])
const tutorForm = reactive({ question: '', images: [] as string[], files: [] as UploadedFile[] })
const isDragOver = ref(false)
const abortControllerRef = ref<AbortController | null>(null)
let dragCounter = 0

const activeTutorConversation = computed(() => {
  if (tutorConversations.value.length === 0) return null
  const found = tutorConversations.value.find((item) => item.id === activeTutorConversationId.value)
  if (found) return found
  return tutorConversations.value[0]
})

const chatMessages = computed(() => activeTutorConversation.value?.messages || [])
const streamingAssistantMessage = ref<ChatMessage | null>(null)
const editingMessageId = ref<string | null>(null)
const editingContent = ref('')
const copyFeedbackId = ref<string | null>(null)
const regeneratingMessageId = ref<string | null>(null)

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function previewUserImage(img: string) {
  const el = document.createElement('div')
  el.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;cursor:pointer;'
  el.addEventListener('click', () => document.body.removeChild(el))
  const imgEl = document.createElement('img')
  imgEl.src = img
  imgEl.style.cssText = 'max-width:90vw;max-height:90vh;border-radius:8px;object-fit:contain;box-shadow:0 4px 24px rgba(0,0,0,0.3);'
  el.appendChild(imgEl)
  document.body.appendChild(el)
}

function previewUserFile(file: UploadedFile) {
  if (file.content) {
    window.open(file.content, '_blank')
  }
}

async function startNewTutorConversation() {
  try {
    const { data } = await api.createChatConversation({ title: '新学习辅导', messages: [] })
    tutorConversations.value.unshift(data.conversation)
    activeTutorConversationId.value = data.conversation.id
    tutorForm.question = ''
    tutorForm.images = []
    tutorForm.files = []
    autoResizeTutorInput()
    await nextTick()
    await scrollChatToBottom()
    ElMessage.success('新对话已创建')
  } catch (error) {
    console.error('创建对话失败:', error)
    ElMessage.error('无法连接服务器，对话将保存在本地（刷新后会丢失）')
    const tempId = -Date.now()
    tutorConversations.value.unshift({
      id: tempId,
      title: '新学习辅导',
      messages: []
    })
    activeTutorConversationId.value = tempId
    tutorForm.question = ''
  }
}

async function saveActiveConversation() {
  const conversation = activeTutorConversation.value
  if (!conversation || conversation.id < 0) return
  try {
    await api.updateChatConversation(conversation.id, {
      title: conversation.title,
      messages: conversation.messages
    })
  } catch (error) {
    console.error('保存对话失败:', error)
    ElMessage.warning('对话保存失败，请检查网络连接')
  }
}

async function loadChatConversations() {
  try {
    const { data } = await api.getChatConversations()
    tutorConversations.value = data.conversations || []
    if (tutorConversations.value.length > 0) {
      activeTutorConversationId.value = tutorConversations.value[0].id
      await nextTick()
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
      scrollChatToBottom()
    } else {
      await startNewTutorConversation()
    }
  } catch (error: any) {
    console.error('加载对话失败:', error)
    if (tutorConversations.value.length === 0) {
      const tempId = -Date.now()
      tutorConversations.value.unshift({
        id: tempId,
        title: '新学习辅导',
        messages: []
      })
      activeTutorConversationId.value = tempId
      await nextTick()
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
      scrollChatToBottom()
    }
  }
}

function handleTutorImageUpload(file: File): boolean {
  const maxSize = 10 * 1024 * 1024
  if (file.size > maxSize) {
    ElMessage.warning('图片大小不能超过 10MB')
    return false
  }
  const reader = new FileReader()
  reader.onload = () => {
    const result = reader.result as string
    if (result) tutorForm.images.push(result)
  }
  reader.readAsDataURL(file)
  return false
}

function removeTutorImage(index: number) {
  tutorForm.images.splice(index, 1)
}

function handleTutorFileUpload(file: File): boolean {
  const maxSize = 20 * 1024 * 1024
  if (file.size > maxSize) {
    ElMessage.warning('文件大小不能超过 20MB')
    return false
  }
  const reader = new FileReader()
  reader.onload = () => {
    const result = reader.result as string
    if (result) {
      const base64Content = result.split(',')[1] || result
      tutorForm.files.push({
        name: file.name,
        type: file.type || 'application/octet-stream',
        content: base64Content
      })
    }
  }
  reader.readAsDataURL(file)
  return false
}

function removeTutorFile(index: number) {
  tutorForm.files.splice(index, 1)
}

function onDragEnter(e: DragEvent) {
  dragCounter++
  isDragOver.value = true
}

function onDragOver(e: DragEvent) {
  isDragOver.value = true
}

function onDragLeave(e: DragEvent) {
  dragCounter--
  if (dragCounter <= 0) {
    dragCounter = 0
    isDragOver.value = false
  }
}

function onDrop(e: DragEvent) {
  dragCounter = 0
  isDragOver.value = false
  const items = e.dataTransfer?.files
  if (!items || items.length === 0) return
  for (let i = 0; i < items.length; i++) {
    const file = items[i]
    const isImage = file.type.startsWith('image/')
    if (isImage) {
      readImageFile(file)
    } else {
      readFile(file)
    }
  }
}

function onTutorInputPaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items || items.length === 0) return
  let hasImage = false
  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    if (item.type.startsWith('image/')) {
      e.preventDefault()
      hasImage = true
      const file = item.getAsFile()
      if (file) {
        readImageFile(file)
      }
    }
  }
  if (hasImage) {
    ElMessage.success('已粘贴图片，点击发送按钮一起发送')
  }
}

function handleTutorInputFocus() {
  if (sidebarExamplesHideTimer) {
    clearTimeout(sidebarExamplesHideTimer)
    sidebarExamplesHideTimer = null
  }
  showSidebarExamples.value = true
}

function handleTutorInputBlur() {
  if (sidebarExamplesHideTimer) clearTimeout(sidebarExamplesHideTimer)
  sidebarExamplesHideTimer = setTimeout(() => {
    showSidebarExamples.value = false
    sidebarExamplesHideTimer = null
  }, 180)
}

/**
 * 输入框自适应高度：内容增多时自动增高，超出最大高度后出现滚动条
 */
function autoResizeTutorInput() {
  nextTick(() => {
    const el = tutorInputRef.value
    if (!el) return
    const textarea = el.$el?.querySelector('textarea') || el.textarea
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = textarea.scrollHeight + 'px'
  })
}

/**
 * 编辑框自适应高度：内容增多时自动增高，超过 4 行后出现滚动条
 */
function autoResizeEditInput() {
  nextTick(() => {
    const textarea = getEditTextarea()
    if (!textarea) return
    const fourLinesPx = parseFloat(getComputedStyle(textarea).lineHeight || '21') * 4
    textarea.style.height = 'auto'
    const scrollH = textarea.scrollHeight
    if (scrollH > fourLinesPx) {
      textarea.style.height = scrollH + 'px'
      textarea.style.maxHeight = 'none'
      textarea.style.overflow = 'hidden'
    } else {
      textarea.style.height = scrollH + 'px'
      textarea.style.maxHeight = ''
      textarea.style.overflow = ''
    }
  })
}

function readImageFile(file: File) {
  const maxSize = 10 * 1024 * 1024
  if (file.size > maxSize) {
    ElMessage.warning(`图片 ${file.name} 大小不能超过 10MB`)
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    const result = reader.result as string
    if (result) tutorForm.images.push(result)
  }
  reader.readAsDataURL(file)
}

function readFile(file: File) {
  const maxSize = 20 * 1024 * 1024
  if (file.size > maxSize) {
    ElMessage.warning(`文件 ${file.name} 大小不能超过 20MB`)
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    const result = reader.result as string
    if (result) {
      const base64Content = result.split(',')[1] || result
      tutorForm.files.push({
        name: file.name,
        type: file.type || 'application/octet-stream',
        content: base64Content
      })
    }
  }
  reader.readAsDataURL(file)
}

function stopTutorAnswer() {
  if (abortControllerRef.value) {
    abortControllerRef.value.abort()
    abortControllerRef.value = null
  }
  // 标记正在流式生成的消息为已停止状态
  if (streamingAssistantMessage.value) {
    streamingAssistantMessage.value.status = 'stopped'
    streamingAssistantMessage.value = null
  }
}

const examplePrompts = [
  '我正在学习【机器学习中的过拟合与正则化】，目前不太理解【为什么 L2 正则化可以缓解过拟合】。我的基础是【已经学过线性回归和梯度下降，但对损失函数理解不深】。请你结合我的学习画像，用【通俗解释 + 公式推导 + 小例子】的方式讲解，并最后给我 3 道练习题。',
  '我正在学习【神经网络反向传播】，不理解【链式法则如何传递梯度】。请用通俗语言、步骤图和一个简单数值例子讲解。',
  '这道题我不会做：【粘贴题目】。请先判断考察的知识点，再一步步提示，不要直接给最终答案。',
  '我最近在学习【机器学习】，测评中【过拟合、池化层、激活函数】经常出错。请根据我的学习记录，帮我制定今天 30 分钟的复习计划。',
]

function useExamplePrompt(idx: number) {
  tutorForm.question = examplePrompts[idx] || examplePrompts[0]
  autoResizeTutorInput()
  nextTick(() => {
    const el = tutorInputRef.value
    if (el) {
      const textarea = (el as any).$el?.querySelector('textarea') || (el as any).textarea
      if (textarea) textarea.focus()
    }
  })
}

async function askTutor() {
  if (!tutorForm.question.trim()) {
    ElMessage.warning('请输入要提问的问题')
    return
  }
  if (loading.value) return

  const question = tutorForm.question.trim()
  const images = [...tutorForm.images]
  const files = [...tutorForm.files]
  const conversation = activeTutorConversation.value
  if (!conversation) {
    await startNewTutorConversation()
    return
  }
  if (conversation.title === '新学习辅导') {
    conversation.title = question.length > 18 ? `${question.slice(0, 18)}...` : question
  }

  const userMessage: ChatMessage = {
    id: `user-${Date.now()}`,
    role: 'user',
    content: question,
    images: images.length > 0 ? images : undefined,
    files: files.length > 0 ? files : undefined,
  }
  const assistantMessage: ChatMessage = {
    id: `assistant-${Date.now()}`,
    role: 'assistant',
    content: '',
    thinking: '',
    openPanels: ['thinking'],
    status: 'generating',
  }
  conversation.messages.push(userMessage, assistantMessage)
  streamingAssistantMessage.value = assistantMessage
  streamingMessageId.value = assistantMessage.id
  tutorForm.question = ''
  tutorForm.images = []
  tutorForm.files = []
  autoResizeTutorInput()
  await scrollChatToBottom()

  startLiveTimer()
  loading.value = true
  const _tutorStart = Date.now()
  abortControllerRef.value = new AbortController()
  const signal = abortControllerRef.value.signal
  try {
    await streamTutorAnswer(question, '', images, files, signal, buildConversationHistory(chatMessages.value.slice(0, -2)))
    if (!signal.aborted) {
      ElMessage.success('回答已生成')
    }
  } catch (error: any) {
    if (error.name === 'AbortError' || signal.aborted) return
    assistantMessage.content += `\n\n> ${getErrorMessage(error)}`
    ElMessage.error(getErrorMessage(error))
  } finally {
    abortControllerRef.value = null
    stopLiveTimer()
    assistantMessage.status = 'completed'
    assistantMessage.duration = (Date.now() - _tutorStart) / 1000
    loading.value = false
    streamingMessageId.value = ''
    streamingAssistantMessage.value = null
    await scrollChatToBottom()
    await saveActiveConversation()
  }
}

function buildConversationHistory(messages: any[]): { role: string, content: string }[] {
  return messages
    .filter(m => m.content && m.content.trim())
    .map(m => ({
      role: m.role === 'user' ? 'user' : 'assistant',
      content: m.content
    }))
}

async function streamTutorAnswer(question: string, context: string, images?: string[], files?: UploadedFile[], signal?: AbortSignal, history?: { role: string, content: string }[]) {
  const token = localStorage.getItem('study_token')
  const apiBase = import.meta.env.VITE_API_BASE_URL || ''
  const response = await fetch(`${apiBase}/api/tutor/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify({ question, context, images: images || [], files: files || [], stream: true, history: history || [], knowledge_base_mode: knowledgeBaseMode.value, image_gen_enabled: enableImageGen.value }),
    signal
  })
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
  if (!reader) throw new Error('当前浏览器不支持流式响应')
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
      handleTutorStreamEvent(rawEvent)
      boundary = buffer.indexOf('\n\n')
    }
  }
  if (buffer.trim()) handleTutorStreamEvent(buffer)
}

function handleTutorStreamEvent(rawEvent: string) {
  const lines = rawEvent.split('\n')
  const eventLine = lines.find((line) => line.startsWith('event:'))
  const dataLine = lines.find((line) => line.startsWith('data:'))
  const eventName = eventLine?.replace('event:', '').trim() || 'message'
  const rawData = dataLine?.replace('data:', '').trim() || '{}'
  let payload: { content?: string; image_url?: string; video_url?: string } = {}
  try {
    payload = JSON.parse(rawData)
  } catch {
    payload = { content: rawData }
  }

  function streamScroll() {
    if (continueTargetMessageId.value) {
      scrollToContinueMessage(continueTargetMessageId.value)
    } else if (regeneratingMessageId.value) {
      scrollToContinueMessage(regeneratingMessageId.value)
    } else {
      scrollChatToBottom()
    }
  }

  if (eventName === 'thinking') {
    if (streamingAssistantMessage.value) {
      streamingAssistantMessage.value.thinking = `${streamingAssistantMessage.value.thinking || ''}${payload.content || ''}`
      streamScroll()
    }
  } else if (eventName === 'answer') {
    if (streamingAssistantMessage.value) {
      streamingAssistantMessage.value.content += payload.content || ''
      streamScroll()
    }
  } else if (eventName === 'image') {
    if (streamingAssistantMessage.value && payload.image_url) {
      streamingAssistantMessage.value.image_url = payload.image_url
      streamScroll()
    }
  } else if (eventName === 'video') {
    if (streamingAssistantMessage.value && payload.video_url) {
      streamingAssistantMessage.value.video_url = payload.video_url
      streamScroll()
    }
  } else if (eventName === 'done') {
    if (streamingAssistantMessage.value) {
      streamingAssistantMessage.value.status = 'completed'
    }
  }
}

function selectTutorConversation(id: number) {
  activeTutorConversationId.value = id
  nextTick(async () => {
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
    scrollChatToBottom()
  })
}

async function renameTutorConversation(conversation?: ChatConversation) {
  if (!conversation) return
  try {
    const { value } = await ElMessageBox.prompt('请输入新的对话标题', '重命名对话', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: conversation.title,
      inputValidator: (value) => Boolean(value.trim()) || '标题不能为空',
    })
    conversation.title = value.trim()
    if (conversation.id > 0) {
      await api.updateChatConversation(conversation.id, { title: conversation.title })
    }
    ElMessage.success('对话标题已更新')
  } catch {
    // 用户取消时不提示错误。
  }
}

async function deleteTutorConversation(conversation?: ChatConversation) {
  if (!conversation) return
  try {
    await ElMessageBox.confirm(`确定删除"${conversation.title}"吗？`, '删除对话', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    if (conversation.id > 0) {
      await api.deleteChatConversation(conversation.id)
    }
    const index = tutorConversations.value.findIndex((item) => item.id === conversation.id)
    if (index < 0) return
    const deletingActive = activeTutorConversationId.value === conversation.id
    tutorConversations.value.splice(index, 1)
    if (tutorConversations.value.length === 0) {
      await startNewTutorConversation()
    } else if (deletingActive) {
      const nextIdx = Math.min(index, tutorConversations.value.length - 1)
      activeTutorConversationId.value = tutorConversations.value[nextIdx].id
      nextTick(scrollChatToBottom)
    }
    ElMessage.success('对话已删除')
  } catch {
    // 用户取消时不提示错误。
  }
}

async function deleteChatMessage(messageId: string) {
  const conversation = activeTutorConversation.value
  if (!conversation) return
  const index = conversation.messages.findIndex((m) => m.id === messageId)
  if (index < 0) return
  conversation.messages.splice(index, 1)
  await saveActiveConversation()
}

function copyMessage(message: ChatMessage) {
  navigator.clipboard.writeText(message.content).then(() => {
    copyFeedbackId.value = message.id
    setTimeout(() => {
      if (copyFeedbackId.value === message.id) {
        copyFeedbackId.value = null
      }
    }, 1500)
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

function startEditMessage(message: ChatMessage) {
  const bubbleEl = document.querySelector(`[data-message-id="${message.id}"] .chat-bubble`) as HTMLElement | null
  const bubbleHeight = bubbleEl ? bubbleEl.getBoundingClientRect().height : 0
  editingMessageId.value = message.id
  editingContent.value = message.content
  nextTick(() => {
    const textarea = getEditTextarea()
    if (!textarea) return
    textarea.style.height = 'auto'
    const scrollH = textarea.scrollHeight
    const fourLinesPx = parseFloat(getComputedStyle(textarea).lineHeight || '21') * 4
    if (scrollH > fourLinesPx) {
      textarea.style.height = scrollH + 'px'
      textarea.style.maxHeight = 'none'
      textarea.style.overflow = 'hidden'
    } else {
      const initH = Math.max(scrollH, bubbleHeight)
      textarea.style.height = Math.min(initH, fourLinesPx) + 'px'
      textarea.style.maxHeight = ''
      textarea.style.overflow = ''
    }
    textarea.focus()
  })
}

function cancelEditMessage() {
  editingMessageId.value = null
  editingContent.value = ''
}

async function submitEditMessage() {
  const text = editingContent.value.trim()
  if (!text) {
    ElMessage.warning('消息内容不能为空')
    return
  }
  const conversation = activeTutorConversation.value
  if (!conversation) return
  const messageId = editingMessageId.value
  if (!messageId) return
  const msgIndex = conversation.messages.findIndex((m) => m.id === messageId)
  if (msgIndex < 0) return

  const originalMessage = conversation.messages[msgIndex]

  // 更新用户消息内容（保留附件）
  originalMessage.content = text

  // 移除紧接着的助手回复（如果有的话）
  let insertIndex = msgIndex + 1
  if (insertIndex < conversation.messages.length && conversation.messages[insertIndex].role === 'assistant') {
    conversation.messages.splice(insertIndex, 1)
  }

  // 创建新助手消息并插入到原位置
  const newAssistantMessage: ChatMessage = {
    id: `assistant-${Date.now()}`,
    role: 'assistant',
    content: '',
    thinking: '',
    openPanels: ['thinking'],
    status: 'generating',
  }
  conversation.messages.splice(insertIndex, 0, newAssistantMessage)
  streamingAssistantMessage.value = newAssistantMessage
  streamingMessageId.value = newAssistantMessage.id
  regeneratingMessageId.value = newAssistantMessage.id

  editingMessageId.value = null
  editingContent.value = ''

  startLiveTimer()
  loading.value = true
  const _tutorStart = Date.now()
  abortControllerRef.value = new AbortController()
  const signal = abortControllerRef.value.signal
  try {
    await streamTutorAnswer(text, '', originalMessage.images || [], originalMessage.files || [], signal, buildConversationHistory(chatMessages.value.slice(0, insertIndex)))
    if (!signal.aborted) {
      ElMessage.success('回答已生成')
    }
  } catch (error: any) {
    if (error.name === 'AbortError' || signal.aborted) return
    newAssistantMessage.content += `\n\n> ${getErrorMessage(error)}`
    ElMessage.error(getErrorMessage(error))
  } finally {
    abortControllerRef.value = null
    stopLiveTimer()
    newAssistantMessage.status = 'completed'
    newAssistantMessage.duration = (Date.now() - _tutorStart) / 1000
    loading.value = false
    streamingMessageId.value = ''
    streamingAssistantMessage.value = null
    regeneratingMessageId.value = null
    await saveActiveConversation()
  }
}

async function regenerateAssistantMessage(message: ChatMessage) {
  const conversation = activeTutorConversation.value
  if (!conversation) return
  const msgIndex = conversation.messages.findIndex((m) => m.id === message.id)
  if (msgIndex < 0) return

  // 查找上一条用户消息
  let prevUserIndex = -1
  for (let i = msgIndex - 1; i >= 0; i--) {
    if (conversation.messages[i].role === 'user') {
      prevUserIndex = i
      break
    }
  }
  if (prevUserIndex < 0) {
    ElMessage.warning('未找到上一条用户消息')
    return
  }
  const prevUserMessage = conversation.messages[prevUserIndex]

  // 清空当前助手消息，准备重新生成
  message.content = ''
  message.image_url = ''
  message.video_url = ''
  message.thinking = ''
  message.status = 'generating'

  regeneratingMessageId.value = message.id
  streamingMessageId.value = message.id
  streamingAssistantMessage.value = message
  startLiveTimer()

  loading.value = true
  const _tutorStart = Date.now()
  abortControllerRef.value = new AbortController()
  const signal = abortControllerRef.value.signal
  try {
    await streamTutorAnswer(
      prevUserMessage.content,
      '',
      prevUserMessage.images || [],
      prevUserMessage.files || [],
      signal,
      buildConversationHistory(chatMessages.value.filter(m => m.id !== prevUserMessage.id && m.id !== message.id)),
    )
    if (!signal.aborted) {
      ElMessage.success('回答已重新生成')
    }
  } catch (error: any) {
    if (error.name === 'AbortError' || signal.aborted) return
    message.content += `\n\n> ${getErrorMessage(error)}`
    ElMessage.error(getErrorMessage(error))
  } finally {
    stopLiveTimer()
    abortControllerRef.value = null
    message.status = 'completed'
    message.duration = (Date.now() - _tutorStart) / 1000
    loading.value = false
    streamingMessageId.value = ''
    streamingAssistantMessage.value = null
    regeneratingMessageId.value = null
    await saveActiveConversation()
  }
}

async function continueTutorAnswer(message: ChatMessage) {
  const conversation = activeTutorConversation.value
  if (!conversation) return

  const msgIndex = conversation.messages.findIndex((m) => m.id === message.id)
  if (msgIndex < 0) return

  // 查找上一条用户消息
  let prevUserIndex = -1
  for (let i = msgIndex - 1; i >= 0; i--) {
    if (conversation.messages[i].role === 'user') {
      prevUserIndex = i
      break
    }
  }
  if (prevUserIndex < 0) {
    ElMessage.warning('未找到上一条用户消息')
    return
  }
  const prevUserMessage = conversation.messages[prevUserIndex]

  // 设置状态为生成中
  message.status = 'generating'
  streamingMessageId.value = message.id
  streamingAssistantMessage.value = message

  continueTargetMessageId.value = message.id
  startLiveTimer()
  scrollToContinueMessage(message.id)

  loading.value = true
  const _tutorStart = Date.now()
  abortControllerRef.value = new AbortController()
  const signal = abortControllerRef.value.signal
  try {
    // 构建历史：排除当前用户消息和助手消息，但保留助手已生成的部分
    // 将已停止的助手内容作为历史消息传给后端，让 LLM 从中断位置继续生成
    const assistantPartialContent = message.content || ''
    const history = buildConversationHistory(
      chatMessages.value.filter(m => m.id !== prevUserMessage.id && m.id !== message.id)
    )
    // 把已生成的助手响应片段作为历史消息传给后端，让 LLM 接着生成
    if (assistantPartialContent) {
      history.push({ role: 'assistant', content: assistantPartialContent })
    }

    await streamTutorAnswer(
      prevUserMessage.content,
      '',
      prevUserMessage.images || [],
      prevUserMessage.files || [],
      signal,
      history
    )
    if (!signal.aborted) {
      ElMessage.success('回答已继续生成')
    }
  } catch (error: any) {
    if (error.name === 'AbortError' || signal.aborted) return
    message.content += `\n\n> ${getErrorMessage(error)}`
    ElMessage.error(getErrorMessage(error))
  } finally {
    stopLiveTimer()
    message.status = 'completed'
    abortControllerRef.value = null
    message.duration = (Date.now() - _tutorStart) / 1000
    loading.value = false
    streamingMessageId.value = ''
    streamingAssistantMessage.value = null
    continueTargetMessageId.value = null
    await saveActiveConversation()
  }
}

async function scrollChatToBottom() {
  await nextTick()
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
  if (!chatViewportRef.value) return
  chatViewportRef.value.scrollTop = chatViewportRef.value.scrollHeight
}

function scrollToContinueMessage(messageId: string) {
  nextTick(() => {
    const el = document.querySelector(`[data-message-id="${messageId}"]`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  })
}

function isMessageNearViewportBottom(messageId: string): boolean {
  const el = document.querySelector(`[data-message-id="${messageId}"]`)
  if (!el || !chatViewportRef.value) return true
  const viewportRect = chatViewportRef.value.getBoundingClientRect()
  const elRect = el.getBoundingClientRect()
  return (viewportRect.bottom - elRect.bottom) < 200
}

async function handleBeforeUnload() {
  const conversation = activeTutorConversation.value
  if (conversation && conversation.id > 0 && conversation.messages.length > 0) {
    try {
      const blob = new Blob([JSON.stringify({
        title: conversation.title,
        messages: conversation.messages
      })], { type: 'application/json' })
      navigator.sendBeacon(
        `${import.meta.env.VITE_API_BASE_URL || ''}/api/chat-conversations/${conversation.id}`,
        blob
      )
    } catch (error) {
      console.error('自动保存对话失败:', error)
    }
  }
}

onMounted(async () => {
  api.logTaskAction('visit_tutor').catch(() => {})
  api.getCurrentTeachingStrategy()
    .then(({ data }) => {
      currentTeachingStrategy.value = data.strategy || null
    })
    .catch(() => {
      currentTeachingStrategy.value = null
    })
  await loadChatConversations()
  window.addEventListener('beforeunload', handleBeforeUnload)
  // 页面加载完成后滚动到最下方（确保所有消息渲染完毕）
  await nextTick()
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
  scrollChatToBottom()
})

onUnmounted(() => {
  stopLiveTimer()
  window.removeEventListener('beforeunload', handleBeforeUnload)
})

watch(() => chatMessages.value.length, async (newLen, oldLen) => {
  if (newLen > oldLen) {
    await nextTick()
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
    scrollChatToBottom()
  }
})
</script>

<style scoped>
.chat-header-badges {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  flex-wrap: wrap;
}
.chat-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 14px;
  border-bottom: 2px solid var(--surface-200, #e2e8f0);
  margin-bottom: 4px;
}

.tutor-identity-line {
  margin-top: 6px;
  font-size: 13px;
  color: var(--surface-500, #64748b);
  line-height: 1.45;
}

.tutor-identity-card {
  max-width: 520px;
  margin: 0 auto 18px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  border: 1px solid var(--primary-100, #e0e7ff);
  border-radius: 12px;
  background: linear-gradient(135deg, #ffffff, #f8fafc);
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.05));
}

.tutor-identity-card strong {
  font-size: 15px;
  color: var(--surface-900, #0f172a);
}

.tutor-identity-card span {
  font-size: 14px;
  line-height: 1.6;
  color: var(--surface-600, #475569);
}

.chat-sidebar {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.new-chat-button {
  flex: 0 0 auto;
}

.input-examples-popover {
  position: absolute;
  left: clamp(-302px, -25vw, -224px);
  bottom: calc(100% + 12px);
  width: clamp(236px, 19vw, 282px);
  padding: 12px 10px 10px 14px;
  border-radius: 18px;
  border: 1px solid rgba(191, 219, 254, 0.78);
  background: linear-gradient(135deg, #ffffff 0%, #f8fbff 58%, #eef6ff 100%);
  box-shadow: 0 18px 44px rgba(15, 23, 42, 0.16), 0 8px 24px rgba(59, 130, 246, 0.12);
  z-index: 80;
  transform-origin: left bottom;
}

.input-examples-popover::before {
  content: '';
  position: absolute;
  left: clamp(216px, 91%, 260px);
  bottom: -8px;
  width: 14px;
  height: 14px;
  background: #ffffff;
  border-right: 1px solid rgba(191, 219, 254, 0.78);
  border-bottom: 1px solid rgba(191, 219, 254, 0.78);
  transform: rotate(45deg);
  border-radius: 3px;
}

@media (max-width: 1100px) {
  .input-examples-popover {
    left: 12px;
    width: min(300px, calc(100% - 24px));
  }

  .input-examples-popover::before {
    left: 44px;
  }
}

.input-examples-fade-enter-active,
.input-examples-fade-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.input-examples-fade-enter-from,
.input-examples-fade-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.98);
}

.sidebar-examples-head {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 8px;
}

.sidebar-examples-head strong {
  color: var(--primary-600, #4f46e5);
  font-size: 14px;
  line-height: 1.25;
}

.sidebar-examples-head span {
  color: var(--surface-400, #94a3b8);
  font-size: 12px;
}

.sidebar-example-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
  max-height: 118px;
  overflow-y: auto;
  padding-right: 4px;
}

.sidebar-example-list::-webkit-scrollbar {
  width: 5px;
}

.sidebar-example-list::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.42);
}

.sidebar-example-card {
  width: 100%;
  min-height: 108px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  border: 1px solid rgba(219, 234, 254, 0.95);
  border-radius: 14px 14px 14px 6px;
  background: #ffffff;
  color: inherit;
  text-align: left;
  cursor: pointer;
  position: relative;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.05);
  transition: border-color 0.16s ease, background 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}

.sidebar-example-card::before {
  content: '';
  position: absolute;
  left: -5px;
  top: 18px;
  width: 10px;
  height: 10px;
  background: #ffffff;
  border-left: 1px solid rgba(219, 234, 254, 0.95);
  border-bottom: 1px solid rgba(219, 234, 254, 0.95);
  transform: rotate(45deg);
  border-radius: 2px;
}

.sidebar-example-card:hover {
  background: #f8fbff;
  border-color: #93c5fd;
  box-shadow: 0 10px 22px rgba(59, 130, 246, 0.13);
  transform: translateX(2px);
}

.sidebar-example-card:hover::before {
  background: #f8fbff;
  border-color: #93c5fd;
}

.sidebar-example-label {
  color: var(--primary-600, #4f46e5);
  font-size: 12px;
  font-weight: 700;
  min-width: 0;
}

.sidebar-example-text {
  color: var(--surface-600, #475569);
  font-size: 12px;
  line-height: 1.45;
  display: block;
  min-width: 0;
  word-break: break-word;
  overflow-wrap: anywhere;
  overflow: hidden;
}

.chat-list {
  min-height: 0;
  overflow-y: auto;
}

/* ---- Attachments ---- */
.attachments-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.attachment-card {
  display: inline-flex;
  align-items: center;
  background: #ffffff;
  border-radius: 12px;
  padding: 6px 10px 6px 6px;
  gap: 8px;
  border: 1px solid var(--surface-200, #e2e8f0);
  max-width: 220px;
  position: relative;
  transition: all 0.2s ease;
}
.attachment-card:hover {
  background: var(--surface-50, #f8fafc);
  box-shadow: var(--shadow-sm, 0 1px 3px rgba(0,0,0,0.06));
}
.attachment-thumb {
  width: 44px;
  height: 44px;
  border-radius: 8px;
  object-fit: cover;
  display: block;
  flex-shrink: 0;
  border: 1px solid var(--surface-100, #f1f5f9);
}
.attachment-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 1px;
}
.attachment-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--surface-800, #1e293b);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
  line-height: 1.3;
}
.attachment-size {
  font-size: 12px;
  color: var(--surface-400, #94a3b8);
  line-height: 1.3;
}
.attachment-icon {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}
.attachment-icon-pdf {
  background: #fef2f2;
  color: #dc2626;
}
.attachment-icon-file {
  background: var(--surface-100, #f1f5f9);
  color: var(--surface-500, #64748b);
}

/* ---- User message wrapper ---- */
.user-message-wrapper {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  max-width: 90%;
  margin-left: auto;
  gap: 8px;
}
.user-message-wrapper.is-editing {
  width: 100%;
}
.user-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
}
.user-attach-img {
  width: 64px;
  height: 64px;
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  flex-shrink: 0;
  border: 1px solid rgba(0,0,0,0.08);
  transition: all 0.2s ease;
}
.user-attach-img:hover {
  opacity: 0.85;
  transform: scale(1.05);
}
.user-attach-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.user-attach-file {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: rgba(255,255,255,0.7);
  border: 1px solid var(--surface-200, #e2e8f0);
  border-radius: 20px;
  padding: 4px 10px 4px 5px;
  cursor: pointer;
  max-width: 200px;
  transition: all 0.15s;
}
.user-attach-file:hover {
  background: #fff;
  border-color: var(--primary-300, #c7d2fe);
}
.user-attach-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 5px;
  flex-shrink: 0;
  letter-spacing: 0.02em;
}
.badge-pdf {
  background: #fee2e2;
  color: #dc2626;
}
.badge-file {
  background: var(--surface-200, #e2e8f0);
  color: var(--surface-600, #475569);
}
.user-attach-filename {
  font-size: 13px;
  color: var(--surface-700, #334155);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.attachment-close {
  position: absolute;
  top: -7px;
  right: -7px;
  width: 18px;
  height: 18px;
  background: var(--danger, #ef4444);
  color: #fff;
  border-radius: 50%;
  display: none;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  z-index: 1;
  box-shadow: 0 2px 6px rgba(239, 68, 68, 0.3);
}
.attachment-card:hover .attachment-close {
  display: flex;
}
.message-attachments {
  margin-top: 8px;
}
.user-message-text {
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: break-word;
  color: #ffffff;
  line-height: 1.6;
}

/* ---- User bubble container ---- */
.user-bubble-container {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

/* ---- User message actions ---- */
.user-msg-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-top: 6px;
  padding-left: 4px;
}
.user-msg-actions .el-button {
  color: var(--surface-400, #94a3b8);
  --el-button-hover-text-color: var(--surface-600, #475569);
  --el-button-hover-bg-color: var(--surface-100, #f1f5f9);
  --el-button-hover-border-color: transparent;
  transition: all 0.2s ease;
}
.user-msg-actions .el-button:hover {
  color: var(--surface-600, #475569);
  background: var(--surface-100, #f1f5f9);
}

/* ---- Assistant message markdown ---- */
.chat-row.assistant .chat-bubble .markdown {
  color: var(--surface-800, #1e293b);
}

/* ---- Drop overlay ---- */
.drop-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  background: rgba(99, 102, 241, 0.06);
  border: 2px dashed var(--primary-400, #818cf8);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(4px);
}
.drop-overlay-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--primary-500, #6366f1);
  font-size: 15px;
  font-weight: 500;
}
.drop-overlay-content p {
  margin: 0;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
.chat-composer {
  position: relative;
  flex-shrink: 0;
  margin-top: 8px;
  border: 2px solid var(--surface-300, #cbd5e1);
  border-radius: 14px;
  background: var(--surface-50, #f8fafc);
  padding: 12px 14px 10px;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.chat-composer:focus-within {
  border-color: var(--primary-400, #818cf8);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.12);
}
.composer-line {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.composer-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.kb-switch {
  display: flex;
  align-items: center;
}
.kb-switch-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--surface-400, #94a3b8);
  white-space: nowrap;
  user-select: none;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.15s ease, color 0.15s ease;
}
.kb-switch-label:hover {
  background: var(--surface-100, #f1f5f9);
  color: var(--surface-600, #475569);
}
.kb-mode-tag {
  font-size: 11px !important;
  padding: 0 6px !important;
  height: 20px !important;
  line-height: 18px !important;
  border-radius: 4px !important;
  border: 1px solid var(--surface-200, #e2e8f0) !important;
  background: #fff !important;
  color: var(--surface-500, #64748b) !important;
  font-weight: 500;
}
.kb-switch .el-radio-group {
  gap: 0;
}
.img-switch {
  display: flex;
  align-items: center;
  margin-left: 4px;
}
.img-switch .el-switch {
  --el-switch-off-color: var(--surface-300, #cbd5e1);
}
.img-switch .el-switch .el-switch__label.is-active {
  color: var(--primary-500, #6366f1);
  font-weight: 600;
}
.img-switch .el-switch .el-switch__label--right {
  color: var(--surface-500, #64748b);
  font-weight: 500;
}
.stop-button {
  --el-button-text-color: #1e293b;
  --el-button-bg-color: #e2e8f0;
  --el-button-border-color: #cbd5e1;
  --el-button-hover-text-color: #0f172a;
  --el-button-hover-bg-color: #cbd5e1;
  --el-button-hover-border-color: #94a3b8;
  --el-button-active-text-color: #0f172a;
  --el-button-active-bg-color: #cbd5e1;
  --el-button-active-border-color: #94a3b8;
  animation: stopPulse 1.5s ease-in-out infinite;
  color: #1e293b !important;
  font-weight: 600;
}
@keyframes stopPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.75; }
}

/* ---- Tutor textarea ---- */
.tutor-textarea {
  --el-input-border-color: var(--surface-200, #e2e8f0);
  --el-input-hover-border-color: var(--primary-300, #c7d2fe);
  --el-input-focus-border-color: var(--primary-500, #6366f1);
  transition: border-color 0.2s ease;
}
.tutor-textarea :deep(.el-textarea__inner) {
  min-height: 48px;
  max-height: 200px;
  overflow-y: auto;
  padding: 12px 16px;
  line-height: 1.6;
  resize: none;
  scrollbar-width: thin;
  scrollbar-color: var(--surface-300, #cbd5e1) transparent;
  transition: box-shadow 0.2s ease;
}
.tutor-textarea :deep(.el-textarea__inner::-webkit-scrollbar) {
  width: 5px;
}
.tutor-textarea :deep(.el-textarea__inner::-webkit-scrollbar-thumb) {
  background: var(--surface-300, #cbd5e1);
  border-radius: 4px;
}

/* ---- Edit state ---- */
.chat-bubble.editing {
  background: #eff6ff;
  display: block !important;
  width: 100% !important;
  max-width: 100% !important;
  box-shadow: 0 0 0 2px var(--primary-400, #818cf8);
}
.user-bubble-container.is-editing {
  display: block;
  width: 100%;
}
.edit-inline-textarea {
  width: 100%;
  min-height: 44px;
  border: none;
  outline: none;
  background: transparent;
  padding: 0;
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
  color: var(--surface-800, #1e293b);
  resize: none;
  font-family: inherit;
  overflow: hidden;
  box-sizing: border-box;
}
.edit-inline-textarea::placeholder {
  color: var(--surface-400, #94a3b8);
}
.chat-bubble.editing .edit-inline-textarea {
  max-height: 6em;
  overflow: hidden auto;
  scrollbar-width: thin;
  scrollbar-color: var(--surface-300, #cbd5e1) transparent;
}
.chat-bubble.editing .edit-inline-textarea::-webkit-scrollbar {
  width: 5px;
}
.chat-bubble.editing .edit-inline-textarea::-webkit-scrollbar-thumb {
  background: var(--surface-300, #cbd5e1);
  border-radius: 4px;
}

/* ---- Edit float actions ---- */
.edit-float-actions {
  position: absolute;
  bottom: 0;
  right: 0;
  transform: translateY(calc(100% + 4px));
  display: flex;
  gap: 6px;
  z-index: 5;
}
.edit-cancel-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid var(--surface-200, #e2e8f0);
  background: #fff;
  color: var(--surface-600, #475569);
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s ease;
  line-height: 1.4;
  white-space: nowrap;
}
.edit-cancel-btn:hover {
  background: var(--surface-50, #f8fafc);
  border-color: var(--surface-300, #cbd5e1);
}
.edit-submit-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 6px 14px;
  border-radius: 8px;
  border: none;
  background: linear-gradient(135deg, var(--primary-500, #6366f1), var(--primary-600, #4f46e5));
  color: #fff;
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s ease;
  line-height: 1.4;
  white-space: nowrap;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.25);
}
.edit-submit-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.35);
}

/* ---- Assistant message ---- */
.assistant-msg-display {
  position: relative;
}
.assistant-msg-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
  margin-top: 8px;
}
.assistant-msg-actions .el-button {
  color: var(--surface-400, #94a3b8);
  transition: all 0.2s ease;
}
.assistant-msg-actions .el-button:hover {
  color: var(--surface-600, #475569);
}
.assistant-msg-actions .el-button.is-disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.regenerating-hint {
  padding: 12px 16px;
  color: var(--surface-400, #94a3b8);
  font-size: 14px;
  font-style: italic;
  animation: pulseHint 1.2s ease-in-out infinite;
}

/* ---- Generating state ---- */
.assistant-msg-generating {
  position: relative;
}
.generating-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  padding: 6px 0;
}
.loading-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2.5px solid var(--surface-200, #e2e8f0);
  border-top-color: var(--primary-500, #6366f1);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  flex-shrink: 0;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.generating-text {
  font-size: 14px;
  color: var(--surface-500, #64748b);
  font-weight: 500;
}

/* ---- Stopped state ---- */
.assistant-msg-stopped {
  position: relative;
}
.stopped-header {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}
.stopped-tag {
  font-size: 13px;
  border-radius: 4px;
}

/* ---- Stop gen button ---- */
.stop-gen-btn {
  --el-button-text-color: #1e293b;
  --el-button-bg-color: #e2e8f0;
  --el-button-border-color: #cbd5e1;
  --el-button-hover-text-color: #0f172a;
  --el-button-hover-bg-color: #cbd5e1;
  --el-button-hover-border-color: #94a3b8;
  --el-button-active-text-color: #0f172a;
  --el-button-active-bg-color: #cbd5e1;
  --el-button-active-border-color: #94a3b8;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border-radius: 6px;
  font-weight: 500;
  color: #1e293b !important;
}
.stop-gen-btn .el-icon {
  font-size: 14px;
}

/* ---- Continue button ---- */
.continue-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 18px;
  border-radius: 9999px;
  font-weight: 400;
  font-size: 14px;
  background: #fff;
  border: 1px solid var(--surface-200, #e2e8f0);
  color: var(--surface-700, #334155);
  transition: all 0.2s ease;
}
.continue-btn:hover {
  background: var(--primary-50, #eef2ff);
  border-color: var(--primary-300, #c7d2fe);
  color: var(--primary-600, #4f46e5);
}
.continue-btn.is-disabled,
.continue-btn:disabled {
  background: #fafafa;
  border-color: #f0f0f0;
  color: #ccc;
  cursor: not-allowed;
}
.continue-btn .el-icon {
  font-size: 15px;
  color: var(--surface-500, #64748b);
}
.continue-btn:hover .el-icon {
  color: var(--primary-500, #6366f1);
}

@keyframes pulseHint {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

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
  white-space: nowrap;
  animation: timer-pulse 2s ease-in-out infinite;
}

@keyframes timer-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

/* ---- 输入区域 ---- */
.tutor-input-wrapper {
  position: relative;
  width: 100%;
}
</style>

<style>
/* 知识库下拉菜单（非 scoped：popover 内容 teleport 到 body） */
.kb-popover {
  padding: 4px !important;
  border-radius: 10px !important;
  min-width: 100px;
}
.kb-dropdown {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.kb-dropdown-item {
  padding: 8px 12px;
  font-size: 13px;
  color: var(--surface-700, #334155);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
  user-select: none;
  line-height: 1.4;
}
.kb-dropdown-item:hover {
  background: var(--surface-100, #f1f5f9);
  color: var(--primary-600, #4f46e5);
}
.kb-dropdown-item.active {
  background: var(--primary-50, #eef2ff);
  color: var(--primary-600, #4f46e5);
  font-weight: 600;
}
</style>
