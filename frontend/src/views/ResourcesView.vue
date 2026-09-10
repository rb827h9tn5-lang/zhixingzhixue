<template>
  <section class="resources-page">
    <!-- Dynamic Header per sub-page -->
    <div class="resources-header">
      <div class="resources-header-left">
        <div class="resources-header-icon">
          <el-icon :size="28"><Collection /></el-icon>
        </div>
        <div>
          <h2 class="resources-page-title">{{ currentTypeHeader.title }}</h2>
          <p class="resources-desc">{{ currentTypeHeader.desc }}</p>
        </div>
      </div>
      <div class="resources-header-right">
        <el-tag class="header-badge badge-rag" effect="plain" round>RAG增强</el-tag>
        <el-tag class="header-badge badge-agent" effect="plain" round>AI生成</el-tag>
        <el-tag class="header-badge badge-personal" effect="plain" round>个性化生成</el-tag>
      </div>
    </div>

    <!-- Resource Type Description -->
    <!-- <div class="resources-type-bar" v-if="currentTypeDescription">
      <div class="type-bar-desc">{{ currentTypeDescription }}</div>
    </div> -->

    <!-- 只展示后端真实返回的生成状态。 -->
    <transition name="agent-slide">
      <div v-if="currentStreamingState?.active" class="agent-collab-section">
        <div class="agent-collab-header">
          <el-icon class="is-loading" :size="18"><Loading /></el-icon>
          <span>正在生成资源</span>
        </div>
        <div class="agent-collab-progress">
          <span>{{ currentStreamingState?.progress || '正在准备生成...' }}</span>
          <span v-if="showTiming" class="live-timer">已耗时 {{ formatDuration(liveElapsed) }}</span>
        </div>
      </div>
    </transition>

    <el-alert
      v-if="resourceArtifact?.message"
      :title="resourceArtifact.message"
      type="info"
      :closable="false"
      class="resource-message-alert"
    />

    <!-- ===== Exercise Bank ===== -->
    <div v-if="selectedResourceType === 'exercise_bank'" class="resource-workbench">
      <aside class="resource-history-sidebar">
        <div class="sidebar-header">
          <el-icon :size="18"><Clock /></el-icon>
          <span>练习题库记录</span>
        </div>
        <div class="sidebar-list">
          <div
            v-for="item in exerciseHistoryRecords"
            :key="item.id"
            class="sidebar-item"
            :class="{ active: selectedQuizRecord?.id === item.id }"
            @click="selectQuizHistory(item)"
          >
            <div class="sidebar-item-top">
              <div class="sidebar-title-row">
                <el-icon :size="14" class="sidebar-item-icon"><EditPen /></el-icon>
                <strong class="sidebar-title" :title="quizRecordTitle(item)">{{ quizRecordTitle(item) }}</strong>
              </div>
              <div class="sidebar-actions">
                <el-button :icon="EditPen" size="small" text circle title="重命名记录" @click.stop="renameQuizRecord(item)" />
                <el-button :icon="Delete" size="small" text circle type="danger" title="删除记录" @click.stop="deleteQuizRecord(item)" />
              </div>
            </div>
            <div class="sidebar-meta">
              <el-tag size="small" type="warning" effect="plain" round>练习</el-tag>
              <span class="sidebar-date" :title="formatDateTime(item.created_at)">{{ formatDateTime(item.created_at) }}</span>
              <span v-if="item.answers?.details?.length" class="sidebar-score" :class="item.score >= 60 ? 'score-high' : 'score-low'">{{ scoreText(item.score) }}</span>
              <span v-else class="sidebar-score score-none">未完成</span>
            </div>
          </div>
          <div v-if="exerciseHistoryRecords.length === 0" class="sidebar-empty">
            <el-empty description="暂无练习记录" :image-size="60" />
          </div>
        </div>
      </aside>

      <main class="resource-main-content">
        <div class="content-toolbar">
          <el-input v-model="quizForm.focus" placeholder="填写题目相关知识点" style="max-width: 220px" clearable>
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <div class="count-control">
            <span class="count-label">题数</span>
            <el-input-number v-model="quizForm.count" :min="3" :max="10" size="small" controls-position="right" />
          </div>
          <el-button type="primary" :loading="quizLoading" @click="handleGenerateExerciseBank">生成题目</el-button>
        </div>

        <div v-if="structuredQuiz && !currentStreamingState?.active" class="question-list">
          <div class="quiz-title-bar">
            <h2>{{ structuredQuiz.title }}</h2>
            <span v-if="showTiming && generationDuration" class="resource-timing-badge">生成耗时 {{ formatDuration(generationDuration) }}</span>
          </div>
          <section v-for="question in structuredQuiz.questions" :key="question.id" class="question-card">
            <div class="question-heading">
              <span class="question-number">{{ question.id }}</span>
              <h3>{{ question.prompt }}</h3>
              <el-tag size="small" effect="plain" round>{{ questionTypeLabel(question.type) }}</el-tag>
            </div>
            <div class="question-options">
              <el-checkbox-group v-if="question.type === 'multiple_choice'" v-model="quizAnswers[String(question.id)]" :disabled="Boolean(selectedQuizRecord)">
                <el-checkbox v-for="(option, optionIndex) in question.options" :key="option" :value="optionValue(optionIndex)" class="option-item">
                  {{ optionLabel(optionIndex, option) }}
                </el-checkbox>
              </el-checkbox-group>
              <el-radio-group v-else-if="question.options?.length" v-model="quizAnswers[String(question.id)]" :disabled="Boolean(selectedQuizRecord)">
                <el-radio v-for="(option, optionIndex) in question.options" :key="option" :value="optionValue(optionIndex)" class="option-item">
                  {{ optionLabel(optionIndex, option) }}
                </el-radio>
              </el-radio-group>
              <el-input v-else v-model="quizAnswers[String(question.id)]" type="textarea" :rows="question.type === 'fill_blank' ? 2 : 3" placeholder="填写你的答案" :disabled="Boolean(selectedQuizRecord)" class="fill-input" />
            </div>
            <el-collapse class="hint-collapse">
              <el-collapse-item title="💡 提示" :name="`hint-${question.id}`">
                {{ question.hint }}
              </el-collapse-item>
            </el-collapse>
            <div v-if="quizResult" class="answer-explain">
              <div class="answer-row">
                <span class="answer-label">作答结果</span>
                <el-tag size="small" :type="answerStatusType(getQuizDetail(question.id)?.status)" effect="dark" round>
                  {{ answerStatusLabel(getQuizDetail(question.id)?.status) }}
                </el-tag>
              </div>
              <div class="answer-row">
                <span class="answer-label">你的答案</span>
                <span class="answer-value">{{ getQuizDetail(question.id)?.user_answer || '未填写' }}</span>
              </div>
              <div class="answer-row">
                <span class="answer-label">参考答案</span>
                <span class="answer-value answer-ref">{{ getQuizDetail(question.id)?.reference_answer }}</span>
              </div>
              <div class="answer-row answer-row-explain">
                <span class="answer-label">解析</span>
                <span class="answer-value">{{ getQuizDetail(question.id)?.explanation }}</span>
              </div>
            </div>
          </section>
          <el-alert v-if="selectedQuizRecord" title="当前正在查看历史答题记录，内容为只读。" type="info" show-icon :closable="false" />
          <div v-else class="submit-bar">
            <div class="draft-save-row">
              <span class="draft-save-status" :class="`is-${quizDraftSaveState}`">
                <el-icon v-if="quizDraftSaveState === 'saving'" class="is-loading"><Loading /></el-icon>
                <el-icon v-else-if="quizDraftSaveState === 'saved'"><CircleCheckFilled /></el-icon>
                <el-icon v-else><EditPen /></el-icon>
                {{ quizDraftSaveLabel }}
              </span>
              <el-button
                text
                :loading="quizDraftSaveState === 'saving'"
                @click="saveQuizDraftAnswers(true)"
              >
                保存进度
              </el-button>
            </div>
            <el-button type="primary" size="large" :loading="quizLoading" @click="submitStructuredQuiz()">
              提交答案并查看解析
            </el-button>
          </div>
          <el-alert v-if="quizResult" :title="quizResult.summary" type="success" show-icon :closable="false" class="result-summary-alert" />
          <DigitalHumanPanel
            v-if="quizResult && selectedQuizRecord?.id"
            :key="`exercise-digital-human-${selectedQuizRecord.id}`"
            :result-id="selectedQuizRecord.id"
            :score="Number(quizResult.score || 0)"
          />
        </div>
        <div v-else class="content-empty">
          <div class="content-empty-icon"><el-icon :size="36"><EditPen /></el-icon></div>
          <h3>开始练习</h3>
          <p>选择知识点，点击"生成题目"进行练习</p>
        </div>
      </main>
    </div>

    <!-- ===== Coding Case ===== -->
    <div v-else-if="selectedResourceType === 'coding_case'" class="resource-workbench">
      <aside class="resource-history-sidebar">
        <div class="sidebar-header">
          <el-icon :size="18"><Clock /></el-icon>
          <span>{{ selectedResourceLabel }}历史记录</span>
        </div>
        <div class="sidebar-list">
          <div
            v-for="item in resourceHistoryForSelected"
            :key="item.id"
            class="sidebar-item"
            :class="{ active: currentResourceForSelected?.id === item.id }"
            @click="selectResourceHistory(item)"
          >
            <div class="sidebar-item-top">
              <div class="sidebar-title-row">
                <el-icon :size="14" class="sidebar-item-icon"><EditPen /></el-icon>
                <strong class="sidebar-title" :title="item.title">{{ item.title }}</strong>
              </div>
              <div class="sidebar-actions">
                <el-button :icon="EditPen" size="small" text circle title="重命名资源" @click.stop="renameResourceRecord(item)" />
                <el-button :icon="Delete" size="small" text circle type="danger" title="删除资源" @click.stop="deleteResourceRecord(item)" />
              </div>
            </div>
            <div class="sidebar-meta">
              <span class="sidebar-date" :title="formatDateTime(item.created_at)">{{ formatDateTime(item.created_at) }}</span>
            </div>
          </div>
          <div v-if="resourceHistoryForSelected.length === 0" class="sidebar-empty">
            <el-empty description="暂无记录" :image-size="60" />
          </div>
        </div>
      </aside>

      <main class="resource-main-content">
        <div class="content-toolbar">
          <el-input v-model="resourceExtraInput" placeholder="补充你的学习背景、实验要求或想使用的算法库（可选）" clearable style="max-width: 320px" />
          <el-button type="primary" :loading="codingLoading" @click="generateCodingCase">生成实操案例</el-button>
        </div>
        <section v-if="codingCase" class="question-card coding-card">
          <h2>{{ codingCase.title }}</h2>
          <span v-if="showTiming && generationDuration" class="resource-timing-badge">生成耗时 {{ formatDuration(generationDuration) }}</span>
          <div class="coding-prompt markdown" v-html="renderMarkdown(codingCase.prompt)"></div>
          <ul v-if="codingCase.requirements?.length" class="coding-reqs">
            <li v-for="item in codingCase.requirements" :key="item" class="markdown" v-html="renderMarkdown(item)"></li>
          </ul>
          <div class="coding-answer-block">
            <div class="coding-answer-label">答题区域</div>
            <el-input v-model="codingAnswer" type="textarea" :rows="8" placeholder="在这里填写你的代码、思路或答案" class="coding-input" />
          </div>
          <div class="submit-bar">
            <el-button type="primary" size="large" :loading="codingSubmitting" @click="submitCodingCase">提交答案</el-button>
          </div>
          <div v-if="codingResult" class="answer-explain coding-result">
            <div class="result-score" :class="codingResult.is_passed ? 'pass' : 'fail'">
              <span class="result-score-num">{{ codingResult.score }}/100分</span>
              <span class="result-score-label">{{ codingResult.is_passed ? '通过' : '需要修改' }}</span>
            </div>
            <div class="answer-row">
              <span class="answer-label">参考答案</span>
              <span class="answer-value answer-ref markdown" v-html="renderMarkdown(codingResult.reference_answer)"></span>
            </div>
            <div class="answer-row answer-row-explain">
              <span class="answer-label">解析</span>
              <span class="answer-value markdown" v-html="renderMarkdown(codingResult.analysis)"></span>
            </div>
          </div>
        </section>
        <div v-else class="content-empty">
          <div class="content-empty-icon"><el-icon :size="36"><EditPen /></el-icon></div>
          <h3>创建你的代码实验</h3>
          <p>点击"生成实操案例"开始练习</p>
        </div>
      </main>
    </div>

    <!-- ===== PPT Generation Workbench ===== -->
    <div v-else-if="selectedResourceType === 'ppt_deck'" class="ppt-workbench-wrapper">
      <PptWorkbench />
    </div>

    <!-- ===== General Resources ===== -->
    <div v-else class="resource-workbench">
      <aside class="resource-history-sidebar">
        <div class="sidebar-header">
          <el-icon :size="18"><Clock /></el-icon>
          <span>{{ selectedResourceLabel }}历史记录</span>
        </div>
        <div class="sidebar-list">
          <div
            v-for="item in resourceHistoryForSelected"
            :key="item.id"
            class="sidebar-item"
            :class="{ active: currentResourceForSelected?.id === item.id }"
            @click="selectResourceHistory(item)"
          >
            <div class="sidebar-item-top">
              <div class="sidebar-title-row">
                <el-icon :size="14" class="sidebar-item-icon"><Files /></el-icon>
                <strong class="sidebar-title" :title="item.title">{{ item.title }}</strong>
              </div>
              <div class="sidebar-actions">
                <el-button :icon="EditPen" size="small" text circle title="重命名资源" @click.stop="renameResourceRecord(item)" />
                <el-button :icon="Delete" size="small" text circle type="danger" title="删除资源" @click.stop="deleteResourceRecord(item)" />
              </div>
            </div>
            <div class="sidebar-meta">
              <span class="sidebar-date" :title="formatDateTime(item.created_at)">{{ formatDateTime(item.created_at) }}</span>
            </div>
          </div>
          <div v-if="resourceHistoryForSelected.length === 0" class="sidebar-empty">
            <el-empty description="暂无记录，开始创建你的第一份资源" :image-size="60" />
          </div>
        </div>
      </aside>

      <main class="resource-main-content">
        <div class="content-toolbar">
          <div class="gen-input-row">
            <template v-if="selectedResourceType === 'multimedia_video' && videoSearchMode === 'search'">
              <el-input v-model="searchKeyword" placeholder="输入搜索关键词" clearable style="max-width: 240px" @keyup.enter="searchBiliVideos" />
            </template>
            <template v-else>
              <el-input v-model="resourceExtraInput" placeholder="补充相关背景（可选）" clearable style="max-width: 240px" />
            </template>
          </div>
          <template v-if="selectedResourceType === 'multimedia_video'" style="display: flex; align-items: center">
            <el-segmented v-model="videoSearchMode" :options="[
              { label: '搜索', value: 'search' },
              { label: '生成', value: 'generate' },
            ]" @change="switchVideoMode" size="small" style="margin-right: 8px; flex-shrink: 0" />
            <div class="video-toolbar-actions" style="display: flex; align-items: center; min-width: 200px">
              <!-- 搜索模式：搜索按钮 + Cookie设置按钮（搜索后出现） -->
              <template v-if="videoSearchMode === 'search'">
                <el-button size="small" plain title="设置Cookie" @click="cookieDialogVisible = true" style="margin-left: 6px">
                  <el-icon style="margin-right: 3px"><Setting /></el-icon>Cookie
                </el-button>
                <el-button type="primary" :icon="Search" :loading="searchLoading" @click="searchBiliVideos">
                  搜索
                </el-button>

              </template>
              <!-- 生成模式：生成按钮 -->
              <el-button v-else type="primary" :icon="Collection" :loading="typeLoadingMap[selectedResourceType]" @click="generateCurrentResource">
                生成个性化<span class="gen-btn-label">{{ selectedResourceLabel }}</span>
              </el-button>
            </div>
          </template>
          <el-button v-else type="primary" :icon="Collection" :loading="typeLoadingMap[selectedResourceType]" @click="generateCurrentResource">
            生成个性化<span class="gen-btn-label">{{ selectedResourceLabel }}</span>
          </el-button>
        </div>

        <!-- B站Cookie设置弹窗 -->
        <el-dialog v-model="cookieDialogVisible" title="设置Cookie" width="480px" append-to-body>
          <p style="margin-bottom: 8px; font-size: 13px; color: var(--text-500, #64748b);">
            从浏览器复制 B站 Cookie（F12 → 网络 → 请求头 → Cookie），粘贴后点击保存。留空则使用默认 Cookie。
          </p>
          <el-input v-model="cookieTempInput" type="textarea" :rows="4" placeholder="粘贴Cookie..." />
          <template #footer>
            <el-button @click="cookieDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="biliCookie = cookieTempInput; cookieTempInput = ''; cookieDialogVisible = false">保存</el-button>
          </template>
        </el-dialog>
        <el-dialog
          v-model="biliPlayerDialogVisible"
          :title="activeBiliVideo?.title || '视频播放'"
          width="min(1120px, 92vw)"
          append-to-body
          class="bili-player-dialog"
          @closed="activeBiliVideo = null"
        >
          <div v-if="activeBiliVideo" class="bili-player-modal">
            <iframe
              :src="biliPlayerUrl(activeBiliVideo)"
              class="bili-player-modal-frame"
              frameborder="0"
              allow="fullscreen; autoplay; encrypted-media; picture-in-picture"
              allowfullscreen
            ></iframe>
            <div class="bili-player-modal-hint">
              <span>可在播放器内调整音量、倍速和进度</span>
              <el-link :href="'https://www.bilibili.com/video/' + activeBiliVideo.bvid" target="_blank" type="primary">打开原视频</el-link>
            </div>
          </div>
        </el-dialog>
        <div v-if="currentStreamingState?.active && (selectedResourceType === 'course_document' || selectedResourceType === 'extension_reading')" class="resource-card streaming-card">
          <div class="streaming-card-header">
            <h3>{{ currentStreamingState?.title || '生成中...' }}</h3>
          </div>
          <div class="markdown" v-html="renderResourceMarkdown(currentStreamingState?.content || '')"></div>
          <div class="streaming-footer"><el-icon class="is-loading"><Loading /></el-icon> 正在生成中...</div>
        </div>
        <article v-else-if="currentResourceForSelected" class="resource-card">
          <div v-if="!(selectedResourceType === 'multimedia_video' && videoSearchMode === 'search')" class="resource-card-header">
            <div class="resource-card-title-row">
              <h3>{{ currentResourceForSelected.title }}</h3>
              <div class="resource-card-meta-group">
                <span v-if="showTiming && generationDuration" class="resource-timing-badge">生成耗时 {{ formatDuration(generationDuration) }}</span>
                <span class="resource-card-meta" v-if="currentResourceForSelected.created_at">{{ formatDateTime(currentResourceForSelected.created_at) }}</span>
              </div>
            </div>
            <div v-if="selectedResourceType === 'course_document' || selectedResourceType === 'extension_reading'" class="resource-card-actions">
              <el-button size="small" :icon="CopyDocument" text @click="copyContent">复制</el-button>
              <el-button size="small" :icon="Download" text @click="downloadMarkdown">下载</el-button>
              <el-button size="small" :icon="Printer" text @click="printDocument">导出 PDF</el-button>
              <!-- <el-button size="small" :icon="Plus" text @click="addToLearningPath">加入学习路径</el-button> -->
              <!-- <el-button size="small" :icon="Refresh" text @click="generateCurrentResource">重新生成</el-button> -->
            </div>
          </div>
          <el-image v-if="resourceArtifact?.image_url && selectedResourceType !== 'mind_map'" :src="resourceArtifact.image_url" fit="contain" class="resource-image" />
          <el-link v-if="resourceArtifact?.file_url" :href="resourceArtifact.file_url" target="_blank" type="primary" class="resource-file-link">
            打开模型生成文件
          </el-link>
          <div v-if="resourceArtifact?.mindmap_url && selectedResourceType !== 'mind_map'" class="mindmap-section">
            <el-link :href="resourceArtifact.mindmap_url" target="_blank" type="success" :icon="Collection" class="mindmap-link">
              下载/打开旧版思维导图文件
            </el-link>
          </div>
          <div v-if="selectedResourceType === 'mind_map'" class="mindmap-wrapper">
            <MindMapViewer
              ref="mindMapViewerRef"
              :content="currentResourceForSelected.content"
              :data="mindMapPreviewData"
            />
            <div class="mindmap-actions">
              <el-button class="mindmap-action-btn" size="small" :icon="Download" text @click="downloadMindMap">下载 SVG</el-button>
              <!-- <el-button class="mindmap-action-btn" size="small" :icon="Collection" text @click="copyLayoutJson"
                :disabled="!hasMindMapLayoutJson">导出 JSON 布局</el-button> -->
            </div>
          </div>
          <template v-else-if="selectedResourceType === 'multimedia_video'">
            <!-- 搜索模式：搜索结果 -->
            <template v-if="videoSearchMode === 'search'">
              <div v-if="searchResults.length > 0" class="bili-results">
                <div v-for="(video, index) in searchResults" :key="index" class="bili-video-card">
                  <div class="bili-video-player">
                    <iframe
                      :src="'https://player.bilibili.com/player.html?bvid=' + video.bvid + '&page=1&high_quality=1&autoplay=0'"
                      class="bili-video-iframe"
                      frameborder="0"
                      allowfullscreen
                    ></iframe>
                  </div>
                  <div class="bili-video-info">
                    <div class="bili-video-title">{{ video.title }}</div>
                    <button class="bili-expand-btn" type="button" @click="openBiliPlayer(video)">
                      <el-icon><FullScreen /></el-icon>
                      放大播放
                    </button>
                  </div>
                  <div class="bili-video-meta">
                    <span>播放 {{ video.play || '--' }}</span>
                    <span>时长 {{ video.duration || '--' }}</span>
                    <span>UP {{ video.author || '--' }}</span>
                  </div>
                </div>
              </div>
              <div v-else class="bili-search-hint">
                <el-empty description="输入关键词搜索视频" />
              </div>
            </template>
            <!-- 生成模式：原有视频生成内容 -->
            <template v-else>
              <div v-if="videoResultUrls.length > 0" class="video-results">
                <div v-for="(url, index) in videoResultUrls" :key="index" class="video-card">
                  <div class="video-card-top">
                    <div class="video-card-title">
                      <span class="video-card-icon"><el-icon><VideoPlay /></el-icon></span>
                      <div>
                        <strong>{{ currentResourceForSelected.title || '教学视频' }}</strong>
                        <span>AI 生成视频 {{ videoResultUrls.length > 1 ? index + 1 : '' }}</span>
                      </div>
                    </div>
                    <el-link :href="url" target="_blank" type="primary" class="video-download-link">
                      <el-icon><Download /></el-icon>
                      下载视频
                    </el-link>
                  </div>
                  <div class="video-player-shell">
                    <video :src="url" controls class="resource-video">
                      您的浏览器不支持视频播放
                    </video>
                  </div>
                </div>
              </div>
              <div v-else-if="videoTaskRunning" class="video-status">
                <el-alert title="视频生成中，请稍后刷新查看" type="info" :closable="false" show-icon />
                <p class="task-id-text">任务 ID：{{ videoTaskId }}</p>
              </div>
              <div v-else class="markdown" v-html="renderResourceMarkdown(currentResourceForSelected.content)"></div>
            </template>
          </template>
          <div v-else class="markdown" v-html="renderResourceMarkdown(currentResourceForSelected.content)"></div>
        </article>
        <div v-else class="content-empty">
          <div class="content-empty-icon"><el-icon :size="36"><Collection /></el-icon></div>
          <h3>生成个性化{{ selectedResourceLabel }}</h3>
          <p>补充背景信息或选择难度与目标，点击按钮生成个性化学习资源</p>
        </div>
      </main>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import {
  activateProgress, pollGenerationStatus, streamingStates,
} from '../composables/useResourceProgress'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheckFilled, Clock, Collection, CopyDocument, Delete, Download, EditPen, Files, FullScreen, Loading, Plus, Printer, Refresh, Search, Setting, VideoPlay } from '@element-plus/icons-vue'
import { api, resourceOptions, type ResourceType } from '../api/learning'
import { formatDateTime, getErrorMessage, renderMarkdown, runAction, scoreText } from '../composables/useUtils'
import { useQuiz } from '../composables/useQuiz'
import MindMapViewer from '../components/MindMapViewer.vue'
import PptWorkbench from '../components/PptWorkbench.vue'
import DigitalHumanPanel from '../components/digital-human/DigitalHumanPanel.vue'

