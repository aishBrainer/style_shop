'use client'

import { useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'

import { ApiError, api } from '@/lib/api'
import { Button, Card, Field, Input } from '@/components/ui'

const MIN_PASSWORD_LENGTH = 10

export default function RegisterPage() {
  const router = useRouter()
  const queryClient = useQueryClient()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)

  const passwordTooShort = password.length > 0 && password.length < MIN_PASSWORD_LENGTH

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setFieldErrors({})
    setSubmitting(true)

    try {
      const session = await api.auth.register(email, password, fullName || undefined)
      queryClient.setQueryData(['session'], session)
      router.push('/dashboard')
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors)
        setError(Object.keys(err.fieldErrors).length ? null : err.message)
      } else {
        setError('Something went wrong. Please try again.')
      }
      setSubmitting(false)
    }
  }

  return (
    <Card>
      <h1 className="text-lg font-medium">Create your studio</h1>
      <p className="mt-1 text-sm text-ink-muted">25 free credits, no card required.</p>

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <Field label="Name" error={fieldErrors.full_name}>
          <Input
            autoComplete="name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Alex Chen"
          />
        </Field>

        <Field label="Email" error={fieldErrors.email}>
          <Input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@brand.com"
          />
        </Field>

        <Field
          label="Password"
          error={fieldErrors.password}
          hint={passwordTooShort ? undefined : `At least ${MIN_PASSWORD_LENGTH} characters.`}
        >
          <Input
            type="password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••••"
          />
          {passwordTooShort && (
            <p className="mt-1.5 text-xs text-warning">
              {MIN_PASSWORD_LENGTH - password.length} more character
              {MIN_PASSWORD_LENGTH - password.length === 1 ? '' : 's'} needed.
            </p>
          )}
        </Field>

        {error && (
          <p role="alert" className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
            {error}
          </p>
        )}

        <Button type="submit" className="w-full" loading={submitting}>
          Create account
        </Button>
      </form>

      <div className="my-5 flex items-center gap-3 text-xs text-ink-faint">
        <span className="h-px flex-1 bg-edge" /> or <span className="h-px flex-1 bg-edge" />
      </div>

      <a href="/api/v1/auth/google/start">
        <Button variant="secondary" className="w-full" type="button">
          Continue with Google
        </Button>
      </a>

      <p className="mt-6 text-center text-sm text-ink-muted">
        Already have an account?{' '}
        <Link href="/login" className="text-accent transition hover:text-accent-hover">
          Sign in
        </Link>
      </p>
    </Card>
  )
}
