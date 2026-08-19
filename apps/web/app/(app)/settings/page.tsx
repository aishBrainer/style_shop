'use client'

/** §7 account management + §102 data rights. */

import { useMutation } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { ApiError, api } from '@/lib/api'
import { useSession } from '@/lib/hooks'
import { Badge, Button, Card, Field, Input, Modal } from '@/components/ui'
import { useToast } from '@/components/ui/toast'

export default function SettingsPage() {
  const toast = useToast()
  const { data: session } = useSession()

  const [fullName, setFullName] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [confirmText, setConfirmText] = useState('')
  const [deletePassword, setDeletePassword] = useState('')

  useEffect(() => {
    if (session?.user.full_name) setFullName(session.user.full_name)
  }, [session])

  const saveProfile = useMutation({
    mutationFn: () => api.auth.updateProfile(fullName),
    onSuccess: () => toast.success('Profile updated'),
    onError: () => toast.error('Could not update your profile'),
  })

  const changePassword = useMutation({
    mutationFn: () => api.auth.changePassword(currentPassword, newPassword),
    onSuccess: () => {
      // The API revokes every session on a password change, so the cookie in
      // this tab is already dead — send the user to sign in again.
      toast.success('Password changed', 'Please sign in again.')
      setTimeout(() => (window.location.href = '/login'), 1200)
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : 'Could not change your password'),
  })

  const deleteAccount = useMutation({
    mutationFn: () => api.auth.deleteAccount(confirmText, deletePassword || undefined),
    onSuccess: () => {
      window.location.href = '/'
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : 'Could not delete your account'),
  })

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="mt-1 text-sm text-ink-muted">Your account and workspace.</p>
      </header>

      <Card className="space-y-4">
        <h2 className="text-sm font-medium">Profile</h2>

        <Field label="Email">
          <div className="flex items-center gap-2">
            <Input value={session?.user.email ?? ''} disabled />
            {session?.user.email_verified_at ? (
              <Badge tone="success">Verified</Badge>
            ) : (
              <Button
                size="sm"
                variant="secondary"
                onClick={async () => {
                  await api.auth.requestVerification()
                  toast.success('Verification email sent')
                }}
              >
                Verify
              </Button>
            )}
          </div>
        </Field>

        <Field label="Name">
          <Input value={fullName} onChange={(e) => setFullName(e.target.value)} />
        </Field>

        <div className="flex justify-end">
          <Button onClick={() => saveProfile.mutate()} loading={saveProfile.isPending}>
            Save
          </Button>
        </div>
      </Card>

      <Card className="space-y-4">
        <h2 className="text-sm font-medium">Password</h2>
        <Field label="Current password">
          <Input
            type="password"
            autoComplete="current-password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
          />
        </Field>
        <Field label="New password" hint="At least 10 characters.">
          <Input
            type="password"
            autoComplete="new-password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
        </Field>
        <div className="flex justify-end">
          <Button
            variant="secondary"
            onClick={() => changePassword.mutate()}
            loading={changePassword.isPending}
            disabled={!currentPassword || newPassword.length < 10}
          >
            Change password
          </Button>
        </div>
      </Card>

      <Card className="space-y-3">
        <h2 className="text-sm font-medium">Workspace</h2>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-xs text-ink-faint">Name</dt>
            <dd>{session?.organization.name}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-faint">Plan</dt>
            <dd className="capitalize">{session?.organization.plan}</dd>
          </div>
        </dl>
      </Card>

      <Card className="border-danger/25">
        <h2 className="text-sm font-medium text-danger">Delete account</h2>
        <p className="mt-1.5 text-sm text-ink-muted">
          Removes your account, your workspace and every asset in it. Generated images are
          permanently deleted after a 30-day recovery window.
        </p>
        <Button variant="danger" className="mt-4" onClick={() => setDeleting(true)}>
          Delete my account
        </Button>
      </Card>

      <Modal
        open={deleting}
        onClose={() => setDeleting(false)}
        title="Delete your account"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleting(false)}>Cancel</Button>
            <Button
              variant="danger"
              onClick={() => deleteAccount.mutate()}
              loading={deleteAccount.isPending}
              disabled={confirmText.trim().toUpperCase() !== 'DELETE'}
            >
              Delete permanently
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <p className="text-sm text-ink-muted">This cannot be undone.</p>
          {session?.user.email_verified_at !== null && (
            <Field label="Password">
              <Input
                type="password"
                value={deletePassword}
                onChange={(e) => setDeletePassword(e.target.value)}
                placeholder="Leave blank if you signed up with Google"
              />
            </Field>
          )}
          <Field label='Type "DELETE" to confirm'>
            <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
          </Field>
        </div>
      </Modal>
    </div>
  )
}
