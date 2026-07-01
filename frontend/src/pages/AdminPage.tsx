import { useState, useEffect } from 'react'
import { AppLayout } from '../components/AppLayout'
import { api, OrgSettings, ProjectOut, GitHubRepoOut, GitHubRepoConnect } from '../api/client'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Card, CardContent, CardFooter, CardHeader, CardTitle, CardDescription } from '../components/ui/card'
import { SaveStatus, StatusMessage, FieldRow, Toggle, StatusBadge } from '../components/admin/shared'
import { StacksTab } from './admin/StacksTab'

type Tab = 'organization' | 'stacks' | 'projects'

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

function ProjectsTab() {
  const [projects, setProjects] = useState<ProjectOut[]>([])
  const [repos, setRepos] = useState<Record<string, GitHubRepoOut>>({})
  const [form, setForm] = useState<GitHubRepoConnect>(EMPTY_FORM)
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

          <p className="text-xs text-muted-foreground/60">
            Per-stack Terraform state backend (S3 bucket / DynamoDB lock table) is provisioned
            automatically for every configured stack when infrastructure is bootstrapped.
          </p>

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
  { id: 'stacks', label: 'Stacks' },
  { id: 'projects', label: 'Projects' },
]

export function AdminPage() {
  const [activeTab, setActiveTab] = useState<Tab>('organization')

  return (
    <AppLayout>
      <div className="flex-1 overflow-auto">
        <div className={`mx-auto px-6 py-10 space-y-8 ${activeTab === 'stacks' ? 'max-w-4xl' : 'max-w-2xl'}`}>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Admin</h1>
            <p className="text-sm text-muted-foreground mt-0.5">Manage workspace, stacks, and integrations</p>
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
            {activeTab === 'stacks' && <StacksTab />}
            {activeTab === 'projects' && <ProjectsTab />}
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
