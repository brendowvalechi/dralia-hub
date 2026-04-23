import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getLeads, deleteLead, updateLead, importLeads, getLeadLastMessage } from '../api'
import { Upload, Trash2, Ban, Search, Pencil, Check, X, ChevronRight, MessageSquare } from 'lucide-react'
import type { Lead } from '../types'

const STATUS_BADGE: Record<string, string> = {
  active: 'bg-green-100 text-green-700',
  inactive: 'bg-gray-100 text-gray-500',
  opted_out: 'bg-yellow-100 text-yellow-700',
  blacklisted: 'bg-red-100 text-red-700',
}

const STATUS_LABEL: Record<string, string> = {
  active: 'Ativo',
  inactive: 'Inativo',
  opted_out: 'Opt-out',
  blacklisted: 'Bloqueado',
}

// ---------------------------------------------------------------------------
// Inline editor for a single lead row
// ---------------------------------------------------------------------------
function EditableRow({
  lead,
  onSave,
  onCancel,
  isSaving,
}: {
  lead: Lead
  onSave: (data: { name: string; tags: string[]; notes: string }) => void
  onCancel: () => void
  isSaving: boolean
}) {
  const [name, setName] = useState(lead.name ?? '')
  const [tagsRaw, setTagsRaw] = useState(lead.tags.join(', '))
  const [notes, setNotes] = useState(lead.notes ?? '')

  const handleSave = () => {
    const tags = tagsRaw
      .split(',')
      .map(t => t.trim())
      .filter(Boolean)
    onSave({ name, tags, notes })
  }

  return (
    <>
      <td className="px-4 py-2 font-mono text-xs">{lead.phone}</td>
      <td className="px-4 py-2">
        <input
          value={name}
          onChange={e => setName(e.target.value)}
          className="w-full border border-indigo-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
          placeholder="Nome"
        />
      </td>
      <td className="px-4 py-2">
        <input
          value={tagsRaw}
          onChange={e => setTagsRaw(e.target.value)}
          className="w-full border border-indigo-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
          placeholder="tag1, tag2, grupo"
        />
      </td>
      <td className="px-4 py-2">
        <input
          value={notes}
          onChange={e => setNotes(e.target.value)}
          className="w-full border border-indigo-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
          placeholder="Observações"
        />
      </td>
      <td className="px-4 py-2">
        <div className="flex items-center gap-1 justify-end">
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="p-1.5 text-green-600 hover:text-green-800 rounded hover:bg-green-50 disabled:opacity-50"
            title="Salvar"
          >
            <Check size={14} />
          </button>
          <button
            onClick={onCancel}
            className="p-1.5 text-gray-400 hover:text-gray-600 rounded hover:bg-gray-100"
            title="Cancelar"
          >
            <X size={14} />
          </button>
        </div>
      </td>
    </>
  )
}

