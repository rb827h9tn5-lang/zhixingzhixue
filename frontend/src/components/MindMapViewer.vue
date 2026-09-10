<template>
  <div class="mindmap-viewer">
    <!-- 加载状态 -->
    <div v-if="loading" class="mindmap-loading">
      <div class="loading-spinner"></div>
      <span>正在渲染思维导图...</span>
    </div>

    <!-- 渲染失败回退 -->
    <div v-if="renderingFailed" class="mindmap-fallback">
      <div class="fallback-notice">{{ fallbackNotice }}</div>
      <pre class="fallback-text">{{ fallbackText }}</pre>
    </div>

    <!-- 思维导图画布 -->
    <div v-show="!loading && !renderingFailed" class="mindmap-layout">
      <!-- 工具栏 -->
      <div class="mindmap-toolbar">
        <div class="toolbar-left">
          <el-button size="small" @click="zoomOut">缩小</el-button>
          <span class="zoom-level">{{ Math.round(scale * 100) }}%</span>
          <el-button size="small" @click="zoomIn">放大</el-button>
          <el-button size="small" @click="fit">适配画布</el-button>
        </div>
        <div class="toolbar-right">
          <el-button size="small" :icon="Picture" @click="exportPng">导出 PNG</el-button>
          <el-button size="small" :icon="Collection" @click="exportSvg">导出 SVG</el-button>
        </div>
      </div>
      <!-- 导图画布容器：mind-elixir 在此处渲染纯 HTML 节点 -->
      <div ref="mindmapContainerRef" class="mindmap-container"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch, nextTick } from 'vue'
import { Picture, Collection } from '@element-plus/icons-vue'
import MindElixir from 'mind-elixir'
import 'mind-elixir/style'

const props = defineProps<{
  data?: any
  content?: string
  height?: string
}>()

const loading = ref(false)
const renderingFailed = ref(false)
const fallbackText = ref('')
const fallbackNotice = ref('思维导图渲染失败，以下为文本内容：')
const scale = ref(1)

const mindmapContainerRef = ref<HTMLElement | null>(null)
let instance: any = null

// 分支颜色调色板
const PALETTE = [
  '#3b82f6',
  '#10b981',
  '#f59e0b',
  '#ec4899',
  '#8b5cf6',
  '#06b6d4',
  '#f97316',
  '#ef4444',
  '#84cc16',
  '#14b8a6',
]

// 自定义主题
const CUSTOM_THEME = {
  name: 'study-assistant',
  palette: PALETTE,
  cssVar: {
    '--node-gap-x': '30px',
    '--node-gap-y': '12px',
    '--main-gap-x': '80px',
    '--main-gap-y': '28px',
    '--main-color': '#3b82f6',
    '--main-bgcolor': '#ffffff',
    '--root-color': '#ffffff',
    '--root-bgcolor': '#4F46E5',
    '--root-border-color': '#4F46E5',
    '--root-radius': '8px',
    '--color': '#111827',
    '--bgcolor': '#ffffff',
    '--selected': '#dbeafe',
    '--topic-padding': '6px 14px',
    '--main-radius': '8px',
    '--panel-color': '#111827',
    '--panel-bgcolor': '#ffffff',
    '--panel-border-color': '#dde5f3',
  },
}

// ─── 数据格式转换 ───

