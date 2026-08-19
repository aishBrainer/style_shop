import Link from 'next/link'
import { Sparkles } from 'lucide-react'

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex min-h-screen items-center justify-center px-6 py-12">
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-0 h-[420px] w-[720px]
                   -translate-x-1/2 rounded-full bg-accent/10 blur-[140px]"
      />
      <div className="relative w-full max-w-sm">
        <Link href="/" className="mb-8 flex items-center justify-center gap-2.5 font-medium">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-white">
            <Sparkles className="h-4 w-4" />
          </span>
          AI Fashion Studio
        </Link>
        {children}
      </div>
    </div>
  )
}
