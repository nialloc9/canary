import { useState, useEffect } from 'react'
import { api, StackOut, StackUpdate, WarehouseUpdate, CloudUpdate, WarehouseType, CloudProvider } from '../../api/client'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { Card, CardContent, CardFooter, CardHeader, CardTitle, CardDescription } from '../../components/ui/card'
import { SaveStatus, StatusMessage, FieldRow, AWS_REGIONS, NativeSelect, ConnectionStatus } from '../../components/admin/shared'

function SnowflakeIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path d="M12 2v20M12 2l-3 3M12 2l3 3M12 22l-3-3M12 22l3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M2 12h20M2 12l3-3M2 12l3 3M22 12l-3-3M22 12l-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M5.3 5.3l13.4 13.4M5.3 5.3l3.5 1M5.3 5.3l1 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M18.7 5.3L5.3 18.7M18.7 5.3l-1 3.5M18.7 5.3l-3.5 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

function StackTypeIcon({ type }: { type: WarehouseType }) {
  return type === 'databricks' ? <DatabricksIcon /> : <SnowflakeIcon />
}

function DatabricksIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path d="M3 7l9-4 9 4-9 4-9-4z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M3 12l9 4 9-4M3 17l9 4 9-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function AWSIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path d="M7 14c-1.66 0-3-1.34-3-3s1.34-3 3-3c.17 0 .34.01.5.04A4 4 0 0 1 11.5 5 4 4 0 0 1 15 7.5c.17-.03.33-.05.5-.05a2.5 2.5 0 0 1 0 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M8 19l2-2-2-2M16 19l-2-2 2-2M12 15v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function AzureIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path d="M5 19h14M12 5L7 13l5 2-7 4M12 5l5 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function TilePicker<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { id: T; label: string; available: boolean; icon: React.ReactNode }[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div className="grid grid-cols-2 gap-3">
      {options.map(opt => (
        <button
          key={opt.id}
          type="button"
          disabled={!opt.available}
          onClick={() => opt.available && onChange(opt.id)}
          className={`relative flex flex-col items-center gap-2 rounded-xl border p-3 text-center transition-all ${
            opt.available
              ? value === opt.id
                ? 'border-primary/60 bg-primary/8 text-foreground ring-1 ring-primary/30'
                : 'border-border/60 bg-muted/20 text-foreground hover:border-border hover:bg-muted/40'
              : 'border-border/30 bg-muted/10 text-muted-foreground/40 cursor-not-allowed'
          }`}
        >
          {opt.icon}
          <span className="text-xs font-medium">{opt.label}</span>
          {!opt.available && (
            <span className="absolute top-1.5 right-1.5 text-[9px] font-medium text-muted-foreground/50 bg-muted/40 px-1.5 py-0.5 rounded-full border border-border/30">
              Coming soon
            </span>
          )}
        </button>
      ))}
    </div>
  )
}

