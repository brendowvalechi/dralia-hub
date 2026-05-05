import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getInstances, syncInstance, syncAllInstances, logoutInstance, reconnectInstance, createInstance, deleteInstance, updateInstance } from '../api'
import { RefreshCw, LogOut, Trash2, Plus, Wifi, WifiOff, QrCode, Pencil, Check, X, AlertCircle } from 'lucide-react'
import { useToast } from '../contexts/ToastContext'
import QRCodeModal from '../components/QRCodeModal'
import type { Instance } from '../types'

const STATUS_COLOR: Record<string, string> = {
  connected: 'text-green-600',
  disconnected: 'text-gray-400',
  warming_up: 'text-yellow-500',
  banned: 'text-red-600',
  quarantine: 'text-orange-500',
}

// Mantém alinhado com backend antiban_engine.MIN_HEALTH_SCORE.
// Abaixo desse valor o instance_router NÃO usa a instância em campanhas.
const MIN_HEALTH_TO_SEND = 60

function HealthBar({ score }: { score: number }) {
  // >=70 verde · 60-69 amarelo (no limite) · <60 vermelho (BLOQUEADO de envios)
  const color = score >= 70 ? 'bg-green-500' : score >= MIN_HEALTH_TO_SEND ? 'bg-yellow-500' : 'bg-red-500'
  const blocked = score < MIN_HEALTH_TO_SEND
  return (
    <div className="flex items-center gap-2">
      <div
        className="flex-1 bg-gray-100 rounded-full h-1.5"
        title={blocked ? `Saúde abaixo de ${MIN_HEALTH_TO_SEND}: bloqueado para campanhas` : undefined}
      >
        <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className={`text-xs w-8 ${blocked ? 'text-red-600 font-semibold' : 'text-gray-500'}`}>{score}</span>
    </div>
  )
}

