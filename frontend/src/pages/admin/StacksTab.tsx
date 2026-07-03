import { useState, useEffect } from 'react'
import { api, StackOut, StackUpdate, WarehouseUpdate, CloudUpdate, WarehouseType, CloudProvider, ModuleVersion } from '../../api/client'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { Card, CardContent, CardFooter, CardHeader, CardTitle, CardDescription } from '../../components/ui/card'
import { SaveStatus, StatusMessage, FieldRow, AWS_REGIONS, NativeSelect, ConnectionStatus, Toggle } from '../../components/admin/shared'
import { TopologyDiagram } from '../../components/TopologyDiagram'

// Matches backend/app/api/routes/stacks.py PROTECTED_STACK_NAMES — "dev" and
// "prod" are auto-seeded and load-bearing for the release flow.
const PROTECTED_STACK_NAMES = new Set(['dev', 'prod'])

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

function StackDetail({
  stack,
  isOnly,
  moduleVersions,
  onChanged,
}: {
  stack: StackOut
  isOnly: boolean
  moduleVersions: ModuleVersion[]
  onChanged: () => void
}) {
  const [branch, setBranch] = useState(stack.branch)
  const [verifyBeforePr, setVerifyBeforePr] = useState(stack.verify_before_pr)
  const [verifyMaxAttempts, setVerifyMaxAttempts] = useState(stack.verify_max_attempts)
  const [moduleVersion, setModuleVersion] = useState(stack.module_version)
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
  const [refreshStatus, setRefreshStatus] = useState<'idle' | 'refreshing' | 'done' | 'error'>('idle')
  const [refreshMessage, setRefreshMessage] = useState('')
  const [refreshPrUrl, setRefreshPrUrl] = useState<string | null>(null)

  useEffect(() => {
    setBranch(stack.branch)
    setVerifyBeforePr(stack.verify_before_pr)
    setVerifyMaxAttempts(stack.verify_max_attempts)
    setModuleVersion(stack.module_version)
    setWarehouse(stack.warehouse)
    setCloud(stack.cloud)
    setHasExistingKey(!!stack.warehouse.private_key_b64)
    setHasExistingSecret(!!stack.cloud.secret_access_key)
    setPemInput('')
    setSecretInput('')
    setWarehouseTestStatus('idle')
    setCloudTestStatus('idle')
    setDeleteError('')
    setRefreshStatus('idle')
    setRefreshMessage('')
    setRefreshPrUrl(null)
  }, [stack.id])

  function buildPayload(): StackUpdate {
    const wh: WarehouseUpdate = { ...warehouse }
    if (pemInput) wh.private_key_b64 = btoa(pemInput)
    else delete wh.private_key_b64

    const cl: CloudUpdate = { ...cloud }
    if (secretInput) cl.secret_access_key = secretInput
    else delete cl.secret_access_key

    return {
      branch,
      verify_before_pr: verifyBeforePr,
      verify_max_attempts: verifyMaxAttempts,
      module_version: moduleVersion,
      warehouse: wh,
      cloud: cl,
    }
  }

  async function hardRefreshModules() {
    setRefreshStatus('refreshing')
    setRefreshMessage('')
    setRefreshPrUrl(null)
    try {
      const result = await api.refreshStackModules(stack.id)
      setRefreshStatus('done')
      setRefreshPrUrl(result.pr_url)
      setRefreshMessage(
        result.pr_url
          ? `Opened a PR removing ${result.files_removed} file(s) and adding ${result.files_added} file(s).`
          : result.message ?? 'Already up to date'
      )
    } catch (e) {
      setRefreshStatus('error')
      setRefreshMessage(e instanceof Error ? e.message : 'Failed to refresh modules')
    }
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
  const canDelete = !PROTECTED_STACK_NAMES.has(stack.name) && !isOnly

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Deployment</CardTitle>
          <CardDescription>Which branch triggers CI/CD for this stack, across every project</CardDescription>
        </CardHeader>
        <CardContent>
          <FieldRow id="stack-branch" label="Git branch" hint="Must match a real branch in your connected GitHub repo.">
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

          <div className="mt-5 pt-4 border-t border-border/40">
            <Toggle
              id="stack-verify-before-pr"
              checked={verifyBeforePr}
              onChange={setVerifyBeforePr}
              label="Verify before opening PRs"
              hint="Run terragrunt/terraform plan against generated infra for this stack before opening a PR. On failure, Claude attempts to patch and retry — if it still fails after the retry limit below, no PR is opened. Off by default since it requires this stack's infra to already be bootstrapped and adds time to PR creation."
            />
            <div className={`mt-3 flex items-center gap-2 ${verifyBeforePr ? '' : 'opacity-40 pointer-events-none'}`}>
              <label htmlFor="stack-verify-max-attempts" className="text-xs text-muted-foreground">
                Retry limit
              </label>
              <Input
                id="stack-verify-max-attempts"
                type="number"
                min={1}
                max={10}
                value={verifyMaxAttempts}
                onChange={e => setVerifyMaxAttempts(Math.min(10, Math.max(1, Number(e.target.value) || 1)))}
                disabled={!verifyBeforePr}
                className="bg-input/50 border-border/60 text-sm w-20"
              />
              <span className="text-[10px] text-muted-foreground/60">
                attempts before giving up and reporting the failure (1–10)
              </span>
            </div>
          </div>

          <div className="mt-5 pt-4 border-t border-border/40">
            <FieldRow
              id="stack-module-version"
              label="Terraform module version"
              hint="Which version of Canary's vendored Terraform modules new landing zones on this stack are generated with. Changing this doesn't touch anything already deployed — use 'Hard refresh modules' below to re-sync existing landing zones to the newly selected version."
            >
              <div className="flex items-center gap-2">
                <NativeSelect
                  id="stack-module-version"
                  value={moduleVersion}
                  onChange={setModuleVersion}
                  className="max-w-[160px]"
                >
                  {moduleVersions.map(v => (
                    <option key={v.version} value={v.version}>{v.version}</option>
                  ))}
                </NativeSelect>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={hardRefreshModules}
                  disabled={refreshStatus === 'refreshing' || moduleVersion !== stack.module_version}
                  className="border-border/60"
                >
                  {refreshStatus === 'refreshing' ? 'Refreshing…' : 'Hard refresh modules'}
                </Button>
              </div>
            </FieldRow>
            {moduleVersion !== stack.module_version && (
              <p className="text-[11px] text-muted-foreground mt-2">Save the stack before refreshing — refresh always uses the saved version.</p>
            )}
            {refreshStatus === 'done' && (
              <p className={`text-[11px] mt-2 ${refreshPrUrl ? 'text-foreground' : 'text-muted-foreground'}`}>
                {refreshPrUrl ? (
                  <>
                    {refreshMessage}{' '}
                    <a href={refreshPrUrl} target="_blank" rel="noreferrer" className="text-primary hover:text-primary/80 underline">
                      View PR
                    </a>
                  </>
                ) : (
                  `✓ ${refreshMessage}`
                )}
              </p>
            )}
            {refreshStatus === 'error' && (
              <p className="text-[11px] text-destructive mt-2">{refreshMessage}</p>
            )}
          </div>
        </CardContent>
      </Card>

      <TopologyDiagram stackId={stack.id} />

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
            <FieldRow id="stack-org" label="Organization" hint="Your Snowflake organization name, if you connect using org-account format.">
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
            <FieldRow id="stack-account" label="Account identifier *" hint="The account name portion of your Snowflake identifier, without the org prefix.">
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
            <FieldRow id="stack-user" label="User *" hint="The Snowflake username configured for key-pair (JWT) authentication.">
              <Input
                id="stack-user"
                value={warehouse.user ?? ''}
                onChange={e => setWarehouse(w => ({ ...w, user: e.target.value }))}
                className="bg-input/50 border-border/60"
              />
            </FieldRow>
          </div>

          <FieldRow id="stack-private-key" label="Private key (PEM)" hint="Must match the public key registered on this Snowflake user via ALTER USER ... SET RSA_PUBLIC_KEY.">
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
              <FieldRow id="stack-database" label="Database" hint="Default Snowflake database used for this stack's queries and generated infrastructure.">
                <Input
                  id="stack-database"
                  value={warehouse.database ?? ''}
                  onChange={e => setWarehouse(w => ({ ...w, database: e.target.value || undefined }))}
                  placeholder="ANALYTICS"
                  className="bg-input/50 border-border/60"
                />
              </FieldRow>
              <FieldRow id="stack-schema" label="Schema" hint="Default schema within the database above.">
                <Input
                  id="stack-schema"
                  value={warehouse.schema_ ?? ''}
                  onChange={e => setWarehouse(w => ({ ...w, schema_: e.target.value || undefined }))}
                  placeholder="PUBLIC"
                  className="bg-input/50 border-border/60"
                />
              </FieldRow>
              <FieldRow id="stack-warehouse" label="Warehouse" hint="The Snowflake virtual warehouse (compute) used to run queries for this stack.">
                <Input
                  id="stack-warehouse"
                  value={warehouse.warehouse ?? ''}
                  onChange={e => setWarehouse(w => ({ ...w, warehouse: e.target.value || undefined }))}
                  placeholder="COMPUTE_WH"
                  className="bg-input/50 border-border/60"
                />
              </FieldRow>
              <FieldRow id="stack-role" label="Role" hint="Snowflake role assumed when connecting — determines what this stack's credentials can access.">
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

          <FieldRow id="stack-aws-region" label="Default region" hint="AWS region new resources are created in by default for this stack.">
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
          <FieldRow id="stack-aws-key-id" label="Access key ID" hint="IAM access key ID for a user with least-privilege permissions to manage this stack's infrastructure.">
            <Input
              id="stack-aws-key-id"
              value={cloud.access_key_id ?? ''}
              onChange={e => setCloud(c => ({ ...c, access_key_id: e.target.value }))}
              placeholder="AKIAIOSFODNN7EXAMPLE"
              className="bg-input/50 border-border/60 font-mono text-sm"
            />
          </FieldRow>
          <FieldRow id="stack-aws-secret" label="Secret access key" hint="Paired with the access key ID above. Stored encrypted; never displayed again after saving.">
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
  const [moduleVersions, setModuleVersions] = useState<ModuleVersion[]>([])

  useEffect(() => {
    load()
    api.listModuleVersions().then(setModuleVersions).catch(() => {})
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
        <StackDetail
          stack={selected}
          isOnly={stacks.length <= 1}
          moduleVersions={moduleVersions}
          onChanged={() => load(selected.id)}
        />
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
