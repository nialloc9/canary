import { config } from '../config'
import { mockApi } from '../config/mock'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ChatResponse {
  conversation_id: string
  reply: string
  tool_calls: Array<{ tool: string; input: Record<string, unknown>; result: string }> | null
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface UserOut {
  id: string
  email: string
  username: string
  is_active: boolean
  created_at: string
}

export interface MessageOut {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface ConversationOut {
  id: string
  title: string | null
  stack_id: string | null
  created_at: string
  messages?: MessageOut[]
}

export interface OrgSettings {
  name: string
  domain: string
}

export type WarehouseType = 'snowflake' | 'databricks'
export type CloudProvider = 'aws' | 'azure'

export interface WarehouseOut {
  type: WarehouseType
  organization_name: string
  account_name: string
  user: string
  authenticator: string
  private_key_b64?: string | null
  database?: string | null
  schema_?: string | null
  warehouse?: string | null
  role?: string | null
}

export type WarehouseUpdate = Partial<WarehouseOut>

export interface CloudOut {
  provider: CloudProvider
  access_key_id: string
  secret_access_key?: string | null
  region: string
}

export type CloudUpdate = Partial<CloudOut>

export interface StackOut {
  id: string
  name: string
  branch: string
  verify_before_pr: boolean
  verify_max_attempts: number
  module_version: string
  sort_order: number
  is_default: boolean
  warehouse: WarehouseOut
  cloud: CloudOut
  created_at: string
  updated_at: string
}

export interface StackCreate {
  name: string
  branch?: string
  verify_before_pr?: boolean
  verify_max_attempts?: number
  module_version?: string
  warehouse?: WarehouseUpdate
  cloud?: CloudUpdate
}

export interface StackUpdate {
  name?: string
  branch?: string
  verify_before_pr?: boolean
  verify_max_attempts?: number
  module_version?: string
  warehouse?: WarehouseUpdate
  cloud?: CloudUpdate
}

export interface ConnectionTestResult {
  ok: boolean
  message: string
}

export interface ModuleVersion {
  version: string
  released_at: string
  notes: string
}

export interface ModuleRefreshResult {
  pr_url: string | null
  files_removed: number
  files_added: number
  message: string | null
}

export interface ReleaseConflict {
  path: string
  ours: string | null
  theirs: string | null
}

export interface ReleaseResult {
  pr_urls: string[]
  branch: string | null
  conflicts?: ReleaseConflict[] | null
  source_branch?: string | null
  target_branch?: string | null
}

export type TopologyNodeType =
  | 's3_bucket'
  | 'snowflake_database'
  | 'medallion_schemas'
  | 'storage_integration'
  | 'snowpipe'

export interface TopologyNode {
  id: string
  landing_zone: string
  type: TopologyNodeType
  label: string
  fields: Record<string, string>
}

export interface TopologyEdge {
  source: string
  target: string
}

export interface TopologySkipped {
  dir: string
  reason: string
}

export interface Topology {
  nodes: TopologyNode[]
  edges: TopologyEdge[]
  fetched_at: string
  connected: boolean
  error: string | null
  skipped: TopologySkipped[]
}

export interface AccessKeys {
  access_key_id: string
  secret_access_key: string
}

export interface ProjectOut {
  id: string
  name: string
  version_control_created: boolean
  cicd_created: boolean
  infrastructure_bootstrapped: boolean
  created_at: string
}

export interface GitHubRepoOut {
  id: string
  project_name: string
  repo_full_name: string
  branch: string
  api_url: string
  infrastructure_base_path: string
  auto_merge: boolean
  create_cicd: boolean
  skip_bootstrap: boolean
  skip_module_import: boolean
  created_at: string
  updated_at: string
}

export interface GitHubRepoConnect {
  repo_full_name: string
  branch: string
  token?: string
  api_url: string
  infrastructure_base_path: string
  auto_merge: boolean
  create_cicd: boolean
  skip_bootstrap: boolean
  skip_module_import: boolean
}

export interface DbtRepoOut {
  id: string
  repo_full_name: string
  branch: string
  api_url: string
  dbt_base_path: string
  scaffold_version: string
  created_at: string
  updated_at: string
}

export interface DbtRepoConnectResult extends DbtRepoOut {
  scaffold_pr_url: string | null
}

export interface DbtScaffoldRefreshResult {
  pr_url: string | null
  files_removed: number
  files_added: number
  message: string | null
}

export interface DbtRepoConnect {
  repo_full_name: string
  branch?: string
  token?: string
  api_url?: string
  dbt_base_path?: string
}

export interface StackStateOverride {
  bucket?: string | null
  region?: string | null
  lock_table?: string | null
}

export interface StackStateOut {
  name: string
  bucket: string
  region: string
  lock_table: string
}

export interface ProjectBootstrapResponse {
  pr_url: string | null
  stacks: StackStateOut[]
}

// ── Token storage ─────────────────────────────────────────────────────────────
//
// "Remember me" at login picks the storage: localStorage survives browser
// restarts, sessionStorage clears when the tab/browser closes. Whichever one
// holds the tokens is also where a refreshed access token gets written back.

const ACCESS_TOKEN_KEY = 'access_token'
const REFRESH_TOKEN_KEY = 'refresh_token'

function tokenStorage(): Storage {
  return localStorage.getItem(REFRESH_TOKEN_KEY) ? localStorage : sessionStorage
}

function getToken(): string | null {
  return tokenStorage().getItem(ACCESS_TOKEN_KEY)
}

function getRefreshToken(): string | null {
  return tokenStorage().getItem(REFRESH_TOKEN_KEY)
}

export function storeTokens(tokens: TokenResponse, remember: boolean) {
  const storage = remember ? localStorage : sessionStorage
  const other = remember ? sessionStorage : localStorage
  other.removeItem(ACCESS_TOKEN_KEY)
  other.removeItem(REFRESH_TOKEN_KEY)
  storage.setItem(ACCESS_TOKEN_KEY, tokens.access_token)
  storage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  sessionStorage.removeItem(ACCESS_TOKEN_KEY)
  sessionStorage.removeItem(REFRESH_TOKEN_KEY)
}

export function hasStoredSession(): boolean {
  return !!(localStorage.getItem(ACCESS_TOKEN_KEY) || sessionStorage.getItem(ACCESS_TOKEN_KEY))
}

export function getStoredRefreshToken(): string | null {
  return getRefreshToken()
}

// ── HTTP helper ───────────────────────────────────────────────────────────────

// Auth endpoints legitimately return 401 for reasons unrelated to an expired
// session (bad password, revoked refresh token) — those should surface their
// own error message, not trigger a redirect.
const AUTH_ENDPOINTS = ['/auth/login', '/auth/register', '/auth/refresh']

function handleExpiredSession() {
  clearTokens()
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

let refreshInFlight: Promise<string | null> | null = null

// The access token is short-lived (30 min); the refresh token is long-lived
// and only dies on explicit logout or revocation. On a 401 we try to silently
// mint a new access token before giving up, so the user isn't kicked back to
// the login screen just because their tab was idle for half an hour.
async function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const refreshToken = getRefreshToken()
      if (!refreshToken) return null
      try {
        const tokens = config.mockApi
          ? await mockApi.auth.refresh(refreshToken)
          : await request<TokenResponse>('/auth/refresh', {
              method: 'POST',
              body: JSON.stringify({ refresh_token: refreshToken }),
            })
        storeTokens(tokens, tokenStorage() === localStorage)
        return tokens.access_token
      } catch {
        return null
      }
    })().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

async function request<T>(path: string, options?: RequestInit, isRetry = false): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string>),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${config.apiUrl}${path}`, { ...options, headers })
  if (res.status === 401 && !AUTH_ENDPOINTS.some(p => path.startsWith(p))) {
    if (!isRetry) {
      const newToken = await refreshAccessToken()
      if (newToken) return request<T>(path, options, true)
    }
    handleExpiredSession()
    throw new Error('Session expired — please log in again')
  }
  if (!res.ok) {
    const error = await res.text()
    throw new Error(error || `HTTP ${res.status}`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// ── API ───────────────────────────────────────────────────────────────────────

export const api = {
  auth: {
    login(username: string, password: string): Promise<TokenResponse> {
      if (config.mockApi) return mockApi.auth.login(username, password)
      return request('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })
    },
    register(payload: {
      account_name: string
      account_domain: string
      email: string
      username: string
      password: string
    }): Promise<UserOut> {
      if (config.mockApi) return mockApi.auth.register(payload)
      return request('/auth/register', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
    },
    refresh(refresh_token: string): Promise<TokenResponse> {
      if (config.mockApi) return mockApi.auth.refresh(refresh_token)
      return request('/auth/refresh', {
        method: 'POST',
        body: JSON.stringify({ refresh_token }),
      })
    },
    logout(refresh_token: string): Promise<void> {
      if (config.mockApi) return mockApi.auth.logout(refresh_token)
      return request('/auth/logout', {
        method: 'POST',
        body: JSON.stringify({ refresh_token }),
      })
    },
  },

  chat(message: string, conversationId?: string, stackId?: string): Promise<ChatResponse> {
    if (config.mockApi) return mockApi.chat(message, conversationId, stackId)
    return request('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, conversation_id: conversationId ?? null, stack_id: stackId ?? null }),
    })
  },

  getConversations(): Promise<ConversationOut[]> {
    if (config.mockApi) return mockApi.getConversations()
    return request('/chat/conversations')
  },

  getConversation(id: string): Promise<ConversationOut> {
    if (config.mockApi) return mockApi.getConversation(id)
    return request(`/chat/conversations/${id}`)
  },

  renameConversation(id: string, title: string): Promise<ConversationOut> {
    if (config.mockApi) return mockApi.renameConversation(id, title)
    return request(`/chat/conversations/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) })
  },

  generateConversationTitle(id: string): Promise<ConversationOut> {
    if (config.mockApi) return mockApi.generateConversationTitle(id)
    return request(`/chat/conversations/${id}/generate-title`, { method: 'POST' })
  },

  getProfile(): Promise<UserOut> {
    if (config.mockApi) return mockApi.getProfile()
    return request('/users/me')
  },

  updateProfile(data: { username: string; email: string }): Promise<UserOut> {
    if (config.mockApi) return mockApi.updateProfile(data)
    return request('/users/me', { method: 'PATCH', body: JSON.stringify(data) })
  },

  updatePassword(data: { current: string; next: string }): Promise<void> {
    if (config.mockApi) return mockApi.updatePassword(data)
    return request('/users/me/password', { method: 'PUT', body: JSON.stringify(data) })
  },

  getOrgSettings(): Promise<OrgSettings> {
    if (config.mockApi) return mockApi.getOrgSettings()
    return request('/org/settings')
  },

  updateOrgSettings(data: OrgSettings): Promise<OrgSettings> {
    if (config.mockApi) return mockApi.updateOrgSettings(data)
    return request('/org/settings', { method: 'PUT', body: JSON.stringify(data) })
  },

  listStacks(): Promise<StackOut[]> {
    if (config.mockApi) return mockApi.listStacks()
    return request('/stacks')
  },

  createStack(data: StackCreate): Promise<StackOut> {
    if (config.mockApi) return mockApi.createStack(data)
    return request('/stacks', { method: 'POST', body: JSON.stringify(data) })
  },

  updateStack(id: string, data: StackUpdate): Promise<StackOut> {
    if (config.mockApi) return mockApi.updateStack(id, data)
    return request(`/stacks/${id}`, { method: 'PUT', body: JSON.stringify(data) })
  },

  deleteStack(id: string): Promise<void> {
    if (config.mockApi) return mockApi.deleteStack(id)
    return request(`/stacks/${id}`, { method: 'DELETE' })
  },

  testStackConnection(id: string, data: StackUpdate): Promise<ConnectionTestResult> {
    if (config.mockApi) return mockApi.testStackConnection(id, data)
    return request(`/stacks/${id}/test`, { method: 'POST', body: JSON.stringify(data) })
  },

  testStackCloudConnection(id: string, data: StackUpdate): Promise<ConnectionTestResult> {
    if (config.mockApi) return mockApi.testStackCloudConnection(id, data)
    return request(`/stacks/${id}/test-cloud`, { method: 'POST', body: JSON.stringify(data) })
  },

  reorderStacks(stackIds: string[]): Promise<StackOut[]> {
    if (config.mockApi) return mockApi.reorderStacks(stackIds)
    return request('/stacks/reorder', { method: 'PUT', body: JSON.stringify({ stack_ids: stackIds }) })
  },

  listModuleVersions(): Promise<ModuleVersion[]> {
    if (config.mockApi) return mockApi.listModuleVersions()
    return request('/stacks/module-versions')
  },

  refreshStackModules(id: string): Promise<ModuleRefreshResult> {
    if (config.mockApi) return mockApi.refreshStackModules(id)
    return request(`/stacks/${id}/refresh-modules`, { method: 'POST' })
  },

  releaseStack(
    id: string,
    target: 'prod' | 'develop',
    resolutions?: Record<string, 'ours' | 'theirs'>
  ): Promise<ReleaseResult> {
    if (config.mockApi) return mockApi.releaseStack(id, target, resolutions)
    return request(`/stacks/${id}/release`, { method: 'POST', body: JSON.stringify({ target, resolutions }) })
  },

  getStackTopology(id: string, refresh = false): Promise<Topology> {
    if (config.mockApi) return mockApi.getStackTopology(id, refresh)
    return request(`/stacks/${id}/topology${refresh ? '?refresh=true' : ''}`)
  },

  getLandingZoneAccessKeys(stackId: string, landingZoneName: string): Promise<AccessKeys> {
    if (config.mockApi) return mockApi.getLandingZoneAccessKeys(stackId, landingZoneName)
    return request(`/stacks/${stackId}/landing-zones/${encodeURIComponent(landingZoneName)}/access-keys`)
  },

  listProjects(): Promise<ProjectOut[]> {
    if (config.mockApi) return mockApi.listProjects()
    return request('/projects')
  },

  connectRepo(data: GitHubRepoConnect): Promise<GitHubRepoOut> {
    if (config.mockApi) return mockApi.connectRepo(data)
    return request('/github/repos', { method: 'POST', body: JSON.stringify(data) })
  },

  getRepo(): Promise<GitHubRepoOut> {
    if (config.mockApi) return mockApi.getRepo()
    return request('/github/repos')
  },

  disconnectRepo(): Promise<void> {
    if (config.mockApi) return mockApi.disconnectRepo()
    return request('/github/repos', { method: 'DELETE' })
  },

  connectDbtRepo(data: DbtRepoConnect): Promise<DbtRepoConnectResult> {
    if (config.mockApi) return mockApi.connectDbtRepo(data)
    return request('/dbt/repo', { method: 'POST', body: JSON.stringify(data) })
  },

  getDbtRepo(): Promise<DbtRepoOut> {
    if (config.mockApi) return mockApi.getDbtRepo()
    return request('/dbt/repo')
  },

  disconnectDbtRepo(): Promise<void> {
    if (config.mockApi) return mockApi.disconnectDbtRepo()
    return request('/dbt/repo', { method: 'DELETE' })
  },

  refreshDbtScaffold(): Promise<DbtScaffoldRefreshResult> {
    if (config.mockApi) return mockApi.refreshDbtScaffold()
    return request('/dbt/repo/refresh', { method: 'POST' })
  },
}
