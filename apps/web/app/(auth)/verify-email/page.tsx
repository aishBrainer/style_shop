'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Suspense, useEffect, useRef, useState } from 'react'
import { CheckCircle2, Loader2, XCircle } from 'lucide-react'

import { ApiError, api } from '@/lib/api'
import { Button, Card } from '@/components/ui'

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<Card className="h-48" />}>
      <VerifyEmail />
    </Suspense>
  )
}

function VerifyEmail() {
  const token = useSearchParams().get('token')
  const [state, setState] = useState<'pending' | 'ok' | 'error'>('pending')
  const [message, setMessage] = useState('')
  const attempted = useRef(false)

  useEffect(() => {
    if (!token) {
      setState('error')
      setMessage('That link is missing its token.')
      return
    }
    // React 18 StrictMode mounts effects twice in development; verifying twice
    // would show a spurious failure on the second call.
    if (attempted.current) return
    attempted.current = true

    api.auth
      .verifyEmail(token)
      .then(() => setState('ok'))
      .catch((err) => {
        setState('error')
        setMessage(
          err instanceof ApiError ? err.message : 'That link is invalid or has expired.',
        )
      })
  }, [token])

  return (
    <Card className="text-center">
      {state === 'pending' && (
        <>
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-accent" />
          <p className="mt-4 text-sm text-ink-muted">Verifying your email…</p>
        </>
      )}

      {state === 'ok' && (
        <>
          <CheckCircle2 className="mx-auto h-8 w-8 text-success" />
          <h1 className="mt-4 display text-xl">Email verified</h1>
          <p className="mt-1 text-sm text-ink-muted">Your account is fully active.</p>
          <Link href="/dashboard" className="mt-6 block">
            <Button className="w-full">Go to your studio</Button>
          </Link>
        </>
      )}

      {state === 'error' && (
        <>
          <XCircle className="mx-auto h-8 w-8 text-danger" />
          <h1 className="mt-4 display text-xl">Could not verify</h1>
          <p className="mt-1 text-sm text-ink-muted">{message}</p>
          <Link href="/settings" className="mt-6 block">
            <Button variant="secondary" className="w-full">Request a new link</Button>
          </Link>
        </>
      )}
    </Card>
  )
}
