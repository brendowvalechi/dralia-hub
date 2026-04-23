import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSegments, createSegment, deleteSegment, refreshSegment } from '../api'
import { Plus, Trash2, RefreshCw, Users } from 'lucide-react'
import { useToast } from '../contexts/ToastContext'

export default function Segments() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', tags: '', status: 'active' })
  const [formError, setFormError] = useState('')

  const { data: segments = [], isLoading } = useQuery({
    queryKey: ['segments'],
    queryFn: () => getSegments().then(r => r.data),
  })

  const create = useMutation({
    mutationFn: createSegment,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['segments'] })
      setShowForm(false)
      setForm({ name: '', tags: '', status: 'active' })
      toast('Segmento criado', 'success')
    },
    onError: (e: any) => setFormError(e.response?.data?.detail ?? 'Erro ao criar segmento'),
  })

  const del = useMutation({
    mutationFn: deleteSegment,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['segments'] }); toast('Segmento excluído', 'info') },
    onError: () => toast('Erro ao excluir segmento', 'error'),
  })

  const refresh = useMutation({
    mutationFn: refreshSegment,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['segments'] }); toast('Contagem atualizada', 'success') },
    onError: () => toast('Erro ao atualizar contagem', 'error'),
  })

  const handleCreate = () => {
    if (!form.name.trim()) { setFormError('Nome é obrigatório'); return }
    const filters: Record<string, unknown> = { status: form.status }
    if (form.tags.trim()) {
      filters.tags = form.tags.split(',').map(t => t.trim()).filter(Boolean)
    }
    create.mutate({ name: form.name, filters })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-800">Segmentos</h1>
        <button onClick={() => setShowForm(s => !s)} className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-500">
          <Plus size={14} /> Novo segmento
        </button>
      </div>

      {showForm && (
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100 space-y-3">
          <h2 className="font-medium text-gray-700">Novo segmento</h2>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-gray-500 block mb-1">Nome</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="Clientes VIP" />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Tags (separadas por vírgula)</label>
              <input value={form.tags} onChange={e => setForm(f => ({ ...f, tags: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="vip, sp, premium" />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Status dos leads</label>
              <select value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <option value="active">Ativo</option>
                <option value="inactive">Inativo</option>
              </select>
            </div>
          </div>
          {formError && <p className="text-red-500 text-sm">{formError}</p>}
          <div className="flex gap-2">
            <button onClick={handleCreate} disabled={create.isPending}
              className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-500 disabled:opacity-50">
              {create.isPending ? 'Criando...' : 'Criar'}
            </button>
            <button onClick={() => { setShowForm(false); setFormError('') }}
              className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50">Cancelar</button>
          </div>
        </div>
      )}

      {isLoading ? (
        <p className="text-center py-12 text-gray-400 text-sm">Carregando...</p>
      ) : segments.length === 0 ? (
        <div className="bg-white rounded-xl p-12 text-center shadow-sm border border-gray-100">
          <p className="text-gray-400 text-sm">Nenhum segmento criado.</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {segments.map((seg: any) => (
            <div key={seg.id} className="bg-white rounded-xl p-5 shadow-sm border border-gray-100 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-indigo-50 rounded-lg">
                  <Users size={16} className="text-indigo-500" />
                </div>
                <div>
                  <p className="font-medium text-gray-800">{seg.name}</p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {seg.lead_count} leads
                    {seg.filters?.tags?.length > 0 && ` · tags: ${seg.filters.tags.join(', ')}`}
                    {seg.filters?.status && ` · status: ${seg.filters.status}`}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => refresh.mutate(seg.id)} title="Recalcular contagem"
                  className="p-1.5 text-gray-400 hover:text-gray-700 rounded-lg hover:bg-gray-100">
                  <RefreshCw size={14} />
                </button>
                <button onClick={() => { if (confirm('Excluir segmento?')) del.mutate(seg.id) }} title="Excluir"
                  className="p-1.5 text-red-400 hover:text-red-600 rounded-lg hover:bg-red-50">
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
