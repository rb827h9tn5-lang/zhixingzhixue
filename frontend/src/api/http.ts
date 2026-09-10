import axios from 'axios'

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 300000
})

// 登录/注册专用实例：不触发 auth-expired 事件
export const authHttp = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 300000
})

// authHttp 的响应拦截器：只提取后端消息，不触发 token 过期事件
authHttp.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.message || error.message || '请求失败'
    return Promise.reject(new Error(message))
  }
)

let authExpiredDispatched = false

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('study_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    if (status === 401 || status === 422) {
      localStorage.removeItem('study_token')
      if (!authExpiredDispatched) {
        authExpiredDispatched = true
        window.dispatchEvent(new Event('auth-expired'))
      }
    }
    const message = error.response?.data?.message || error.message || '请求失败'
    return Promise.reject(new Error(message))
  }
)
