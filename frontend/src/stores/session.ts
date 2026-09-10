import { defineStore } from 'pinia'
import { api } from '../api/learning'

type User = {
  id: number
  username: string
  role: string
  email?: string
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    token: localStorage.getItem('study_token') || '',
    user: null as User | null
  }),
  actions: {
    async login(username: string, password: string) {
      const { data } = await api.login({ username, password })
      this.setSession(data.token, data.user)
      localStorage.removeItem('study_recommended_tasks')
      localStorage.setItem('study_tasks_force_refresh', '1')
      try {
        await api.resetTasks()
      } catch {
        // 登录接口已清理后端记录，这里作为前端同步兜底。
      }
    },
    async register(username: string, password: string) {
      const { data } = await api.register({ username, password })
      this.setSession(data.token, data.user)
      localStorage.removeItem('study_recommended_tasks')
      localStorage.setItem('study_tasks_force_refresh', '1')
    },
    async loadMe() {
      if (!this.token) return
      const { data } = await api.me()
      this.user = data.user
    },
    setSession(token: string, user: User) {
      this.token = token
      this.user = user
      localStorage.setItem('study_token', token)
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('study_token')
    }
  }
})
