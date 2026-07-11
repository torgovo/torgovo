import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json'
  }
})

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export const login = async (credentials) => {
  const response = await api.post('/auth/login/', credentials)
  return response.data
}

export const register = async (userData) => {
  const response = await api.post('/auth/register/', userData)
  return response.data
}

export const logout = () => {
  const token = localStorage.getItem('refresh_token')
  if (token) {
    api.post('/auth/logout/', { refresh: token }).catch(() => {})
  }
}

export const getUserProfile = async () => {
  const response = await api.get('/users/profile/')
  return response.data
}

export default api