const {
  quizLoading,
  quizForm,
  structuredQuiz,
  quizAnswers,
  quizResult,
  quizHistoryRecords,
  exerciseHistoryRecords,
  selectedQuizRecord,
  quizDraftSaveState,
  quizDraftSaveLabel,
  getQuizDetail,
  quizRecordTitle,
  questionTypeLabel,
  optionLabel,
  optionValue,
  answerStatusLabel,
  answerStatusType,
  generateExerciseBank: generateExerciseBankBase,
  submitStructuredQuiz,
  saveQuizDraftAnswers,
  loadQuizHistory,
  selectQuizHistory,
  renameQuizRecord,
  deleteQuizRecord,
  resetQuizAnswers,
} = useQuiz()

const props = defineProps<{ resourceType?: string }>()

const selectedResourceType = ref<ResourceType>((props.resourceType || 'course_document') as ResourceType)
const resources = ref<any[]>([])
const currentResource = ref<any | null>(null)
const resourceArtifact = ref<any | null>(null)
const mindMapViewerRef = ref<InstanceType<typeof MindMapViewer> | null>(null)
const hasMindMapLayoutJson = computed(() => {
  const layoutJson = resourceArtifact.value?.mindmap || resourceArtifact.value?.layout_json
  if (Array.isArray(layoutJson)) return layoutJson.length > 0
  return Boolean(layoutJson && typeof layoutJson === 'object')
})
const resourceExtraInput = ref('')
const resourceDifficulty = ref('')
const resourceGoal = ref('')
const generationDuration = ref<number | null>(null)  // 前端本地计时（秒），不写回后端
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

