export interface User {
  id: string
  email: string
  role: 'admin' | 'operator' | 'viewer'
  is_active: boolean
  created_at: string
  last_login: string | null
}

export interface Lead {
  id: string
  phone: string
  name: string | null
  email: string | null
  tags: string[]
  custom_fields: Record<string, string>
  source: string
  status: 'active' | 'inactive' | 'opted_out' | 'blacklisted'
  opt_in_date: string | null
  opt_out_date: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface LeadList {
  total: number
  page: number
  page_size: number
  items: Lead[]
}

export interface Instance {
  id: string
  phone_number: string | null
  display_name: string
  evolution_instance_name: string
  status: 'connected' | 'disconnected' | 'warming_up' | 'banned' | 'quarantine'
  health_score: number
  daily_limit: number
  daily_sent: number
  warmup_day: number | null
  ban_count: number
  last_connected_at: string | null
  last_disconnected_at: string | null
  created_at: string
  updated_at: string
}

export interface Campaign {
  id: string
  name: string
  user_id: string
  segment_id: string | null
  message_template: string
  media_url: string | null
  media_type: 'image' | 'video' | 'audio' | 'document' | null
  status: 'draft' | 'scheduled' | 'running' | 'paused' | 'completed' | 'failed'
  lead_group: string | null
  allowed_instances: string[] | null
  scheduled_at: string | null
  started_at: string | null
  completed_at: string | null
  total_leads: number
  sent_count: number
  delivered_count: number
  read_count: number
  failed_count: number
  created_at: string
  updated_at: string
}

export interface DeliveryMessage {
  message_id: string
  lead_id: string
  lead_name: string | null
  lead_phone: string
  status: string
  sent_at: string | null
  failure_reason: string | null
}

export interface DeliveryReport {
  campaign_id: string
  campaign_name: string
  status: string
  total_leads: number
  summary: Record<string, number>
  delivery_rate_pct: number
  messages: DeliveryMessage[]
}

export interface CampaignList {
  total: number
  page: number
  page_size: number
  items: Campaign[]
}

export interface DashboardOverview {
  leads: { total: number; active: number; opted_out: number }
  campaigns: { total: number; running: number; completed: number }
  instances: { total: number; connected: number }
  messages: { total: number; sent: number; delivered: number; failed: number; delivery_rate_pct: number }
}

export interface MessageSeries {
  date: string
  total: number
  sent: number
  delivered: number
  failed: number
}

export interface LastMessage {
  found: boolean
  content?: string
  sent_at?: string
  status?: string
  campaign_id?: string | null
}
