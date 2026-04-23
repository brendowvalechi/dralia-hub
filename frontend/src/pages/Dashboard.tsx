import { useQuery } from '@tanstack/react-query'
import { getDashboardOverview, getDashboardMessages } from '../api'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

function StatCard({ label, value, sub, color }: { label: string; value: number | string; sub?: string; color: string }) {
  return (
    <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-3xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  )
}

export default function Dashboard() {
  const { data: overview } = useQuery({ queryKey: ['dashboard-overview'], queryFn: () => getDashboardOverview().then(r => r.data) })
  const { data: messages } = useQuery({ queryKey: ['dashboard-messages'], queryFn: () => getDashboardMessages(14).then(r => r.data) })

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-gray-800">Dashboard</h1>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Leads ativos" value={overview?.leads.active ?? '—'} sub={`${overview?.leads.opted_out ?? 0} opt-outs`} color="text-indigo-600" />
        <StatCard label="Campanhas" value={overview?.campaigns.total ?? '—'} sub={`${overview?.campaigns.running ?? 0} em execução`} color="text-green-600" />
        <StatCard label="Instâncias conectadas" value={`${overview?.instances.connected ?? 0}/${overview?.instances.total ?? 0}`} color="text-blue-600" />
        <StatCard label="Taxa de entrega" value={`${overview?.messages.delivery_rate_pct ?? 0}%`} sub={`${overview?.messages.delivered ?? 0} entregues`} color="text-emerald-600" />
      </div>

      <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
        <p className="text-sm font-medium text-gray-700 mb-4">Mensagens — últimos 14 dias</p>
        {messages?.series && messages.series.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={messages.series}>
              <defs>
                <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Area type="monotone" dataKey="delivered" stroke="#6366f1" fill="url(#grad)" name="Entregues" />
              <Area type="monotone" dataKey="failed" stroke="#ef4444" fill="none" name="Falhas" />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-gray-400 text-sm text-center py-10">Sem dados de mensagens ainda.</p>
        )}
      </div>
    </div>
  )
}
