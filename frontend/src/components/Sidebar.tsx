import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Users, Smartphone, Megaphone, LogOut, Layers, UserCog } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const links = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/leads', label: 'Leads', icon: Users },
  { to: '/segments', label: 'Segmentos', icon: Layers },
  { to: '/instances', label: 'Instâncias', icon: Smartphone },
  { to: '/campaigns', label: 'Campanhas', icon: Megaphone },
]

const adminLinks = [
  { to: '/users', label: 'Usuários', icon: UserCog },
]

export default function Sidebar() {
  const { user, logout } = useAuth()

  return (
    <aside className="w-56 flex-shrink-0 bg-gray-900 text-gray-100 flex flex-col h-screen sticky top-0">
      <div className="px-5 py-4 border-b border-gray-700">
        <span className="text-lg font-bold tracking-tight">Dra Lia Hub</span>
      </div>

      <nav className="flex-1 py-4 space-y-1 px-2 overflow-y-auto">
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-indigo-600 text-white'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-white'
              }`
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}

        {user?.role === 'admin' && (
          <>
            <div className="px-3 pt-4 pb-1">
              <p className="text-xs text-gray-600 uppercase tracking-wider">Admin</p>
            </div>
            {adminLinks.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                    isActive
                      ? 'bg-indigo-600 text-white'
                      : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                  }`
                }
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}
          </>
        )}
      </nav>

      <div className="px-4 py-3 border-t border-gray-700 text-xs text-gray-400">
        <p className="truncate mb-0.5">{user?.email}</p>
        <p className="text-gray-600 mb-2 capitalize">{user?.role}</p>
        <button
          onClick={logout}
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
        >
          <LogOut size={14} /> Sair
        </button>
      </div>
    </aside>
  )
}
