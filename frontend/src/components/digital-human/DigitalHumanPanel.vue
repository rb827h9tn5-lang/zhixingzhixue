<template>
  <section class="digital-human-panel">
    <header class="digital-human-header">
      <div>
        <div class="digital-human-title">
          <el-icon><Service /></el-icon>
          <h3>AI 错题精讲</h3>
          <el-tag size="small" effect="plain">AI 生成</el-tag>
        </div>
        <span v-if="scriptProvider" class="provider-label">讲稿：{{ scriptProvider }}</span>
      </div>

      <div class="digital-human-settings">
        <el-select
          :model-value="voice"
          size="small"
          class="voice-select"
          aria-label="语音讲解音色"
          @update:model-value="setVoice"
        >
          <el-option
            v-for="item in voices"
            :key="item.id"
            :label="`${item.label} · ${item.gender}`"
            :value="item.id"
          />
        </el-select>
        <el-select
          :model-value="rate"
          size="small"
          class="rate-select"
          aria-label="播放速度"
          @update:model-value="setRate"
        >
          <el-option label="0.8×" :value="0.8" />
          <el-option label="1.0×" :value="1" />
          <el-option label="1.2×" :value="1.2" />
          <el-option label="1.5×" :value="1.5" />
        </el-select>
        <el-tooltip v-if="lessons.length" content="重新生成讲稿">
          <el-button
            circle
            :icon="Refresh"
            aria-label="重新生成讲稿"
            :loading="status === 'loading'"
            @click="regenerate"
          />
        </el-tooltip>
      </div>
    </header>

    <div class="digital-human-body">
      <div class="lesson-stage">
        <template v-if="status === 'idle'">
          <div class="lesson-empty">
            <el-icon :size="30"><Service /></el-icon>
            <strong>{{ score >= 100 ? '生成本次测评总结' : '生成本次错题讲解' }}</strong>
            <el-button type="primary" :icon="MagicStick" @click="prepare(false)">
              生成错题讲解
            </el-button>
          </div>
        </template>

        <template v-else-if="status === 'loading' && !lessons.length">
          <div class="lesson-empty">
            <el-icon class="is-loading" :size="30"><Loading /></el-icon>
            <strong>MiMo 正在准备讲稿</strong>
          </div>
        </template>

        <template v-else-if="status === 'failed' && !lessons.length">
          <div class="lesson-empty is-error" role="alert">
            <el-icon :size="28"><WarningFilled /></el-icon>
            <strong>{{ errorMessage }}</strong>
            <el-button @click="prepare(false)">重试</el-button>
          </div>
        </template>

        <template v-else-if="currentLesson">
          <el-tabs
            :model-value="String(currentIndex)"
            class="lesson-tabs"
            @tab-change="onTabChange"
          >
            <el-tab-pane
              v-for="(lesson, index) in lessons"
              :key="lesson.question_id"
              :name="String(index)"
              :label="lesson.status === 'summary' ? '总结' : `第 ${lesson.question_number} 题`"
            />
          </el-tabs>

          <div class="lesson-scroll">
            <div class="lesson-heading">
              <div>
                <span class="lesson-concept">{{ currentLesson.concept }}</span>
                <h4>{{ currentLesson.question_summary }}</h4>
              </div>
              <el-tag
                :type="currentLesson.status === 'partial' ? 'warning' : currentLesson.status === 'summary' ? 'success' : 'danger'"
                effect="plain"
              >
                {{ lessonStatusLabel }}
              </el-tag>
            </div>

            <div v-if="currentLesson.status !== 'summary'" class="answer-compare">
              <div>
                <span>你的答案</span>
                <strong>{{ currentLesson.user_answer || '未作答' }}</strong>
              </div>
              <div>
                <span>参考答案</span>
                <strong>{{ currentLesson.reference_answer || '暂不可用' }}</strong>
              </div>
            </div>

            <div class="lesson-analysis">
              <strong>{{ currentLesson.mistake_reason }}</strong>
              <ol v-if="currentLesson.reasoning_steps.length">
                <li v-for="step in currentLesson.reasoning_steps" :key="step">{{ step }}</li>
              </ol>
              <p><span>记忆提示</span>{{ currentLesson.memory_tip }}</p>
            </div>

            <div class="subtitle-panel" aria-live="polite">
              <span>语音讲解</span>
              <p>{{ subtitleText || currentLesson.speech_text }}</p>
            </div>
          </div>

          <el-alert
            v-if="warningMessage"
            :title="warningMessage"
            type="warning"
            show-icon
            :closable="false"
            class="digital-human-warning"
          />

          <div class="speech-controls">
            <div class="progress-track">
              <span :style="{ width: `${progress}%` }"></span>
            </div>
            <div class="control-row">
              <div>
                <el-tooltip content="上一题">
                  <el-button
                    circle
                    :icon="ArrowLeft"
                    aria-label="上一题"
                    :disabled="!hasPrevious"
                    @click="previous"
                  />
                </el-tooltip>
                <el-tooltip content="重播">
                  <el-button circle :icon="RefreshLeft" aria-label="重播" @click="replay" />
                </el-tooltip>
              </div>

              <el-button
                v-if="status === 'playing'"
                class="primary-play"
                type="primary"
                circle
                :icon="VideoPause"
                aria-label="暂停讲解"
                @click="pause"
              />
              <el-button
                v-else
                class="primary-play"
                type="primary"
                circle
                :icon="VideoPlay"
                aria-label="播放讲解"
                :loading="status === 'loading'"
                @click="status === 'paused' ? resume() : play()"
              />

              <div>
                <el-tooltip content="停止">
                  <el-button circle :icon="Close" aria-label="停止讲解" @click="stop" />
                </el-tooltip>
                <el-tooltip content="下一题">
                  <el-button
                    circle
                    :icon="ArrowRight"
                    aria-label="下一题"
                    :disabled="!hasNext"
                    @click="next"
                  />
                </el-tooltip>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  ArrowLeft,
  ArrowRight,
  Close,
  Loading,
  MagicStick,
  Refresh,
  RefreshLeft,
  Service,
  VideoPause,
  VideoPlay,
  WarningFilled,
} from '@element-plus/icons-vue'
import { useDigitalHuman } from '../../composables/useDigitalHuman'

