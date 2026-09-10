/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_ENABLE_RESOURCE_TIMING: string
  readonly VITE_API_TIMEOUT_MS: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}