function formatLiveTime(seconds: number) {
  if (seconds == null || seconds < 0) return ''
  if (seconds < 60) return `${seconds}秒`
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}分${secs}秒`
}

const typeLoadingMap = reactive<Record<string, boolean>>({})
const loading = ref(false)
const codingLoading = ref(false)
const codingSubmitting = ref(false)
const codingCase = ref<any | null>(null)
const codingAnswer = ref('')
const codingResult = ref<any | null>(null)

// 教学视频搜索模式状态
const videoSearchMode = ref<'generate' | 'search'>('generate')
const biliCookie = ref('')
const searchKeyword = ref('')
const searchResults = ref<any[]>([])
const searchLoading = ref(false)
const cookieDialogVisible = ref(false)
const cookieTempInput = ref('')
const biliPlayerDialogVisible = ref(false)
const activeBiliVideo = ref<any | null>(null)

function biliPlayerUrl(video: any) {
  const bvid = encodeURIComponent(video?.bvid || '')
  return `https://player.bilibili.com/player.html?bvid=${bvid}&page=1&high_quality=1&autoplay=0`
}

function openBiliPlayer(video: any) {
  activeBiliVideo.value = video
  biliPlayerDialogVisible.value = true
}

async function searchBiliVideos() {
  const keyword = searchKeyword.value.trim()
  if (!keyword) {
    ElMessage.warning('请输入搜索关键词')
    return
  }
  searchLoading.value = true
  try {
    // 如果用户填写了 Cookie，暂时存储到全局以备后续请求
    if (biliCookie.value.trim()) {
      ;(window as any).__bili_cookie = biliCookie.value.trim()
    }
    const { data } = await api.searchBiliVideo(keyword, 6, biliCookie.value)
    searchResults.value = data.videos || []
    if (data.need_cookie) {
      ElMessage.warning(data.message || 'B站Cookie已过期，请点击Cookie按钮重新设置')
      // 自动弹出Cookie设置弹窗
      cookieTempInput.value = biliCookie.value
      cookieDialogVisible.value = true
    } else if (searchResults.value.length === 0) {
      ElMessage.info('未搜索到相关视频')
    }
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    searchLoading.value = false
  }
}

function switchVideoMode(mode: 'generate' | 'search') {
  videoSearchMode.value = mode
  if (mode === 'generate') {
    searchResults.value = []
  }
}

// Agent collaboration steps — imported from composable for persistent state

const typeDescriptions: Record<string, string> = {
  course_document: '根据课程知识库生成个性化的课程讲解文档，适合预习和复习',
  mind_map: '自动梳理知识点之间的关联，生成可视化的思维导图',
  exercise_bank: '基于知识库生成不同题型的练习题，检验知识掌握程度',
  extension_reading: '根据当前学习内容，生成相关拓展阅读材料',
  coding_case: '生成可运行的代码实验案例，在动手实践中巩固知识、提升编程能力',
  multimedia_video: '生成多模态教学内容，包括视频等多媒体资源',
  ppt_deck: '输入主题或要求，AI 自动生成大纲并制作精美 PPT，支持多种主题风格',
}
const currentTypeDescription = computed(() => typeDescriptions[selectedResourceType.value] || '')

