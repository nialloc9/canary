import { useState, useEffect } from 'react'
import { AppLayout } from '../components/AppLayout'
import { api } from '../api/client'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Card, CardContent, CardFooter, CardHeader, CardTitle, CardDescription } from '../components/ui/card'

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

function StatusMessage({ status, savedText = 'Saved', errorText = 'Failed to save' }: { status: SaveStatus; savedText?: string; errorText?: string }) {
  if (status === 'saved') return <span className="text-xs text-green-500">{savedText}</span>
  if (status === 'error') return <span className="text-xs text-destructive">{errorText}</span>
  return null
}

export function SettingsPage() {
  const [profile, setProfile] = useState({ username: '', email: '' })
  const [profileStatus, setProfileStatus] = useState<SaveStatus>('idle')

  const [password, setPassword] = useState({ current: '', next: '', confirm: '' })
  const [passwordStatus, setPasswordStatus] = useState<SaveStatus>('idle')
  const [passwordError, setPasswordError] = useState('')

  useEffect(() => {
    api.getProfile().then(u => setProfile({ username: u.username, email: u.email })).catch(() => {})
  }, [])

  async function saveProfile() {
    setProfileStatus('saving')
    try {
      await api.updateProfile(profile)
      setProfileStatus('saved')
      setTimeout(() => setProfileStatus('idle'), 2500)
    } catch {
      setProfileStatus('error')
    }
  }

  async function updatePassword() {
    setPasswordError('')
    if (password.next !== password.confirm) {
      setPasswordError('Passwords do not match')
      return
    }
    if (password.next.length < 8) {
      setPasswordError('Must be at least 8 characters')
      return
    }
    setPasswordStatus('saving')
    try {
      await api.updatePassword({ current: password.current, next: password.next })
      setPasswordStatus('saved')
      setPassword({ current: '', next: '', confirm: '' })
      setTimeout(() => setPasswordStatus('idle'), 2500)
    } catch {
      setPasswordStatus('error')
    }
  }

  return (
    <AppLayout>
      <div className="flex-1 overflow-auto">
        <div className="max-w-xl mx-auto px-6 py-10 space-y-8">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
            <p className="text-sm text-muted-foreground mt-0.5">Manage your account preferences</p>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Profile</CardTitle>
              <CardDescription>Update your display name and email address</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="username" className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  Username
                </Label>
                <Input
                  id="username"
                  value={profile.username}
                  onChange={e => setProfile(p => ({ ...p, username: e.target.value }))}
                  className="bg-input/50 border-border/60"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="email" className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  Email
                </Label>
                <Input
                  id="email"
                  type="email"
                  value={profile.email}
                  onChange={e => setProfile(p => ({ ...p, email: e.target.value }))}
                  className="bg-input/50 border-border/60"
                />
              </div>
            </CardContent>
            <CardFooter className="gap-3">
              <Button
                size="sm"
                onClick={saveProfile}
                disabled={profileStatus === 'saving'}
                className="shadow-md shadow-primary/20"
              >
                {profileStatus === 'saving' ? 'Saving…' : 'Save profile'}
              </Button>
              <StatusMessage status={profileStatus} savedText="Profile updated" />
            </CardFooter>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Password</CardTitle>
              <CardDescription>Change your account password</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="current-password" className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  Current password
                </Label>
                <Input
                  id="current-password"
                  type="password"
                  value={password.current}
                  onChange={e => setPassword(p => ({ ...p, current: e.target.value }))}
                  autoComplete="current-password"
                  className="bg-input/50 border-border/60"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="new-password" className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  New password
                </Label>
                <Input
                  id="new-password"
                  type="password"
                  value={password.next}
                  onChange={e => setPassword(p => ({ ...p, next: e.target.value }))}
                  autoComplete="new-password"
                  className="bg-input/50 border-border/60"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="confirm-password" className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  Confirm new password
                </Label>
                <Input
                  id="confirm-password"
                  type="password"
                  value={password.confirm}
                  onChange={e => setPassword(p => ({ ...p, confirm: e.target.value }))}
                  autoComplete="new-password"
                  className="bg-input/50 border-border/60"
                />
              </div>
              {passwordError && (
                <p className="text-xs text-destructive bg-destructive/10 border border-destructive/20 px-3 py-2 rounded-md">
                  {passwordError}
                </p>
              )}
            </CardContent>
            <CardFooter className="gap-3">
              <Button
                size="sm"
                onClick={updatePassword}
                disabled={
                  passwordStatus === 'saving' ||
                  !password.current ||
                  !password.next ||
                  !password.confirm
                }
                className="shadow-md shadow-primary/20"
              >
                {passwordStatus === 'saving' ? 'Updating…' : 'Update password'}
              </Button>
              <StatusMessage status={passwordStatus} savedText="Password updated" errorText="Failed to update" />
            </CardFooter>
          </Card>
        </div>
      </div>
    </AppLayout>
  )
}
