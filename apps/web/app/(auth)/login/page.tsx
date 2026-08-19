'use client'

import { useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { Suspense, useState } from 'react'

import { ApiError, api } from '@/lib/api'
import { Button, Card, Field, Input } from '@/components/ui'

const OAUTH_ERRORS: Record<string, string> = {
  oauth_failed: 'Google sign-in did not complete. Please try again.',
  oauth_state: 'That sign-in attempt expired. Please try again.',
  email_unverified: 'Your Google account email is not verified.',
}

export default function LoginPage() {
  return (
    <Suspense fallback={<Card className="h-72" />}>
      <LoginForm />
    </Suspense>
  )
}

function LoginForm() {
  const router = useRouter()
  const params = useSearchParams()
  const queryClient = useQueryClient()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(OAUTH_ERRORS[params.get('error') ?? ''] ?? null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)

    try {
      const session = await api.auth.login(email, password)
      // Seed the cache so the dashboard does not flash a loading state.
      queryClient.setQueryData(['session'], session)
      router.push(params.get('next') || '/dashboard')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
      setSubmitting(false)
    }
  }

  return (
    <Card>
      <h1 className="text-lg font-medium">Welcome back</h1>
      <p className="mt-1 text-sm text-ink-muted">Sign in to your studio.</p>

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <Field label="Email">
          <Input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@brand.com"
          />
        </Field>

        <Field label="Password">
          <Input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••••"
          />
        </Field>

        {error && (
          <p role="alert" className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
            {error}
          </p>
        )}

        <Button type="submit" className="w-full" loading={submitting}>
          Sign in
        </Button>
      </form>

      <div className="my-5 flex items-center gap-3 text-xs text-ink-faint">
        <span className="h-px flex-1 bg-edge" /> or <span className="h-px flex-1 bg-edge" />
      </div>

      {/* A full navigation, not fetch — the OAuth flow redirects the browser. */}
      <a href="/api/v1/auth/google/start">
        <Button variant="secondary" className="w-full" type="button">
          Continue with Google
        </Button>
      </a>

      <p className="mt-6 text-center text-sm text-ink-muted">
        <Link href="/forgot-password" className="transition hover:text-ink">
          Forgot your password?
        </Link>
      </p>
      <p className="mt-2 text-center text-sm text-ink-muted">
        New here?{' '}
        <Link href="/register" className="text-accent transition hover:text-accent-hover">
          Create an account
        </Link>
      </p>
    </Card>
  )
}
