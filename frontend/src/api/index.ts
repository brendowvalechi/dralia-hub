import api from './client'
import type { Campaign, CampaignList, DashboardOverview, DeliveryReport, Instance, LastMessage, Lead, LeadList, MessageSeries, User } from '../types'

// ── Auth ────────────────────────────────────────────────────────────────────
export const login = (email: string, password: string) =>
  api.post<{ access_token: string }>('/auth/login', { email, password })

export const getMe = () => api.get<User>('/auth/me')

// ── Leads ───────────────────────────────────────────────────────────────────
export const getLeadTags = () => api.get<string[]>('/leads/tags')

export const getLeads = (params?: { page?: number; page_size?: number; status?: string; search?: string; tag?: string }) =>
  api.get<LeadList>('/leads', { params })

export const getLead = (id: string) => api.get<Lead>(`/leads/${id}`)

export const createLead = (data: Partial<Lead> & { phone: string }) =>
  api.post<Lead>('/leads', data)

export const updateLead = (id: string, data: Partial<Lead>) =>
  api.put<Lead>(`/leads/${id}`, data)

export const deleteLead = (id: string) => api.delete(`/leads/${id}`)

export const importLeads = (file: File, updateExisting = false, group?: string) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/leads/import', form, {
    params: { update_existing: updateExisting, ...(group ? { group } : {}) },
  })
}

export const getLeadLastMessage = (id: string) =>
  api.get<LastMessage>(`/leads/${id}/last-message`)

// ── Mídia ────────────────────────────────────────────────────────────────────
export const uploadMedia = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.post<{ url: string; media_type: string; filename: string; original_filename: string; size_mb: number }>(
    '/media/upload',
    form,
  )
}

// ── Instâncias ──────────────────────────────────────────────────────────────
export const getInstances = () => api.get<Instance[]>('/instances')

export const getInstance = (id: string) => api.get<Instance>(`/instances/${id}`)

export const createInstance = (data: { display_name: string; evolution_instance_name: string; daily_limit: number }) =>
  api.post<Instance>('/instances', data)

export const updateInstance = (id: string, data: Partial<Instance>) =>
  api.put<Instance>(`/instances/${id}`, data)

export const deleteInstance = (id: string) => api.delete(`/instances/${id}`)

export const syncInstance = (id: string) => api.post<Instance>(`/instances/${id}/sync`)

export const getQRCode = (id: string) => api.get(`/instances/${id}/qrcode`)

export const logoutInstance = (id: string) => api.post<Instance>(`/instances/${id}/logout`)

// ── Campanhas ───────────────────────────────────────────────────────────────
export const getCampaigns = (params?: { page?: number; page_size?: number; status?: string }) =>
  api.get<CampaignList>('/campaigns', { params })

export const getCampaign = (id: string) => api.get<Campaign>(`/campaigns/${id}`)

export const createCampaign = (data: Partial<Campaign>) => api.post<Campaign>('/campaigns', data)

export const updateCampaign = (id: string, data: Partial<Campaign>) =>
  api.put<Campaign>(`/campaigns/${id}`, data)

export const deleteCampaign = (id: string) => api.delete(`/campaigns/${id}`)

export const launchCampaign = (id: string) => api.post<Campaign>(`/campaigns/${id}/launch`)

export const pauseCampaign = (id: string) => api.post<Campaign>(`/campaigns/${id}/pause`)

export const resumeCampaign = (id: string) => api.post<Campaign>(`/campaigns/${id}/resume`)

export const getCampaignDeliveryReport = (id: string) =>
  api.get<DeliveryReport>(`/campaigns/${id}/delivery-report`)

// ── Dashboard ───────────────────────────────────────────────────────────────
export const getDashboardOverview = () => api.get<DashboardOverview>('/dashboard/overview')

export const getDashboardMessages = (days = 7) =>
  api.get<{ days: number; since: string; series: MessageSeries[] }>('/dashboard/messages', { params: { days } })

export const getDashboardCampaigns = (limit = 10) =>
  api.get('/dashboard/campaigns', { params: { limit } })

// ── Segmentos ────────────────────────────────────────────────────────────────
export const getSegments = () => api.get('/segments')
export const createSegment = (data: { name: string; filters: Record<string, unknown> }) =>
  api.post('/segments', data)
export const deleteSegment = (id: string) => api.delete(`/segments/${id}`)
export const refreshSegment = (id: string) => api.post(`/segments/${id}/refresh`)

// ── Usuários ─────────────────────────────────────────────────────────────────
export const getUsers = () => api.get('/users')
export const createUser = (data: { email: string; password: string; role: string }) =>
  api.post('/users', data)
export const deleteUser = (id: string) => api.delete(`/users/${id}`)