// ---------------------------------------------------------------------------
// Last message preview panel
// ---------------------------------------------------------------------------
function LastMessagePanel({ leadId }: { leadId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['lead-last-message', leadId],
    queryFn: () => getLeadLastMessage(leadId).then(r => r.data),
    staleTime: 30000,
  })

  if (isLoading) return (
    <div className="px-5 py-3 bg-gray-50 border-t border-gray-100 text-xs text-gray-400">
      Carregando...
    </div>
  )

  if (!data || !data.found) return (
    <div className="px-5 py-3 bg-gray-50 border-t border-gray-100 text-xs text-gray-400">
      Nenhuma mensagem enviada para este contato ainda.
    </div>
  )

  return (
    <div className="px-5 py-3 bg-blue-50 border-t border-blue-100">
      <div className="flex items-center gap-3 mb-1.5">
        <MessageSquare size={13} className="text-blue-500" />
        <span className="text-xs font-medium text-blue-700">Última mensagem enviada</span>
        <span className="text-xs text-blue-500 ml-auto">
          {data.sent_at ? new Date(data.sent_at).toLocaleString('pt-BR') : '—'}
          {' · '}
          <span className="capitalize">{data.status}</span>
        </span>
      </div>
      <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono bg-white rounded border border-blue-100 px-3 py-2 max-h-28 overflow-y-auto">
        {data.content || '(sem conteúdo)'}
      </pre>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Import modal
// ---------------------------------------------------------------------------
function ImportModal({
  onImport,
  onClose,
}: {
  onImport: (file: File, updateExisting: boolean, group: string) => void
  onClose: () => void
}) {
  const [group, setGroup] = useState('')
  const [updateExisting, setUpdateExisting] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    onImport(file, updateExisting, group.trim())
    e.target.value = ''
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-sm p-6 space-y-4">
        <h2 className="font-semibold text-gray-800">Importar CSV / XLSX</h2>

        <div>
          <label className="text-xs text-gray-500 block mb-1">Grupo (tag aplicada a todos os leads importados)</label>
          <input
            value={group}
            onChange={e => setGroup(e.target.value)}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Ex: pacientes-2025, lista-vip"
          />
          <p className="text-xs text-gray-400 mt-1">Deixe em branco para não aplicar nenhum grupo.</p>
        </div>

        <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
          <input
            type="checkbox"
            checked={updateExisting}
            onChange={e => setUpdateExisting(e.target.checked)}
            className="rounded"
          />
          Atualizar leads existentes pelo telefone
        </label>

        <div className="flex gap-2 pt-1">
          <button
            onClick={() => fileRef.current?.click()}
            className="flex-1 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-500"
          >
            Escolher arquivo
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50"
          >
            Cancelar
          </button>
        </div>
        <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={handleFileChange} />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function Leads() {
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [tagFilter, setTagFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [importMsg, setImportMsg] = useState('')
  const [showImport, setShowImport] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['leads', page, search, statusFilter, tagFilter],
    queryFn: () =>
      getLeads({
        page,
        page_size: 50,
        search: search || undefined,
        status: statusFilter || undefined,
        tag: tagFilter || undefined,
      }).then(r => r.data),
    placeholderData: prev => prev,
  })

  const del = useMutation({
    mutationFn: deleteLead,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['leads'] }),
  })

  const optOut = useMutation({
    mutationFn: (id: string) => updateLead(id, { status: 'opted_out' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['leads'] }),
  })

  const update = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Lead> }) => updateLead(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['leads'] })
      setEditingId(null)
    },
  })

  const handleImport = async (file: File, updateExisting: boolean, group: string) => {
    setShowImport(false)
    try {
      const { data } = await importLeads(file, updateExisting, group || undefined)
      setImportMsg(`Importados: ${data.created} criados, ${data.updated} atualizados, ${data.skipped} ignorados.`)
      qc.invalidateQueries({ queryKey: ['leads'] })
    } catch {
      setImportMsg('Erro ao importar arquivo.')
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-800">Leads</h1>
        <button
          onClick={() => setShowImport(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-white border border-gray-200 rounded-lg hover:bg-gray-50"
        >
          <Upload size={14} /> Importar CSV/XLSX
        </button>
      </div>

      {importMsg && (
        <div className="bg-blue-50 border border-blue-200 text-blue-700 text-sm px-4 py-2 rounded-lg flex items-center justify-between">
          <span>{importMsg}</span>
          <button onClick={() => setImportMsg('')} className="ml-2 text-blue-400 hover:text-blue-600">
            <X size={14} />
          </button>
        </div>
      )}

      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            placeholder="Buscar por nome ou telefone..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
            className="w-full pl-8 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <input
          placeholder="Filtrar por tag / grupo"
          value={tagFilter}
          onChange={e => { setTagFilter(e.target.value); setPage(1) }}
          className="w-44 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <select
          value={statusFilter}
          onChange={e => { setStatusFilter(e.target.value); setPage(1) }}
          className="text-sm border border-gray-200 rounded-lg px-3 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">Todos os status</option>
          <option value="active">Ativo</option>
          <option value="inactive">Inativo</option>
          <option value="opted_out">Opt-out</option>
          <option value="blacklisted">Bloqueado</option>
        </select>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        {isLoading ? (
          <p className="text-center py-12 text-gray-400 text-sm">Carregando...</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="text-left px-4 py-3 text-gray-500 font-medium w-8" />
                <th className="text-left px-4 py-3 text-gray-500 font-medium">Telefone</th>
                <th className="text-left px-4 py-3 text-gray-500 font-medium">Nome</th>
                <th className="text-left px-4 py-3 text-gray-500 font-medium">Tags / Grupos</th>
                <th className="text-left px-4 py-3 text-gray-500 font-medium">Observações</th>
                <th className="text-left px-4 py-3 text-gray-500 font-medium">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {data?.items.map((lead: Lead) => (
                <>
                  <tr
                    key={lead.id}
                    className={`border-b border-gray-50 hover:bg-gray-50 ${editingId === lead.id ? 'bg-indigo-50' : ''}`}
                  >
                    <td className="px-4 py-3">
                      <button
                        onClick={() => setExpandedId(expandedId === lead.id ? null : lead.id)}
                        className="text-gray-300 hover:text-blue-500"
                        title="Ver última mensagem"
                      >
                        <ChevronRight
                          size={14}
                          className={`transition-transform ${expandedId === lead.id ? 'rotate-90 text-blue-400' : ''}`}
                        />
                      </button>
                    </td>

                    {editingId === lead.id ? (
                      <EditableRow
                        lead={lead}
                        isSaving={update.isPending}
                        onSave={d => update.mutate({ id: lead.id, data: d })}
                        onCancel={() => setEditingId(null)}
                      />
                    ) : (
                      <>
                        <td className="px-4 py-3 font-mono text-xs">{lead.phone}</td>
                        <td className="px-4 py-3">{lead.name ?? <span className="text-gray-300">—</span>}</td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-1">
                            {lead.tags.map(t => (
                              <span key={t} className="px-1.5 py-0.5 bg-indigo-50 text-indigo-600 rounded text-xs">
                                {t}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-gray-500 text-xs max-w-[180px] truncate" title={lead.notes ?? ''}>
                          {lead.notes ?? <span className="text-gray-300">—</span>}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_BADGE[lead.status]}`}>
                            {STATUS_LABEL[lead.status]}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1.5 justify-end">
                            <button
                              onClick={() => setEditingId(lead.id)}
                              title="Editar"
                              className="p-1.5 text-gray-400 hover:text-indigo-600 rounded hover:bg-indigo-50"
                            >
                              <Pencil size={13} />
                            </button>
                            {lead.status === 'active' && (
                              <button
                                onClick={() => optOut.mutate(lead.id)}
                                title="Opt-out"
                                className="p-1.5 text-yellow-500 hover:text-yellow-700 rounded hover:bg-yellow-50"
                              >
                                <Ban size={13} />
                              </button>
                            )}
                            <button
                              onClick={() => { if (confirm('Excluir lead?')) del.mutate(lead.id) }}
                              title="Excluir"
                              className="p-1.5 text-red-400 hover:text-red-600 rounded hover:bg-red-50"
                            >
                              <Trash2 size={13} />
                            </button>
                          </div>
                        </td>
                      </>
                    )}
                  </tr>

                  {expandedId === lead.id && (
                    <tr key={`${lead.id}-msg`} className="border-b border-gray-50">
                      <td colSpan={7} className="p-0">
                        <LastMessagePanel leadId={lead.id} />
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}

        {data && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 text-sm text-gray-500">
            <span>{data.total} leads</span>
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
      </div>

      {showImport && (
        <ImportModal onImport={handleImport} onClose={() => setShowImport(false)} />
      )}
    </div>
  )
}
