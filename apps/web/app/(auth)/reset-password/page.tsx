'use client'

import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { Suspense, useState } from 'react'

import { ApiError, api } from '@/lib/api'
import { Button, Card, Field, Input } from '@/components/ui'

const MIN_PASSWORD_LENGTH = 10

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<Card className="h-64" />}>
      <ResetPasswordForm />
    </Suspense>
  )
}

function ResetPasswordForm() {
  const router = useRouter()
  const token = useSearchParams().get('token')

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const mismatch = confirm.length > 0 && password !== confirm

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!token || mismatch) return

    setError(null)
    setSubmitting(true)
    try {
      await api.auth.resetPassword(token, password)
      router.push('/login?reset=1')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
      setSubmitting(false)
    }
  }

  if (!token) {
    return (
      <Card>
        <h1 className="text-lg font-medium">Invalid reset link</h1>
        <p className="mt-2 text-sm text-ink-muted">
          That link is missing its token. Request a new one.
        </p>
        <Link href="/forgot-password" className="mt-6 block">
          <Button variant="secondary" className="w-full">Request a new link</Button>
        </Link>
      </Card>
    )
  }

  return (
    <Card>
      <h1 className="text-lg font-medium">Choose a new password</h1>

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <Field label="New password" hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}>
          <Input
            type="password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>

        <Field label="Confirm password" error={mismatch ? 'Passwords do not match.' : undefined}>
          <Input
            type="password"
            required
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </Field>

        {error && (
          <p role="alert" className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
            {error}
          </p>
        )}

        <Button
          type="submit"
          className="w-full"
          loading={submitting}
          disabled={mismatch || password.length < MIN_PASSWORD_LENGTH}
        >
          Set new password
        </Button>
      </form>
    </Card>
  )
}
