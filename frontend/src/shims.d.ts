declare module 'vue-router'

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}

declare namespace JSX {
  interface IntrinsicElements {
    [elem: string]: unknown
  }
}
