<template>
  <section class="knowledge-page">
    <!-- Enhanced Header -->
    <div class="knowledge-header">
      <div class="knowledge-header-left">
        <div class="knowledge-header-icon">
          <el-icon :size="28"><Files /></el-icon>
        </div>
        <div>
          <h2 class="knowledge-page-title">课程知识库与 RAG 管理</h2>
          <p class="knowledge-desc">上传教材、讲义与课程资料，构建向量索引，为智能辅导和资源生成提供检索依据</p>
        </div>
      </div>
      <div class="knowledge-header-right">
        <div class="knowledge-header-tags">
          <el-tag class="header-badge badge-rag" effect="plain" round>RAG检索</el-tag>
          <el-tag class="header-badge badge-index" effect="plain" round>混合检索</el-tag>
          <el-tag class="header-badge badge-source" effect="plain" round>内容溯源</el-tag>
        </div>
        <div class="knowledge-header-actions">
          <el-button
            type="primary"
            :icon="Download"
            :loading="courseImporting"
            @click="importBuiltinCourse"
          >
            导入内置课程
          </el-button>
          <el-tooltip content="刷新课程和文档状态" placement="bottom">
            <el-button
              circle
              :icon="Refresh"
              :loading="refreshing"
              aria-label="刷新课程和文档状态"
              @click="handleRefresh"
            />
          </el-tooltip>
        </div>
      </div>
    </div>

    <!-- RAG Flow Card -->
    <div class="rag-flow-card">
      <div class="rag-flow-header">
        <el-icon :size="16"><Connection /></el-icon>
        <span>RAG 检索增强生成流程</span>
      </div>
      <div class="rag-flow-steps">
        <div v-for="(step, i) in ragFlowSteps" :key="step.title" class="rag-flow-step">
          <div class="rag-flow-step-icon" :style="{ background: step.bg, color: step.color }">
            <el-icon :size="20"><component :is="step.icon" /></el-icon>
          </div>
          <div class="rag-flow-step-body">
            <strong>{{ step.title }}</strong>
            <span>{{ step.desc }}</span>
          </div>
          <div v-if="i < ragFlowSteps.length - 1" class="rag-flow-arrow">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
          </div>
        </div>
      </div>
    </div>

    <!-- Statistics Cards -->
    <div class="knowledge-stats">
      <div v-for="stat in knowledgeStats" :key="stat.label" class="knowledge-stat-card" :style="{ borderTop: `3px solid ${stat.color}` }">
        <div class="knowledge-stat-icon" :style="{ background: stat.bg, color: stat.color }">
          <el-icon :size="20"><component :is="stat.icon" /></el-icon>
        </div>
        <div class="knowledge-stat-body">
          <span class="knowledge-stat-value">{{ stat.value }}</span>
          <span class="knowledge-stat-label">{{ stat.label }}</span>
        </div>
      </div>
    </div>

    <!-- Course structure -->
    <section class="course-overview" aria-labelledby="course-overview-title">
      <div class="course-overview-header">
        <div>
          <h3 id="course-overview-title">课程结构</h3>
          <p>导入报告直接来自 PDF 解析结果，不补写缺失章节。</p>
        </div>
        <span>{{ courses.length }} 门课程</span>
      </div>
      <div v-if="courses.length" class="course-list">
        <article v-for="course in courses" :key="course.id" class="course-row">
          <div class="course-main">
            <div class="course-title-line">
              <strong>{{ course.title }}</strong>
              <el-tag size="small" :type="course.status === 'ready' ? 'success' : 'warning'" effect="plain">
                {{ course.status === 'ready' ? '可用' : '草稿' }}
              </el-tag>
              <span>{{ course.code }}</span>
            </div>
            <div class="course-coverage-line">
              <el-progress
                :percentage="courseCoveragePercent(course)"
                :stroke-width="8"
                :status="courseCoveragePercent(course) === 100 ? 'success' : 'warning'"
              />
              <span>正文章节 {{ importedChapterCount(course) }}/{{ expectedChapterCount(course) }}</span>
            </div>
            <p v-if="missingChapterSummary(course)" class="course-missing">
              尚缺正文：{{ missingChapterSummary(course) }}
            </p>
            <p v-else class="course-complete">已识别目录中的全部章节正文</p>
          </div>
          <div class="course-metrics">
            <span>已建章节<strong>{{ course.chapter_count || 0 }}</strong></span>
            <span>来源<strong>{{ course.source_coverage?.source_filename || '暂无' }}</strong></span>
          </div>
        </article>
      </div>
      <el-empty v-else description="尚未导入结构化课程" :image-size="48" />
    </section>

    <!-- Upload Card -->
    <div class="knowledge-upload-card">
      <div class="upload-card-header">
        <div class="upload-card-title">
          <el-icon :size="18"><Upload /></el-icon>
          <span>上传课程资料</span>
        </div>
        <el-segmented v-model="knowledgeUploadMode" :options="knowledgeUploadOptions" />
      </div>

      <el-form label-position="top">
        <el-form-item label="文档标题（可选）">
          <el-input v-model="documentForm.title" placeholder="不填则文本材料使用默认标题，文件材料使用文件名" clearable />
        </el-form-item>
        <!-- <div class="upload-form-row">
          <el-form-item label="所属章节（可选）">
            <el-input v-model="documentForm.chapter" placeholder="如：第三章" clearable />
          </el-form-item>
          <el-form-item label="知识点标签（可选）">
            <el-input v-model="documentForm.tags" placeholder="用逗号分隔，如：线性回归,梯度下降" clearable />
          </el-form-item>
          <el-form-item label="难度等级（可选）">
            <el-select v-model="documentForm.difficulty" placeholder="选择难度" clearable style="width: 100%">
              <el-option label="入门" value="入门" />
              <el-option label="中级" value="中级" />
              <el-option label="进阶" value="进阶" />
            </el-select>
          </el-form-item>
        </div> -->
      </el-form>

      <!-- Text Upload -->
      <div v-if="knowledgeUploadMode === 'text'" class="text-upload-area">
        <el-form label-position="top">
          <el-form-item label="文档内容">
            <el-input v-model="documentForm.content" placeholder="请输入文本内容，支持 Markdown 格式..." class="knowledge-textarea" type="textarea" resize="none" :autosize="{ minRows: 1, maxRows: 8 }" />
          </el-form-item>
        </el-form>
        <div class="text-upload-footer">
          <span class="text-length-counter">{{ documentForm.content.length }} 字</span>
          <el-button type="primary" :icon="Upload" :loading="loading" @click="uploadDocument">
            上传文本材料
          </el-button>
        </div>
        <div v-if="loading" class="upload-progress-bar">
          <el-icon class="is-loading" :size="18"><Loading /></el-icon>
          <span class="upload-phase-text">{{ uploadPhaseText }}</span>
        </div>
      </div>

      <!-- File Upload -->
      <div v-if="knowledgeUploadMode === 'file'" class="file-upload-panel">
        <!-- 未选择文件时显示拖拽区 -->
        <el-upload
          v-if="!knowledgeFile"
          action="#"
          drag
          :auto-upload="false"
          :limit="1"
          :on-change="handleKnowledgeFileChange"
          :on-remove="clearKnowledgeFile"
          accept=".txt,.md,.markdown,.csv,.json,.pdf,.docx"
          class="knowledge-file-uploader"
        >
          <el-icon class="el-icon--upload" :size="40"><Upload /></el-icon>
          <div class="el-upload__text">拖拽文件到这里，或 <em>点击选择文件</em></div>
          <template #tip>
            <div class="el-upload__tip">支持 TXT、Markdown、CSV、JSON、PDF、DOCX 格式，单文件最大 100MB</div>
          </template>
        </el-upload>

        <!-- 已选择文件时显示卡片 -->
        <div v-else class="file-card">
          <div class="file-card-icon">
            <el-icon :size="36"><Files /></el-icon>
          </div>
          <div class="file-card-info">
            <span class="file-card-name">{{ knowledgeFile.name }}</span>
            <span class="file-card-size">{{ formatFileSize(knowledgeFile.size) }}</span>
          </div>
          <div class="file-card-actions">
            <el-button class="file-card-remove" circle :icon="Close" size="small" @click="clearKnowledgeFile" />
            <el-button type="primary" :icon="Upload" :loading="loading" @click="uploadKnowledgeFile">上传</el-button>
          </div>
        </div>
        <div v-if="loading" class="upload-progress-bar">
          <el-progress
            v-if="uploadPhase === 'upload'"
            :percentage="uploadProgress"
            :striped="uploadProgress < 100"
            :stroke-width="10"
          />
          <el-icon v-else class="is-loading" :size="18"><Loading /></el-icon>
          <span class="upload-phase-text">{{ uploadPhaseText }}</span>
        </div>
      </div>
    </div>

    <!-- Document Table -->
    <div class="knowledge-table-wrap">
      <div class="table-header-row">
        <span class="table-header-title">已入库文档（{{ documents.length }}）</span>
        <el-button size="small" :icon="Search" @click="searchDialogVisible = true">检索测试</el-button>
      </div>
      <el-table :data="documents" style="width: 100%" stripe header-row-class-name="knowledge-table-header">
        <el-table-column label="文档名称" min-width="200">
          <template #default="{ row }">
            <div class="doc-title-cell">
              <el-icon :size="16"><Files /></el-icon>
              <span>{{ row.title }}</span>
              <el-tag v-if="row.is_builtin" size="small" type="info" effect="plain" round>内置</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="110" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="docTypeTagType(row.doc_type)" effect="light" round>
              {{ row.doc_type || '文本' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="解析结果" min-width="150">
          <template #default="{ row }">
            <span class="doc-parse-result">
              {{ row.page_count || 1 }} 页 · {{ row.chunk_count || 0 }} 个分块
            </span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            <span class="doc-time">{{ formatDateTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="130" align="center">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.processing_status === 'indexed' ? 'success' : 'warning'"
              effect="light"
              round
            >
              {{ row.processing_status === 'indexed' ? '向量已索引' : '可关键词检索' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="210" align="center" header-align="center">
          <template #default="{ row }">
            <div class="table-actions">
              <el-tooltip content="重命名" placement="top">
                <button class="table-action-btn action-rename" :disabled="row.is_builtin" @click="renameKnowledgeDocument(row)">
                  <el-icon :size="15"><EditPen /></el-icon>
                </button>
              </el-tooltip>
              <span class="action-divider"></span>
              <el-tooltip content="重新索引" placement="top">
                <button class="table-action-btn action-reindex" :disabled="row.is_builtin" @click="reindexDocument(row)">
                  <el-icon :size="15"><Refresh /></el-icon>
                </button>
              </el-tooltip>
              <span class="action-divider"></span>
              <el-tooltip content="删除" placement="top">
                <button class="table-action-btn action-delete" :disabled="row.is_builtin" @click="deleteKnowledgeDocument(row)">
                  <el-icon :size="15"><Delete /></el-icon>
                </button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!documents.length" class="table-empty">
        <div class="table-empty-icon">
          <el-icon :size="36"><Files /></el-icon>
        </div>
        <h3>暂无文档</h3>
        <p>上传文本或文件材料，构建你的课程知识库</p>
      </div>
    </div>

    
  </section>

  <!-- 检索测试对话框 -->
  <el-dialog v-model="searchDialogVisible" title="检索测试" width="600px" :close-on-click-modal="false">
    <div class="search-dialog-body">
      <el-input
        v-model="searchQuery"
        placeholder="输入测试查询语句，查看知识库检索效果..."
        clearable
        @keyup.enter="testRagSearch"
      >
        <template #append>
          <el-button :loading="searchLoading" @click="testRagSearch">检索</el-button>
        </template>
      </el-input>
      <div v-if="searchResults.length" class="search-dialog-results">
        <div v-for="(r, i) in searchResults" :key="i" class="search-dialog-result-item">
          <div class="search-result-header">
            <el-tag size="small" :type="similarityType(r.similarity)" round>{{ r.similarity }}</el-tag>
            <span class="search-result-source">{{ r.source }}</span>
          </div>
          <p class="search-result-content">{{ cleanDisplayText(r.content) }}</p>
        </div>
      </div>
      <div v-if="searchTried && !searchResults.length" class="search-dialog-empty">
        <el-empty description="未检索到相关内容，请尝试其他查询" :image-size="40" />
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close, Connection, Delete, DocumentCopy, Download, EditPen, Files, Loading, Refresh, Search, Upload } from '@element-plus/icons-vue'
import { api } from '../api/learning'
import { getErrorMessage, formatDateTime } from '../composables/useUtils'

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

const documentForm = reactive({ title: '', content: '', chapter: '', tags: '', difficulty: '' })
const loading = ref(false)
const uploadProgress = ref(0)
const uploadPhase = ref<'upload' | 'process' | ''>('')
const deleting = ref(false)
const refreshing = ref(false)
const courseImporting = ref(false)
const knowledgeUploadMode = ref<'text' | 'file'>('text')
const knowledgeUploadOptions = [
  { label: '上传文本知识', value: 'text' },
  { label: '上传文件知识', value: 'file' },
]
const knowledgeFile = ref<File | null>(null)
const documents = ref<any[]>([])
const courses = ref<any[]>([])

// RAG flow steps
const ragFlowSteps = [
  { title: '上传课程资料', desc: '上传教材、讲义与实验指导', icon: Upload, bg: '#eff6ff', color: '#3b82f6' },
  { title: '文档切片与清洗', desc: '智能分段，去除噪声与冗余', icon: DocumentCopy, bg: '#ecfeff', color: '#0891b2' },
  { title: '建立检索索引', desc: '向量可用时建索引，否则保留关键词检索', icon: Connection, bg: '#fdf4ff', color: '#9333ea' },
  { title: '检索相关片段', desc: '查询向量索引并返回相关课程内容', icon: Search, bg: '#f0fdf4', color: '#059669' },
]

// Stats
const knowledgeStats = computed(() => {
  const docs = documents.value
  const now = new Date()
  const recentDate = docs.length > 0
    ? docs.reduce((latest: Date, d: any) => {
        const t = new Date(d.created_at)
        return t > latest ? t : latest
      }, new Date(0))
    : null

  const uploadedCount = docs.filter(d => !d.is_builtin).length
  return [
    { label: '文档总数', value: docs.length, icon: Files, color: '#3b82f6', bg: '#eff6ff' },
    { label: '用户上传', value: uploadedCount, icon: Upload, color: '#0891b2', bg: '#ecfeff' },
    { label: '最近更新', value: recentDate ? formatShortDate(recentDate) : '暂无', icon: Refresh, color: '#9333ea', bg: '#fdf4ff' },
  ]
})

const uploadPhaseText = computed(() => {
  if (uploadPhase.value === 'upload') return uploadProgress.value < 100 ? `上传中 ${uploadProgress.value}%` : '文件已发送，等待后端解析...'
  if (uploadPhase.value === 'process') return '正在解析文档并写入知识库...'
  return ''
})

// RAG Search Test
const searchDialogVisible = ref(false)
const searchQuery = ref('')
const searchLoading = ref(false)
const searchResults = ref<Array<{ similarity: string; source: string; content: string }>>([])
const searchTried = ref(false)

function formatShortDate(date: Date): string {
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  if (diff < 86400000) return '今天'
  if (diff < 172800000) return '昨天'
  return `${date.getMonth() + 1}月${date.getDate()}号`
}

function docTypeTagType(docType: string): string {
  const map: Record<string, string> = { 'PDF': 'danger', 'DOCX': 'warning', 'Markdown': 'info', 'CSV': '', 'JSON': '', 'TXT': 'success', '文本': 'primary' }
  return map[docType] || ''
}

function expectedChapterCount(course: any): number {
  return course.source_coverage?.expected_chapters?.length || course.chapter_count || 0
}

function importedChapterCount(course: any): number {
  return course.source_coverage?.imported_chapters?.length || course.chapter_count || 0
}

function courseCoveragePercent(course: any): number {
  return Math.round(Number(course.source_coverage?.chapter_coverage || 0) * 100)
}

function missingChapterSummary(course: any): string {
  const missing = course.source_coverage?.missing_chapters || []
  if (!missing.length) return ''
  const visible = missing.slice(0, 4).map((item: any) => `第${item.order}章 ${item.title}`)
  return `${visible.join('、')}${missing.length > visible.length ? ` 等 ${missing.length} 章` : ''}`
}

function formatSearchSource(source: any): string {
  const parts: string[] = []
  if (source.course_title) parts.push(`课程：${source.course_title}`)
  if (source.chapter) parts.push(`章节：${source.chapter}`)
  if (source.section) parts.push(`小节：${source.section}`)
  if (source.page_start) {
    const page = source.page_end && source.page_end !== source.page_start
      ? `${source.page_start}-${source.page_end}`
      : source.page_start
    parts.push(`物理页：${page}`)
  }
  parts.push(`文档：${source.source_filename || source.title || '未知来源'}`)
  return parts.join(' · ')
}

function similarityScoreLabel(score: number): string {
  if (score >= 0.6) return '高相似度'
  if (score >= 0.3) return '中相似度'
  return '低相似度'
}

function similarityType(similarity: string) {
  if (similarity.includes('高')) return 'success'
  if (similarity.includes('中')) return 'warning'
  return 'info'
}

// 前端兜底：过滤显示文本中的乱码字符
function cleanDisplayText(text: string): string {
  if (!text) return ''
  // Unicode 替换字符 � 表示为
  return text.replace(/�/g, '').replace(/�+/g, '')
}

async function testRagSearch() {
  if (!searchQuery.value.trim()) {
    ElMessage.warning('请输入查询内容')
    return
  }
  searchLoading.value = true
  searchTried.value = true
  try {
    const { data } = await api.queryKnowledge(searchQuery.value)
    const sources = data.sources || []
    searchResults.value = sources.map((s: any) => ({
      similarity: similarityScoreLabel(s.score),
      source: formatSearchSource(s),
      content: s.content || '',
    }))
  } catch (e: any) {
    ElMessage.error(e?.message || '检索失败')
    searchResults.value = []
  } finally {
    searchLoading.value = false
  }
}

// ===== API / Data Loading =====
async function uploadDocument() {
  if (!documentForm.content.trim()) {
    ElMessage.warning('请先填写文档内容')
    return
  }
  if (loading.value) return
  loading.value = true
  uploadProgress.value = 0
  uploadPhase.value = 'process'
  try {
    await api.uploadTextDocument({
      title: documentForm.title,
      content: documentForm.content,
      chapter: documentForm.chapter,
      tags: documentForm.tags,
      difficulty: documentForm.difficulty,
    })
    documentForm.content = ''
    documentForm.title = ''
    documentForm.chapter = ''
    documentForm.tags = ''
    documentForm.difficulty = ''
    await loadDocuments()
    ElMessage.success('文档已上传')
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    loading.value = false
    uploadProgress.value = 0
    uploadPhase.value = ''
  }
}

function handleKnowledgeFileChange(uploadFile: any) {
  knowledgeFile.value = uploadFile.raw || null
}

function clearKnowledgeFile() {
  knowledgeFile.value = null
}

async function uploadKnowledgeFile() {
  if (!knowledgeFile.value) {
    ElMessage.warning('请先选择文件')
    return
  }
  if (loading.value) return

  const MAX_FILE_SIZE = 100 * 1024 * 1024
  if (knowledgeFile.value.size > MAX_FILE_SIZE) {
    const sizeMB = (knowledgeFile.value.size / (1024 * 1024)).toFixed(1)
    ElMessage.warning(`文件过大（${sizeMB}MB），当前限制为 100MB`)
    return
  }

  loading.value = true
  uploadProgress.value = 0
  uploadPhase.value = 'upload'
  try {
    await api.uploadFileDocument(knowledgeFile.value as File, documentForm.title.trim(), (pct) => {
      uploadProgress.value = pct
      if (pct >= 100) uploadPhase.value = 'process'
    })
    knowledgeFile.value = null
    documentForm.title = ''
    documentForm.chapter = ''
    documentForm.tags = ''
    documentForm.difficulty = ''
    await loadDocuments()
    ElMessage.success('文件材料已上传')
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    loading.value = false
    uploadProgress.value = 0
    uploadPhase.value = ''
  }
}

async function renameKnowledgeDocument(row: any) {
  if (row.is_builtin) {
    ElMessage.warning('内置知识库文档不允许修改名称')
    return
  }
  try {
    const result = await ElMessageBox.prompt('请输入新的文档名称', '重命名文档', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: row.title,
      inputValidator: (value) => Boolean(value && value.trim()),
    })
    if (loading.value) return
    loading.value = true
    try {
      await api.renameDocument(row.id, result.value.trim())
      await loadDocuments()
      ElMessage.success('文档名称已更新')
    } catch (error) {
      ElMessage.error(getErrorMessage(error))
    } finally {
      loading.value = false
    }
  } catch {
    // 用户取消时不提示错误。
  }
}

async function deleteKnowledgeDocument(row: any) {
  if (row.is_builtin) {
    ElMessage.warning('内置知识库文档不允许删除')
    return
  }
  try {
    await ElMessageBox.confirm(`确定删除"${row.title}"吗？删除后智能辅导将不再检索该文档。`, '删除文档', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
    if (deleting.value) return
    deleting.value = true
    // 先在本地移除文档，再删除后端数据
    const deletedIndex = documents.value.findIndex(d => d.id === row.id)
    const deletedDoc = deletedIndex !== -1 ? documents.value.splice(deletedIndex, 1)[0] : null
    try {
      await api.deleteDocument(row.id)
      ElMessage.success('文档已删除')
    } catch (error) {
      // 删除失败，恢复文档
      if (deletedDoc && deletedIndex !== -1) {
        documents.value.splice(deletedIndex, 0, deletedDoc)
      } else if (deletedDoc) {
        documents.value.push(deletedDoc)
      }
      ElMessage.error(getErrorMessage(error))
    } finally {
      deleting.value = false
    }
  } catch {
    // 用户取消时不提示错误。
  }
}

async function reindexDocument(row: any) {
  try {
    const { data } = await api.reindexDocument(row.id)
    ElMessage.success(data.message || '重新索引完成')
    await loadDocuments()
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}

async function loadDocuments() {
  try {
    const { data } = await api.listDocuments()
    documents.value = data.documents || []
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}

async function loadCourses() {
  try {
    const { data } = await api.listCourses()
    courses.value = data.courses || []
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  }
}

async function importBuiltinCourse() {
  if (courseImporting.value) return
  courseImporting.value = true
  try {
    const { data } = await api.importBuiltinCourse()
    const report = data.import_report || {}
    const imported = report.imported_chapters?.length || 0
    const expected = report.expected_chapters?.length || 0
    ElMessage.success(
      data.idempotent
        ? '课程已导入，无需重复写入'
        : `课程已入库：识别 ${imported}/${expected || imported} 个正文章节`
    )
    await Promise.all([loadCourses(), loadDocuments()])
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    courseImporting.value = false
  }
}

async function handleRefresh() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    await Promise.all([loadCourses(), loadDocuments()])
  } finally {
    refreshing.value = false
  }
}

onMounted(() => {
  api.logTaskAction('visit_knowledge').catch(() => {})
  Promise.all([loadCourses(), loadDocuments()])
})
</script>

<style scoped>
/* ======= Page ======= */
.knowledge-page {
  max-width: 1280px;
  margin: 0 auto;
  animation: knowledgeFadeIn 0.4s ease-out;
}

@keyframes knowledgeFadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ======= Header ======= */
.knowledge-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  margin-bottom: 16px;
  border-radius: 16px;
  position: relative;
  overflow: hidden;
  background: linear-gradient(135deg, rgba(255,255,255,0.96), rgba(248,250,252,0.92));
  border: 1px solid rgba(226, 232, 240, 0.9);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
}

.knowledge-header::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    linear-gradient(90deg, rgba(99, 102, 241, 0.08), transparent 38%),
    linear-gradient(135deg, transparent 0 72%, rgba(16, 185, 129, 0.08) 72% 100%);
  pointer-events: none;
}

.knowledge-header-left {
  display: flex;
  align-items: center;
  gap: 16px;
  position: relative;
  z-index: 1;
}

.knowledge-header-icon {
  width: 46px;
  height: 46px;
  border-radius: 12px;
  background: linear-gradient(135deg, #3b82f6, #0891b2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  box-shadow: 0 8px 18px rgba(79, 70, 229, 0.22);
  flex-shrink: 0;
}

.knowledge-page-title {
  font-size: 21px;
  font-weight: 800;
  color: var(--surface-900, #0f172a);
  margin: 0 0 4px;
  letter-spacing: 0;
}

.knowledge-desc {
  font-size: 14px;
  color: var(--surface-500, #64748b);
  margin: 0;
  line-height: 1.5;
  max-width: 500px;
}

.knowledge-header-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12px;
  position: relative;
  z-index: 1;
  flex-shrink: 0;
}

.knowledge-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.knowledge-header-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.header-badge {
  border: 1px solid transparent !important;
  font-weight: 600;
  font-size: 12px;
  padding: 0 10px;
  height: 22px;
  line-height: 22px;
  letter-spacing: 0;
}
.header-badge.badge-rag { background: #eff6ff; color: #3b82f6; border-color: #bfdbfe !important; }
.header-badge.badge-index { background: #ecfeff; color: #0891b2; border-color: #cffafe !important; }
.header-badge.badge-source { background: #ecfdf5; color: #059669; border-color: #bbf7d0 !important; }
.header-badge.badge-safe { background: #fff7ed; color: #ea580c; border-color: #fed7aa !important; }

.knowledge-header-right .el-button {
  background: #ffffff;
  border: 1px solid var(--surface-200, #e2e8f0);
  color: var(--surface-700, #334155);
  border-radius: var(--radius-md, 8px);
  height: 32px;
  padding: 0 14px;
  font-weight: 500;
  transition: all 0.2s ease;
}
.knowledge-header-right .el-button:hover {
  color: var(--primary-600, #4f46e5);
  border-color: var(--primary-200, #c7d2fe);
  background: var(--primary-50, #eef2ff);
}

.knowledge-header-right .el-button.is-refreshing :deep(.el-icon) {
  animation: knowledgeRefreshSpin 0.6s linear infinite;
}

@keyframes knowledgeRefreshSpin {
  to { transform: rotate(360deg); }
}

/* ======= RAG Flow Card ======= */
.rag-flow-card {
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 14px;
  padding: 16px 20px;
  margin-bottom: 16px;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.05);
}

.rag-flow-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-700, #334155);
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--surface-100, #f1f5f9);
}

.rag-flow-steps {
  display: flex;
  align-items: flex-start;
  gap: 0;
}

.rag-flow-step {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.rag-flow-step-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.rag-flow-step-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.rag-flow-step-body strong {
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-700, #334155);
  white-space: nowrap;
}

.rag-flow-step-body span {
  font-size: 12px;
  color: var(--surface-400, #94a3b8);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rag-flow-arrow {
  color: var(--surface-300, #cbd5e1);
  display: flex;
  align-items: center;
  flex-shrink: 0;
  padding: 0 4px;
}

/* ======= Stats ======= */
.knowledge-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.knowledge-stat-card {
  background: #ffffff;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 12px;
  padding: 16px 18px;
  display: flex;
  align-items: center;
  gap: 14px;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.05);
  transition: all 0.3s ease;
  cursor: default;
}

.knowledge-stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.08);
}

.knowledge-stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.knowledge-stat-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.knowledge-stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--surface-900, #0f172a);
  line-height: 1.2;
}

.knowledge-stat-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--surface-500, #64748b);
}

/* ======= Course structure ======= */
.course-overview {
  margin-bottom: 16px;
  padding: 16px 20px;
  background: #ffffff;
  border: 1px solid var(--surface-200, #e2e8f0);
  border-radius: 8px;
}

.course-overview-header,
.course-row,
.course-title-line,
.course-coverage-line,
.course-metrics {
  display: flex;
  align-items: center;
}

.course-overview-header {
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--surface-100, #f1f5f9);
}

.course-overview-header h3 {
  margin: 0 0 3px;
  font-size: 15px;
  color: var(--surface-800, #1e293b);
}

.course-overview-header p,
.course-overview-header > span {
  margin: 0;
  font-size: 12px;
  color: var(--surface-500, #64748b);
}

.course-list {
  display: flex;
  flex-direction: column;
}

.course-row {
  justify-content: space-between;
  gap: 24px;
  padding: 15px 0;
}

.course-row + .course-row {
  border-top: 1px solid var(--surface-100, #f1f5f9);
}

.course-main {
  flex: 1;
  min-width: 0;
}

.course-title-line {
  gap: 8px;
  margin-bottom: 10px;
}

.course-title-line strong {
  font-size: 15px;
  color: var(--surface-800, #1e293b);
}

.course-title-line > span {
  font-size: 12px;
  color: var(--surface-400, #94a3b8);
}

.course-coverage-line {
  gap: 12px;
}

.course-coverage-line .el-progress {
  width: min(360px, 55vw);
}

.course-coverage-line > span,
.course-missing,
.course-complete {
  font-size: 12px;
}

.course-coverage-line > span {
  white-space: nowrap;
  color: var(--surface-600, #475569);
}

.course-missing,
.course-complete {
  margin: 7px 0 0;
  line-height: 1.5;
}

.course-missing {
  color: #b45309;
}

.course-complete {
  color: #047857;
}

.course-metrics {
  gap: 18px;
  flex-shrink: 0;
}

.course-metrics span {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 11px;
  color: var(--surface-400, #94a3b8);
}

.course-metrics strong {
  max-width: 180px;
  overflow: hidden;
  color: var(--surface-700, #334155);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ======= Upload Card ======= */
.knowledge-upload-card {
  background: #ffffff;
  border: 1px solid rgba(199, 210, 254, 0.9);
  border-top: 3px solid var(--primary-500, #6366f1);
  border-radius: 14px;
  padding: 16px 22px;
  margin-bottom: 14px;
  box-shadow: 0 10px 24px rgba(79, 70, 229, 0.08);
  transition: box-shadow 0.2s ease;
}

.knowledge-upload-card:hover {
  box-shadow: var(--shadow-md, 0 4px 6px -1px rgba(0,0,0,0.07));
}

.upload-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--surface-100, #f1f5f9);
}

.upload-card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--surface-700, #334155);
}

.upload-form-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}

.upload-form-row .el-form-item {
  margin-bottom: 18px;
}

/* ======= Text Upload ======= */
.text-upload-area {
  margin-top: 4px;
}

.knowledge-textarea :deep(.el-textarea__inner) {
  min-height: 38px !important;
  max-height: 240px;
  resize: none;
  line-height: 1.55;
  font-size: 14px;
  padding: 8px 12px;
  overflow-y: auto;
}

.text-upload-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
}

.text-length-counter {
  font-size: 14px;
  color: var(--surface-400, #94a3b8);
  font-weight: 500;
}

.text-upload-footer .el-button--primary {
  background: linear-gradient(135deg, var(--primary-500, #6366f1), var(--primary-600, #4f46e5));
  border: none;
  border-radius: var(--radius-md, 8px);
  height: 36px;
  padding: 0 20px;
  font-weight: 500;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.3);
  transition: all 0.2s ease;
}

.text-upload-footer .el-button--primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4);
}

/* ======= File Upload ======= */
.file-upload-panel {
  background: var(--surface-50, #f8fafc);
  border: 1px dashed var(--surface-300, #cbd5e1);
  border-radius: var(--radius-lg, 12px);
  padding: 10px 12px;
  transition: all 0.2s ease;
  margin-top: 4px;
}

.file-upload-panel:hover {
  border-color: var(--primary-400, #818cf8);
  background: var(--primary-50, #eef2ff);
}

.file-upload-panel :deep(.el-upload-dragger) {
  border: 2px dashed var(--surface-300, #cbd5e1);
  border-radius: var(--radius-md, 8px);
  transition: all 0.2s ease;
  width: 100%;
  height: 86px !important;
  min-height: 86px;
  padding: 8px 14px !important;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.file-upload-panel :deep(.el-upload-dragger:hover),
.file-upload-panel :deep(.el-upload-dragger.is-dragover) {
  border-color: var(--primary-400, #818cf8);
  background: var(--primary-50, #eef2ff);
}

.file-upload-panel :deep(.el-icon--upload) {
  color: var(--primary-400, #818cf8);
  margin-bottom: 2px;
  font-size: 26px !important;
}

.file-upload-panel :deep(.el-upload__text) {
  font-size: 14px;
  line-height: 1.35;
  color: var(--surface-600, #475569);
}

.file-upload-panel :deep(.el-upload__text em) {
  color: var(--primary-500, #6366f1);
  font-style: normal;
  font-weight: 600;
}

.file-upload-panel :deep(.el-upload__tip) {
  font-size: 12px;
  line-height: 1.35;
  color: var(--surface-400, #94a3b8);
  margin-top: 2px;
}

.file-upload-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--surface-200, #e2e8f0);
}

/* ======= File Card ======= */
.file-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  background: var(--surface-50, #f8fafc);
  border: 1px solid var(--primary-200, #c7d2fe);
  border-radius: var(--radius-lg, 12px);
  margin: 12px 0;
  transition: all 0.2s ease;
}
.file-card:hover {
  border-color: var(--primary-300, #a5b4fc);
  background: #eff6ff;
}
.file-card-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: var(--radius-md, 8px);
  background: linear-gradient(135deg, var(--primary-100, #e0e7ff), var(--primary-50, #eef2ff));
  color: var(--primary-600, #4f46e5);
  flex-shrink: 0;
}
.file-card-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.file-card-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-700, #334155);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-card-size {
  font-size: 12px;
  color: var(--surface-400, #94a3b8);
}
.file-card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.file-card-remove {
  --el-color-primary: var(--surface-300, #cbd5e1) !important;
  --el-color-primary-light-3: var(--surface-200, #e2e8f0) !important;
  color: var(--surface-400, #94a3b8) !important;
  transition: all 0.2s ease;
}
.file-card-remove:hover {
  --el-color-primary: #ef4444 !important;
  --el-color-primary-light-3: #fecaca !important;
  color: #ef4444 !important;
}
.file-card-actions .el-button--primary {
  background: linear-gradient(135deg, var(--primary-500, #6366f1), var(--primary-600, #4f46e5));
  border: none;
  border-radius: var(--radius-md, 8px);
  height: 36px;
  padding: 0 20px;
  font-weight: 500;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.3);
  transition: all 0.2s ease;
}
.file-card-actions .el-button--primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4);
}

.file-upload-footer .el-button--primary {
  background: linear-gradient(135deg, var(--primary-500, #6366f1), var(--primary-600, #4f46e5));
  border: none;
  border-radius: var(--radius-md, 8px);
  height: 36px;
  padding: 0 20px;
  font-weight: 500;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.3);
  transition: all 0.2s ease;
}

.file-upload-footer .el-button--primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4);
}

/* ======= RAG Search Section ======= */
.search-dialog-body {
  min-height: 200px;
}
.search-dialog-body .el-input {
  margin-bottom: 16px;
}
.search-dialog-results {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.search-dialog-result-item {
  padding: 14px 16px;
  background: var(--surface-50, #f8fafc);
  border: 1px solid var(--surface-100, #f1f5f9);
  border-radius: var(--radius-md, 8px);
  transition: all 0.2s ease;
}
.search-dialog-result-item:hover {
  border-color: var(--primary-200, #c7d2fe);
  background: #eff6ff;
}
.search-result-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.search-result-source {
  font-size: 13px;
  font-weight: 500;
  color: var(--primary-600, #4f46e5);
}
.search-result-content {
  font-size: 14px;
  color: var(--surface-600, #475569);
  line-height: 1.6;
  margin: 0;
}
.search-dialog-empty {
  padding: 20px 0;
}

/* ======= Anti-hallucination Card ======= */
.anti-hallucination-card {
  background: linear-gradient(135deg, #eff6ff 0%, #eff6ff 50%, #ffffff 100%);
  border: 1px solid #dbeafe;
  border-radius: var(--radius-xl, 16px);
  padding: 20px 24px;
  margin: 20px 0;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.05));
}

.anti-hall-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--primary-700, #4338ca);
  margin-bottom: 14px;
}

.anti-hall-body {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}

.anti-hall-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.8);
  border-radius: var(--radius-md, 10px);
  border: 1px solid rgba(255, 255, 255, 0.9);
  transition: all 0.2s ease;
}

.anti-hall-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.04);
}

.anti-hall-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.anti-hall-text {
  min-width: 0;
}

.anti-hall-text strong {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-700, #334155);
  margin-bottom: 2px;
}

.anti-hall-text span {
  display: block;
  font-size: 12px;
  color: var(--surface-400, #94a3b8);
  line-height: 1.5;
}

/* ======= Document Table ======= */
.knowledge-table-wrap {
  background: #ffffff;
  border: 1px solid var(--surface-100, #f1f5f9);
  border-radius: var(--radius-xl, 16px);
  overflow: hidden;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.05));
}

.table-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--surface-100, #f1f5f9);
  background: linear-gradient(180deg, #ffffff 0%, #fafbfc 100%);
}

.table-header-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-700, #334155);
}

.doc-title-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.doc-title-cell .el-icon {
  color: var(--primary-500, #6366f1);
  flex-shrink: 0;
}

.doc-title-cell span {
  font-weight: 500;
  color: var(--surface-700, #334155);
}

.doc-time {
  font-size: 14px;
  color: var(--surface-400, #94a3b8);
}

.doc-parse-result {
  font-size: 13px;
  color: var(--surface-500, #64748b);
}

/* ======= Table Actions ======= */
.table-actions {
  display: inline-flex;
  align-items: center;
  background: var(--surface-50, #f8fafc);
  border: 1px solid var(--surface-200, #e2e8f0);
  border-radius: 8px;
  padding: 2px;
  gap: 0;
}

.table-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 28px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  color: var(--surface-400, #94a3b8);
}

.table-action-btn:hover:not(:disabled) {
  transform: scale(1.05);
}

.table-action-btn:disabled {
  cursor: not-allowed;
  opacity: 0.3;
}

.table-action-btn.action-rename:hover:not(:disabled) {
  background: var(--primary-50, #eef2ff);
  color: var(--primary-500, #6366f1);
}

.table-action-btn.action-reindex:hover:not(:disabled) {
  background: #fffbeb;
  color: #d97706;
}

.table-action-btn.action-delete:hover:not(:disabled) {
  background: #fef2f2;
  color: #dc2626;
}

.action-divider {
  width: 1px;
  height: 16px;
  background: var(--surface-200, #e2e8f0);
  flex-shrink: 0;
}

.table-empty {
  text-align: center;
  padding: 60px 20px;
}

.table-empty-icon {
  width: 80px;
  height: 80px;
  margin: 0 auto 16px;
  border-radius: 50%;
  background: linear-gradient(135deg, #eff6ff, #e0f2fe);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary-400, #818cf8);
}

.table-empty h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--surface-600, #475569);
  margin: 0 0 6px;
}

.table-empty p {
  font-size: 14px;
  color: var(--surface-400, #94a3b8);
  margin: 0;
}

/* ======= Element Table Override ======= */
:deep(.knowledge-table-header th) {
  background: var(--surface-50, #f8fafc);
  color: var(--surface-500, #64748b);
  font-weight: 600;
  font-size: 14px;
  border-bottom: 1px solid var(--surface-100, #f1f5f9);
}

:deep(.el-table) {
  border: none;
}

:deep(.el-table__body tr) {
  transition: background 0.2s ease;
}

:deep(.el-table__body tr:hover td) {
  background: var(--primary-50, #eef2ff);
}

:deep(.el-table td) {
  border-bottom: 1px solid var(--surface-50, #f8fafc);
  padding: 14px 0;
}

:deep(.el-table--striped .el-table__body tr.el-table__row--striped td) {
  background: var(--surface-50, #f8fafc);
}

/* ======= Responsive ======= */
@media (max-width: 1100px) {
  .rag-flow-steps {
    flex-wrap: wrap;
    gap: 12px;
  }
  .rag-flow-step {
    flex: 1 1 45%;
  }
  .rag-flow-arrow {
    display: none;
  }
  .anti-hall-body {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 900px) {
  .knowledge-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
    padding: 24px 20px;
  }
  .knowledge-header-right {
    align-items: flex-start;
    width: 100%;
  }
  .knowledge-header-tags {
    justify-content: flex-start;
  }
  .knowledge-header-actions {
    width: 100%;
  }
  .knowledge-stats {
    grid-template-columns: repeat(2, 1fr);
  }
  .course-row {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }
  .course-metrics {
    width: 100%;
  }
  .upload-form-row {
    grid-template-columns: 1fr;
    gap: 0;
  }
  .knowledge-upload-card {
    padding: 20px;
  }
  .upload-card-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  .text-upload-footer {
    flex-direction: column;
    gap: 12px;
    align-items: stretch;
  }
  .file-upload-footer {
    flex-direction: column;
    gap: 12px;
    align-items: stretch;
  }
  .text-upload-footer .el-button,
  .file-upload-footer .el-button {
    width: 100%;
  }
  .rag-flow-steps {
    flex-direction: column;
  }
  .rag-flow-step {
    width: 100%;
  }
}

@media (max-width: 600px) {
  .knowledge-page-title {
    font-size: 18px;
  }
  .knowledge-header-icon {
    width: 44px;
    height: 44px;
  }
  .knowledge-header-left {
    gap: 12px;
  }
  .knowledge-stats {
    grid-template-columns: 1fr;
  }
  .knowledge-stat-card {
    padding: 14px 16px;
  }
  .knowledge-stat-value {
    font-size: 18px;
  }
  .anti-hall-body {
    grid-template-columns: 1fr;
  }
}

.upload-progress-bar {
  margin-top: 14px;
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8px;
}
.upload-progress-bar .el-progress {
  width: 100%;
}
.upload-phase-text {
  font-size: 12px;
  color: var(--surface-400, #94a3b8);
  white-space: nowrap;
}
</style>
