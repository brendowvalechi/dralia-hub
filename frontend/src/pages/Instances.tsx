import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getInstances, syncInstance, logoutInstance, createInstance, deleteInstance } from '../api'
import { RefreshCw, LogOut, Trash2, Plus, Wifi, WifiOff, QrCode } from 'lucide-react'
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

function HealthBar({ score }: { score: number }) {
  const color = score >= 70 ? 'bg-green-500' : score >= 40 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-gray-100 rounded-full h-1.5">
        <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-xs text-gray-500 w-8">{score}</span>
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

  const { data: instances = [], isLoading } = useQuery({
    queryKey: ['instances'],
    queryFn: () => getInstances().then(r => r.data),
    refetchInterval: 30000,
  })

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

  const del = useMutation({
    mutationFn: deleteInstance,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['instances'] }); toast('Instância excluída', 'info') },
    onError: () => toast('Erro ao excluir', 'error'),
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
                  {inst.status !== 'connected' && (
                    <button onClick={() => setQrModal({ id: inst.id, name: inst.evolution_instance_name })} title="Escanear QR Code"
                      className="p-1.5 text-indigo-400 hover:text-indigo-700 rounded-lg hover:bg-indigo-50">
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
                  <p className="font-medium text-gray-700">{inst.daily_sent} / {inst.daily_limit}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 mb-1">Saúde</p>
                  <HealthBar score={inst.health_score} />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