function StackDetail({ stack, isOnly, onChanged }: { stack: StackOut; isOnly: boolean; onChanged: () => void }) {
  const [branch, setBranch] = useState(stack.branch)
  const [warehouse, setWarehouse] = useState<WarehouseUpdate>(stack.warehouse)
  const [cloud, setCloud] = useState<CloudUpdate>(stack.cloud)
  const [pemInput, setPemInput] = useState('')
  const [hasExistingKey, setHasExistingKey] = useState(!!stack.warehouse.private_key_b64)
  const [secretInput, setSecretInput] = useState('')
  const [hasExistingSecret, setHasExistingSecret] = useState(!!stack.cloud.secret_access_key)
  const [showSecret, setShowSecret] = useState(false)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [warehouseTestStatus, setWarehouseTestStatus] = useState<'idle' | 'testing' | 'ok' | 'fail'>('idle')
  const [warehouseTestMessage, setWarehouseTestMessage] = useState('')
  const [cloudTestStatus, setCloudTestStatus] = useState<'idle' | 'testing' | 'ok' | 'fail'>('idle')
  const [cloudTestMessage, setCloudTestMessage] = useState('')
  const [deleteError, setDeleteError] = useState('')
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    setBranch(stack.branch)
    setWarehouse(stack.warehouse)
    setCloud(stack.cloud)
    setHasExistingKey(!!stack.warehouse.private_key_b64)
    setHasExistingSecret(!!stack.cloud.secret_access_key)
    setPemInput('')
    setSecretInput('')
    setWarehouseTestStatus('idle')
    setCloudTestStatus('idle')
    setDeleteError('')
  }, [stack.id])

  function buildPayload(): StackUpdate {
    const wh: WarehouseUpdate = { ...warehouse }
    if (pemInput) wh.private_key_b64 = btoa(pemInput)
    else delete wh.private_key_b64

    const cl: CloudUpdate = { ...cloud }
    if (secretInput) cl.secret_access_key = secretInput
    else delete cl.secret_access_key

    return { branch, warehouse: wh, cloud: cl }
  }

  async function save() {
    setSaveStatus('saving')
    try {
      await api.updateStack(stack.id, buildPayload())
      setSaveStatus('saved')
      if (pemInput) { setPemInput(''); setHasExistingKey(true) }
      if (secretInput) { setSecretInput(''); setHasExistingSecret(true) }
      setTimeout(() => setSaveStatus('idle'), 2500)
      onChanged()
    } catch {
      setSaveStatus('error')
    }
  }

  async function testWarehouseConnection() {
    setWarehouseTestStatus('testing')
    setWarehouseTestMessage('')
    try {
      const result = await api.testStackConnection(stack.id, buildPayload())
      setWarehouseTestStatus(result.ok ? 'ok' : 'fail')
      setWarehouseTestMessage(result.message)
    } catch {
      setWarehouseTestStatus('fail')
      setWarehouseTestMessage('Connection failed')
    }
  }

  async function testCloudConnection() {
    setCloudTestStatus('testing')
    setCloudTestMessage('')
    try {
      const result = await api.testStackCloudConnection(stack.id, buildPayload())
      setCloudTestStatus(result.ok ? 'ok' : 'fail')
      setCloudTestMessage(result.message)
    } catch {
      setCloudTestStatus('fail')
      setCloudTestMessage('Connection failed')
    }
  }

  async function remove() {
    setDeleteError('')
    setDeleting(true)
    try {
      await api.deleteStack(stack.id)
      onChanged()
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : 'Failed to delete stack')
    }
    setDeleting(false)
  }

  const canTestWarehouse = !!warehouse.account_name && !!warehouse.user && (hasExistingKey || !!pemInput)
  const canTestCloud = !!cloud.access_key_id && (hasExistingSecret || !!secretInput)
  const canDelete = !stack.is_default && !isOnly

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Deployment</CardTitle>
          <CardDescription>Which branch triggers CI/CD for this stack, across every project</CardDescription>
        </CardHeader>
        <CardContent>
          <FieldRow id="stack-branch" label="Git branch">
            <Input
              id="stack-branch"
              value={branch}
              onChange={e => setBranch(e.target.value)}
              placeholder={stack.name}
              className="bg-input/50 border-border/60 font-mono text-sm"
            />
          </FieldRow>
          <p className="text-[10px] text-muted-foreground/60 mt-2">
            Pushes and PRs targeting this branch drive this stack's plan/apply jobs in every project's
            generated CI/CD workflow — independent of the other stacks' branches.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Warehouse</CardTitle>
          <CardDescription>Account and user are required. All other fields are optional.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <TilePicker<WarehouseType>
            options={[
              { id: 'snowflake', label: 'Snowflake', available: true, icon: <SnowflakeIcon /> },
              { id: 'databricks', label: 'Databricks', available: false, icon: <DatabricksIcon /> },
            ]}
            value={warehouse.type ?? 'snowflake'}
            onChange={v => setWarehouse(w => ({ ...w, type: v }))}
          />

          <div className="grid grid-cols-2 gap-4">
            <FieldRow id="stack-org" label="Organization">
              <Input
                id="stack-org"
                value={warehouse.organization_name ?? ''}
                onChange={e => setWarehouse(w => ({ ...w, organization_name: e.target.value }))}
                placeholder="MYORG"
                className="bg-input/50 border-border/60"
              />
              <p className="text-[10px] text-muted-foreground/60 mt-1">
                Leave blank if you connect with a legacy locator (e.g. <code className="text-muted-foreground/80">xy12345.us-east-1</code>) instead of an org name.
              </p>
            </FieldRow>
            <FieldRow id="stack-account" label="Account identifier *">
              <Input
                id="stack-account"
                value={warehouse.account_name ?? ''}
                onChange={e => setWarehouse(w => ({ ...w, account_name: e.target.value }))}
                placeholder="myaccount"
                className="bg-input/50 border-border/60"
              />
              <p className="text-[10px] text-muted-foreground/60 mt-1">
                Just the account name (e.g. <code className="text-muted-foreground/80">snow001</code>) — combined
                with Organization automatically. From Snowflake's Admin → Accounts page or your account URL
                (<code className="text-muted-foreground/80">https://org-account.snowflakecomputing.com</code>).
              </p>
            </FieldRow>
            <FieldRow id="stack-user" label="User *">
              <Input
                id="stack-user"
                value={warehouse.user ?? ''}
                onChange={e => setWarehouse(w => ({ ...w, user: e.target.value }))}
                className="bg-input/50 border-border/60"
              />
            </FieldRow>
          </div>

          <FieldRow id="stack-private-key" label="Private key (PEM)">
            <textarea
              id="stack-private-key"
              value={pemInput}
              onChange={e => setPemInput(e.target.value)}
              placeholder={hasExistingKey ? '••••••••  (key saved — paste new key to replace)' : '-----BEGIN PRIVATE KEY-----\n…\n-----END PRIVATE KEY-----'}
              rows={5}
              className="w-full rounded-lg border border-input bg-input/50 px-3 py-2 text-xs font-mono text-foreground placeholder:text-muted-foreground/50 outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/30 resize-none"
            />
            <p className="text-[10px] text-muted-foreground/60 mt-1">Paste the RSA private key PEM used for key-pair auth. It will be base64-encoded before being stored.</p>
          </FieldRow>

          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-3">Optional</p>
            <div className="grid grid-cols-2 gap-4">
              <FieldRow id="stack-database" label="Database">
                <Input
                  id="stack-database"
                  value={warehouse.database ?? ''}
                  onChange={e => setWarehouse(w => ({ ...w, database: e.target.value || undefined }))}
                  placeholder="ANALYTICS"
                  className="bg-input/50 border-border/60"
                />
              </FieldRow>
              <FieldRow id="stack-schema" label="Schema">
                <Input
                  id="stack-schema"
                  value={warehouse.schema_ ?? ''}
                  onChange={e => setWarehouse(w => ({ ...w, schema_: e.target.value || undefined }))}
                  placeholder="PUBLIC"
                  className="bg-input/50 border-border/60"
                />
              </FieldRow>
              <FieldRow id="stack-warehouse" label="Warehouse">
                <Input
                  id="stack-warehouse"
                  value={warehouse.warehouse ?? ''}
                  onChange={e => setWarehouse(w => ({ ...w, warehouse: e.target.value || undefined }))}
                  placeholder="COMPUTE_WH"
                  className="bg-input/50 border-border/60"
                />
              </FieldRow>
              <FieldRow id="stack-role" label="Role">
                <Input
                  id="stack-role"
                  value={warehouse.role ?? ''}
                  onChange={e => setWarehouse(w => ({ ...w, role: e.target.value || undefined }))}
                  placeholder="SYSADMIN"
                  className="bg-input/50 border-border/60"
                />
              </FieldRow>
            </div>
          </div>

          <ConnectionStatus status={warehouseTestStatus} message={warehouseTestMessage} />
        </CardContent>
        <CardFooter className="gap-3">
          <Button
            size="sm"
            variant="outline"
            onClick={testWarehouseConnection}
            disabled={!canTestWarehouse || warehouseTestStatus === 'testing'}
            className="border-border/60"
          >
            {warehouseTestStatus === 'testing' ? 'Testing…' : 'Test connection'}
          </Button>
        </CardFooter>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Cloud</CardTitle>
          <CardDescription>Credentials used to deploy this stack's infrastructure</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <TilePicker<CloudProvider>
            options={[
              { id: 'aws', label: 'AWS', available: true, icon: <AWSIcon /> },
              { id: 'azure', label: 'Azure', available: false, icon: <AzureIcon /> },
            ]}
            value={cloud.provider ?? 'aws'}
            onChange={v => setCloud(c => ({ ...c, provider: v }))}
          />

          <FieldRow id="stack-aws-region" label="Default region">
            <NativeSelect
              id="stack-aws-region"
              value={cloud.region ?? 'us-east-1'}
              onChange={v => setCloud(c => ({ ...c, region: v }))}
            >
              {AWS_REGIONS.map(r => (
                <option key={r} value={r}>{r}</option>
              ))}
            </NativeSelect>
          </FieldRow>
          <FieldRow id="stack-aws-key-id" label="Access key ID">
            <Input
              id="stack-aws-key-id"
              value={cloud.access_key_id ?? ''}
              onChange={e => setCloud(c => ({ ...c, access_key_id: e.target.value }))}
              placeholder="AKIAIOSFODNN7EXAMPLE"
              className="bg-input/50 border-border/60 font-mono text-sm"
            />
          </FieldRow>
          <FieldRow id="stack-aws-secret" label="Secret access key">
            <div className="relative">
              <Input
                id="stack-aws-secret"
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

          <ConnectionStatus status={cloudTestStatus} message={cloudTestMessage} />
        </CardContent>
        <CardFooter className="gap-3">
          <Button
            size="sm"
            variant="outline"
            onClick={testCloudConnection}
            disabled={!canTestCloud || cloudTestStatus === 'testing'}
            className="border-border/60"
          >
            {cloudTestStatus === 'testing' ? 'Testing…' : 'Test connection'}
          </Button>
        </CardFooter>
      </Card>

      <div className="flex items-center gap-3 flex-wrap">
        <Button size="sm" onClick={save} disabled={saveStatus === 'saving'} className="shadow-md shadow-primary/20">
          {saveStatus === 'saving' ? 'Saving…' : 'Save stack'}
        </Button>
        <StatusMessage status={saveStatus} savedText="Stack saved" />
        {canDelete && (
          <Button
            size="sm"
            variant="outline"
            onClick={remove}
            disabled={deleting}
            className="border-destructive/30 text-destructive hover:bg-destructive/10 ml-auto"
          >
            {deleting ? 'Deleting…' : 'Delete stack'}
          </Button>
        )}
      </div>
      {deleteError && (
        <p className="text-xs text-destructive bg-destructive/10 border border-destructive/20 px-3 py-2 rounded-md">
          {deleteError}
        </p>
      )}
    </div>
  )
}

