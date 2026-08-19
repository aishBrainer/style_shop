'use client'

import Link from 'next/link'
import { useState } from 'react'

import { api } from '@/lib/api'
import { Button, Card, Field, Input } from '@/components/ui'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    try {
      await api.auth.forgotPassword(email)
    } finally {
      // Always show the same confirmation, whether or not the address exists —
      // anything else turns this form into an account-enumeration oracle.
      setSent(true)
      setSubmitting(false)
    }
  }

  if (sent) {
    return (
      <Card>
        <h1 className="display text-xl">Check your inbox</h1>
        <p className="mt-2 text-sm text-ink-muted">
          If <span className="text-ink">{email}</span> is registered, a reset link is on its way.
          It expires in one hour.
        </p>
        <Link href="/login" className="mt-6 block">
          <Button variant="secondary" className="w-full">Back to sign in</Button>
        </Link>
      </Card>
    )
  }

  return (
    <Card>
      <h1 className="display text-xl">Reset your password</h1>
      <p className="mt-1 text-sm text-ink-muted">We will email you a link.</p>

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
        <Button type="submit" className="w-full" loading={submitting}>
          Send reset link
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-ink-muted">
        <Link href="/login" className="transition hover:text-ink">Back to sign in</Link>
      </p>
    </Card>
  )
}