const typeHeaders: Record<string, { title: string; desc: string }> = {
  course_document: {
    title: '智能讲解文档',
    desc: '基于课程知识库与学习画像，自动生成结构清晰、重点突出的课程讲解文档',
  },
  mind_map: {
    title: '思维导图生成',
    desc: '自动梳理知识点关联，生成可视化的知识图谱，帮助建立系统性认知',
  },
  exercise_bank: {
    title: '智能练习题库',
    desc: '基于知识库自动生成多种题型，检验知识掌握程度，精准定位薄弱环节',
  },
  extension_reading: {
    title: '拓展阅读推荐',
    desc: '根据当前学习内容与兴趣方向，智能推荐与生成相关拓展阅读材料',
  },
  coding_case: {
    title: '实操案例工坊',
    desc: '生成可运行的代码实验案例，在动手实践中巩固知识、提升编程能力',
  },
  multimedia_video: {
    title: '多媒体教学视频',
    desc: '将学习内容转化为生动的教学视频与动画，多模态辅助理解复杂概念',
  },
  ppt_deck: {
    title: 'AI PPT 制作',
    desc: '输入主题或要求，AI 自动生成幻灯片内容并排版制作精美演示文稿',
  },
}

const currentTypeHeader = computed(() => typeHeaders[selectedResourceType.value] || typeHeaders.course_document)

const selectedResourceLabel = computed(() => {
  return resourceOptions.find((item) => item.value === selectedResourceType.value)?.label || '资源'
})

const showTiming = computed(() => {
  return import.meta.env.VITE_ENABLE_RESOURCE_TIMING === 'true'
})

function formatDuration(seconds: number) {
  if (seconds == null) return ''
  if (seconds < 60) return `${Math.floor(seconds)}秒`
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}分${secs}秒`
}

function renderResourceMarkdown(content: string) {
  const shouldCollapse = selectedResourceType.value === 'course_document' || selectedResourceType.value === 'extension_reading'
  return renderMarkdown(content, { collapsibleHeadings: shouldCollapse })
}

// 教学视频相关计算属性：解析后端返回的 JSON 内容
const videoResultUrls = computed(() => {
  try {
    const parsed = JSON.parse(currentResourceForSelected.value?.content || '{}')
    const results = parsed.results || []
    return results.map((r: any) => r.url || r).filter(Boolean)
  } catch {
    return []
  }
})
const videoTaskRunning = computed(() => {
  try {
    const parsed = JSON.parse(currentResourceForSelected.value?.content || '{}')
    return parsed.task_status === 'RUNNING' || parsed.task_status === 'PENDING'
  } catch {
    return false
  }
})
const videoTaskId = computed(() => {
  try {
    const parsed = JSON.parse(currentResourceForSelected.value?.content || '{}')
    return parsed.task_id || ''
  } catch {
    return ''
  }
})

const currentResourceForSelected = computed(() => {
  return currentResource.value?.resource_type === selectedResourceType.value ? currentResource.value : null
})

const mindMapPreviewData = computed(() => {
  if (selectedResourceType.value !== 'mind_map') return null
  return resourceArtifact.value?.mindmap
    || resourceArtifact.value?.layout_json
    || currentResourceForSelected.value?.content
    || null
})

const resourceHistoryForSelected = computed(() => {
  const filtered = resources.value.filter((item) => item.resource_type === selectedResourceType.value)
  return filtered
})

const currentStreamingState = computed(() => streamingStates[selectedResourceType.value])
const activePolls: Record<string, { stop: () => void }> = {}

onUnmounted(() => {
  Object.values(activePolls).forEach(poll => poll.stop())
  stopLiveTimer()
})

// ===== Copy / Download / Action =====
function copyContent() {
  const resource = currentResourceForSelected.value
  if (!resource?.content) return
  navigator.clipboard.writeText(resource.content).then(() => {
    ElMessage.success('内容已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败，请手动选择复制')
  })
}

function downloadMarkdown() {
  const resource = currentResourceForSelected.value
  if (!resource?.content) return
  const blob = new Blob([resource.content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${resource.title || 'resource'}.md`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  ElMessage.success('文件已下载')
}

async function downloadMindMap() {
  if (mindMapViewerRef.value) {
    await mindMapViewerRef.value.exportSvg()
  } else {
    ElMessage.warning('思维导图组件尚未初始化')
  }
}

function copyLayoutJson() {
  const nodes = resourceArtifact.value?.mindmap || resourceArtifact.value?.layout_json
  if (!hasMindMapLayoutJson.value) { ElMessage.warning('暂无布局数据'); return }
  const json = JSON.stringify(nodes, null, 2)
  navigator.clipboard.writeText(json).then(() => {
    ElMessage.success('JSON 布局已复制到剪贴板')
  }).catch(() => {
    const textarea = document.createElement('textarea')
    textarea.value = json
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    ElMessage.success('JSON 布局已复制到剪贴板')
  })
}

function printDocument() {
  const resource = currentResourceForSelected.value
  if (!resource?.content) return
  const printWindow = window.open('', '_blank')
  if (!printWindow) { ElMessage.warning('浏览器阻止了弹出窗口，请允许后重试'); return }
  printWindow.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>${resource.title || '文档'}</title><style>body{max-width:800px;margin:40px auto;padding:0 20px;font-family:Inter,'PingFang SC',sans-serif;font-size:15px;line-height:1.75;color:#1e293b}h1{font-size:24px;font-weight:700}h2{font-size:20px;font-weight:700}h3{font-size:17px;font-weight:600}pre{background:#0f172a;color:#f8fafc;padding:16px;border-radius:8px;overflow:auto}code{font-family:'JetBrains Mono',monospace}blockquote{border-left:4px solid #60a5fa;padding:8px 16px;background:#f8fafc;margin:0}table{border-collapse:collapse;width:100%}td,th{border:1px solid #e2e8f0;padding:8px 12px}img{max-width:100%}</style></head><body>${renderMarkdown(resource.content)}</body></html>`)
  printWindow.document.close()
  printWindow.focus()
  setTimeout(() => printWindow.print(), 500)
}

function addToLearningPath() {
  // ElMessage.info('加入学习路径功能即将上线')
}


// ===== API / Data Loading =====
async function loadResources() {
  try {
    const { data } = await api.listResources()
    resources.value = (data.resources || []).filter((r: any) => r.resource_type !== 'ppt_deck')
  } catch (error) {
    // 静默处理
  }
}

function ensureSelectedResource() {
  if (selectedResourceType.value === 'exercise_bank') return
  const stillExists = currentResource.value
    && currentResource.value.resource_type === selectedResourceType.value
    && resources.value.some((item) => item.id === currentResource.value.id)
  if (!stillExists) {
    const latest = resourceHistoryForSelected.value[0] || null
    if (latest) {
      selectResourceHistory(latest)
    } else {
      currentResource.value = null
      resourceArtifact.value = null
      if (selectedResourceType.value === 'coding_case') {
        codingCase.value = null
        codingAnswer.value = ''
        codingResult.value = null
      }
    }
  }
}

function parseCodingCaseResource(resource: any) {
  try {
    const parsed = JSON.parse(resource.content || '{}')
    if (parsed?.prompt) return parsed
  } catch {
    // 兼容旧的 Markdown 实操案例资源。
  }
  return {
    title: resource.title,
    prompt: resource.content || '',
    requirements: [],
    reference_answer: '',
  }
}

async function selectResourceHistory(resource: any) {
  // 点击教学视频历史记录时切回生成模式
  if (resource.resource_type === 'multimedia_video') {
    videoSearchMode.value = 'generate'
  }
  currentResource.value = resource
  resourceArtifact.value = null
  if (resource.resource_type === 'coding_case') {
    codingCase.value    = parseCodingCaseResource(resource)
    codingAnswer.value  = ''
    codingResult.value  = null
    try {
      const { data } = await api.getCaseRecord(resource.id)
      if (data.record) {
        codingAnswer.value = data.record.answer || ''
        codingResult.value = {
          score:            data.record.score,
          is_passed:        data.record.is_passed,
          analysis:         data.record.analysis,
          reference_answer: data.record.reference_answer,
        }
      }
    } catch {
      // 静默处理，未找到记录不影响查看题目
    }
  }
}

async function renameResourceRecord(resource: any) {
  try {
    const { value } = await ElMessageBox.prompt('请输入新的资源名称', '重命名资源', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: resource.title,
      inputValidator: (value) => Boolean(value.trim()) || '名称不能为空',
    })
    await runAction(loading, async () => {
      const { data } = await api.renameResource(resource.id, value.trim())
      Object.assign(resource, data.resource)
      if (currentResource.value?.id === resource.id) currentResource.value = data.resource
    }, '资源已重命名')
  } catch {
    // 用户取消时不提示错误。
  }
}

