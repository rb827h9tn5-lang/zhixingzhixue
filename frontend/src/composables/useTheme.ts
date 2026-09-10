import { ref } from 'vue'

export type ThemeKey = 'ocean' | 'mint' | 'sunset' | 'violet'

export const themes: Array<{
  key: ThemeKey
  label: string
  color: string
}> = [
  { key: 'ocean', label: '云海蓝', color: '#2563eb' },
  { key: 'mint', label: '青柠绿', color: '#059669' },
  { key: 'sunset', label: '暖阳橙', color: '#ea580c' },
  { key: 'violet', label: '星云紫', color: '#9333ea' },
]

const STORAGE_KEY = 'zhixing-theme'
const validThemes = new Set<ThemeKey>(themes.map(item => item.key))
const currentTheme = ref<ThemeKey>('ocean')

export function applyTheme(theme: ThemeKey) {
  const next = validThemes.has(theme) ? theme : 'ocean'
  currentTheme.value = next
  document.documentElement.dataset.theme = next
  localStorage.setItem(STORAGE_KEY, next)
}

export function restoreTheme() {
  const saved = localStorage.getItem(STORAGE_KEY) as ThemeKey | null
  applyTheme(saved && validThemes.has(saved) ? saved : 'ocean')
}

export function useTheme() {
  return {
    currentTheme,
    themes,
    applyTheme,
  }
}
