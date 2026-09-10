<template>
  <div ref="editorHost" class="code-editor-host"></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { basicSetup } from 'codemirror'
import { EditorState } from '@codemirror/state'
import { EditorView, keymap } from '@codemirror/view'
import { python } from '@codemirror/lang-python'
import { cpp } from '@codemirror/lang-cpp'

const props = defineProps<{
  modelValue: string
  language: 'python' | 'c'
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  run: []
}>()

const editorHost = ref<HTMLDivElement | null>(null)
let editor: EditorView | null = null

const editorTheme = EditorView.theme({
  '&': {
    height: '100%',
    backgroundColor: '#161b22',
    color: '#e6edf3',
    fontSize: '14px',
  },
  '.cm-scroller': {
    overflow: 'auto',
    fontFamily: "'Cascadia Code', 'JetBrains Mono', Consolas, monospace",
    lineHeight: '1.65',
  },
  '.cm-content': {
    padding: '14px 0 28px',
    caretColor: '#7ee787',
  },
  '.cm-cursor': {
    borderLeftColor: '#7ee787',
  },
  '.cm-selectionBackground, &.cm-focused .cm-selectionBackground': {
    backgroundColor: '#264f78',
  },
  '.cm-gutters': {
    backgroundColor: '#161b22',
    color: '#6e7681',
    borderRight: '1px solid #30363d',
  },
  '.cm-activeLine': {
    backgroundColor: '#1f252d',
  },
  '.cm-activeLineGutter': {
    backgroundColor: '#1f252d',
    color: '#c9d1d9',
  },
  '&.cm-focused': {
    outline: 'none',
  },
})

function languageExtension() {
  return props.language === 'python' ? python() : cpp()
}

function createEditor() {
  if (!editorHost.value) return
  editor?.destroy()

  const state = EditorState.create({
    doc: props.modelValue,
    extensions: [
      basicSetup,
      EditorState.tabSize.of(4),
      EditorView.contentAttributes.of({ 'aria-label': '代码编辑器' }),
      languageExtension(),
      editorTheme,
      keymap.of([
        {
          key: 'Mod-Enter',
          run: () => {
            emit('run')
            return true
          },
        },
      ]),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          emit('update:modelValue', update.state.doc.toString())
        }
      }),
    ],
  })

  editor = new EditorView({
    state,
    parent: editorHost.value,
  })
}

watch(
  () => props.modelValue,
  (value) => {
    if (!editor) return
    const current = editor.state.doc.toString()
    if (current === value) return
    editor.dispatch({
      changes: {
        from: 0,
        to: current.length,
        insert: value,
      },
    })
  },
)

watch(() => props.language, createEditor)

onMounted(createEditor)
onBeforeUnmount(() => editor?.destroy())
</script>

<style scoped>
.code-editor-host {
  height: 100%;
  min-height: 360px;
  overflow: hidden;
}
</style>