async function deleteResourceRecord(resource: any) {
  try {
    await ElMessageBox.confirm(`确定删除"${resource.title}"吗？`, '删除资源记录', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await runAction(loading, async () => {
      await api.deleteResource(resource.id)
      if (currentResource.value?.id === resource.id) {
        currentResource.value = null
        resourceArtifact.value = null
        if (resource.resource_type === 'coding_case') {
          codingCase.value = null
          codingAnswer.value = ''
          codingResult.value = null
        }
      }
      await loadResources()
    }, '资源已删除')
  } catch {
    // 用户取消时不提示错误。
  }
}

function buildExtraInput(): string {
  const parts: string[] = []
  if (resourceExtraInput.value.trim()) parts.push(resourceExtraInput.value.trim())
  if (resourceDifficulty.value) parts.push(`难度:${resourceDifficulty.value}`)
  if (resourceGoal.value) parts.push(`目标:${resourceGoal.value}`)
  return parts.join(' | ')
}

async function handleGenerateExerciseBank() {
  if (quizLoading.value) return
  generationDuration.value = null
  const _quizGenStart = Date.now()
  startLiveTimer()
  activateProgress('exercise_bank', '正在分析练习目标与知识薄弱点...')
  try {
    await generateExerciseBankBase()
    generationDuration.value = (Date.now() - _quizGenStart) / 1000
    liveElapsed.value = Math.floor((Date.now() - _quizGenStart) / 1000)
    await loadQuizHistory()
  } finally {
    stopLiveTimer()
    streamingStates['exercise_bank'].active = false
  }
}

async function generateCurrentResource() {
  const typeKey = selectedResourceType.value
  if (typeLoadingMap[typeKey]) return
  typeLoadingMap[typeKey] = true
  generationDuration.value = null
  const _genStart = Date.now()
  startLiveTimer()

  const streamingTypes = ['course_document', 'exercise_bank', 'extension_reading', 'coding_case']
  if (streamingTypes.includes(typeKey)) {
    activateProgress(typeKey, '')

    const input = buildExtraInput()
    resourceExtraInput.value = ''
    resourceDifficulty.value = ''
    resourceGoal.value = ''
    let streamCompletionKind: 'done' | 'fallback' | '' = ''
    let streamCompletionData: any = null
    let streamErrorMessage = ''

    try {
      await api.generateResourceStream(typeKey, input, (event, data) => {
        if (event === 'status') {
          streamingStates[typeKey].progress = data.message || ''
        } else if (event === 'outline') {
          streamingStates[typeKey].title = data.title || ''
          streamingStates[typeKey].progress = `共 ${data.total} 个章节`
        } else if (event === 'section') {
          streamingStates[typeKey].sections[Number(data.index || 0)] = data.content || ''
          streamingStates[typeKey].content = Object.keys(streamingStates[typeKey].sections)
            .map(Number)
            .sort((a, b) => a - b)
            .map((index) => streamingStates[typeKey].sections[index])
            .filter(Boolean)
            .join('\n\n')
          streamingStates[typeKey].progress = `已完成 ${data.completed}/${data.total} 章节`
        } else if (event === 'done') {
          streamingStates[typeKey].done = true
          streamCompletionKind = 'done'
          streamCompletionData = data
        } else if (event === 'error') {
          streamErrorMessage = data.message || '生成失败'
        } else if (event === 'fallback') {
          streamingStates[typeKey].done = true
          streamCompletionKind = 'fallback'
          streamCompletionData = data
        }
      })
      if (streamErrorMessage) {
        ElMessage.error(streamErrorMessage)
      } else if (streamCompletionKind && streamCompletionData) {
        generationDuration.value = (Date.now() - _genStart) / 1000
        stopLiveTimer()
        liveElapsed.value = Math.floor((Date.now() - _genStart) / 1000)
        currentResource.value = streamCompletionData.resource
        await loadResources()
        await nextTick()
        currentResource.value = resources.value.find((item) => item.id === streamCompletionData.resource.id) || streamCompletionData.resource
        if (streamCompletionKind === 'fallback') {
          ElMessage.info('已使用本地模板生成')
        } else {
          ElMessage.success('资源已生成')
        }
      }
    } catch (error: any) {
      if (error?.name !== 'AbortError') {
        ElMessage.error(getErrorMessage(error))
      }
    } finally {
      stopLiveTimer()
      streamingStates[typeKey].active = false
      typeLoadingMap[typeKey] = false
    }
    return
  }

  // 非流式类型（思维导图、教学视频等）— 异步生成 + 轮询
  activateProgress(typeKey)
  try {
    const { data: asyncData } = await api.generateResourceAsync(typeKey, buildExtraInput())
    resourceExtraInput.value = ''
    resourceDifficulty.value = ''
    resourceGoal.value = ''
    const startedAt = asyncData.started_at

    const result = await new Promise<{ resource: any; artifact?: any }>((resolve, reject) => {
      const poll = pollGenerationStatus(
        typeKey, startedAt,
        async (t, s) => {
          const { data } = await api.getAsyncGenerationStatus(t, s)
          return data
        },
        (data) => {
          // 从完整响应中提取 resource 和 artifact
          const res = typeof data === 'object' && data !== null && 'id' in data ? data : null
          const art = typeof data === 'object' && data !== null && 'artifact' in data ? data.artifact : null
          delete activePolls[typeKey]
          resolve({ resource: res || data, artifact: art })
        },
        () => { delete activePolls[typeKey]; reject(new Error('生成超时，请重试')) },
      )
      activePolls[typeKey] = poll
    })
    currentResource.value = result.resource
    resourceArtifact.value = result.artifact || null
    await loadResources()
    if (result.resource) {
      currentResource.value = resources.value.find((item) => item.id === result.resource.id) || result.resource
    }
    generationDuration.value = (Date.now() - _genStart) / 1000
    stopLiveTimer()
    liveElapsed.value = Math.floor((Date.now() - _genStart) / 1000)
    ElMessage.success('资源已生成')
  } catch (error: any) {
    if (error?.message !== '生成超时，请重试') {
      ElMessage.error(getErrorMessage(error))
    } else {
      ElMessage.error(error.message)
    }
  } finally {
    stopLiveTimer()
    streamingStates[typeKey].active = false
    typeLoadingMap[typeKey] = false
  }
}

async function generateCodingCase() {
  if (codingLoading.value) return
  codingLoading.value = true
  generationDuration.value = null
  const _codingGenStart = Date.now()
  startLiveTimer()
  activateProgress('coding_case', '正在准备生成实操案例...')
  try {
    const { data } = await api.generateCase(buildExtraInput())
    resourceExtraInput.value = ''
    resourceDifficulty.value = ''
    resourceGoal.value = ''
    currentResource.value = data.resource
    codingCase.value = parseCodingCaseResource(data.resource)
    codingAnswer.value = ''
    codingResult.value = null
    generationDuration.value = (Date.now() - _codingGenStart) / 1000
    stopLiveTimer()
    liveElapsed.value = Math.floor((Date.now() - _codingGenStart) / 1000)
    await loadResources()
    ElMessage.success('实操题已生成')
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    stopLiveTimer()
    codingLoading.value = false
    streamingStates['coding_case'].active = false
  }
}

async function submitCodingCase() {
  if (codingSubmitting.value) return
  if (!codingAnswer.value.trim()) {
    ElMessage.warning('请先填写答案')
    return
  }
  codingSubmitting.value = true
  try {
    const resourceId = currentResource.value?.id || codingCase.value?.resource_id
    const { data } = await api.submitCase({
      case: codingCase.value,
      answer: codingAnswer.value,
      resource_id: resourceId,
    })
    codingResult.value = data.result
    await loadResources()
    ElMessage.success('判题完成')
  } catch (error) {
    ElMessage.error(getErrorMessage(error))
  } finally {
    codingSubmitting.value = false
  }
}

watch(() => props.resourceType, (val) => {
  if (val && val !== selectedResourceType.value) {
    selectedResourceType.value = val as ResourceType
  }
})

watch(selectedResourceType, (newVal) => {
  if (selectedResourceType.value === 'exercise_bank') {
    loadQuizHistory()
  }
  currentResource.value = null
  resourceArtifact.value = null
  generationDuration.value = null
  codingCase.value = null
  codingAnswer.value = ''
  codingResult.value = null
  ensureSelectedResource()
  // 用户切换资源子类型时也记录行为
  api.logTaskAction('visit_resources', newVal).catch(() => {})
})

onMounted(async () => {
  await loadResources()
  ensureSelectedResource()
  // 通知后端：用户访问了资源页面（带子类型，用于 task 完成判定）
  api.logTaskAction('visit_resources', selectedResourceType.value).catch(() => {})
})

</script>

<style scoped>
/* ======= Page ======= */
.resources-page {
  display: flex;
  flex-direction: column;
  max-width: 1380px;
  margin: 0 auto;
  width: 100%;
  min-height: 100%;
  overflow: visible;
  animation: resFadeIn 0.4s ease-out;
}

@keyframes resFadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ======= Header ======= */
.resources-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 18px;
  margin-bottom: 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.86);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(226, 232, 240, 0.9);
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
  position: relative;
  overflow: hidden;
  flex-shrink: 0;
}

.resources-header::before {
  content: '';
  position: absolute;
  top: -30px;
  right: -10px;
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.06);
  pointer-events: none;
}

.resources-header::after {
  content: '';
  position: absolute;
  bottom: -20px;
  right: 80px;
  width: 70px;
  height: 70px;
  border-radius: 50%;
  background: rgba(56, 189, 248, 0.06);
  pointer-events: none;
}

.resources-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  position: relative;
  z-index: 1;
}

