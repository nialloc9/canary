import { useState, FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Card, CardContent, CardFooter, CardHeader, CardTitle, CardDescription } from '../components/ui/card'

const FEATURES = [
  { icon: '⚡', label: 'Real-time data pipelines', desc: 'Stream and process data at any scale' },
  { icon: '🤖', label: 'AI-powered insights', desc: 'Surface patterns and anomalies automatically' },
  { icon: '🔒', label: 'Enterprise security', desc: 'SOC 2 compliant with fine-grained access control' },
]

export function SignupPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({
    account_name: '',
    account_domain: '',
    email: '',
    username: '',
    password: '',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function setField(key: keyof typeof form, value: string) {
    setForm(f => ({ ...f, [key]: value }))
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await register(form)
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative min-h-screen flex bg-background overflow-hidden">
      {/* Dot grid */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.3]"
        style={{
          backgroundImage: 'radial-gradient(oklch(0.35 0.04 264) 1px, transparent 1px)',
          backgroundSize: '28px 28px',
        }}
      />
      {/* Ambient glow top-left */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 -left-40 w-[600px] h-[600px] rounded-full bg-primary/10 blur-[160px]" />
        <div className="absolute bottom-0 right-0 w-[400px] h-[400px] rounded-full bg-primary/6 blur-[120px]" />
      </div>

      {/* Left branding panel */}
      <div className="relative hidden lg:flex lg:w-1/2 flex-col justify-between p-12">
        <div className="flex items-center gap-2.5">
          <div className="size-9 rounded-xl bg-primary flex items-center justify-center shadow-lg shadow-primary/30">
            <svg width="18" height="18" viewBox="0 0 32 32" fill="none">
              <path d="M10 22 L16 10 L22 22" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" fill="none" />
              <path d="M12.5 18 L19.5 18" stroke="white" strokeWidth="3" strokeLinecap="round" />
            </svg>
          </div>
          <span className="text-base font-semibold tracking-tight text-foreground">Canary</span>
        </div>

        <div className="space-y-10">
          <div className="space-y-4">
            <h1 className="text-4xl font-bold tracking-tight leading-tight">
              The AI data platform
              <br />
              <span className="text-primary">built for scale.</span>
            </h1>
            <p className="text-muted-foreground text-base leading-relaxed max-w-sm">
              Unify your data, surface insights, and act on them — all from one intelligent workspace.
            </p>
          </div>
          <ul className="space-y-5">
            {FEATURES.map(f => (
              <li key={f.label} className="flex items-start gap-3">
                <span className="text-xl mt-0.5">{f.icon}</span>
                <div>
                  <p className="text-sm font-medium text-foreground">{f.label}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{f.desc}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="text-xs text-muted-foreground/60">
          © {new Date().getFullYear()} Pensieve Technologies
        </p>
      </div>

      {/* Divider */}
      <div className="hidden lg:block w-px bg-border/40 my-8" />

      {/* Right form panel */}
      <div className="relative z-10 flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-md">
          {/* Mobile brand */}
          <div className="flex items-center gap-2 mb-8 lg:hidden">
            <div className="size-8 rounded-xl bg-primary flex items-center justify-center shadow-lg shadow-primary/30">
              <svg width="16" height="16" viewBox="0 0 32 32" fill="none">
                <path d="M10 22 L16 10 L22 22" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" fill="none" />
                <path d="M12.5 18 L19.5 18" stroke="white" strokeWidth="3" strokeLinecap="round" />
              </svg>
            </div>
            <span className="text-base font-semibold tracking-tight">Canary</span>
          </div>

          <Card className="border-border/60 bg-card/80 backdrop-blur-sm shadow-2xl shadow-black/40">
            <CardHeader className="space-y-1 pb-4">
              <CardTitle className="text-xl tracking-tight">Create your account</CardTitle>
              <CardDescription>Set up your workspace in under a minute</CardDescription>
            </CardHeader>
            <form onSubmit={handleSubmit}>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="account_name" className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                      Account name
                    </Label>
                    <Input
                      id="account_name"
                      placeholder="Acme Corp"
                      value={form.account_name}
                      onChange={e => setField('account_name', e.target.value)}
                      autoFocus
                      required
                      className="bg-input/50 border-border/60 focus-visible:ring-primary/50"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="account_domain" className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                      Domain
                    </Label>
                    <Input
                      id="account_domain"
                      placeholder="acme"
                      value={form.account_domain}
                      onChange={e => setField('account_domain', e.target.value)}
                      required
                      className="bg-input/50 border-border/60 focus-visible:ring-primary/50"
                    />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="email" className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                    Work email
                  </Label>
                  <Input
                    id="email"
                    type="email"
                    value={form.email}
                    onChange={e => setField('email', e.target.value)}
                    autoComplete="email"
                    required
                    className="bg-input/50 border-border/60 focus-visible:ring-primary/50"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="username" className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                    Username
                  </Label>
                  <Input
                    id="username"
                    value={form.username}
                    onChange={e => setField('username', e.target.value)}
                    autoComplete="username"
                    required
                    className="bg-input/50 border-border/60 focus-visible:ring-primary/50"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="password" className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                    Password
                  </Label>
                  <Input
                    id="password"
                    type="password"
                    value={form.password}
                    onChange={e => setField('password', e.target.value)}
                    autoComplete="new-password"
                    required
                    className="bg-input/50 border-border/60 focus-visible:ring-primary/50"
                  />
                </div>
                {error && (
                  <p className="text-xs text-destructive bg-destructive/10 border border-destructive/20 px-3 py-2 rounded-md">
                    {error}
                  </p>
                )}
              </CardContent>
              <CardFooter className="flex flex-col gap-3 pt-2">
                <Button type="submit" className="w-full shadow-md shadow-primary/20" disabled={loading}>
                  {loading ? 'Creating account…' : 'Create account'}
                </Button>
                <p className="text-xs text-muted-foreground text-center">
                  Already have an account?{' '}
                  <Link to="/login" className="text-primary hover:text-primary/80 font-medium transition-colors">
                    Sign in
                  </Link>
                </p>
              </CardFooter>
            </form>
          </Card>
        </div>
      </div>
    </div>
  )
}
