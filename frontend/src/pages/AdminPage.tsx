import { useState, useEffect } from 'react'
import { AppLayout } from '../components/AppLayout'
import { api, OrgSettings, WarehouseConfig, CloudConfig } from '../api/client'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Card, CardContent, CardFooter, CardHeader, CardTitle, CardDescription } from '../components/ui/card'

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'
type Tab = 'organization' | 'warehouse' | 'cloud'

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

function WarehouseTab() {
  const [config, setConfig] = useState<WarehouseConfig>({
    type: 'snowflake',
    account: '',
    username: '',
    database: '',
    schema: '',
    warehouse: '',
    role: '',
  })
  const [passwordInput, setPasswordInput] = useState('')
  const [hasExistingPassword, setHasExistingPassword] = useState(false)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'ok' | 'fail'>('idle')
  const [testMessage, setTestMessage] = useState('')

  useEffect(() => {
    api.getWarehouseConfig().then(w => {
      setConfig(w)
      if (w.password) {
        setHasExistingPassword(true)
      }
    }).catch(() => {})
  }, [])

  async function save() {
    setSaveStatus('saving')
    try {
      const payload: WarehouseConfig = { ...config }
      if (passwordInput) payload.password = passwordInput
      await api.updateWarehouseConfig(payload)
      setSaveStatus('saved')
      if (passwordInput) { setPasswordInput(''); setHasExistingPassword(true) }
      setTimeout(() => setSaveStatus('idle'), 2500)
    } catch {
      setSaveStatus('error')
    }
  }

  async function testConnection() {
    setTestStatus('testing')
    setTestMessage('')
    try {
      const payload: WarehouseConfig = { ...config }
      if (passwordInput) payload.password = passwordInput
      const result = await api.testWarehouseConnection(payload)
      setTestStatus(result.ok ? 'ok' : 'fail')
      setTestMessage(result.message)
    } catch {
      setTestStatus('fail')
      setTestMessage('Connection failed')
    }
  }

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
          <CardDescription>Configure your Snowflake connection details</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <FieldRow id="wh-account" label="Account identifier">
              <Input
                id="wh-account"
                value={config.account}
                onChange={e => setConfig(c => ({ ...c, account: e.target.value }))}
                placeholder="my-org.us-east-1"
                className="bg-input/50 border-border/60"
              />
            </FieldRow>
            <FieldRow id="wh-username" label="Username">
              <Input
                id="wh-username"
                value={config.username}
                onChange={e => setConfig(c => ({ ...c, username: e.target.value }))}
                className="bg-input/50 border-border/60"
              />
            </FieldRow>
            <FieldRow id="wh-password" label="Password">
              <Input
                id="wh-password"
                type="password"
                value={passwordInput}
                onChange={e => setPasswordInput(e.target.value)}
                placeholder={hasExistingPassword ? '••••••••  (unchanged)' : 'Enter password'}
                className="bg-input/50 border-border/60"
              />
            </FieldRow>
            <FieldRow id="wh-role" label="Role">
              <Input
                id="wh-role"
                value={config.role}
                onChange={e => setConfig(c => ({ ...c, role: e.target.value }))}
                placeholder="SYSADMIN"
                className="bg-input/50 border-border/60"
              />
            </FieldRow>
            <FieldRow id="wh-warehouse" label="Warehouse">
              <Input
                id="wh-warehouse"
                value={config.warehouse}
                onChange={e => setConfig(c => ({ ...c, warehouse: e.target.value }))}
                placeholder="COMPUTE_WH"
                className="bg-input/50 border-border/60"
              />
            </FieldRow>
            <FieldRow id="wh-database" label="Database">
              <Input
                id="wh-database"
                value={config.database}
                onChange={e => setConfig(c => ({ ...c, database: e.target.value }))}
                placeholder="ANALYTICS"
                className="bg-input/50 border-border/60"
              />
            </FieldRow>
            <FieldRow id="wh-schema" label="Schema">
              <Input
                id="wh-schema"
                value={config.schema}
                onChange={e => setConfig(c => ({ ...c, schema: e.target.value }))}
                placeholder="PUBLIC"
                className="bg-input/50 border-border/60"
              />
            </FieldRow>
          </div>

          {testStatus !== 'idle' && (
            <div className={`flex items-center gap-2 text-xs px-3 py-2 rounded-md border ${
              testStatus === 'testing'
                ? 'border-border/40 bg-muted/20 text-muted-foreground'
                : testStatus === 'ok'
                ? 'border-green-500/30 bg-green-500/10 text-green-500'
                : 'border-destructive/30 bg-destructive/10 text-destructive'
            }`}>
              {testStatus === 'testing' && (
                <span className="size-3 rounded-full border-2 border-current border-t-transparent animate-spin" />
              )}
              {testStatus === 'ok' && (
                <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                  <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.4" />
                  <path d="M4.5 7l2 2 3-3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
              {testStatus === 'fail' && (
                <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                  <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.4" />
                  <path d="M9 5L5 9M5 5l4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                </svg>
              )}
              {testStatus === 'testing' ? 'Testing connection…' : testMessage}
            </div>
          )}
        </CardContent>
        <CardFooter className="gap-3">
          <Button size="sm" onClick={save} disabled={saveStatus === 'saving'} className="shadow-md shadow-primary/20">
            {saveStatus === 'saving' ? 'Saving…' : 'Save configuration'}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={testConnection}
            disabled={testStatus === 'testing'}
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

// ── AdminPage ─────────────────────────────────────────────────────────────────

const TABS: { id: Tab; label: string }[] = [
  { id: 'organization', label: 'Organization' },
  { id: 'warehouse', label: 'Warehouse' },
  { id: 'cloud', label: 'Cloud' },
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
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
