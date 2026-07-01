import { useState, useEffect } from 'react'
import { AppLayout } from '../components/AppLayout'
import { api, OrgSettings, WarehouseConfig, CloudConfig, ProjectOut, GitHubRepoOut, GitHubRepoConnect } from '../api/client'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Card, CardContent, CardFooter, CardHeader, CardTitle, CardDescription } from '../components/ui/card'

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'
type Tab = 'organization' | 'warehouse' | 'cloud' | 'projects'

function StatusMessage({ status, savedText = 'Saved', errorText = 'Failed to save' }: {
  status: SaveStatus
  savedText?: string
  errorText?: string
}) {
  if (status === 'saved') return <span className="text-xs text-green-500">{savedText}</span>
  if (status === 'error') return <span className="text-xs text-destructive">{errorText}</span>
  return null
}

function FieldRow({ id, label, children }: { id?: string; label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
        {label}
      </Label>
      {children}
    </div>
  )
}

const AWS_REGIONS = [
  'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
  'eu-west-1', 'eu-west-2', 'eu-central-1',
  'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1',
  'ca-central-1', 'sa-east-1',
]

function NativeSelect({ id, value, onChange, children, className = '' }: {
  id?: string
  value: string
  onChange: (v: string) => void
  children: React.ReactNode
  className?: string
}) {
  return (
    <select
      id={id}
      value={value}
      onChange={e => onChange(e.target.value)}
      className={`h-8 w-full min-w-0 rounded-lg border border-input bg-input/30 px-2.5 py-1 text-sm text-foreground outline-none transition-colors focus:border-ring focus:ring-3 focus:ring-ring/50 dark:bg-input/30 ${className}`}
    >
      {children}
    </select>
  )
}

// ── Organization tab ──────────────────────────────────────────────────────────

