import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getCampaigns, createCampaign, deleteCampaign, launchCampaign, pauseCampaign, resumeCampaign, updateCampaign, uploadMedia, getInstances, getCampaignDeliveryReport, getLeadTags } from '../api'
import { Plus, Play, Pause, RotateCcw, Trash2, ChevronRight, Pencil, Check, X, Mic, Upload, Clock, BarChart2, Users, Cpu } from 'lucide-react'
import type { Campaign, DeliveryReport } from '../types'

const STATUS_BADGE: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-500',
  running: 'bg-green-100 text-green-700',
  paused: 'bg-yellow-100 text-yellow-700',
  completed: 'bg-blue-100 text-blue-700',
  failed: 'bg-red-100 text-red-700',
  scheduled: 'bg-purple-100 text-purple-700',
}

const STATUS_LABEL: Record<string, string> = {
  draft: 'Rascunho',
  running: 'Executando',
  paused: 'Pausada',
  completed: 'Concluída',
  failed: 'Falhou',
  scheduled: 'Agendada',
}

function ProgressBar({ sent, total }: { sent: number; total: number }) {
  const pct = total > 0 ? Math.round((sent / total) * 100) : 0
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-gray-100 rounded-full h-1.5">
        <div className="h-1.5 rounded-full bg-indigo-500" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-500 w-16 text-right">{sent}/{total}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Estimativa de conclusão — baseada no delay anti-ban de 15–90s entre mensagens
// ---------------------------------------------------------------------------
const MIN_DELAY_S = 15   // delay mínimo real (antiban_engine.py)
const MAX_DELAY_S = 90   // delay máximo real

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h === 0) return `${m} min`
  return `${h}h ${m > 0 ? `${m} min` : ''}`.trim()
}

