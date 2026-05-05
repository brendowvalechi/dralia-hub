import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getCampaigns, createCampaign, deleteCampaign, launchCampaign, pauseCampaign, resumeCampaign, updateCampaign, uploadMedia, getInstances, getCampaignDeliveryReport, getLeadTags } from '../api'
import { Plus, Play, Pause, RotateCcw, Trash2, ChevronRight, Pencil, Check, X, Mic, Upload, Clock, BarChart2, Users, Cpu, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react'
import type { Campaign, DeliveryReport, Instance } from '../types'

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
// Estimativa de conclusão — baseada no delay anti-ban entre mensagens
// (alinhado com antiban_engine.MIN_DELAY/MAX_DELAY no backend)
// ---------------------------------------------------------------------------
const MIN_DELAY_S = 30
const MAX_DELAY_S = 180

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
        {' '}· O sistema aguarda entre 30–180 segundos entre cada envio para não ser bloqueado pelo WhatsApp.
        {camp.use_windows && ' Com janelas ativas, o tempo cresce porque há pausas de almoço e jantar.'}
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
  use_windows: false,
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

function FailureAnalysis({ messages }: { messages: DeliveryReport['messages'] }) {
  const [open, setOpen] = useState(true)
  const failed = messages.filter(m => m.status === 'failed')
  if (failed.length === 0) return null

  const grouped: Record<string, number> = {}
  for (const m of failed) {
    const key = m.failure_reason?.trim() || 'Motivo desconhecido'
    grouped[key] = (grouped[key] ?? 0) + 1
  }
  const sorted = Object.entries(grouped).sort((a, b) => b[1] - a[1])
  const max = sorted[0]?.[1] ?? 1

  return (
    <div className="border border-red-100 rounded-xl mx-6 mb-3">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-red-700 hover:bg-red-50 rounded-xl"
      >
        <span className="flex items-center gap-2">
          <AlertTriangle size={14} className="text-red-500" />
          Análise de falhas — {failed.length} mensagem{failed.length !== 1 ? 's' : ''} não entregue{failed.length !== 1 ? 's' : ''}
        </span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {open && (
        <div className="px-4 pb-3 space-y-2">
          <p className="text-xs text-gray-400 mb-2">Causas agrupadas por frequência:</p>
          {sorted.map(([reason, count]) => (
            <div key={reason}>
              <div className="flex items-center justify-between text-xs mb-0.5">
                <span className="text-gray-700 truncate flex-1 mr-2" title={reason}>{reason}</span>
                <span className="text-red-600 font-medium flex-shrink-0">{count}×</span>
              </div>
              <div className="bg-gray-100 rounded-full h-1.5">
                <div
                  className="h-1.5 rounded-full bg-red-400"
                  style={{ width: `${(count / max) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function DeliveryReportModal({ campaignId, onClose }: { campaignId: string; onClose: () => void }) {
  const [tab, setTab] = useState<'all' | 'failed'>('all')

  const { data, isLoading } = useQuery({
    queryKey: ['delivery-report', campaignId],
    queryFn: () => getCampaignDeliveryReport(campaignId).then(r => r.data),
  })

  const report = data as DeliveryReport | undefined
  const visibleMessages = tab === 'failed'
    ? (report?.messages ?? []).filter(m => m.status === 'failed')
    : (report?.messages ?? [])

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

            {/* Failure analysis section */}
            <div className="pt-3">
              <FailureAnalysis messages={report.messages} />
            </div>

            {/* Tab selector */}
            <div className="px-6 flex gap-2 mb-1">
              <button
                onClick={() => setTab('all')}
                className={`px-3 py-1 text-xs rounded-full font-medium transition-colors ${tab === 'all' ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}`}
              >
                Todas ({report.messages.length})
              </button>
              {(report.summary['failed'] ?? 0) > 0 && (
                <button
                  onClick={() => setTab('failed')}
                  className={`px-3 py-1 text-xs rounded-full font-medium transition-colors ${tab === 'failed' ? 'bg-red-600 text-white' : 'bg-red-50 text-red-600 hover:bg-red-100'}`}
                >
                  Só falhas ({report.summary['failed']})
                </button>
              )}
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-2">
              <div className="space-y-1.5">
                {visibleMessages.map(m => (
                  <div key={m.message_id} className="flex items-center gap-3 py-2 px-3 rounded-lg hover:bg-gray-50">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-700 font-medium truncate">{m.lead_name || m.lead_phone}</p>
                      {m.lead_name && <p className="text-xs text-gray-400">{m.lead_phone}</p>}
                      {m.failure_reason && (
                        <p className="text-xs text-red-500 mt-0.5 break-all">{m.failure_reason}</p>
                      )}
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
// Resume modal — seleciona uma ou mais instâncias ao retomar campanha pausada
// ---------------------------------------------------------------------------
function ResumeModal({
  campaign,
  instances,
  onConfirm,
  onClose,
  isPending,
}: {
  campaign: Campaign
  instances: Instance[]
  onConfirm: (allowedInstances: string[] | null) => void
  onClose: () => void
  isPending: boolean
}) {
  // 'auto' = sistema escolhe qualquer conectada; 'manual' = subconjunto marcado abaixo
  const [mode, setMode] = useState<'auto' | 'manual'>(() =>
    campaign.allowed_instances && campaign.allowed_instances.length > 0 ? 'manual' : 'auto'
  )
  const [selected, setSelected] = useState<string[]>(campaign.allowed_instances ?? [])

  const connected = instances.filter(i => i.status === 'connected')
  const selectedInsts = connected.filter(i => selected.includes(i.evolution_instance_name))
  const lowHealthSelected = selectedInsts.filter(i => i.health_score < 40)

  const toggle = (name: string) => {
    setSelected(s => (s.includes(name) ? s.filter(n => n !== name) : [...s, name]))
  }

  const handleConfirm = () => {
    if (mode === 'auto') {
      // [] = sem restrição (todas as conectadas elegíveis)
      onConfirm([])
    } else {
      onConfirm(selected)
    }
  }

  const canSubmit =
    !isPending &&
    connected.length > 0 &&
    (mode === 'auto' || selected.length > 0)

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-800">Retomar campanha</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>

        <div className="px-6 py-4 space-y-3">
          <p className="text-sm text-gray-600">
            Selecione quais instâncias usar ao retomar <strong>{campaign.name}</strong>.
            Os leads já processados serão pulados automaticamente.
          </p>

          {/* Toggle modo automático/manual */}
          <div className="grid grid-cols-2 gap-2 bg-gray-50 rounded-xl p-1">
            <button
              type="button"
              onClick={() => setMode('auto')}
              className={`text-xs font-medium py-1.5 rounded-lg transition-colors ${
                mode === 'auto' ? 'bg-white text-indigo-600 shadow-sm' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Automático (todas)
            </button>
            <button
              type="button"
              onClick={() => setMode('manual')}
              className={`text-xs font-medium py-1.5 rounded-lg transition-colors ${
                mode === 'manual' ? 'bg-white text-indigo-600 shadow-sm' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Escolher manualmente
            </button>
          </div>

          {mode === 'auto' && (
            <div className="flex items-center gap-2 px-3 py-2 bg-indigo-50 border border-indigo-100 rounded-lg">
              <Cpu size={14} className="text-indigo-500 flex-shrink-0" />
              <p className="text-xs text-indigo-700">
                O sistema usa todas as instâncias conectadas, balanceando por saúde e DDD.
              </p>
            </div>
          )}

          {mode === 'manual' && (
            <div className="space-y-2">
              {connected.length === 0 ? (
                <p className="text-xs text-red-500 px-1">Nenhuma instância conectada no momento.</p>
              ) : (
                connected.map(inst => {
                  const health = inst.health_score
                  const healthColor = health >= 70 ? 'bg-green-500' : health >= 40 ? 'bg-yellow-500' : 'bg-red-500'
                  const healthText = health >= 70 ? 'text-green-600' : health >= 40 ? 'text-yellow-600' : 'text-red-600'
                  const isSelected = selected.includes(inst.evolution_instance_name)
                  return (
                    <label
                      key={inst.id}
                      className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-colors hover:bg-gray-50 ${isSelected ? 'border-indigo-400 bg-indigo-50' : 'border-gray-200'}`}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggle(inst.evolution_instance_name)}
                        className="accent-indigo-600"
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-800 truncate">{inst.display_name}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <div className="flex items-center gap-1">
                            <div className="w-16 bg-gray-200 rounded-full h-1.5">
                              <div className={`h-1.5 rounded-full ${healthColor}`} style={{ width: `${health}%` }} />
                            </div>
                            <span className={`text-xs font-medium ${healthText}`}>{health}</span>
                          </div>
                          <span className="text-xs text-gray-400">{inst.daily_sent}/{inst.daily_limit} msgs</span>
                        </div>
                      </div>
                    </label>
                  )
                })
              )}
              {connected.length > 0 && (
                <p className="text-xs text-gray-400 px-1">
                  {selected.length === 0
                    ? 'Marque ao menos uma instância.'
                    : `${selected.length} de ${connected.length} selecionada${selected.length > 1 ? 's' : ''}.`}
                </p>
              )}
            </div>
          )}

          {/* Aviso de saúde baixa */}
          {mode === 'manual' && lowHealthSelected.length > 0 && (
            <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              <AlertTriangle size={14} className="text-red-500 mt-0.5 flex-shrink-0" />
              <p className="text-xs text-red-700">
                <strong>Atenção:</strong> {lowHealthSelected.length === 1
                  ? `a instância ${lowHealthSelected[0].display_name} tem saúde baixa (${lowHealthSelected[0].health_score})`
                  : `${lowHealthSelected.length} instâncias selecionadas têm saúde abaixo de 40`}.
                Há risco elevado de bloqueio pelo WhatsApp.
              </p>
            </div>
          )}
        </div>

        <div className="px-6 pb-5 flex gap-2">
          <button
            onClick={handleConfirm}
            disabled={!canSubmit}
            className="flex-1 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-500 disabled:opacity-50 font-medium"
          >
            {isPending ? 'Retomando...' : 'Retomar'}
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50"
          >
            Cancelar
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Inline edit form for draft campaigns
// ---------------------------------------------------------------------------
function InlineEditForm({
  camp,
  connectedInstances,
  onSave,
  onCancel,
  isSaving,
}: {
  camp: Campaign
  connectedInstances: Instance[]
  onSave: (data: { name: string; message_template: string; scheduled_at?: string; allowed_instances?: string[] | null; use_windows?: boolean }) => void
  onCancel: () => void
  isSaving: boolean
}) {
  const [name, setName] = useState(camp.name)
  const [message, setMessage] = useState(camp.message_template)
  const [scheduledAt, setScheduledAt] = useState(
    camp.scheduled_at ? camp.scheduled_at.slice(0, 16) : ''
  )
  const [allowedInstances, setAllowedInstances] = useState<string[]>(camp.allowed_instances ?? [])
  const [useWindows, setUseWindows] = useState<boolean>(camp.use_windows ?? false)
  const [error, setError] = useState('')

  const toggleInstance = (n: string) => {
    setAllowedInstances(s => (s.includes(n) ? s.filter(x => x !== n) : [...s, n]))
  }

  const handleSave = () => {
    if (!name.trim() || !message.trim()) {
      setError('Nome e mensagem são obrigatórios.')
      return
    }
    onSave({
      name,
      message_template: message,
      scheduled_at: scheduledAt || undefined,
      allowed_instances: allowedInstances.length > 0 ? allowedInstances : null,
      use_windows: useWindows,
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
        <label className="text-xs text-gray-500 block mb-1 flex items-center gap-1">
          <Cpu size={11} /> Instâncias permitidas (opcional, marque uma ou mais)
        </label>
        {connectedInstances.length === 0 ? (
          <p className="text-xs text-gray-400 py-2">Nenhuma instância conectada.</p>
        ) : (
          <div className="space-y-1 max-h-28 overflow-y-auto border border-gray-200 rounded-lg px-3 py-2 bg-white">
            {connectedInstances.map(inst => (
              <label key={inst.id} className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={allowedInstances.includes(inst.evolution_instance_name)}
                  onChange={() => toggleInstance(inst.evolution_instance_name)}
                  className="rounded"
                />
                <span className="truncate">{inst.display_name}</span>
                <span className="text-xs text-gray-400 ml-auto">{inst.daily_sent}/{inst.daily_limit}</span>
              </label>
            ))}
          </div>
        )}
        <p className="text-xs text-gray-400 mt-1">Nenhuma marcada = usa todas as conectadas.</p>
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

      <label className="flex items-start gap-2 cursor-pointer bg-amber-50/50 border border-amber-200 rounded-lg p-3">
        <input
          type="checkbox"
          checked={useWindows}
          onChange={e => setUseWindows(e.target.checked)}
          className="accent-amber-600 mt-0.5"
        />
        <div className="flex-1">
          <p className="text-xs font-medium text-amber-900 flex items-center gap-1.5">
            <Clock size={12} /> Distribuir em janelas (manhã/tarde/noite)
          </p>
          <p className="text-xs text-amber-800 mt-0.5 leading-relaxed">
            Divide os envios em 3 blocos do dia com pausas. Reduz risco de ban.
          </p>
        </div>
      </label>

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
  const [resumeCamp, setResumeCamp] = useState<Campaign | null>(null)

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
    mutationFn: ({ id, allowedInstances }: { id: string; allowedInstances: string[] | null }) =>
      resumeCampaign(id, allowedInstances),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['campaigns'] })
      setResumeCamp(null)
    },
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
      use_windows: form.use_windows,
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

          {/* Janelas de envio (anti-ban) */}
          <div className="border border-amber-200 bg-amber-50/40 rounded-lg p-4 space-y-2">
            <label className="flex items-start gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.use_windows}
                onChange={e => setForm(f => ({ ...f, use_windows: e.target.checked }))}
                className="accent-amber-600 mt-0.5"
              />
              <div className="flex-1">
                <p className="text-sm font-medium text-amber-900 flex items-center gap-1.5">
                  <Clock size={13} /> Distribuir envios ao longo do dia (recomendado)
                </p>
                <p className="text-xs text-amber-800 mt-1 leading-relaxed">
                  Em vez de disparar todas as mensagens em sequência, o sistema divide
                  o limite diário em <strong>3 blocos: manhã (8h–11h30), tarde (14h–17h) e noite
                  (17h–20h)</strong>, com pausas de almoço e jantar. Ajuda a parecer comportamento
                  humano e reduz risco de bloqueio. <strong>Quem agendar a campanha não precisa
                  fazer nada</strong> — basta marcar essa caixa, o resto é automático: o robô
                  envia o quanto pode dentro de cada bloco e dorme entre eles.
                </p>
              </div>
            </label>
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
                        {camp.use_windows && (
                          <span title="Envios distribuídos em janelas do dia (manhã/tarde/noite)" className="flex items-center gap-1 bg-amber-50 text-amber-700 px-1.5 py-0.5 rounded-full text-xs">
                            <Clock size={9} /> janelas
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
                        onClick={() => setResumeCamp(camp)}
                        title="Retomar"
                        className="p-1.5 text-indigo-500 hover:text-indigo-700 rounded-lg hover:bg-indigo-50"
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
                  connectedInstances={connectedInstances}
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

      {resumeCamp && (
        <ResumeModal
          campaign={resumeCamp}
          instances={instancesData ?? []}
          isPending={resume.isPending}
          onClose={() => setResumeCamp(null)}
          onConfirm={allowedInstances =>
            resume.mutate({ id: resumeCamp.id, allowedInstances })
          }
        />
      )}
    </div>
  )
}