function OrgTab() {
  const [org, setOrg] = useState<OrgSettings>({ name: '', domain: '' })
  const [status, setStatus] = useState<SaveStatus>('idle')

  useEffect(() => {
    api.getOrgSettings().then(setOrg).catch(() => {})
  }, [])

  async function save() {
    setStatus('saving')
    try {
      await api.updateOrgSettings(org)
      setStatus('saved')
      setTimeout(() => setStatus('idle'), 2500)
    } catch {
      setStatus('error')
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Organization</CardTitle>
        <CardDescription>Update your workspace name and domain</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <FieldRow id="org-name" label="Account name">
          <Input
            id="org-name"
            value={org.name}
            onChange={e => setOrg(o => ({ ...o, name: e.target.value }))}
            className="bg-input/50 border-border/60"
          />
        </FieldRow>
        <FieldRow id="org-domain" label="Account domain">
          <Input
            id="org-domain"
            value={org.domain}
            onChange={e => setOrg(o => ({ ...o, domain: e.target.value }))}
            className="bg-input/50 border-border/60"
          />
        </FieldRow>
      </CardContent>
      <CardFooter className="gap-3">
        <Button size="sm" onClick={save} disabled={status === 'saving'} className="shadow-md shadow-primary/20">
          {status === 'saving' ? 'Saving…' : 'Save organization'}
        </Button>
        <StatusMessage status={status} savedText="Organization updated" />
      </CardFooter>
    </Card>
  )
}

// ── Warehouse tab ─────────────────────────────────────────────────────────────

const WAREHOUSE_TYPES = [
  { id: 'snowflake', label: 'Snowflake', available: true },
  { id: 'bigquery', label: 'BigQuery', available: false },
  { id: 'redshift', label: 'Redshift', available: false },
] as const

function WarehouseTypeIcon({ type }: { type: string }) {
  if (type === 'snowflake') {
    return (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <path d="M12 2v20M12 2l-3 3M12 2l3 3M12 22l-3-3M12 22l3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M2 12h20M2 12l3-3M2 12l3 3M22 12l-3-3M22 12l-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M5.3 5.3l13.4 13.4M5.3 5.3l3.5 1M5.3 5.3l1 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M18.7 5.3L5.3 18.7M18.7 5.3l-1 3.5M18.7 5.3l-3.5 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    )
  }
  if (type === 'bigquery') {
    return (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
        <path d="M8 12l2.5 2.5L16 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <ellipse cx="12" cy="7" rx="8" ry="3" stroke="currentColor" strokeWidth="1.5" />
      <path d="M4 7v5c0 1.66 3.58 3 8 3s8-1.34 8-3V7" stroke="currentColor" strokeWidth="1.5" />
      <path d="M4 12v5c0 1.66 3.58 3 8 3s8-1.34 8-3v-5" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}

function ConnectionStatus({ status, message }: { status: 'idle' | 'testing' | 'ok' | 'fail'; message: string }) {
  if (status === 'idle') return null
  return (
    <div className={`flex items-center gap-2 text-xs px-3 py-2 rounded-md border ${
      status === 'testing' ? 'border-border/40 bg-muted/20 text-muted-foreground'
      : status === 'ok' ? 'border-green-500/30 bg-green-500/10 text-green-500'
      : 'border-destructive/30 bg-destructive/10 text-destructive'
    }`}>
      {status === 'testing' && <span className="size-3 rounded-full border-2 border-current border-t-transparent animate-spin" />}
      {status === 'ok' && <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.4" /><path d="M4.5 7l2 2 3-3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>}
      {status === 'fail' && <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.4" /><path d="M9 5L5 9M5 5l4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>}
      {status === 'testing' ? 'Testing connection…' : message}
    </div>
  )
}

function WarehouseTab() {
  const [config, setConfig] = useState<WarehouseConfig>({
    type: 'snowflake',
    account: '',
    username: '',
    authenticator: 'SNOWFLAKE',
  })
  const [secretInput, setSecretInput] = useState('')
  const [pemInput, setPemInput] = useState('')
  const [hasExistingSecret, setHasExistingSecret] = useState(false)
  const [hasExistingKey, setHasExistingKey] = useState(false)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'ok' | 'fail'>('idle')
  const [testMessage, setTestMessage] = useState('')

  useEffect(() => {
    api.getWarehouseConfig().then(w => {
      setConfig(w)
      setHasExistingSecret(!!w.password)
      setHasExistingKey(!!w.privateKeyB64)
    }).catch(() => {})
  }, [])

  const isKeyPair = config.authenticator === 'SNOWFLAKE_JWT'

  function buildPayload(): WarehouseConfig {
    const p: WarehouseConfig = { ...config }
    if (isKeyPair) {
      if (pemInput) p.privateKeyB64 = btoa(pemInput)
      p.password = undefined
    } else {
      if (secretInput) p.password = secretInput
      p.privateKeyB64 = undefined
    }
    return p
  }

  async function save() {
    setSaveStatus('saving')
    try {
      await api.updateWarehouseConfig(buildPayload())
      setSaveStatus('saved')
      if (isKeyPair && pemInput) { setPemInput(''); setHasExistingKey(true) }
      if (!isKeyPair && secretInput) { setSecretInput(''); setHasExistingSecret(true) }
      setTimeout(() => setSaveStatus('idle'), 2500)
    } catch {
      setSaveStatus('error')
    }
  }

  async function testConnection() {
    setTestStatus('testing')
    setTestMessage('')
    try {
      const result = await api.testWarehouseConnection(buildPayload())
      setTestStatus(result.ok ? 'ok' : 'fail')
      setTestMessage(result.message)
    } catch {
      setTestStatus('fail')
      setTestMessage('Connection failed')
    }
  }

  const canSave = !!config.account && !!config.username && (
    isKeyPair ? (hasExistingKey || !!pemInput) : (hasExistingSecret || !!secretInput)
  )

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Warehouse type</CardTitle>
          <CardDescription>Choose your data warehouse provider</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-3">
            {WAREHOUSE_TYPES.map(wt => (
              <button
                key={wt.id}
                disabled={!wt.available}
                onClick={() => wt.available && setConfig(c => ({ ...c, type: 'snowflake' }))}
                className={`relative flex flex-col items-center gap-2.5 rounded-xl border p-4 text-center transition-all ${
                  wt.available
                    ? config.type === wt.id
                      ? 'border-primary/60 bg-primary/8 text-foreground ring-1 ring-primary/30'
                      : 'border-border/60 bg-muted/20 text-foreground hover:border-border hover:bg-muted/40'
                    : 'border-border/30 bg-muted/10 text-muted-foreground/40 cursor-not-allowed'
                }`}
              >
                <WarehouseTypeIcon type={wt.id} />
                <span className="text-xs font-medium">{wt.label}</span>
                {!wt.available && (
                  <span className="absolute top-2 right-2 text-[9px] font-medium text-muted-foreground/50 bg-muted/40 px-1.5 py-0.5 rounded-full border border-border/30">
                    Soon
                  </span>
                )}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Connection parameters</CardTitle>
          <CardDescription>Account and username are required. All other fields are optional.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">

          {/* Required fields */}
          <div className="grid grid-cols-2 gap-4">
            <FieldRow id="wh-account" label="Account identifier *">
              <Input
                id="wh-account"
                value={config.account}
                onChange={e => setConfig(c => ({ ...c, account: e.target.value }))}
                placeholder="myorg.us-east-1"
                className="bg-input/50 border-border/60"
              />
            </FieldRow>
            <FieldRow id="wh-username" label="Username *">
              <Input
                id="wh-username"
                value={config.username}
                onChange={e => setConfig(c => ({ ...c, username: e.target.value }))}
                className="bg-input/50 border-border/60"
              />
            </FieldRow>
          </div>

          {/* Auth method toggle */}
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Authentication</p>
            <div className="flex gap-1 p-1 rounded-lg bg-muted/30 border border-border/40 w-fit">
              {(['SNOWFLAKE', 'SNOWFLAKE_JWT'] as const).map(method => (
                <button
                  key={method}
                  onClick={() => setConfig(c => ({ ...c, authenticator: method }))}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                    config.authenticator === method
                      ? 'bg-background text-foreground shadow-sm border border-border/60'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {method === 'SNOWFLAKE' ? 'Username / Password' : 'Key pair'}
                </button>
              ))}
            </div>
          </div>

          {/* Auth credential input */}
          {isKeyPair ? (
            <FieldRow id="wh-private-key" label="Private key (PEM)">
              <textarea
                id="wh-private-key"
                value={pemInput}
                onChange={e => setPemInput(e.target.value)}
                placeholder={hasExistingKey ? '••••••••  (key saved — paste new key to replace)' : '-----BEGIN PRIVATE KEY-----\n…\n-----END PRIVATE KEY-----'}
                rows={5}
                className="w-full rounded-lg border border-input bg-input/50 px-3 py-2 text-xs font-mono text-foreground placeholder:text-muted-foreground/50 outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/30 resize-none"
              />
              <p className="text-[10px] text-muted-foreground/60 mt-1">Paste your RSA private key PEM. It will be base64-encoded before being stored.</p>
            </FieldRow>
          ) : (
            <FieldRow id="wh-password" label="Password">
              <Input
                id="wh-password"
                type="password"
                value={secretInput}
                onChange={e => setSecretInput(e.target.value)}
                placeholder={hasExistingSecret ? '••••••••  (unchanged)' : 'Enter password'}
                className="bg-input/50 border-border/60"
              />
            </FieldRow>
          )}

          {/* Optional fields */}
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-3">Optional</p>
            <div className="grid grid-cols-2 gap-4">
              <FieldRow id="wh-database" label="Database">
                <Input
                  id="wh-database"
                  value={config.database ?? ''}
                  onChange={e => setConfig(c => ({ ...c, database: e.target.value || undefined }))}
                  placeholder="ANALYTICS"
                  className="bg-input/50 border-border/60"
                />
              </FieldRow>
              <FieldRow id="wh-schema" label="Schema">
                <Input
                  id="wh-schema"
                  value={config.schema ?? ''}
                  onChange={e => setConfig(c => ({ ...c, schema: e.target.value || undefined }))}
                  placeholder="PUBLIC"
                  className="bg-input/50 border-border/60"
                />
              </FieldRow>
              <FieldRow id="wh-warehouse" label="Warehouse">
                <Input
                  id="wh-warehouse"
                  value={config.warehouse ?? ''}
                  onChange={e => setConfig(c => ({ ...c, warehouse: e.target.value || undefined }))}
                  placeholder="COMPUTE_WH"
                  className="bg-input/50 border-border/60"
                />
              </FieldRow>
              <FieldRow id="wh-role" label="Role">
                <Input
                  id="wh-role"
                  value={config.role ?? ''}
                  onChange={e => setConfig(c => ({ ...c, role: e.target.value || undefined }))}
                  placeholder="SYSADMIN"
                  className="bg-input/50 border-border/60"
                />
              </FieldRow>
            </div>
          </div>

          <ConnectionStatus status={testStatus} message={testMessage} />
        </CardContent>
        <CardFooter className="gap-3">
          <Button size="sm" onClick={save} disabled={!canSave || saveStatus === 'saving'} className="shadow-md shadow-primary/20">
            {saveStatus === 'saving' ? 'Saving…' : 'Save configuration'}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={testConnection}
            disabled={!canSave || testStatus === 'testing'}
            className="border-border/60"
          >
            {testStatus === 'testing' ? 'Testing…' : 'Test connection'}
          </Button>
          <StatusMessage status={saveStatus} savedText="Configuration saved" />
        </CardFooter>
      </Card>
    </div>
  )
}

// ── Cloud tab ─────────────────────────────────────────────────────────────────

const CLOUD_PROVIDERS = [
  { id: 'aws', label: 'Amazon Web Services', available: true },
  { id: 'azure', label: 'Microsoft Azure', available: false },
  { id: 'gcp', label: 'Google Cloud', available: false },
] as const

function CloudProviderIcon({ provider }: { provider: string }) {
  if (provider === 'aws') {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
        <path d="M7 14c-1.66 0-3-1.34-3-3s1.34-3 3-3c.17 0 .34.01.5.04A4 4 0 0 1 11.5 5 4 4 0 0 1 15 7.5c.17-.03.33-.05.5-.05a2.5 2.5 0 0 1 0 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M8 19l2-2-2-2M16 19l-2-2 2-2M12 15v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  if (provider === 'azure') {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
        <path d="M5 19h14M12 5L7 13l5 2-7 4M12 5l5 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="1.5" />
      <path d="M12 2v4M12 18v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M2 12h4M18 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

function CloudTab() {
  const [config, setConfig] = useState<CloudConfig>({
    provider: 'aws',
    accessKeyId: '',
    region: 'us-east-1',
  })
  const [secretInput, setSecretInput] = useState('')
  const [hasExistingSecret, setHasExistingSecret] = useState(false)
  const [showSecret, setShowSecret] = useState(false)
  const [status, setStatus] = useState<SaveStatus>('idle')

  useEffect(() => {
    api.getCloudConfig().then(c => {
      setConfig(c)
      if (c.secretAccessKey) setHasExistingSecret(true)
    }).catch(() => {})
  }, [])

  async function save() {
    setStatus('saving')
    try {
      const payload: CloudConfig = { ...config }
      if (secretInput) payload.secretAccessKey = secretInput
      await api.updateCloudConfig(payload)
      setStatus('saved')
      if (secretInput) { setSecretInput(''); setHasExistingSecret(true) }
      setTimeout(() => setStatus('idle'), 2500)
    } catch {
      setStatus('error')
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Cloud provider</CardTitle>
          <CardDescription>Select your cloud platform for infrastructure integration</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-3">
            {CLOUD_PROVIDERS.map(cp => (
              <button
                key={cp.id}
                disabled={!cp.available}
                onClick={() => cp.available && setConfig(c => ({ ...c, provider: 'aws' }))}
                className={`relative flex flex-col items-center gap-2.5 rounded-xl border p-4 text-center transition-all ${
                  cp.available
                    ? config.provider === cp.id
                      ? 'border-primary/60 bg-primary/8 text-foreground ring-1 ring-primary/30'
                      : 'border-border/60 bg-muted/20 text-foreground hover:border-border hover:bg-muted/40'
                    : 'border-border/30 bg-muted/10 text-muted-foreground/40 cursor-not-allowed'
                }`}
              >
                <CloudProviderIcon provider={cp.id} />
                <span className="text-xs font-medium leading-tight">{cp.label}</span>
                {!cp.available && (
                  <span className="absolute top-2 right-2 text-[9px] font-medium text-muted-foreground/50 bg-muted/40 px-1.5 py-0.5 rounded-full border border-border/30">
                    Soon
                  </span>
                )}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>AWS credentials</CardTitle>
          <CardDescription>IAM access keys used to authenticate with AWS services</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <FieldRow id="aws-region" label="Default region">
            <NativeSelect
              id="aws-region"
              value={config.region}
              onChange={v => setConfig(c => ({ ...c, region: v }))}
            >
              {AWS_REGIONS.map(r => (
                <option key={r} value={r}>{r}</option>
              ))}
            </NativeSelect>
          </FieldRow>
          <FieldRow id="aws-key-id" label="Access key ID">
            <Input
              id="aws-key-id"
              value={config.accessKeyId}
              onChange={e => setConfig(c => ({ ...c, accessKeyId: e.target.value }))}
              placeholder="AKIAIOSFODNN7EXAMPLE"
              className="bg-input/50 border-border/60 font-mono text-sm"
            />
          </FieldRow>
          <FieldRow id="aws-secret" label="Secret access key">
            <div className="relative">
              <Input
                id="aws-secret"
                type={showSecret ? 'text' : 'password'}
                value={secretInput}
                onChange={e => setSecretInput(e.target.value)}
                placeholder={hasExistingSecret ? '••••••••  (unchanged)' : 'Enter secret access key'}
                className="bg-input/50 border-border/60 font-mono text-sm pr-9"
              />
              <button
                type="button"
                onClick={() => setShowSecret(s => !s)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/50 hover:text-muted-foreground transition-colors"
                aria-label={showSecret ? 'Hide secret' : 'Show secret'}
              >
                {showSecret ? (
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z" stroke="currentColor" strokeWidth="1.3" />
                    <circle cx="8" cy="8" r="2" stroke="currentColor" strokeWidth="1.3" />
                    <path d="M2 2l12 12" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                  </svg>
                ) : (
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z" stroke="currentColor" strokeWidth="1.3" />
                    <circle cx="8" cy="8" r="2" stroke="currentColor" strokeWidth="1.3" />
                  </svg>
                )}
              </button>
            </div>
          </FieldRow>
          <p className="text-xs text-muted-foreground/60">
            Credentials are encrypted at rest. Use an IAM user with least-privilege permissions.
          </p>
        </CardContent>
        <CardFooter className="gap-3">
          <Button size="sm" onClick={save} disabled={status === 'saving'} className="shadow-md shadow-primary/20">
            {status === 'saving' ? 'Saving…' : 'Save credentials'}
          </Button>
          <StatusMessage status={status} savedText="Credentials saved" />
        </CardFooter>
      </Card>
    </div>
  )
}

// ── Projects tab ──────────────────────────────────────────────────────────────

const EMPTY_FORM: GitHubRepoConnect = {
  project_name: '',
  repo_full_name: '',
  branch: 'develop',
  token: '',
  api_url: 'https://api.github.com',
  infrastructure_base_path: 'infrastructure',
  auto_merge: false,
  create_cicd: true,
  skip_bootstrap: false,
  skip_module_import: false,
}

function Toggle({
  id,
  checked,
  onChange,
  label,
  hint,
}: {
  id: string
  checked: boolean
  onChange: (v: boolean) => void
  label: string
  hint?: string
}) {
  return (
    <label htmlFor={id} className="flex items-start gap-3 cursor-pointer group">
      <div className="relative mt-0.5 shrink-0">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={e => onChange(e.target.checked)}
          className="sr-only"
        />
        <div
          className={`w-8 h-4.5 rounded-full transition-colors ${checked ? 'bg-primary' : 'bg-muted border border-border/60'}`}
          style={{ height: '18px' }}
        >
          <div
            className={`absolute top-0.5 size-3.5 rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-[18px]' : 'translate-x-0.5'}`}
          />
        </div>
      </div>
      <div>
        <p className="text-sm font-medium leading-none">{label}</p>
        {hint && <p className="text-xs text-muted-foreground/70 mt-0.5">{hint}</p>}
      </div>
    </label>
  )
}

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full border ${
      ok
        ? 'bg-green-500/10 border-green-500/30 text-green-600 dark:text-green-400'
        : 'bg-muted/40 border-border/40 text-muted-foreground/60'
    }`}>
      <span className={`size-1.5 rounded-full ${ok ? 'bg-green-500' : 'bg-muted-foreground/30'}`} />
      {label}
    </span>
  )
}

function ProjectsTab() {
  const [projects, setProjects] = useState<ProjectOut[]>([])
  const [repos, setRepos] = useState<Record<string, GitHubRepoOut>>({})
  const [form, setForm] = useState<GitHubRepoConnect>(EMPTY_FORM)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [status, setStatus] = useState<SaveStatus>('idle')
  const [error, setError] = useState('')
  const [disconnecting, setDisconnecting] = useState<string | null>(null)

  useEffect(() => {
    loadProjects()
  }, [])

  async function loadProjects() {
    try {
      const list = await api.listProjects()
      setProjects(list)
      const repoMap: Record<string, GitHubRepoOut> = {}
      await Promise.all(
        list.map(async p => {
          if (p.version_control_created) {
            try {
              repoMap[p.name] = await api.getRepo(p.name)
            } catch {}
          }
        })
      )
      setRepos(repoMap)
    } catch {}
  }

  async function connect() {
    setError('')
    setStatus('saving')
    try {
      await api.connectRepo(form)
      setStatus('saved')
      setForm(EMPTY_FORM)
      setTimeout(() => setStatus('idle'), 2500)
      await loadProjects()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to connect repository')
      setStatus('error')
    }
  }

  async function disconnect(projectName: string) {
    setDisconnecting(projectName)
    try {
      await api.disconnectRepo(projectName)
      await loadProjects()
    } catch {}
    setDisconnecting(null)
  }

  const isValid = form.project_name && form.repo_full_name && form.token

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Connect repository</CardTitle>
          <CardDescription>Link a GitHub repo to a project to enable landing zone management</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <FieldRow id="proj-name" label="Project name">
              <Input
                id="proj-name"
                value={form.project_name}
                onChange={e => setForm(f => ({ ...f, project_name: e.target.value }))}
                placeholder="buttercup"
                className="bg-input/50 border-border/60"
              />
            </FieldRow>
            <FieldRow id="repo-full" label="Repository (owner/repo)">
              <Input
                id="repo-full"
                value={form.repo_full_name}
                onChange={e => setForm(f => ({ ...f, repo_full_name: e.target.value }))}
                placeholder="acme/infrastructure"
                className="bg-input/50 border-border/60 font-mono text-sm"
              />
            </FieldRow>
            <FieldRow id="repo-branch" label="Branch">
              <Input
                id="repo-branch"
                value={form.branch}
                onChange={e => setForm(f => ({ ...f, branch: e.target.value }))}
                placeholder="develop"
                className="bg-input/50 border-border/60 font-mono text-sm"
              />
            </FieldRow>
            <FieldRow id="repo-token" label="GitHub token">
              <Input
                id="repo-token"
                type="password"
                value={form.token}
                onChange={e => setForm(f => ({ ...f, token: e.target.value }))}
                placeholder="ghp_…"
                className="bg-input/50 border-border/60 font-mono text-sm"
              />
            </FieldRow>
            <FieldRow id="repo-base-path" label="Infrastructure base path">
              <Input
                id="repo-base-path"
                value={form.infrastructure_base_path}
                onChange={e => setForm(f => ({ ...f, infrastructure_base_path: e.target.value }))}
                className="bg-input/50 border-border/60 font-mono text-sm"
              />
            </FieldRow>
          </div>

          <div className="space-y-3 pt-1">
            <Toggle
              id="auto-merge"
              checked={form.auto_merge}
              onChange={v => setForm(f => ({ ...f, auto_merge: v }))}
              label="Auto-merge PRs"
              hint="Automatically squash-merge landing zone PRs after opening"
            />
            <Toggle
              id="create-cicd"
              checked={form.create_cicd}
              onChange={v => setForm(f => ({ ...f, create_cicd: v }))}
              label="Create CI/CD"
              hint="Generate GitHub Actions workflows for Terragrunt plan/apply"
            />
            <Toggle
              id="skip-bootstrap"
              checked={form.skip_bootstrap}
              onChange={v => setForm(f => ({ ...f, skip_bootstrap: v }))}
              label="Skip bootstrap"
              hint="Repo already has global.hcl and env.hcl — skip writing root HCL files"
            />
            <Toggle
              id="skip-module-import"
              checked={form.skip_module_import}
              onChange={v => setForm(f => ({ ...f, skip_module_import: v }))}
              label="Skip module import"
              hint="Terraform modules already exist in the repo — skip copying them"
            />
          </div>

          <button
            type="button"
            onClick={() => setShowAdvanced(a => !a)}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <svg
              width="10" height="10" viewBox="0 0 10 10" fill="none"
              className={`transition-transform ${showAdvanced ? 'rotate-90' : ''}`}
            >
              <path d="M3 2l4 3-4 3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Advanced — state backend config
          </button>

          {showAdvanced && (
            <div className="space-y-4 pt-1 border-t border-border/40">
              {(
                [
                  { env: 'dev', bucket: 'dev_state_bucket', region: 'dev_state_region', lock: 'dev_state_lock_table' },
                  { env: 'prod', bucket: 'prod_state_bucket', region: 'prod_state_region', lock: 'prod_state_lock_table' },
                ] as const
              ).map(({ env, bucket, region, lock }) => (
                <div key={env} className="grid grid-cols-3 gap-3">
                  <p className="col-span-3 text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-widest pt-1">
                    {env} state backend
                  </p>
                  <FieldRow label="S3 bucket">
                    <Input
                      value={form[bucket] ?? ''}
                      onChange={e => setForm(f => ({ ...f, [bucket]: e.target.value || undefined }))}
                      placeholder={`${form.project_name || 'proj'}-${env}-terraform-state`}
                      className="bg-input/50 border-border/60 font-mono text-xs"
                    />
                  </FieldRow>
                  <FieldRow label="Region">
                    <Input
                      value={form[region] ?? ''}
                      onChange={e => setForm(f => ({ ...f, [region]: e.target.value || undefined }))}
                      placeholder="eu-west-1"
                      className="bg-input/50 border-border/60 font-mono text-xs"
                    />
                  </FieldRow>
                  <FieldRow label="DynamoDB lock table">
                    <Input
                      value={form[lock] ?? ''}
                      onChange={e => setForm(f => ({ ...f, [lock]: e.target.value || undefined }))}
                      placeholder={`${form.project_name || 'proj'}-${env}-terraform-lock`}
                      className="bg-input/50 border-border/60 font-mono text-xs"
                    />
                  </FieldRow>
                </div>
              ))}
            </div>
          )}

          {error && (
            <p className="text-xs text-destructive bg-destructive/10 border border-destructive/20 px-3 py-2 rounded-md">
              {error}
            </p>
          )}
        </CardContent>
        <CardFooter className="gap-3">
          <Button
            size="sm"
            onClick={connect}
            disabled={!isValid || status === 'saving'}
            className="shadow-md shadow-primary/20"
          >
            {status === 'saving' ? 'Connecting…' : 'Connect repository'}
          </Button>
          <StatusMessage status={status} savedText="Repository connected" />
        </CardFooter>
      </Card>

      {projects.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Connected projects</CardTitle>
            <CardDescription>Active projects and their infrastructure status</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {projects.map(p => {
              const repo = repos[p.name]
              return (
                <div key={p.id} className="rounded-lg border border-border/50 bg-muted/10 p-3.5 space-y-2.5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold">{p.name}</p>
                      {repo && (
                        <p className="text-xs text-muted-foreground font-mono mt-0.5">
                          {repo.repo_full_name} · {repo.branch}
                        </p>
                      )}
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => disconnect(p.name)}
                      disabled={disconnecting === p.name}
                      className="text-xs border-destructive/30 text-destructive hover:bg-destructive/10 shrink-0"
                    >
                      {disconnecting === p.name ? 'Removing…' : 'Disconnect'}
                    </Button>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <StatusBadge ok={p.version_control_created} label="Repo" />
                    <StatusBadge ok={p.infrastructure_bootstrapped} label="Bootstrapped" />
                    <StatusBadge ok={p.cicd_created} label="CI/CD" />
                    <StatusBadge ok={p.warehouse_created} label="Warehouse" />
                    {repo?.skip_bootstrap && (
                      <span className="inline-flex items-center text-[10px] font-medium px-1.5 py-0.5 rounded-full border bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400">
                        skip bootstrap
                      </span>
                    )}
                    {repo?.skip_module_import && (
                      <span className="inline-flex items-center text-[10px] font-medium px-1.5 py-0.5 rounded-full border bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400">
                        skip module import
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ── AdminPage ─────────────────────────────────────────────────────────────────

const TABS: { id: Tab; label: string }[] = [
  { id: 'organization', label: 'Organization' },
  { id: 'warehouse', label: 'Warehouse' },
  { id: 'cloud', label: 'Cloud' },
  { id: 'projects', label: 'Projects' },
]

export function AdminPage() {
  const [activeTab, setActiveTab] = useState<Tab>('organization')

  return (
    <AppLayout>
      <div className="flex-1 overflow-auto">
        <div className="max-w-2xl mx-auto px-6 py-10 space-y-8">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Admin</h1>
            <p className="text-sm text-muted-foreground mt-0.5">Manage workspace, integrations, and cloud settings</p>
          </div>

          <div className="border-b border-border/50">
            <nav className="flex gap-0 -mb-px">
              {TABS.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === tab.id
                      ? 'border-primary text-foreground'
                      : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>

          <div>
            {activeTab === 'organization' && <OrgTab />}
            {activeTab === 'warehouse' && <WarehouseTab />}
            {activeTab === 'cloud' && <CloudTab />}
            {activeTab === 'projects' && <ProjectsTab />}
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