export default function Instances() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ display_name: '', evolution_instance_name: '', daily_limit: 50 })
  const [formError, setFormError] = useState('')
  const [qrModal, setQrModal] = useState<{ id: string; name: string } | null>(null)
  const [editingLimitId, setEditingLimitId] = useState<string | null>(null)
  const [editLimitValue, setEditLimitValue] = useState(50)

  const { data: instances = [], isLoading } = useQuery({
    queryKey: ['instances'],
    queryFn: () => getInstances().then(r => r.data),
    refetchInterval: 30000,
  })

  // Sincroniza status de todas as instâncias com a Evolution API ao entrar na
  // página. Sem isso, o banco pode ficar com status estagnado (DB diz
  // 'connected' enquanto o WhatsApp já caiu) e o botão de QR Code some.
  useEffect(() => {
    syncAllInstances()
      .then(() => qc.invalidateQueries({ queryKey: ['instances'] }))
      .catch(() => {})
  }, [qc])

  const sync = useMutation({
    mutationFn: syncInstance,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['instances'] }); toast('Status sincronizado', 'success') },
    onError: () => toast('Erro ao sincronizar', 'error'),
  })

  const logout = useMutation({
    mutationFn: logoutInstance,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['instances'] }); toast('Instância desconectada', 'info') },
    onError: () => toast('Erro ao desconectar', 'error'),
  })

  const reconnect = useMutation({
    mutationFn: reconnectInstance,
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: ['instances'] })
      const inst = instances.find(i => i.id === id)
      if (inst) setQrModal({ id: inst.id, name: inst.evolution_instance_name })
    },
    onError: () => toast('Erro ao reconectar', 'error'),
  })

  const del = useMutation({
    mutationFn: deleteInstance,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['instances'] }); toast('Instância excluída', 'info') },
    onError: () => toast('Erro ao excluir', 'error'),
  })

  const updateLimit = useMutation({
    mutationFn: ({ id, daily_limit }: { id: string; daily_limit: number }) =>
      updateInstance(id, { daily_limit }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['instances'] })
      setEditingLimitId(null)
      toast('Limite atualizado', 'success')
    },
    onError: () => toast('Erro ao atualizar limite', 'error'),
  })

  const create = useMutation({
    mutationFn: createInstance,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['instances'] })
      setShowForm(false)
      setForm({ display_name: '', evolution_instance_name: '', daily_limit: 50 })
      toast('Instância criada com sucesso', 'success')
    },
    onError: (e: any) => {
      const detail = e.response?.data?.detail
      if (Array.isArray(detail)) {
        const msgs = detail.map((d: any) => d.msg ?? String(d)).join('; ')
        setFormError(msgs)
      } else {
        setFormError(detail ?? 'Erro ao criar instância')
      }
    },
  })

  return (
    <div className="space-y-4">
      {qrModal && (
        <QRCodeModal
          instanceId={qrModal.id}
          instanceName={qrModal.name}
          onClose={() => setQrModal(null)}
        />
      )}

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-800">Instâncias WhatsApp</h1>
        <button onClick={() => setShowForm(s => !s)} className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-500">
          <Plus size={14} /> Nova instância
        </button>
      </div>

      {showForm && (
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100 space-y-3">
          <h2 className="font-medium text-gray-700">Nova instância</h2>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-gray-500 block mb-1">Nome de exibição</label>
              <input value={form.display_name} onChange={e => setForm(f => ({...f, display_name: e.target.value}))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="WhatsApp Principal" />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Nome na Evolution API</label>
              <input value={form.evolution_instance_name} onChange={e => setForm(f => ({...f, evolution_instance_name: e.target.value}))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="wp-principal" />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Limite diário</label>
              <input type="number" value={form.daily_limit} onChange={e => setForm(f => ({...f, daily_limit: Number(e.target.value)}))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" min={1} max={1000} />
            </div>
          </div>
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-800">
            <p className="font-medium mb-1">Limites recomendados (anti-ban)</p>
            <p className="leading-relaxed">
              Para um número novo: <strong>15–20/dia nos primeiros dias</strong>, subindo gradualmente
              (35 na 1ª semana, 60 na 2ª, 130 na 3ª, 250 a partir do mês). Para números que já
              passaram por warmup em outro sistema: comece em <strong>50/dia</strong> e suba devagar.
              100+/dia em número recente foi a causa de bans recentes.
            </p>
          </div>
          {formError && <p className="text-red-500 text-sm">{formError}</p>}
          <div className="flex gap-2">
            <button onClick={() => {
              if (!/^[a-zA-Z0-9_-]+$/.test(form.evolution_instance_name)) {
                setFormError('Nome na Evolution API: use apenas letras, números, _ e -')
                return
              }
              setFormError('')
              create.mutate(form)
            }} disabled={create.isPending}
              className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-500 disabled:opacity-50">
              {create.isPending ? 'Criando...' : 'Criar'}
            </button>
            <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50">Cancelar</button>
          </div>
        </div>
      )}

      {isLoading ? (
        <p className="text-center py-12 text-gray-400 text-sm">Carregando...</p>
      ) : instances.length === 0 ? (
        <div className="bg-white rounded-xl p-12 text-center shadow-sm border border-gray-100">
          <p className="text-gray-400 text-sm">Nenhuma instância cadastrada.</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {instances.map((inst: Instance) => (
            <div key={inst.id} className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  {inst.status === 'connected' ? <Wifi size={18} className="text-green-500" /> : <WifiOff size={18} className="text-gray-400" />}
                  <div>
                    <p className="font-medium text-gray-800">{inst.display_name}</p>
                    <p className="text-xs text-gray-400 font-mono">{inst.phone_number ?? inst.evolution_instance_name}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {inst.status !== 'connected' ? (
                    <button onClick={() => setQrModal({ id: inst.id, name: inst.evolution_instance_name })} title="Escanear QR Code"
                      className="p-1.5 text-indigo-400 hover:text-indigo-700 rounded-lg hover:bg-indigo-50">
                      <QrCode size={14} />
                    </button>
                  ) : (
                    <button
                      onClick={() => {
                        if (confirm('Desconectar e gerar novo QR Code para parear outro aparelho?')) reconnect.mutate(inst.id)
                      }}
                      disabled={reconnect.isPending}
                      title="Reconectar (gera novo QR Code)"
                      className="p-1.5 text-indigo-400 hover:text-indigo-700 rounded-lg hover:bg-indigo-50 disabled:opacity-50"
                    >
                      <QrCode size={14} />
                    </button>
                  )}
                  <button onClick={() => sync.mutate(inst.id)} title="Sincronizar status" className="p-1.5 text-gray-400 hover:text-gray-700 rounded-lg hover:bg-gray-100">
                    <RefreshCw size={14} />
                  </button>
                  {inst.status === 'connected' && (
                    <button onClick={() => logout.mutate(inst.id)} title="Desconectar" className="p-1.5 text-yellow-500 hover:text-yellow-700 rounded-lg hover:bg-yellow-50">
                      <LogOut size={14} />
                    </button>
                  )}
                  <button onClick={() => { if (confirm('Excluir instância?')) del.mutate(inst.id) }} title="Excluir" className="p-1.5 text-red-400 hover:text-red-600 rounded-lg hover:bg-red-50">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-3 gap-4 text-sm">
                <div>
                  <p className="text-xs text-gray-400 mb-1">Status</p>
                  <p className={`font-medium capitalize ${STATUS_COLOR[inst.status]}`}>{inst.status.replace('_', ' ')}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 mb-1">Envios hoje</p>
                  {editingLimitId === inst.id ? (
                    <>
                      <div className="flex items-center gap-1">
                        <span className="text-gray-700">{inst.daily_sent} /</span>
                        <input
                          type="number"
                          value={editLimitValue}
                          onChange={e => setEditLimitValue(Number(e.target.value))}
                          min={1}
                          max={1000}
                          className="w-20 border border-indigo-300 rounded px-1.5 py-0.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
                        />
                        <button
                          onClick={() => updateLimit.mutate({ id: inst.id, daily_limit: editLimitValue })}
                          disabled={updateLimit.isPending}
                          className="p-0.5 text-green-600 hover:text-green-800 disabled:opacity-50"
                          title="Salvar"
                        >
                          <Check size={13} />
                        </button>
                        <button
                          onClick={() => setEditingLimitId(null)}
                          className="p-0.5 text-gray-400 hover:text-gray-600"
                          title="Cancelar"
                        >
                          <X size={13} />
                        </button>
                      </div>
                      <p className="text-xs text-amber-700 mt-1">
                        Recomendado: 50/dia para números fora do warmup. Acima de 100/dia = risco alto.
                      </p>
                    </>
                  ) : (
                    <div className="flex items-center gap-1.5">
                      <p className="font-medium text-gray-700">{inst.daily_sent} / {inst.daily_limit}</p>
                      <button
                        onClick={() => { setEditingLimitId(inst.id); setEditLimitValue(inst.daily_limit) }}
                        className="p-0.5 text-gray-300 hover:text-indigo-600"
                        title="Editar limite"
                      >
                        <Pencil size={11} />
                      </button>
                      {inst.daily_limit > 100 && (
                        <span title="Acima do recomendado (100/dia) — risco de ban" className="text-amber-500">
                          <AlertCircle size={11} />
                        </span>
                      )}
                    </div>
                  )}
                </div>
                <div>
                  <p className="text-xs text-gray-400 mb-1">Saúde</p>
                  <HealthBar score={inst.health_score} />
                </div>
              </div>

              {/* Avisos de risco — abaixo do mínimo, em quarentena, ou com falhas em sequência */}
              {(inst.health_score < MIN_HEALTH_TO_SEND || inst.status === 'quarantine' || inst.status === 'banned' || inst.consecutive_failures >= 3) && (
                <div className="mt-3 flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-xs">
                  <AlertCircle size={13} className="text-red-500 mt-0.5 flex-shrink-0" />
                  <div className="text-red-700">
                    {inst.status === 'banned' && <p><strong>Banida.</strong> Use outro número.</p>}
                    {inst.status === 'quarantine' && (
                      <p>
                        <strong>Em quarentena.</strong> Bloqueada de envios após falhas em sequência ou erro grave.
                        Sincronize, verifique a conexão e, se OK, edite o status manualmente.
                      </p>
                    )}
                    {inst.status !== 'banned' && inst.status !== 'quarantine' && inst.health_score < MIN_HEALTH_TO_SEND && (
                      <p>
                        <strong>Saúde abaixo de {MIN_HEALTH_TO_SEND}.</strong> Bloqueada para campanhas até a saúde subir
                        (atualizada no fim do dia conforme taxa de entrega).
                      </p>
                    )}
                    {inst.consecutive_failures >= 3 && inst.status !== 'quarantine' && (
                      <p className="mt-0.5">{inst.consecutive_failures} falhas consecutivas — em {5 - inst.consecutive_failures} entrará em quarentena.</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