function EtaEstimate({ camp }: { camp: Campaign }) {
  const processed = camp.sent_count + camp.failed_count
  const remaining = Math.max(0, camp.total_leads - processed)

  if (remaining === 0 || camp.status !== 'running') return null

  const minSeconds = remaining * MIN_DELAY_S
  const maxSeconds = remaining * MAX_DELAY_S

  const minStr = formatDuration(minSeconds)
  const maxStr = formatDuration(maxSeconds)

  return (
    <div className="flex items-start gap-1.5 mt-2 text-xs text-gray-400">
      <Clock size={11} className="mt-0.5 flex-shrink-0 text-indigo-400" />
      <span>
        <span className="text-gray-600 font-medium">
          Término estimado: {minStr} – {maxStr}
        </span>
        {' '}· O sistema aguarda entre 15–90 segundos entre cada envio para não ser bloqueado pelo WhatsApp. O tempo real depende dessa variação.
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tag Autocomplete
// ---------------------------------------------------------------------------
function TagAutocomplete({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const { data: allTags = [] } = useQuery({
    queryKey: ['lead-tags'],
    queryFn: () => getLeadTags().then(r => r.data),
    staleTime: 60_000,
  })

  const filtered = allTags.filter(t =>
    t.toLowerCase().includes(value.toLowerCase()) && t !== value
  )

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div className="relative" ref={containerRef}>
      <input
        value={value}
        onChange={e => { onChange(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        autoComplete="off"
        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        placeholder="ex: instagram, clientes-vip"
      />
      {open && filtered.length > 0 && (
        <div className="absolute z-20 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-40 overflow-y-auto">
          {filtered.map(tag => (
            <button
              key={tag}
              type="button"
              onMouseDown={e => e.preventDefault()}
              onClick={() => { onChange(tag); setOpen(false) }}
              className="w-full text-left px-3 py-2 text-sm hover:bg-indigo-50 hover:text-indigo-700"
            >
              {tag}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

const EMPTY_FORM = {
  name: '',
  message_template: '',
  scheduled_at: '',
  audio_url: '',
  audio_filename: '',
  lead_group: '',
  allowed_instances: [] as string[],
}

// ---------------------------------------------------------------------------
// Delivery Report Modal
// ---------------------------------------------------------------------------
const STATUS_COLOR: Record<string, string> = {
  sent: 'text-blue-600',
  delivered: 'text-green-600',
  read: 'text-green-700',
  failed: 'text-red-500',
  sending: 'text-yellow-500',
}

function DeliveryReportModal({ campaignId, onClose }: { campaignId: string; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ['delivery-report', campaignId],
    queryFn: () => getCampaignDeliveryReport(campaignId).then(r => r.data),
  })

  const report = data as DeliveryReport | undefined

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[85vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-800">Relatório de entrega</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>

        {isLoading ? (
          <div className="flex-1 flex items-center justify-center py-12 text-gray-400 text-sm">Carregando...</div>
        ) : report ? (
          <>
            <div className="px-6 py-4 border-b border-gray-100">
              <p className="text-sm font-medium text-gray-700 mb-3">{report.campaign_name}</p>
              <div className="grid grid-cols-5 gap-3">
                {(['sent','delivered','read','failed','sending'] as const).map(s => (
                  <div key={s} className="text-center bg-gray-50 rounded-xl py-3">
                    <p className={`text-xl font-bold ${STATUS_COLOR[s] ?? 'text-gray-600'}`}>{report.summary[s] ?? 0}</p>
                    <p className="text-xs text-gray-400 capitalize mt-0.5">{s === 'sent' ? 'Enviados' : s === 'delivered' ? 'Entregues' : s === 'read' ? 'Lidos' : s === 'failed' ? 'Falhas' : 'Enviando'}</p>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex items-center gap-2">
                <div className="flex-1 bg-gray-100 rounded-full h-2">
                  <div className="h-2 rounded-full bg-green-500 transition-all" style={{ width: `${report.delivery_rate_pct}%` }} />
                </div>
                <span className="text-sm font-medium text-green-600">{report.delivery_rate_pct}% confirmados</span>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-3">
              <p className="text-xs text-gray-400 mb-2 font-medium">{report.messages.length} mensagens</p>
              <div className="space-y-1.5">
                {report.messages.map(m => (
                  <div key={m.message_id} className="flex items-center gap-3 py-2 px-3 rounded-lg hover:bg-gray-50">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-700 font-medium truncate">{m.lead_name || m.lead_phone}</p>
                      {m.lead_name && <p className="text-xs text-gray-400">{m.lead_phone}</p>}
                      {m.failure_reason && <p className="text-xs text-red-400 truncate">{m.failure_reason}</p>}
                    </div>
                    <div className="text-right flex-shrink-0">
                      <span className={`text-xs font-medium ${STATUS_COLOR[m.status] ?? 'text-gray-500'}`}>
                        {m.status === 'sent' ? 'Enviado' : m.status === 'delivered' ? 'Entregue' : m.status === 'read' ? 'Lido' : m.status === 'failed' ? 'Falha' : m.status}
                      </span>
                      {m.sent_at && (
                        <p className="text-xs text-gray-400">{new Date(m.sent_at).toLocaleString('pt-BR', { day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit' })}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center py-12 text-gray-400 text-sm">Sem dados disponíveis.</div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Inline edit form for draft campaigns
// ---------------------------------------------------------------------------
function InlineEditForm({
  camp,
  onSave,
  onCancel,
  isSaving,
}: {
  camp: Campaign
  onSave: (data: { name: string; message_template: string; scheduled_at?: string }) => void
  onCancel: () => void
  isSaving: boolean
}) {
  const [name, setName] = useState(camp.name)
  const [message, setMessage] = useState(camp.message_template)
  const [scheduledAt, setScheduledAt] = useState(
    camp.scheduled_at ? camp.scheduled_at.slice(0, 16) : ''
  )
  const [error, setError] = useState('')

  const handleSave = () => {
    if (!name.trim() || !message.trim()) {
      setError('Nome e mensagem são obrigatórios.')
      return
    }
    onSave({
      name,
      message_template: message,
      scheduled_at: scheduledAt || undefined,
    })
  }

  return (
    <div className="border-t border-indigo-100 px-5 py-4 bg-indigo-50 space-y-3">
      <h3 className="text-sm font-medium text-indigo-800">Editar campanha</h3>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-gray-500 block mb-1">Nome</label>
          <input
            value={name}
            onChange={e => setName(e.target.value)}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Agendamento (opcional)</label>
          <input
            type="datetime-local"
            value={scheduledAt}
            onChange={e => setScheduledAt(e.target.value)}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
      </div>
      <div>
        <label className="text-xs text-gray-500 block mb-1">
          Mensagem (suporta spintax: {'{oi|olá}'} e variáveis: {'{{nome}}'})
        </label>
        <textarea
          value={message}
          onChange={e => setMessage(e.target.value)}
          rows={4}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
        />
      </div>
      {error && <p className="text-red-500 text-sm">{error}</p>}
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={isSaving}
          className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-500 disabled:opacity-50"
        >
          <Check size={13} /> {isSaving ? 'Salvando...' : 'Salvar'}
        </button>
        <button
          onClick={onCancel}
          className="flex items-center gap-1.5 px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50"
        >
          <X size={13} /> Cancelar
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function Campaigns() {
  const qc = useQueryClient()
  const audioRef = useRef<HTMLInputElement>(null)
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [formError, setFormError] = useState('')
  const [audioUploading, setAudioUploading] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [reportCampId, setReportCampId] = useState<string | null>(null)

  const { data: instancesData } = useQuery({
    queryKey: ['instances'],
    queryFn: () => getInstances().then(r => r.data),
  })
  const connectedInstances = (instancesData ?? []).filter(i => i.status === 'connected')

  const { data, isLoading } = useQuery({
    queryKey: ['campaigns', page, statusFilter],
    queryFn: () =>
      getCampaigns({ page, page_size: 20, status: statusFilter || undefined }).then(r => r.data),
    placeholderData: prev => prev,
    refetchInterval: 10000,
  })

  const create = useMutation({
    mutationFn: createCampaign,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['campaigns'] })
      setShowForm(false)
      setForm(EMPTY_FORM)
      setFormError('')
    },
    onError: (e: any) => setFormError(e.response?.data?.detail ?? 'Erro ao criar campanha'),
  })

  const update = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Campaign> }) => updateCampaign(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['campaigns'] })
      setEditingId(null)
    },
  })

  const del = useMutation({
    mutationFn: deleteCampaign,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['campaigns'] }),
  })

  const launch = useMutation({
    mutationFn: launchCampaign,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['campaigns'] }),
  })

  const pause = useMutation({
    mutationFn: pauseCampaign,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['campaigns'] }),
  })

  const resume = useMutation({
    mutationFn: resumeCampaign,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['campaigns'] }),
  })

  const handleAudioUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setAudioUploading(true)
    setFormError('')
    try {
      const { data } = await uploadMedia(file)
      setForm(f => ({ ...f, audio_url: data.url, audio_filename: data.original_filename }))
    } catch (err: any) {
      setFormError(err.response?.data?.detail ?? 'Erro ao enviar áudio.')
    } finally {
      setAudioUploading(false)
      e.target.value = ''
    }
  }

  const handleCreate = () => {
    if (!form.name.trim()) {
      setFormError('Nome é obrigatório.')
      return
    }
    if (!form.message_template.trim() && !form.audio_url) {
      setFormError('Adicione uma mensagem de texto ou um áudio.')
      return
    }
    create.mutate({
      name: form.name,
      message_template: form.message_template || ' ',
      media_url: form.audio_url || undefined,
      media_type: form.audio_url ? 'audio' : undefined,
      scheduled_at: form.scheduled_at || undefined,
      lead_group: form.lead_group || undefined,
      allowed_instances: form.allowed_instances.length > 0 ? form.allowed_instances : undefined,
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-800">Campanhas</h1>
        <div className="flex items-center gap-2">
          <select
            value={statusFilter}
            onChange={e => { setStatusFilter(e.target.value); setPage(1) }}
            className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">Todos os status</option>
            <option value="draft">Rascunho</option>
            <option value="running">Executando</option>
            <option value="paused">Pausada</option>
            <option value="completed">Concluída</option>
          </select>
          <button
            onClick={() => setShowForm(s => !s)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-500"
          >
            <Plus size={14} /> Nova campanha
          </button>
        </div>
      </div>

      {showForm && (
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100 space-y-3">
          <h2 className="font-medium text-gray-700">Nova campanha</h2>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500 block mb-1">Nome</label>
              <input
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="Black Friday 2025"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Agendamento (opcional)</label>
              <input
                type="datetime-local"
                value={form.scheduled_at}
                onChange={e => setForm(f => ({ ...f, scheduled_at: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500 block mb-1 flex items-center gap-1">
                <Users size={11} /> Grupo de leads (opcional)
              </label>
              <TagAutocomplete
                value={form.lead_group}
                onChange={v => setForm(f => ({ ...f, lead_group: v }))}
              />
              <p className="text-xs text-gray-400 mt-1">Só envia para leads com esta tag. Vazio = todos.</p>
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1 flex items-center gap-1">
                <Cpu size={11} /> Instâncias (opcional)
              </label>
              {connectedInstances.length === 0 ? (
                <p className="text-xs text-gray-400 py-2">Nenhuma instância conectada.</p>
              ) : (
                <div className="space-y-1 max-h-24 overflow-y-auto border border-gray-200 rounded-lg px-3 py-2">
                  {connectedInstances.map(inst => (
                    <label key={inst.id} className="flex items-center gap-2 text-sm cursor-pointer">
                      <input
                        type="checkbox"
                        checked={form.allowed_instances.includes(inst.evolution_instance_name)}
                        onChange={e => {
                          const name = inst.evolution_instance_name
                          setForm(f => ({
                            ...f,
                            allowed_instances: e.target.checked
                              ? [...f.allowed_instances, name]
                              : f.allowed_instances.filter(n => n !== name),
                          }))
                        }}
                        className="rounded"
                      />
                      <span className="truncate">{inst.display_name}</span>
                      <span className="text-xs text-gray-400 ml-auto">{inst.daily_sent}/{inst.daily_limit}</span>
                    </label>
                  ))}
                </div>
              )}
              <p className="text-xs text-gray-400 mt-1">Nenhuma marcada = usa todas.</p>
            </div>
          </div>

          <div>
            <label className="text-xs text-gray-500 block mb-1">
              Mensagem de texto (opcional com áudio · suporta spintax: {'{oi|olá}'} e variáveis: {'{{nome}}'})
            </label>
            <textarea
              value={form.message_template}
              onChange={e => setForm(f => ({ ...f, message_template: e.target.value }))}
              rows={3}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
              placeholder="{Oi|Olá}, {{nome}}! Ouça nossa mensagem..."
            />
          </div>

          {/* Audio upload */}
          <div className="border border-dashed border-gray-200 rounded-lg p-4 space-y-2">
            <p className="text-xs font-medium text-gray-600 flex items-center gap-1.5">
              <Mic size={13} className="text-indigo-500" /> Áudio (mensagem de voz — não aparece como encaminhado)
            </p>
            {form.audio_url ? (
              <div className="flex items-center gap-2 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
                <Mic size={13} className="text-green-600 flex-shrink-0" />
                <span className="text-xs text-green-700 flex-1 truncate">{form.audio_filename}</span>
                <button
                  onClick={() => setForm(f => ({ ...f, audio_url: '', audio_filename: '' }))}
                  className="text-green-400 hover:text-red-500"
                >
                  <X size={13} />
                </button>
              </div>
            ) : (
              <button
                onClick={() => audioRef.current?.click()}
                disabled={audioUploading}
                className="flex items-center gap-2 px-3 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50"
              >
                <Upload size={13} />
                {audioUploading ? 'Enviando...' : 'Selecionar áudio (MP3, WAV, OGG, M4A…)'}
              </button>
            )}
            <input
              ref={audioRef}
              type="file"
              accept="audio/*,.mp3,.wav,.ogg,.m4a,.aac,.amr,.opus"
              className="hidden"
              onChange={handleAudioUpload}
            />
            <p className="text-xs text-gray-400">
              O áudio é enviado como mensagem de voz gravada. Texto acima é enviado antes do áudio (opcional).
            </p>
          </div>

          {formError && <p className="text-red-500 text-sm">{formError}</p>}
          <div className="flex gap-2">
            <button
              onClick={handleCreate}
              disabled={create.isPending || audioUploading}
              className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-500 disabled:opacity-50"
            >
              {create.isPending ? 'Criando...' : 'Criar'}
            </button>
            <button
              onClick={() => { setShowForm(false); setFormError(''); setForm(EMPTY_FORM) }}
              className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

      {isLoading ? (
        <p className="text-center py-12 text-gray-400 text-sm">Carregando...</p>
      ) : data?.items.length === 0 ? (
        <div className="bg-white rounded-xl p-12 text-center shadow-sm border border-gray-100">
          <p className="text-gray-400 text-sm">Nenhuma campanha encontrada.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {data?.items.map((camp: Campaign) => (
            <div key={camp.id} className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
              <div className="p-5">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => {
                        if (editingId === camp.id) return
                        setExpanded(expanded === camp.id ? null : camp.id)
                      }}
                      className="text-gray-400 hover:text-gray-600"
                    >
                      <ChevronRight
                        size={16}
                        className={`transition-transform ${expanded === camp.id && editingId !== camp.id ? 'rotate-90' : ''}`}
                      />
                    </button>
                    <div>
                      <p className="font-medium text-gray-800 flex items-center gap-1.5">
                        {camp.name}
                        {camp.media_type === 'audio' && (
                          <span title="Campanha com áudio PTT">
                            <Mic size={13} className="text-indigo-400" />
                          </span>
                        )}
                      </p>
                      <p className="text-xs text-gray-400 mt-0.5 flex items-center gap-2 flex-wrap">
                        <span>{camp.total_leads} leads</span>
                        {camp.lead_group && (
                          <span className="flex items-center gap-1 bg-indigo-50 text-indigo-600 px-1.5 py-0.5 rounded-full text-xs">
                            <Users size={9} /> {camp.lead_group}
                          </span>
                        )}
                        {camp.allowed_instances && camp.allowed_instances.length > 0 && (
                          <span className="flex items-center gap-1 bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded-full text-xs">
                            <Cpu size={9} /> {camp.allowed_instances.length} inst.
                          </span>
                        )}
                        {camp.scheduled_at &&
                          ` · agendada ${new Date(camp.scheduled_at).toLocaleString('pt-BR')}`}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_BADGE[camp.status]}`}>
                      {STATUS_LABEL[camp.status]}
                    </span>

                    {/* Delivery report button */}
                    {(camp.status === 'running' || camp.status === 'paused' || camp.status === 'completed') && (
                      <button
                        onClick={() => setReportCampId(camp.id)}
                        title="Relatório de entrega"
                        className="p-1.5 text-gray-400 hover:text-indigo-600 rounded-lg hover:bg-indigo-50"
                      >
                        <BarChart2 size={14} />
                      </button>
                    )}

                    {/* Edit button — only for draft/scheduled */}
                    {(camp.status === 'draft' || camp.status === 'scheduled') && (
                      <button
                        onClick={() => {
                          setEditingId(editingId === camp.id ? null : camp.id)
                          setExpanded(null)
                        }}
                        title="Editar"
                        className={`p-1.5 rounded-lg ${editingId === camp.id ? 'text-indigo-600 bg-indigo-50' : 'text-gray-400 hover:text-indigo-600 hover:bg-indigo-50'}`}
                      >
                        <Pencil size={14} />
                      </button>
                    )}

                    {camp.status === 'draft' && (
                      <button
                        onClick={() => launch.mutate(camp.id)}
                        disabled={launch.isPending}
                        title="Lançar"
                        className="p-1.5 text-green-500 hover:text-green-700 rounded-lg hover:bg-green-50 disabled:opacity-50"
                      >
                        <Play size={14} />
                      </button>
                    )}
                    {camp.status === 'running' && (
                      <button
                        onClick={() => pause.mutate(camp.id)}
                        disabled={pause.isPending}
                        title="Pausar"
                        className="p-1.5 text-yellow-500 hover:text-yellow-700 rounded-lg hover:bg-yellow-50 disabled:opacity-50"
                      >
                        <Pause size={14} />
                      </button>
                    )}
                    {camp.status === 'paused' && (
                      <button
                        onClick={() => resume.mutate(camp.id)}
                        disabled={resume.isPending}
                        title="Retomar"
                        className="p-1.5 text-indigo-500 hover:text-indigo-700 rounded-lg hover:bg-indigo-50 disabled:opacity-50"
                      >
                        <RotateCcw size={14} />
                      </button>
                    )}
                    {(camp.status === 'draft' ||
                      camp.status === 'completed' ||
                      camp.status === 'failed') && (
                      <button
                        onClick={() => { if (confirm('Excluir campanha?')) del.mutate(camp.id) }}
                        title="Excluir"
                        className="p-1.5 text-red-400 hover:text-red-600 rounded-lg hover:bg-red-50"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-4 gap-4 text-sm">
                  <div>
                    <p className="text-xs text-gray-400 mb-1">Enviados</p>
                    <p className="font-medium text-gray-700">{camp.sent_count}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 mb-1">Entregues</p>
                    <p className="font-medium text-green-600">{camp.delivered_count}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 mb-1">Falhas</p>
                    <p className="font-medium text-red-500">{camp.failed_count}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 mb-1">Progresso</p>
                    <ProgressBar sent={camp.sent_count + camp.failed_count} total={camp.total_leads} />
                  </div>
                </div>

                <EtaEstimate camp={camp} />

                {camp.status === 'paused' && (() => {
                  const processed = camp.sent_count + camp.failed_count
                  const remaining = Math.max(0, camp.total_leads - processed)
                  return (
                    <div className="mt-3 flex items-center gap-2 bg-yellow-50 border border-yellow-200 rounded-lg px-3 py-2 text-xs text-yellow-800">
                      <RotateCcw size={11} className="flex-shrink-0 text-yellow-600" />
                      <span>
                        <strong>{processed} leads já processados</strong> serão pulados ao retomar
                        {remaining > 0 && <> · <strong>{remaining} restantes</strong> serão enviados</>}
                      </span>
                    </div>
                  )
                })()}
              </div>

              {/* Inline edit panel */}
              {editingId === camp.id && (
                <InlineEditForm
                  camp={camp}
                  isSaving={update.isPending}
                  onSave={d => update.mutate({ id: camp.id, data: d })}
                  onCancel={() => setEditingId(null)}
                />
              )}

              {/* Message template preview */}
              {expanded === camp.id && editingId !== camp.id && (
                <div className="border-t border-gray-100 px-5 py-4 bg-gray-50">
                  <p className="text-xs text-gray-500 mb-1 font-medium">Template da mensagem</p>
                  <pre className="text-xs text-gray-600 whitespace-pre-wrap font-mono bg-white border border-gray-200 rounded-lg p-3">
                    {camp.message_template}
                  </pre>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {data && (
        <div className="flex items-center justify-between text-sm text-gray-500">
          <span>{data.total} campanhas</span>
          <div className="flex gap-2">
            <button
              disabled={page === 1}
              onClick={() => setPage(p => p - 1)}
              className="px-2 py-1 rounded border border-gray-200 disabled:opacity-40"
            >
              Anterior
            </button>
            <span className="px-2 py-1">Página {data.page}</span>
            <button
              disabled={data.page * data.page_size >= data.total}
              onClick={() => setPage(p => p + 1)}
              className="px-2 py-1 rounded border border-gray-200 disabled:opacity-40"
            >
              Próxima
            </button>
          </div>
        </div>
      )}

      {reportCampId && (
        <DeliveryReportModal campaignId={reportCampId} onClose={() => setReportCampId(null)} />
      )}
    </div>
  )
}
