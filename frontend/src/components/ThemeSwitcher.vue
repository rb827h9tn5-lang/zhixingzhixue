<template>
  <el-dropdown trigger="click" @command="onCommand">
    <el-tooltip content="切换主题">
      <el-button circle :icon="Brush" aria-label="切换主题" />
    </el-tooltip>
    <template #dropdown>
      <el-dropdown-menu class="theme-menu">
        <el-dropdown-item
          v-for="theme in themes"
          :key="theme.key"
          :command="theme.key"
          :class="{ 'is-selected': currentTheme === theme.key }"
        >
          <span class="theme-swatch" :style="{ backgroundColor: theme.color }"></span>
          <span>{{ theme.label }}</span>
          <el-icon v-if="currentTheme === theme.key"><Check /></el-icon>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { Brush, Check } from '@element-plus/icons-vue'
import { useTheme, type ThemeKey } from '../composables/useTheme'

const { currentTheme, themes, applyTheme } = useTheme()

function onCommand(command: ThemeKey) {
  applyTheme(command)
}
</script>

<style scoped>
.theme-swatch {
  width: 14px;
  height: 14px;
  flex: 0 0 14px;
  border: 1px solid rgba(15, 23, 42, 0.16);
  border-radius: 3px;
}

:global(.theme-menu .el-dropdown-menu__item) {
  min-width: 132px;
  display: grid;
  grid-template-columns: 14px 1fr 16px;
  gap: 9px;
}

:global(.theme-menu .el-dropdown-menu__item.is-selected) {
  color: var(--color-primary);
  font-weight: 600;
}
</style>
