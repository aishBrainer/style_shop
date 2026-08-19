'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import {
  Boxes,
  FolderOpen,
  Home,
  Images,
  LayoutGrid,
  LogOut,
  Menu,
  Palette,
  Settings,
  Shield,
  Sparkles,
  Users,
  Wallet,
  X,
} from 'lucide-react'

import { api } from '@/lib/api'
import { useJobStream, useSession } from '@/lib/hooks'
import { cn } from '@/lib/utils'
import { Badge, Button, Skeleton } from '@/components/ui'
import { useToast } from '@/components/ui/toast'

/** §8 — the app shell. Deliberately not a generic admin dashboard. */

const STUDIO_TOOLS = [
  { href: '/studio/vton', label: 'Virtual Try-On' },
  { href: '/studio/photography', label: 'Product Photography' },
  { href: '/studio/background', label: 'Background' },
  { href: '/studio/editor', label: 'Image Editor' },
]

const NAV = [
  { href: '/dashboard', label: 'Home', icon: Home },
  { href: '/projects', label: 'Projects', icon: FolderOpen },
  { href: '/models', label: 'Models', icon: Users },
  { href: '/products', label: 'Products', icon: Boxes },
  { href: '/creations', label: 'Creations', icon: Images },
  { href: '/brand-kit', label: 'Brand Kit', icon: Palette },
  { href: '/billing', label: 'Billing', icon: Wallet },
  { href: '/settings', label: 'Settings', icon: Settings },
]

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const toast = useToast()
  const { data: session, isLoading, isError } = useSession()
  const [mobileOpen, setMobileOpen] = useState(false)

  // One SSE connection for the whole authenticated app (§57).
  useJobStream((event, job) => {
    if (event === 'job.completed') toast.success('Generation complete', 'Your image is ready.')
    if (event === 'job.failed') toast.error('Generation failed', 'The credit has been refunded.')
  })

  useEffect(() => {
    if (isError) router.replace(`/login?next=${encodeURIComponent(pathname)}`)
  }, [isError, pathname, router])

  useEffect(() => {
    setMobileOpen(false)
  }, [pathname])

  if (isLoading) {
    return (
      <div className="flex min-h-screen">
        <Skeleton className="hidden w-60 lg:block" />
        <div className="flex-1 space-y-4 p-8">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-64 w-full" />
        </div>
      </div>
    )
  }

  if (!session) return null

  return (
    <div className="flex min-h-screen">
      <Sidebar
        pathname={pathname}
        isAdmin={session.user.role === 'admin'}
        className={cn(
          'fixed inset-y-0 left-0 z-50 w-64 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0',
          mobileOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      />

      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-plum/40 lg:hidden"
          onClick={() => setMobileOpen(false)}
          role="presentation"
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-4 border-b border-edge bg-canvas/80 px-4 backdrop-blur-xl sm:px-6">
          <button
            className="rounded-lg p-2 text-ink-muted transition hover:bg-canvas-overlay lg:hidden"
            onClick={() => setMobileOpen((v) => !v)}
            aria-label="Toggle navigation"
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>

          <div className="ml-auto flex items-center gap-3">
            <Link href="/billing">
              <Badge tone={session.organization.credit_balance > 5 ? 'accent' : 'warning'}>
                <Sparkles className="h-3 w-3" />
                {session.organization.credit_balance} credits
              </Badge>
            </Link>

            <div className="hidden text-right sm:block">
              <p className="text-sm leading-tight">{session.user.full_name || session.user.email}</p>
              <p className="text-xs capitalize leading-tight text-ink-faint">
                {session.organization.plan} plan
              </p>
            </div>

            <Button
              variant="ghost"
              size="sm"
              aria-label="Sign out"
              onClick={async () => {
                await api.auth.logout()
                // Full reload rather than router.push — clears every cached
                // query so no previous tenant's data can linger in memory.
                window.location.href = '/login'
              }}
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </header>

        <main className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  )
}

function Sidebar({
  pathname,
  isAdmin,
  className,
}: {
  pathname: string
  isAdmin: boolean
  className?: string
}) {
  return (
    <aside
      className={cn(
        'flex flex-col border-r border-edge bg-canvas-raised transition-transform',
        className,
      )}
    >
      <Link href="/dashboard" className="flex h-16 items-center gap-2.5 border-b border-edge px-5 font-medium">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-white">
          <Sparkles className="h-4 w-4" />
        </span>
        <span className="text-sm">AI Fashion Studio</span>
      </Link>

      <nav className="flex-1 overflow-y-auto p-3">
        <NavLink href="/dashboard" icon={Home} label="Home" active={pathname === '/dashboard'} />

        <p className="mb-1 mt-4 px-3 text-[11px] font-medium uppercase tracking-wider text-ink-faint">
          Studio
        </p>
        <div className="space-y-0.5">
          {STUDIO_TOOLS.map((tool) => (
            <NavLink
              key={tool.href}
              href={tool.href}
              icon={LayoutGrid}
              label={tool.label}
              active={pathname.startsWith(tool.href)}
            />
          ))}
        </div>

        <p className="mb-1 mt-4 px-3 text-[11px] font-medium uppercase tracking-wider text-ink-faint">
          Library
        </p>
        <div className="space-y-0.5">
          {NAV.slice(1).map((item) => (
            <NavLink
              key={item.href}
              href={item.href}
              icon={item.icon}
              label={item.label}
              active={pathname.startsWith(item.href)}
            />
          ))}
        </div>

        {isAdmin && (
          <>
            <p className="mb-1 mt-4 px-3 text-[11px] font-medium uppercase tracking-wider text-ink-faint">
              Platform
            </p>
            <NavLink href="/admin" icon={Shield} label="Admin" active={pathname.startsWith('/admin')} />
          </>
        )}
      </nav>
    </aside>
  )
}

function NavLink({
  href,
  icon: Icon,
  label,
  active,
}: {
  href: string
  icon: typeof Home
  label: string
  active: boolean
}) {
  return (
    <Link
      href={href}
      className={cn(
        'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition',
        active ? 'bg-accent-muted text-accent' : 'text-ink-muted hover:bg-canvas-overlay hover:text-ink',
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      {label}
    </Link>
  )
}