/** 将简单的 { text, children } 树转换为 mind-elixir 的 NodeObj 格式 */
function toMindElixirNode(simpleNode: any, paletteIdx = 0, depth = 0): any {
  if (!simpleNode) return null
  const text = simpleNode.text || simpleNode.topic || simpleNode.label || '节点'
  const result: any = {
    topic: text,
    id: `node_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    children: [],
  }
  if (depth > 0) {
    result.branchColor = PALETTE[paletteIdx % PALETTE.length]
  }

  if (Array.isArray(simpleNode.children)) {
    result.children = simpleNode.children
      .map((child: any, idx: number) => toMindElixirNode(child, depth === 0 ? idx : paletteIdx, depth + 1))
      .filter(Boolean)
  }
  return result
}

/** 将后端返回的简单树 JSON 转换为 mind-elixir 初始化数据 */
function buildMindElixirData(input: any): any {
  // 支持多种输入格式
  const raw = input?.root || input?.mindmap || input?.tree || input
  if (!raw || typeof raw !== 'object') return null

  // 根节点若有 text 字段，即认为有效
  if (!raw.text && !raw.topic && !raw.label) return null

  const rootNode = toMindElixirNode(raw, 0)
  if (!rootNode) return null

  return {
    nodeData: rootNode,
    direction: MindElixir.SIDE,
  }
}

/** 从 JSON 字符串或嵌套对象中提取原始树数据 */
function extractTreeData(input: any): any {
  if (!input) return null

  // 如果是字符串，尝试 JSON 解析
  if (typeof input === 'string') {
    try {
      // 尝试提取 JSON 代码块
      const mermaidMatch = input.match(/```(?:mermaid)?\s*([\s\S]*?)```/i)
      if (mermaidMatch) return extractTreeData(mermaidMatch[1])

      // 尝试直接 JSON 解析
      const parsed = JSON.parse(input)
      return extractTreeData(parsed)
    } catch {
      // 不是 JSON，尝试解析 Mermaid mindmap 文本
      return parseMermaidToTree(input)
    }
  }

  // 如果是数组（扁平节点列表），先转成树
  if (Array.isArray(input)) {
    return convertFlatNodesToTree(input)
  }

  // 已经是对象：尝试提取嵌套的 root/mindmap/tree
  return input
}

/** 将 Mermaid mindmap 文本解析为简单树 JSON */
function parseMermaidToTree(text: string): any {
  const lines = text.split(/\r?\n/).filter(l => l.trim())
  const startIdx = lines.findIndex(l => /^```/.test(l.trim()))
  const endIdx = startIdx >= 0
    ? lines.slice(startIdx + 1).findIndex(l => /^```/.test(l.trim()))
    : -1
  const mermaidLines = startIdx >= 0 && endIdx >= 0
    ? lines.slice(startIdx + 1, startIdx + 1 + endIdx)
    : lines

  // 找到 mindmap 起始行
  const mmIdx = mermaidLines.findIndex(l => l.trim().toLowerCase() === 'mindmap')
  if (mmIdx < 0) return null

  const content = mermaidLines.slice(mmIdx + 1)
  if (!content.length) return null

  // 提取 root 节点
  const rootLine = content.find(l => /^\s*root\s*/.test(l.trim()))
  let rootText = '思维导图'
  if (rootLine) {
    const match = rootLine.match(/\(\((.+?)\)\)/)
    if (match) rootText = match[1].trim()
  }

  // 解析缩进构建树
  interface LineItem { level: number; text: string }
  const items: LineItem[] = []
  for (const line of content) {
    const trimmed = line.trim()
    if (!trimmed || /^root\s*/.test(trimmed)) continue
    const indent = line.search(/\S/)
    const cleanText = trimmed
      .replace(/^[\(\[\{]+|[\)\]\}]+$/g, '')
      .replace(/<\s*br\s*\/?\s*>/gi, ' ')
      .replace(/<[^>]+>/g, ' ')
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/^[#\s\-*+\d.、]+/, '')
      .replace(/\s+/g, ' ')
      .trim()
    if (!cleanText) continue
    items.push({ level: Math.floor(indent / 2), text: cleanText })
  }

  if (!items.length) return null

  const minLevel = Math.min(...items.map(i => i.level))
  const normalized = items.map(i => ({ ...i, level: i.level - minLevel + 1 }))

  // 构建嵌套树
  function buildTree(levelItems: LineItem[], startLevel: number): any[] {
    const result: any[] = []
    let i = 0
    while (i < levelItems.length) {
      if (levelItems[i].level === startLevel) {
        const node: any = { text: levelItems[i].text, children: [] }
        i++
        // 收集当前节点的子节点（层级更大的项）
        const children: LineItem[] = []
        while (i < levelItems.length && levelItems[i].level > startLevel) {
          children.push(levelItems[i])
          i++
        }
        if (children.length) {
          node.children = buildTree(children, startLevel + 1)
        }
        result.push(node)
      } else {
        i++
      }
    }
    return result
  }

  const children = buildTree(normalized, 1)
  return { text: rootText, children }
}

/** 将扁平节点列表转换为树 */
function convertFlatNodesToTree(nodes: any[]): any {
  if (!nodes.length) return null
  const map = new Map<string, any>()
  const roots: any[] = []

  nodes.forEach((item, index) => {
    const id = String(item.id ?? item.uid ?? item.key ?? index)
    map.set(id, { text: item.text || item.label || item.topic || item.name || '节点', children: [] })
  })

  nodes.forEach((item, index) => {
    const id = String(item.id ?? item.uid ?? item.key ?? index)
    const node = map.get(id)
    const parentId = item.parent_id ?? item.parentId ?? item.pid ?? item.parent
    if (parentId !== undefined && parentId !== null && map.has(String(parentId))) {
      map.get(String(parentId)).children.push(node)
    } else {
      roots.push(node)
    }
  })

  if (!roots.length) return null
  if (roots.length === 1) return roots[0]
  return { text: '思维导图', children: roots }
}

// ─── 渲染 ───

function initMindElixir(el: HTMLElement, data: any) {
  // 保留已存在的实例
  if (instance) {
    instance.refresh(data)
    instance.toCenter()
    return
  }

  // 创建新实例
  instance = new MindElixir({
    el,
    direction: MindElixir.SIDE,
    editable: false,
    contextMenu: false,
    toolBar: false,
    keypress: false,
    allowUndo: false,
    theme: CUSTOM_THEME,
    scaleSensitivity: 0.1,
    scaleMin: 0.3,
    scaleMax: 2,
    overflowHidden: false,
  })

  // 初始化
  const err = instance.init(data)
  if (err) {
    throw new Error(`mind-elixir 初始化失败: ${err.message || err}`)
  }

  // 居中显示
  instance.toCenter()

  // 监听缩放变化
  instance.bus.addListener('scale', (s: number) => {
    scale.value = s
  })
}

function destroyMindElixir() {
  if (instance) {
    instance.destroy()
    instance = null
  }
}

async function renderMindMap() {
  // 从 data prop 中提取树数据
  const source = props.data || props.content
  if (!source) {
    renderingFailed.value = true
    fallbackText.value = '无内容'
    return
  }

  loading.value = true
  renderingFailed.value = false

  try {
    const tree = extractTreeData(source)
    const mindData = buildMindElixirData(tree)
    if (!mindData) {
      throw new Error('无法解析思维导图数据')
    }

    await nextTick()
    loading.value = false
    await nextTick()

    // 等待容器渲染
    if (mindmapContainerRef.value && mindmapContainerRef.value.offsetWidth === 0) {
      await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
    }

    if (!mindmapContainerRef.value) throw new Error('容器元素不存在')

    initMindElixir(mindmapContainerRef.value, mindData)
  } catch (e: any) {
    console.error('思维导图渲染失败:', e)
    renderingFailed.value = true
    fallbackNotice.value = '思维导图渲染失败，以下为原始内容：'
    fallbackText.value = typeof source === 'string' ? source : JSON.stringify(source, null, 2)
    loading.value = false
  }
}

// ─── 导出方法 ───

async function exportSvg() {
  if (!instance) return
  try {
    const blob = await instance.exportSvg()
    if (!blob) { console.warn('导出 SVG 返回空'); return }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = '思维导图.svg'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error('导出 SVG 失败:', e)
  }
}

async function exportPng() {
  if (!instance) return
  try {
    const blob = await instance.exportPng()
    if (!blob) { console.warn('导出 PNG 返回空'); return }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = '思维导图.png'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error('导出 PNG 失败:', e)
  }
}

// ─── 视图操作 ───

function zoomIn() {
  if (!instance) return
  const s = Math.min(instance.scaleVal + 0.15, 2)
  instance.scale(s)
}

function zoomOut() {
  if (!instance) return
  const s = Math.max(instance.scaleVal - 0.15, 0.3)
  instance.scale(s)
}

function fit() {
  if (!instance) return
  instance.scaleFit()
  setTimeout(() => instance.toCenter(), 100)
}

// ─── 生命周期 ───

onMounted(() => {
  renderMindMap()
})

onUnmounted(() => {
  destroyMindElixir()
})

watch(() => props.data, () => {
  renderMindMap()
}, { deep: false })

defineExpose({
  fit,
  zoomIn,
  zoomOut,
  exportSvg,
  exportPng,
  getInstance: () => instance,
})
</script>

<style scoped>
.mindmap-viewer {
  margin: 12px 0;
  border-radius: 12px;
  border: 1px solid var(--surface-200, #e2e8f0);
  overflow: hidden;
  background: #ffffff;
}

.mindmap-layout {
  display: flex;
  flex-direction: column;
  min-height: 620px;
}

/* ── 工具栏 ── */
.mindmap-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  border-bottom: 1px solid var(--surface-100, #f1f5f9);
  background: #fafbfc;
  flex-shrink: 0;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.zoom-level {
  font-size: 13px;
  color: var(--surface-500, #64748b);
  min-width: 48px;
  text-align: center;
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}

/* ── 画布容器 ── */
.mindmap-container {
  flex: 1;
  min-height: 560px;
  position: relative;
  overflow: hidden;
  background: #ffffff;
  /* mind-elixir 在此容器内创建纯 HTML 节点和 SVG 连线 */
}

/* 根节点文字加粗 */
.mindmap-container :deep(.mind-elixir .root :is(.topic, .topic-text)) {
  font-weight: 700 !important;
}

/* 子节点文字加粗 */
.mindmap-container :deep(.mind-elixir .topic-text) {
  font-weight: 500 !important;
  color: #111827 !important;
}

/* 节点 box 阴影精细 */
.mindmap-container :deep(.mind-elixir .topic) {
  box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
}

/* 确保容器高度不受SCSS影响 */
.mindmap-container :deep(.mind-elixir) {
  width: 100%;
  height: 100%;
}

/* ── 加载状态 ── */
.mindmap-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 60px 20px;
  color: var(--surface-500, #64748b);
  font-size: 14px;
}

.loading-spinner {
  width: 18px;
  height: 18px;
  border: 2.5px solid var(--surface-200, #e2e8f0);
  border-top-color: var(--primary-500, #6366f1);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ── 回退显示 ── */
.mindmap-fallback {
  padding: 16px 20px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 12px;
}

.fallback-notice {
  font-size: 14px;
  color: #92400e;
  margin-bottom: 12px;
  font-weight: 500;
}

.fallback-text {
  margin: 0;
  padding: 16px;
  background: #fefce8;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  color: #713f12;
  max-height: 400px;
  overflow-y: auto;
}
</style>