export function StacksTab() {
  const [stacks, setStacks] = useState<StackOut[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [newStackName, setNewStackName] = useState('')
  const [addError, setAddError] = useState('')
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    load()
  }, [])

  async function load(preferId?: string) {
    try {
      const list = await api.listStacks()
      setStacks(list)
      setSelectedId(prev => preferId ?? (list.some(s => s.id === prev) ? prev : list[0]?.id ?? null))
    } catch {}
  }

  async function addStack() {
    if (!newStackName.trim()) return
    setAddError('')
    setAdding(true)
    try {
      const created = await api.createStack({ name: newStackName.trim() })
      setNewStackName('')
      await load(created.id)
    } catch (e) {
      setAddError(e instanceof Error ? e.message : 'Failed to create stack')
    }
    setAdding(false)
  }

  async function move(stackId: string, direction: -1 | 1) {
    const index = stacks.findIndex(s => s.id === stackId)
    const target = index + direction
    if (target < 0 || target >= stacks.length) return
    const reordered = [...stacks]
    ;[reordered[index], reordered[target]] = [reordered[target], reordered[index]]
    try {
      const updated = await api.reorderStacks(reordered.map(s => s.id))
      setStacks(updated)
    } catch {}
  }

  const selected = stacks.find(s => s.id === selectedId) ?? null

  return (
    <div className="grid grid-cols-[220px_1fr] gap-6 items-start">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Stacks</CardTitle>
          <CardDescription className="text-xs">Environments deployed with the same infra</CardDescription>
        </CardHeader>
        <CardContent className="space-y-1">
          {stacks.map((s, i) => (
            <div
              key={s.id}
              className={`flex items-center gap-1.5 rounded-md border px-2 py-1.5 cursor-pointer transition-colors ${
                s.id === selectedId
                  ? 'border-primary/60 bg-primary/8'
                  : 'border-transparent hover:bg-muted/30'
              }`}
              onClick={() => setSelectedId(s.id)}
            >
              <StackTypeIcon type={s.warehouse.type} />
              <span className="text-sm font-medium flex-1 truncate">{s.name}</span>
              {s.is_default && (
                <span className="text-[9px] font-medium text-muted-foreground/60 bg-muted/40 px-1.5 py-0.5 rounded-full border border-border/30 shrink-0">
                  default
                </span>
              )}
              <div className="flex flex-col shrink-0">
                <button
                  type="button"
                  disabled={i === 0}
                  onClick={e => { e.stopPropagation(); move(s.id, -1) }}
                  className="text-muted-foreground/50 hover:text-foreground disabled:opacity-20 leading-none"
                  aria-label="Move up"
                >
                  ▲
                </button>
                <button
                  type="button"
                  disabled={i === stacks.length - 1}
                  onClick={e => { e.stopPropagation(); move(s.id, 1) }}
                  className="text-muted-foreground/50 hover:text-foreground disabled:opacity-20 leading-none"
                  aria-label="Move down"
                >
                  ▼
                </button>
              </div>
            </div>
          ))}
        </CardContent>
        <CardFooter className="flex-col items-stretch gap-2">
          <Input
            value={newStackName}
            onChange={e => setNewStackName(e.target.value)}
            placeholder="e.g. staging"
            className="bg-input/50 border-border/60 text-sm"
          />
          <Button size="sm" variant="outline" onClick={addStack} disabled={adding || !newStackName.trim()} className="border-border/60">
            {adding ? 'Adding…' : '+ Add stack'}
          </Button>
          {addError && <p className="text-xs text-destructive">{addError}</p>}
        </CardFooter>
      </Card>

      {selected ? (
        <StackDetail stack={selected} isOnly={stacks.length <= 1} onChanged={() => load(selected.id)} />
      ) : (
        <Card>
          <CardContent className="text-sm text-muted-foreground py-8 text-center">
            No stacks yet — add one to get started.
          </CardContent>
        </Card>
      )}
    </div>
  )
}
