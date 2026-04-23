import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Injeta token em toda requisição e remove Content-Type para FormData
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  // Se o body for FormData, deixa o browser definir o Content-Type com o boundary correto
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type']
  }
  return config
})

// Redireciona para login em 401
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api
