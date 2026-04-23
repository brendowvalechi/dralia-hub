import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getUsers, createUser, deleteUser } from '../api'
import { Plus, Trash2, ShieldCheck } from 'lucide-react'
import { useToast } from '../contexts/ToastContext'
import { useAuth } from '../contexts/AuthContext'

const ROLE_BADGE: Record<string, string> = {
  admin: 'bg-purple-100 text-purple-700',
  operator: 'bg-blue-100 text-blue-700',
  viewer: 'bg-gray-100 text-gray-500',
}

export default function Users() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const { user: me } = useAuth()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ email: '', password: '', role: 'operator' })
  const [formError, setFormError] = useState('')

  const { data: users = [], isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: () => getUsers().then(r => r.data),
  })

  const create = useMutation({
    mutationFn: createUser,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] })
      setShowForm(false)
      setForm({ email: '', password: '', role: 'operator' })
      toast('Usuário criado', 'success')
    },
    onError: (e: any) => setFormError(e.response?.data?.detail ?? 'Erro ao criar usuário'),
  })

  const del = useMutation({
    mutationFn: deleteUser,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); toast('Usuário excluído', 'info') },
    onError: (e: any) => toast(e.response?.data?.detail ?? 'Erro ao excluir', 'error'),
  })

  const handleCreate = () => {
    if (!form.email.trim() || !form.password.trim()) { setFormError('Email e senha são obrigatórios'); return }
    create.mutate(form)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-800">Usuários</h1>
        <button onClick={() => setShowForm(s => !s)} className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-500">
          <Plus size={14} /> Novo usuário
        </button>
      </div>

      {showForm && (
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100 space-y-3">
          <h2 className="font-medium text-gray-700">Novo usuário</h2>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-gray-500 block mb-1">Email</label>
              <input type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="operador@empresa.com" />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Senha</label>
              <input type="password" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="Mínimo 8 caracteres" />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Papel</label>
              <select value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <option value="operator">Operador</option>
                <option value="viewer">Visualizador</option>
                <option value="admin">Admin</option>
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

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        {isLoading ? (
          <p className="text-center py-12 text-gray-400 text-sm">Carregando...</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="text-left px-4 py-3 text-gray-500 font-medium">Email</th>
                <th className="text-left px-4 py-3 text-gray-500 font-medium">Papel</th>
                <th className="text-left px-4 py-3 text-gray-500 font-medium">Status</th>
                <th className="text-left px-4 py-3 text-gray-500 font-medium">Criado em</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {users.map((u: any) => (
                <tr key={u.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-gray-700">
                    <div className="flex items-center gap-2">
                      {u.id === me?.id && <ShieldCheck size={14} className="text-indigo-500" />}
                      {u.email}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${ROLE_BADGE[u.role]}`}>{u.role}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${u.is_active ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-500'}`}>
                      {u.is_active ? 'Ativo' : 'Inativo'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{new Date(u.created_at).toLocaleDateString('pt-BR')}</td>
                  <td className="px-4 py-3">
                    {u.id !== me?.id && (
                      <button onClick={() => { if (confirm('Excluir usuário?')) del.mutate(u.id) }}
                        className="text-red-400 hover:text-red-600">
                        <Trash2 size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
