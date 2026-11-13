import { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { Separator } from './ui/separator'

function CanaryLogo({ size = 20 }: { size?: number }) {
  return (
    <div
      className="rounded-xl bg-primary flex items-center justify-center shrink-0 shadow-md shadow-primary/30"
      style={{ width: size, height: size }}
    >
      <svg width={size * 0.55} height={size * 0.55} viewBox="0 0 32 32" fill="none">
        <path d="M10 22 L16 10 L22 22" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <path d="M12.5 18 L19.5 18" stroke="white" strokeWidth="3" strokeLinecap="round" />
      </svg>
    </div>
  )
}

interface AppLayoutProps {
  children: ReactNode
  sidebarContent?: ReactNode
}

const NAV_ITEMS = [
  {
    label: 'Chat',
    href: '/',
    icon: (
      <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
        <path d="M2 2h10v7.5H7.5L5 11.5V9.5H2V2z" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    label: 'Settings',
    href: '/settings',
    icon: (
      <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
        <circle cx="7" cy="7" r="1.8" stroke="currentColor" strokeWidth="1.4" />
        <path
          d="M7 1.5v1M7 11.5v1M1.5 7h1M11.5 7h1M3.2 3.2l.7.7M10.1 10.1l.7.7M10.8 3.2l-.7.7M3.9 10.1l-.7.7"
          stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"
        />
      </svg>
    ),
  },
  {
    label: 'Admin',
    href: '/admin',
    icon: (
      <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
        <path d="M7 1.5L2 3.5v3c0 2.8 2.1 5.4 5 6.1 2.9-.7 5-3.3 5-6.1v-3L7 1.5z" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
]

export function AppLayout({ children, sidebarContent }: AppLayoutProps) {
  const { logout } = useAuth()
  const { pathname } = useLocation()

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      <aside className="w-56 shrink-0 flex flex-col bg-sidebar border-r border-sidebar-border">
        <div className="flex items-center gap-2 px-3 py-3.5 border-b border-sidebar-border">
          <CanaryLogo size={24} />
          <span className="font-semibold text-sm tracking-tight text-sidebar-foreground">Canary</span>
        </div>

        <div className="flex-1 overflow-hidden flex flex-col">
          {sidebarContent}
        </div>

        <Separator className="bg-sidebar-border" />
        <div className="p-2 space-y-0.5">
          {NAV_ITEMS.map(item => (
            <Link
              key={item.href}
              to={item.href}
              className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-xs transition-colors ${
                pathname === item.href || (item.href === '/' && pathname.startsWith('/chat/'))
                  ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                  : 'text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
              }`}
            >
              {item.icon}
              {item.label}
            </Link>
          ))}
          <button
            onClick={logout}
            className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-xs text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground transition-colors"
          >
            <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
              <path d="M5 2H2v10h3M9 10l3-3-3-3M12 7H5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 flex flex-col overflow-hidden">
        {children}
      </main>
    </div>
  )
}