const props = defineProps<{
  resultId: number
  score: number
}>()

const {
  status,
  lessons,
  currentIndex,
  currentLesson,
  errorMessage,
  warningMessage,
  scriptProvider,
  voices,
  voice,
  rate,
  progress,
  subtitleText,
  hasPrevious,
  hasNext,
  loadStatus,
  prepare,
  play,
  pause,
  resume,
  replay,
  stop,
  previous,
  next,
  selectLesson,
  setRate,
  setVoice,
} = useDigitalHuman(toRef(props, 'resultId'))

const lessonStatusLabel = computed(() => {
  if (currentLesson.value?.status === 'partial') return '部分正确'
  if (currentLesson.value?.status === 'summary') return '全部正确'
  return '错题'
})

async function regenerate() {
  try {
    await ElMessageBox.confirm(
      '重新生成会再次调用 MiMo，并替换当前讲稿。',
      '重新生成讲解',
      { type: 'warning', confirmButtonText: '重新生成', cancelButtonText: '取消' },
    )
    await prepare(true)
  } catch {
    // 用户取消重新生成。
  }
}

function onTabChange(value: string | number) {
  selectLesson(Number(value))
}

onMounted(loadStatus)
</script>

<style scoped>
.digital-human-panel {
  margin-top: 22px;
  overflow: hidden;
  background: var(--color-panel-bg, #ffffff);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 8px;
}

.digital-human-header {
  min-height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--color-border, #e2e8f0);
}

.digital-human-title,
.digital-human-settings {
  display: flex;
  align-items: center;
}

.digital-human-title {
  gap: 8px;
}

.digital-human-title .el-icon {
  color: var(--color-primary, #0f766e);
}

.digital-human-title h3 {
  margin: 0;
  color: var(--color-text-primary, #0f172a);
  font-size: 16px;
  letter-spacing: 0;
}

.provider-label {
  display: block;
  margin-top: 2px;
  color: var(--color-text-muted, #94a3b8);
  font-size: 11px;
}

.digital-human-settings {
  gap: 8px;
}

.voice-select {
  width: 132px;
}

.rate-select {
  width: 82px;
}

.digital-human-body {
  min-height: 0;
}

.lesson-stage {
  min-width: 0;
  min-height: 300px;
  display: flex;
  flex-direction: column;
  padding: 0 18px 14px;
}

.lesson-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--color-text-secondary, #475569);
}

.lesson-empty > .el-icon {
  color: var(--color-primary, #0f766e);
}

.lesson-empty.is-error > .el-icon,
.lesson-empty.is-error strong {
  color: #b91c1c;
}

.lesson-tabs {
  flex: 0 0 auto;
}

.lesson-tabs :deep(.el-tabs__header) {
  margin-bottom: 10px;
}

.lesson-scroll {
  flex: 1;
  min-height: 0;
  padding-right: 4px;
}

.lesson-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.lesson-concept {
  color: var(--color-primary, #0f766e);
  font-size: 12px;
  font-weight: 600;
}

.lesson-heading h4 {
  margin: 4px 0 0;
  color: var(--color-text-primary, #0f172a);
  font-size: 15px;
  line-height: 1.55;
  letter-spacing: 0;
}

.answer-compare {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  margin-top: 12px;
  overflow: hidden;
  background: var(--color-border, #e2e8f0);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 6px;
}

.answer-compare > div {
  min-width: 0;
  padding: 9px 11px;
  background: var(--color-panel-bg, #ffffff);
}

.answer-compare span,
.subtitle-panel > span {
  display: block;
  color: var(--color-text-muted, #94a3b8);
  font-size: 11px;
}

.answer-compare strong {
  display: block;
  margin-top: 2px;
  color: var(--color-text-primary, #0f172a);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.lesson-analysis {
  margin-top: 12px;
  color: var(--color-text-secondary, #475569);
  font-size: 13px;
}

.lesson-analysis > strong {
  color: #b45309;
}

.lesson-analysis ol {
  margin: 7px 0 0;
  padding-left: 20px;
  line-height: 1.65;
}

.lesson-analysis p {
  margin: 8px 0 0;
}

.lesson-analysis p span {
  margin-right: 7px;
  color: var(--color-primary, #0f766e);
  font-weight: 600;
}

.subtitle-panel {
  margin-top: 12px;
  padding: 10px 12px;
  background: var(--color-primary-soft, #ecfdf5);
  border-left: 3px solid var(--color-primary, #0f766e);
}

.subtitle-panel p {
  min-height: 44px;
  margin: 4px 0 0;
  color: var(--color-text-primary, #0f172a);
  font-size: 14px;
  line-height: 1.65;
}

.digital-human-warning {
  margin-top: 10px;
}

.speech-controls {
  flex: 0 0 auto;
  margin-top: 10px;
}

.progress-track {
  height: 3px;
  overflow: hidden;
  background: var(--color-border, #e2e8f0);
}

.progress-track span {
  display: block;
  height: 100%;
  background: var(--color-primary, #0f766e);
  transition: width 140ms linear;
}

.control-row {
  min-height: 52px;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 12px;
}

.control-row > div {
  display: flex;
  align-items: center;
  gap: 8px;
}

.control-row > div:last-child {
  justify-content: flex-end;
}

.primary-play {
  width: 42px;
  height: 42px;
}

@media (max-width: 900px) {
  .digital-human-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .digital-human-settings {
    width: 100%;
  }

  .voice-select {
    flex: 1;
  }

}

@media (max-width: 700px) {
  .lesson-stage {
    min-height: 360px;
    padding-top: 4px;
  }

  .answer-compare {
    grid-template-columns: 1fr;
  }
}
</style>