.resources-header-icon {
  width: 38px;
  height: 38px;
  border-radius: 9px;
  background: linear-gradient(135deg, var(--primary-500, #6366f1), var(--primary-600, #4f46e5));
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  box-shadow: 0 3px 10px rgba(99, 102, 241, 0.25);
  flex-shrink: 0;
}

.resources-page-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--surface-800, #1e293b);
  margin: 0 0 1px;
  letter-spacing: 0;
}

.resources-desc {
  font-size: 12.5px;
  color: var(--surface-500, #64748b);
  margin: 0;
  line-height: 1.35;
}

.resources-header-right {
  display: flex;
  gap: 6px;
  position: relative;
  z-index: 1;
  flex-shrink: 0;
}

.header-badge {
  border: none !important;
  font-weight: 600;
  font-size: 12px;
  padding: 0 10px;
  height: 24px;
  line-height: 24px;
  letter-spacing: 0;
}
.header-badge.badge-rag {
  background: linear-gradient(135deg, #eff6ff, #dbeafe);
  color: #3b82f6;
}
.header-badge.badge-agent {
  background: linear-gradient(135deg, #ecfeff, #cffafe);
  color: #0891b2;
}
.header-badge.badge-personal {
  background: linear-gradient(135deg, #fdf4ff, #fae8ff);
  color: #9333ea;
}

/* ======= Type Bar ======= */
.resources-type-bar {
  margin-bottom: 14px;
  flex-shrink: 0;
  background: #ffffff;
  border: 1px solid var(--surface-100, #f1f5f9);
  border-radius: var(--radius-lg, 12px);
  padding: 12px 16px 10px;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.05));
  transition: box-shadow 0.2s ease;
}


.type-bar-desc {
  font-size: 13px;
  color: var(--surface-400, #94a3b8);
  margin-top: 8px;
  padding: 0 4px;
  line-height: 1.5;
}

/* ======= Agent Collaboration Section ======= */
.agent-collab-section {
  margin-bottom: 14px;
  background: linear-gradient(135deg, #eff6ff 0%, #eff6ff 50%, #ecfeff 100%);
  border: 1px solid #dbeafe;
  border-radius: var(--radius-lg, 12px);
  padding: 16px 20px;
  flex-shrink: 0;
  position: relative;
  overflow: hidden;
}

.agent-collab-section::before {
  content: '';
  position: absolute;
  top: -40px;
  right: -20px;
  width: 100px;
  height: 100px;
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.05);
  pointer-events: none;
}

.agent-collab-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--primary-700, #4338ca);
  margin-bottom: 16px;
}

.agent-collab-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary-500, #6366f1);
  animation: agentPulse 1.5s ease-in-out infinite;
}

@keyframes agentPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}

.agent-steps {
  display: flex;
  align-items: flex-start;
  gap: 0;
}

.agent-step {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  position: relative;
  min-width: 0;
}

.agent-step-indicator {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.4s ease;
  position: relative;
}

.agent-step.pending .agent-step-indicator {
  background: #f1f5f9;
  color: #94a3b8;
}

.agent-step.running .agent-step-indicator {
  background: #eff6ff;
  color: var(--primary-500, #6366f1);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
}

.agent-step.done .agent-step-indicator {
  background: #d1fae5;
  color: #10b981;
}

.step-pending-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #cbd5e1;
}

.step-done-icon,
.step-running-icon {
  font-size: 18px;
}

.agent-step-body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.agent-step-body strong {
  font-size: 13px;
  font-weight: 600;
  color: var(--surface-700, #334155);
  white-space: nowrap;
}

.agent-step-body span {
  font-size: 12px;
  color: var(--surface-400, #94a3b8);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.agent-step-tail {
  flex: 1;
  display: flex;
  align-items: center;
  padding: 0 8px;
  min-width: 16px;
}

.tail-line {
  height: 2px;
  flex: 1;
  background: #e2e8f0;
  border-radius: 2px;
  transition: background 0.5s ease;
}

.tail-line.active {
  background: linear-gradient(90deg, var(--primary-300, #a5b4fc), var(--primary-400, #818cf8));
}

.agent-collab-progress {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid rgba(99, 102, 241, 0.1);
  font-size: 13px;
  color: var(--primary-600, #4f46e5);
  display: flex;
  align-items: center;
  gap: 6px;
}

/* Agent slide transition */
.agent-slide-enter-active {
  animation: agentSlideIn 0.35s ease-out;
}
.agent-slide-leave-active {
  animation: agentSlideIn 0.25s ease-in reverse;
}
@keyframes agentSlideIn {
  from { opacity: 0; transform: translateY(-8px); max-height: 0; }
  to { opacity: 1; transform: translateY(0); max-height: 200px; }
}

/* ======= Message Alert ======= */
.resource-message-alert {
  margin-bottom: 16px;
  flex-shrink: 0;
}

/* ======= Workbench Layout ======= */
.resource-workbench {
  flex: 0 0 auto;
  min-height: 0;
  height: calc(100vh - 96px);
  display: flex;
  gap: 14px;
  overflow: hidden;
}

/* ======= History Sidebar (shared) ======= */
.resource-history-sidebar {
  order: 2;
  width: 44px;
  flex-shrink: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: linear-gradient(180deg, #eff6ff 0%, #e0f2fe 100%);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 18px;
  padding: 18px 10px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
  transition: width 0.26s ease, padding 0.26s ease, box-shadow 0.26s ease;
  position: relative;
}

.resource-history-sidebar:hover {
  width: 240px;
  padding: 20px 14px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: -8px 0 28px rgba(99, 102, 241, 0.12), 0 10px 30px rgba(15, 23, 42, 0.06);
}

.resource-history-sidebar:not(:hover) .sidebar-header {
  justify-content: center;
  padding: 0 0 14px;
  border-bottom: none;
  height: 100%;
}

.resource-history-sidebar:not(:hover) .sidebar-header .el-icon {
  display: none;
}

.resource-history-sidebar:not(:hover) .sidebar-header span {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  letter-spacing: 4px;
  font-size: 14px;
  font-weight: 700;
  color: #3b82f6;
  opacity: 1;
  pointer-events: none;
}

.resource-history-sidebar:not(:hover) .sidebar-list {
  opacity: 0;
  pointer-events: none;
}

.resource-history-sidebar .sidebar-list,
.resource-history-sidebar .sidebar-header span {
  transition: opacity 0.16s ease;
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--surface-700, #334155);
  padding: 0 6px 14px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--surface-100, #f1f5f9);
  flex-shrink: 0;
}

.sidebar-item {
  padding: 10px;
  border-radius: var(--radius-md, 8px);
  cursor: pointer;
  transition: all 0.2s ease;
  margin-bottom: 6px;
  border: 1px solid transparent;
  position: relative;
}

.sidebar-item:last-child { margin-bottom: 0; }

.sidebar-item:hover {
  background: var(--surface-50, #f8fafc);
  border-color: var(--surface-100, #f1f5f9);
}

.sidebar-item.active {
  background: #eff6ff;
  border-color: var(--primary-200, #c7d2fe);
}

.sidebar-item.active::before {
  content: '';
  position: absolute;
  left: -2px;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 60%;
  background: linear-gradient(180deg, var(--primary-400, #818cf8), var(--primary-500, #6366f1));
  border-radius: 0 3px 3px 0;
}

.sidebar-item-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 6px;
}

.sidebar-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex: 1;
}

.sidebar-item-icon {
  color: var(--primary-500, #6366f1);
  flex-shrink: 0;
}

.sidebar-title {
  font-size: 14px;
  color: var(--surface-700, #334155);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: block;
  max-width: 9em;
}

.sidebar-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.sidebar-item:hover .sidebar-actions {
  opacity: 1;
}

.sidebar-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--surface-400, #94a3b8);
  padding-left: 20px;
}

.sidebar-meta :deep(.el-tag) {
  flex-shrink: 0;
}

.sidebar-date {
  color: var(--surface-400, #94a3b8);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.sidebar-score {
  margin-left: auto;
  flex-shrink: 0;
  font-weight: 700;
  font-size: 14px;
  padding: 2px 10px;
  border-radius: 20px;
  line-height: 1.5;
  letter-spacing: 0.3px;
  transition: all 0.2s ease;
}

.sidebar-score.score-high {
  color: #065f46;
  background: linear-gradient(135deg, #d1fae5, #a7f3d0);
}

.sidebar-score.score-low {
  color: #991b1b;
  background: linear-gradient(135deg, #fee2e2, #fecaca);
}

.sidebar-score.score-none {
  color: #6b7280;
  background: transparent;
  font-weight: 500;
}

.sidebar-item:hover .sidebar-score.score-high {
  box-shadow: 0 2px 6px rgba(16, 185, 129, 0.2);
}

.sidebar-item:hover .sidebar-score.score-low {
  box-shadow: 0 2px 6px rgba(239, 68, 68, 0.2);
}

.sidebar-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.sidebar-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.sidebar-list::-webkit-scrollbar {
  width: 4px;
}
.sidebar-list::-webkit-scrollbar-track {
  background: transparent;
}
.sidebar-list::-webkit-scrollbar-thumb {
  background: var(--surface-200, #e2e8f0);
  border-radius: 4px;
}

/* ======= Main Content ======= */
.resource-main-content {
  order: 1;
  flex: 1;
  min-width: 0;
  height: 100%;
  overflow-y: auto;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 18px;
  padding: 22px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
}

.resource-main-content::-webkit-scrollbar {
  width: 4px;
}
.resource-main-content::-webkit-scrollbar-track {
  background: transparent;
}
.resource-main-content::-webkit-scrollbar-thumb {
  background: var(--surface-200, #e2e8f0);
  border-radius: 4px;
}

/* ======= Content Toolbar ======= */
.content-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  margin-bottom: 20px;
  background: #f8faff;
  border: 1px solid #dbeafe;
  border-radius: 14px;
  flex-wrap: wrap;
  position: sticky;
  top: 0;
  z-index: 10;
  margin-left: 0;
  margin-right: 0;
}

.gen-input-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.gen-btn-label {
  display: inline;
}
@media (max-width: 600px) {
  .gen-btn-label { display: none; }
}

.count-control {
  display: flex;
  align-items: center;
  gap: 8px;
}

.count-label {
  font-size: 14px;
  color: var(--surface-500, #64748b);
  font-weight: 500;
}

.content-toolbar .el-button--primary {
  background: linear-gradient(135deg, var(--primary-500, #6366f1), var(--primary-600, #4f46e5));
  border: none;
  border-radius: var(--radius-md, 8px);
  height: 36px;
  padding: 0 20px;
  font-weight: 500;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.3);
  transition: all 0.2s ease;
}

.content-toolbar .el-button--primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4);
}

/* ======= Resource Card (general) ======= */
.resource-card {
  transition: all 0.2s ease;
}

.resource-card:hover {
  box-shadow: var(--shadow-md, 0 4px 6px -1px rgba(0,0,0,0.07));
}

.resource-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--surface-100, #f1f5f9);
}

.resource-card-title-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.resource-card-title-row h3 {
  font-size: 17px;
  font-weight: 600;
  color: var(--surface-800, #1e293b);
  margin: 0;
  line-height: 1.4;
}

.resource-card-meta-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.resource-timing-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  color: #3b82f6;
  background: linear-gradient(135deg, #eff6ff, #dbeafe);
  border: 1px solid #bfdbfe;
  border-radius: 12px;
  padding: 1px 10px;
  white-space: nowrap;
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
  margin-left: 8px;
  white-space: nowrap;
  animation: timer-pulse 2s ease-in-out infinite;
}

@keyframes timer-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.resource-card-meta {
  font-size: 13px;
  color: var(--surface-400, #94a3b8);
}

.resource-card-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.resource-card-actions .el-button {
  font-size: 13px;
  padding: 0 10px;
  height: 28px;
  border-radius: 6px;
  color: var(--surface-500, #64748b);
  transition: all 0.2s ease;
}
.resource-card-actions .el-button:hover {
  color: var(--primary-600, #4f46e5);
  background: var(--primary-50, #eef2ff);
}

/* Streaming Card */
.streaming-card-header h3 {
  font-size: 17px;
  font-weight: 600;
  color: var(--surface-800, #1e293b);
  margin: 0 0 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--surface-100, #f1f5f9);
}

.resource-image {
  max-width: 100%;
  margin: 8px 0;
  border-radius: var(--radius-md, 8px);
  border: 1px solid var(--surface-200, #e2e8f0);
}

.resource-file-link {
  display: inline-block;
  margin: 8px 0;
}

.mindmap-section {
  margin: 12px 0;
}

.mindmap-link {
  display: inline-block;
  margin-top: 8px;
}

.mindmap-wrapper {
  position: relative;
  transform: none !important;
}

.mindmap-actions {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 2;
  display: flex;
  gap: 6px;
}

.mindmap-action-btn {
  font-size: 13px;
  padding: 0 12px;
  height: 28px;
  border-radius: 6px;
  color: var(--surface-500, #64748b);
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(4px);
  border: 1px solid var(--surface-100, #f1f5f9);
  transition: all 0.2s ease;
}
.mindmap-action-btn:hover {
  color: var(--primary-600, #4f46e5);
  background: #ffffff;
  border-color: var(--primary-200, #c7d2fe);
}
.mindmap-action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.video-results {
  margin: 18px auto 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  gap: 18px;
}

.video-card {
  width: 100%;
  max-width: min(100%, 1120px);
  margin: 0 auto;
  border: 1px solid rgba(203, 213, 225, 0.88);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 18px 45px rgba(15, 23, 42, 0.1);
  transition: box-shadow 0.2s ease, transform 0.2s ease, border-color 0.2s ease;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.98));
}

.video-card:hover {
  transform: translateY(-2px);
  border-color: rgba(129, 140, 248, 0.5);
  box-shadow: 0 22px 56px rgba(79, 70, 229, 0.16);
}

.video-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
}

.video-card-title {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.video-card-icon {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #3b82f6;
  background: linear-gradient(135deg, #eff6ff, #e0f2fe);
}

.video-card-title strong {
  display: block;
  max-width: 720px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 16px;
  color: #0f172a;
}

.video-card-title span:last-child {
  display: block;
  margin-top: 3px;
  font-size: 12px;
  color: #64748b;
}

.video-download-link {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 7px 12px;
  border-radius: 999px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
}

.video-player-shell {
  padding: 18px;
  background:
    radial-gradient(circle at 12% 0%, rgba(99, 102, 241, 0.18), transparent 32%),
    linear-gradient(135deg, #0f172a, #1e293b);
}

.resource-video {
  width: 100%;
  aspect-ratio: 16 / 9;
  max-height: min(62vh, 560px);
  display: block;
  object-fit: contain;
  background: #020617;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.36);
  box-shadow: 0 16px 36px rgba(2, 6, 23, 0.42);
}

.video-card :deep(.el-link) {
  margin: 0;
}

.video-status {
  margin-top: 12px;
}

.task-id-text {
  margin-top: 8px;
  font-size: 14px;
  color: var(--surface-400, #94a3b8);
}

/* ======= 教学视频 B站搜索模式样式 ======= */
.bili-results {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 18px;
  margin: 14px auto 0;
  width: 100%;
}

.bili-video-card {
  min-width: 0;
  border: 1px solid rgba(203, 213, 225, 0.86);
  border-radius: 14px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08);
  transition: box-shadow 0.2s ease, transform 0.2s ease, border-color 0.2s ease;
}

.bili-video-card:hover {
  transform: translateY(-2px);
  border-color: rgba(14, 165, 233, 0.45);
  box-shadow: 0 18px 44px rgba(14, 165, 233, 0.16);
}

.bili-video-player {
  padding: 12px 12px 0;
  background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
}

.bili-video-title {
  flex: 1;
  min-width: 0;
  font-weight: 600;
  font-size: 15px;
  padding: 0;
  color: var(--text-900, #0f172a);
  line-height: 1.5;
  min-height: 44px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.bili-video-iframe {
  width: 100%;
  aspect-ratio: 16 / 9;
  border: none;
  display: block;
  border-radius: 10px;
  background: #020617;
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.24);
}

.bili-video-info {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  background: #ffffff;
  padding: 12px 14px 0;
}

.bili-video-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 14px 14px;
  font-size: 12px;
  color: #64748b;
}

.bili-video-meta span {
  max-width: 100%;
  padding: 4px 9px;
  border-radius: 999px;
  background: #f1f5f9;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bili-expand-btn {
  flex: 0 0 auto;
  height: 30px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid #bfdbfe;
  background: #eff6ff;
  color: #3b82f6;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
}

.bili-expand-btn:hover {
  background: #3b82f6;
  border-color: #3b82f6;
  color: #ffffff;
  box-shadow: 0 10px 22px rgba(79, 70, 229, 0.22);
}

:global(.bili-player-dialog .el-dialog) {
  border-radius: 16px;
  overflow: hidden;
}

:global(.bili-player-dialog .el-dialog__header) {
  margin: 0;
  padding: 16px 20px;
  border-bottom: 1px solid #e2e8f0;
}

:global(.bili-player-dialog .el-dialog__title) {
  max-width: calc(100% - 48px);
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 700;
  color: #0f172a;
}

:global(.bili-player-dialog .el-dialog__body) {
  padding: 0;
  background: #0f172a;
}

.bili-player-modal {
  background: #0f172a;
}

.bili-player-modal-frame {
  width: 100%;
  aspect-ratio: 16 / 9;
  min-height: min(64vh, 640px);
  display: block;
  border: none;
  background: #020617;
}

.bili-player-modal-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 18px;
  font-size: 13px;
  color: #cbd5e1;
  background: linear-gradient(180deg, #111827, #0f172a);
}

.bili-search-hint {
  margin-top: 20px;
}

/* ======= Title Bar (exercise) ======= */
.quiz-title-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  padding-bottom: 14px;
  border-bottom: 2px solid transparent;
  border-image: linear-gradient(90deg, var(--primary-400, #818cf8), var(--primary-200, #c7d2fe), transparent) 1;
  position: relative;
}

.quiz-title-bar h2 {
  font-size: 18px;
  font-weight: 700;
  color: var(--surface-900, #0f172a);
  margin: 0;
  padding-left: 14px;
  border-left: 3px solid var(--primary-500, #6366f1);
  line-height: 1.4;
}

.question-list :deep(.el-alert.el-alert--info) {
  margin-top: 16px;
  border-radius: var(--radius-md, 8px);
  border: 1px solid #bae6fd;
  background: #f0f9ff;
}

.question-list :deep(.el-alert.el-alert--info .el-alert__title) {
  font-size: 14px;
}

/* ======= Question Card (shared) ======= */
.question-card {
  background: #ffffff;
  border: 1px solid var(--surface-100, #f1f5f9);
  border-radius: var(--radius-lg, 12px);
  padding: 20px 22px;
  margin-bottom: 16px;
  transition: all 0.25s ease;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  position: relative;
}

.question-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  background: linear-gradient(180deg, var(--primary-400, #818cf8), var(--primary-200, #c7d2fe));
  border-radius: 4px 0 0 4px;
  opacity: 0;
  transition: opacity 0.25s ease;
}

.question-card:hover {
  border-color: var(--primary-200, #c7d2fe);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.08);
}

.question-card:hover::before {
  opacity: 1;
}

.question-heading {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.question-number {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--primary-500, #6366f1), var(--primary-600, #4f46e5));
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  flex-shrink: 0;
  margin-top: 1px;
  box-shadow: 0 2px 6px rgba(99, 102, 241, 0.3);
}

.question-heading h3 {
  flex: 1;
  font-size: 15px;
  font-weight: 600;
  color: var(--surface-800, #1e293b);
  margin: 0;
  line-height: 1.6;
}

.question-heading :deep(.el-tag) {
  flex-shrink: 0;
  margin-top: 2px;
  border-radius: 20px;
  padding: 0 10px;
  font-weight: 500;
}

.question-options {
  padding: 4px 0 4px 42px;
}

.option-item {
  display: flex;
  margin-bottom: 10px;
  margin-right: 0;
  padding: 11px 16px;
  border-radius: var(--radius-md, 8px);
  border: 1px solid var(--surface-100, #f1f5f9);
  background: var(--surface-50, #f8fafc);
  transition: all 0.25s ease;
  width: 100%;
}

.option-item:hover {
  border-color: var(--primary-300, #c7d2fe);
  background: linear-gradient(135deg, #eff6ff, #f8faff);
  transform: translateX(2px);
}

.option-item :deep(.el-radio),
.option-item :deep(.el-checkbox) {
  margin-right: 0;
}

.option-item :deep(.el-radio.is-checked .el-radio__label),
.option-item :deep(.el-checkbox.is-checked .el-checkbox__label) {
  color: var(--primary-700, #4338ca);
  font-weight: 600;
}

.option-item :deep(.el-radio.is-checked .el-radio__inner),
.option-item :deep(.el-checkbox.is-checked .el-checkbox__inner) {
  border-color: var(--primary-500, #6366f1);
  background: var(--primary-500, #6366f1);
}

.option-item:last-child { margin-bottom: 0; }

.fill-input { padding: 0; }

.fill-input :deep(.el-textarea__inner) {
  border-radius: var(--radius-md, 8px);
  transition: all 0.2s ease;
}

.fill-input :deep(.el-textarea__inner:focus) {
  box-shadow: 0 0 0 1px var(--primary-500, #6366f1) inset;
}

/* ======= Hint ======= */
:deep(.hint-collapse) {
  margin-top: 12px;
  margin-left: 42px;
  border-radius: var(--radius-md, 8px);
  overflow: hidden;
  background: #fffbeb;
  border: 1px solid #fde68a;
}

:deep(.hint-collapse .el-collapse-item__header) {
  font-size: 14px;
  font-weight: 600;
  color: #92400e;
  padding: 0 12px;
  height: 36px;
  border-bottom: none;
  background: transparent;
}

:deep(.hint-collapse .el-collapse-item__wrap) {
  border-bottom: none;
  background: transparent;
}

:deep(.hint-collapse .el-collapse-item__content) {
  font-size: 14px;
  color: #78350f;
  line-height: 1.7;
  padding: 2px 12px 12px;
}

/* ======= Answer Explain ======= */
.answer-explain {
  margin-top: 16px;
  margin-left: 42px;
  padding: 16px 18px;
  background: #f8fafc;
  border: 1px solid var(--surface-100, #f1f5f9);
  border-radius: var(--radius-lg, 12px);
  border-left: 3px solid var(--primary-500, #6366f1);
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}

.answer-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
  font-size: 14px;
  line-height: 1.5;
}

.answer-row:last-child { margin-bottom: 0; }

.answer-label {
  flex-shrink: 0;
  min-width: 72px;
  font-weight: 600;
  color: var(--surface-600, #475569);
  font-size: 14px;
  padding: 3px 8px;
  background: var(--surface-100, #f1f5f9);
  border-radius: 4px;
  text-align: center;
}

.answer-value { color: var(--surface-700, #334155); flex: 1; padding-top: 2px; }
.answer-ref { color: var(--primary-600, #4f46e5); font-weight: 500; }
.answer-row-explain .answer-value {
  color: var(--surface-600, #475569);
  line-height: 1.7;
}

.answer-row:first-child .answer-label {
  background: transparent;
  padding: 0;
}

.answer-row:first-child .answer-value {
  padding-top: 0;
}

/* ======= Submit Bar ======= */
.submit-bar {
  text-align: center;
  padding: 20px 0 4px;
}

.draft-save-row {
  min-height: 32px;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.draft-save-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--surface-500, #64748b);
  font-size: 12px;
}

.draft-save-status.is-saved {
  color: #15803d;
}

.draft-save-status.is-failed,
.draft-save-status.is-dirty {
  color: #b45309;
}

.submit-bar .el-button--primary {
  background: linear-gradient(135deg, var(--primary-500, #6366f1), var(--primary-600, #4f46e5));
  border: none;
  border-radius: var(--radius-lg, 10px);
  padding: 0 40px;
  height: 46px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.5px;
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.35);
  transition: all 0.25s ease;
}

.submit-bar .el-button--primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.45);
}

.submit-bar .el-button--primary:active {
  transform: translateY(0);
}

/* ======= Result Alert ======= */
.result-summary-alert {
  margin-top: 18px;
}

.result-summary-alert :deep(.el-alert__content) {
  font-weight: 500;
}

/* ======= Coding Case ======= */
.coding-card h2 {
  font-size: 18px;
  font-weight: 700;
  color: var(--surface-900, #0f172a);
  margin: 0 0 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--surface-100, #f1f5f9);
}

.coding-prompt {
  font-size: 15px;
  color: var(--surface-700, #334155);
  line-height: 1.7;
  margin: 0 0 12px;
}

.coding-reqs {
  padding-left: 20px;
  margin: 0 0 16px;
}

.coding-reqs li {
  margin-bottom: 8px;
  color: var(--surface-700, #334155);
  line-height: 1.6;
}

.coding-answer-block {
  margin-top: 16px;
}

.coding-answer-label {
  display: inline-flex;
  align-items: center;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 700;
  color: var(--surface-800, #1e293b);
}

.coding-input :deep(.el-textarea__inner) {
  font-family: 'Cascadia Code', 'JetBrains Mono', 'Consolas', monospace;
  font-size: 14px;
  line-height: 1.6;
  border: 1.5px solid #94a3b8;
  border-radius: 10px;
  background: #ffffff;
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.12);
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

.coding-input :deep(.el-textarea__inner:hover) {
  border-color: #64748b;
}

.coding-input :deep(.el-textarea__inner:focus) {
  border-color: var(--primary-500, #6366f1);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.14), inset 0 0 0 1px rgba(99, 102, 241, 0.28);
}

.coding-result {
  margin-left: 0;
  margin-top: 16px;
}

.result-score {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-radius: var(--radius-md, 8px);
  margin-bottom: 14px;
}

.result-score.pass {
  background: linear-gradient(135deg, #d1fae5, #ecfdf5);
  color: #059669;
}

.result-score.fail {
  background: linear-gradient(135deg, #fee2e2, #fef2f2);
  color: #dc2626;
}

.result-score-num {
  font-size: 28px;
  font-weight: 800;
}

.result-score-label {
  font-size: 15px;
  font-weight: 600;
}

/* ======= Content Empty State ======= */
.content-empty {
  text-align: center;
  padding: 64px 20px;
}

.content-empty-icon {
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

.content-empty h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--surface-600, #475569);
  margin: 0 0 6px;
}

.content-empty p {
  font-size: 14px;
  color: var(--surface-400, #94a3b8);
  margin: 0;
  line-height: 1.6;
}

/* ======= Streaming ======= */
.streaming-card {
  position: relative;
}

.streaming-card h3 {
  padding-right: 80px;
}

.streaming-progress {
  display: inline-block;
  font-size: 13px;
  color: var(--primary-500, #6366f1);
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 20px;
  padding: 2px 12px;
  margin-bottom: 14px;
}
.streaming-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--primary-500, #6366f1);
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--surface-100, #f1f5f9);
}

/* ======= PPT Workbench Wrapper ======= */
.ppt-workbench-wrapper {
  flex: 0 0 auto;
  height: calc(100vh - 96px);
  min-height: 0;
  overflow: hidden;
}

/* ======= Responsive ======= */
@media (max-width: 1100px) {
  .agent-steps {
    flex-wrap: wrap;
    gap: 12px;
  }
  .agent-step {
    flex: 1 1 45%;
    min-width: 0;
  }
  .agent-step-tail {
    display: none;
  }
}

@media (max-width: 900px) {
  .resource-workbench {
    flex-direction: column;
    height: auto;
    min-height: calc(100vh - 96px);
  }
  .resource-history-sidebar {
    width: 100%;
    height: auto;
    max-height: 260px;
    padding: 18px 14px;
  }
  .resource-history-sidebar:hover { width: 100%; padding: 18px 14px; }
  .resource-history-sidebar:not(:hover) .sidebar-header { justify-content: flex-start; padding: 0 6px 14px; }
  .resource-history-sidebar:not(:hover) .sidebar-header span,
  .resource-history-sidebar:not(:hover) .sidebar-list { opacity: 1; pointer-events: auto; }
  .sidebar-list {
    overflow-y: auto;
  }
  .resource-main-content {
    height: auto;
    overflow: visible;
    min-height: calc(100vh - 220px);
  }
  .question-heading { flex-direction: column; gap: 8px; }
  .question-options { padding-left: 0; }
  :deep(.hint-collapse) { margin-left: 0; }
  .answer-explain { margin-left: 0; }
  .coding-result { margin-left: 0; }
  .resources-header { flex-direction: column; align-items: flex-start; gap: 12px; }
  .agent-steps { flex-direction: column; gap: 10px; }
  .agent-step { width: 100%; }
  .agent-step-tail { display: none; }
}

@media (max-width: 600px) {
  .resources-header { padding: 10px 14px; }
  .resources-page-title { font-size: 16px; }
  .resources-header-icon { width: 34px; height: 34px; }
  .resources-header-left { gap: 9px; }
  .resources-type-bar { padding: 8px 12px; }
  .resource-main-content { padding: 16px; }
  .content-toolbar { flex-direction: column; align-items: stretch; }
  .content-toolbar .el-input { max-width: 100% !important; }
  .gen-input-row { flex-direction: column; align-items: stretch; }
  .gen-input-row .el-select,
  .gen-input-row .el-input { max-width: 100% !important; width: 100% !important; }
  .question-card { padding: 14px 16px; }
  .resource-card-header { flex-direction: column; gap: 8px; }
  .resource-card-actions { align-self: flex-start; }
}

.innovation-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 18px;
}

.innovation-loading-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 18px;
  border-radius: 14px;
  border: 1px dashed rgba(99, 102, 241, 0.38);
  background: linear-gradient(135deg, rgba(248, 250, 252, 0.96), rgba(238, 242, 255, 0.92));
  box-shadow: 0 12px 28px rgba(79, 70, 229, 0.08);
}

.innovation-loading-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 12px;
  color: #3b82f6;
  background: rgba(99, 102, 241, 0.12);
  flex: 0 0 auto;
}

.innovation-loading-icon .el-icon {
  font-size: 22px;
}

.innovation-loading-text strong {
  display: block;
  font-size: 15px;
  color: #1e293b;
  margin-bottom: 4px;
}

.innovation-loading-text p {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: #64748b;
}

.innovation-error {
  border-radius: 12px;
}
</style>
