import type {
  ChatResponse,
  TokenResponse,
  UserOut,
  ConversationOut,
  MessageOut,
  OrgSettings,
  StackOut,
  StackCreate,
  StackUpdate,
  ConnectionTestResult,
  ProjectOut,
  GitHubRepoOut,
  GitHubRepoConnect,
  DbtRepoOut,
  DbtRepoConnect,
  DbtRepoConnectResult,
  DbtScaffoldRefreshResult,
  ReleaseResult,
  Topology,
  AccessKeys,
  ModuleVersion,
  ModuleRefreshResult,
} from '../../api/client'
import {
  MOCK_TOKENS,
  MOCK_USER,
  MOCK_CONVERSATIONS,
  mockChatReply,
  MOCK_ORG,
  MOCK_STACKS,
  MOCK_PROJECT,
  MOCK_REPO,
  MOCK_DBT_REPO,
  MOCK_TOPOLOGY,
  MOCK_ACCESS_KEYS,
  MOCK_MODULE_VERSIONS,
} from './data'

let mockProfile = { ...MOCK_USER }
let mockOrg = { ...MOCK_ORG }
let mockStacks: StackOut[] = MOCK_STACKS.map(s => ({ ...s, warehouse: { ...s.warehouse }, cloud: { ...s.cloud } }))
let mockStackCounter = mockStacks.length
let mockConversations: ConversationOut[] = MOCK_CONVERSATIONS.map(c => ({ ...c, messages: [...(c.messages ?? [])] }))
let mockProject: ProjectOut = { ...MOCK_PROJECT }
let mockRepo: GitHubRepoOut | null = { ...MOCK_REPO }
let mockDbtRepo: DbtRepoOut | null = { ...MOCK_DBT_REPO }

function delay(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

let convCounter = mockConversations.length
let messageCounter = 0

export const mockApi = {
  auth: {
    async login(_username: string, _password: string): Promise<TokenResponse> {
      await delay(600)
      return { ...MOCK_TOKENS }
    },
    async register(_payload: {
      account_name: string
      account_domain: string
      email: string
      username: string
      password: string
    }): Promise<UserOut> {
      await delay(800)
      return { ...MOCK_USER }
    },
    async refresh(_refresh_token: string): Promise<TokenResponse> {
      await delay(200)
      return { ...MOCK_TOKENS }
    },
    async logout(_refresh_token: string): Promise<void> {
      await delay(200)
    },
  },

  async chat(message: string, conversationId?: string, stackId?: string): Promise<ChatResponse> {
    await delay(900 + Math.random() * 600)

    let conv = conversationId ? mockConversations.find(c => c.id === conversationId) : undefined
    if (!conv) {
      conv = {
        id: `conv-${++convCounter}`,
        title: message.slice(0, 60),
        stack_id: stackId ?? null,
        created_at: new Date().toISOString(),
        messages: [],
      }
      mockConversations = [conv, ...mockConversations]
    } else if (stackId !== undefined && stackId !== conv.stack_id) {
      conv.stack_id = stackId
    }

    const reply = mockChatReply(message)
    const userMsg: MessageOut = { id: `msg-${++messageCounter}`, role: 'user', content: message, created_at: new Date().toISOString() }
    const assistantMsg: MessageOut = { id: `msg-${++messageCounter}`, role: 'assistant', content: reply, created_at: new Date().toISOString() }
    conv.messages = [...(conv.messages ?? []), userMsg, assistantMsg]

    return {
      conversation_id: conv.id,
      reply,
      tool_calls: null,
    }
  },

  async getConversations(): Promise<ConversationOut[]> {
    await delay(300)
    return mockConversations.map(c => ({ ...c, messages: undefined }))
  },

  async getConversation(id: string): Promise<ConversationOut> {
    await delay(200)
    const found = mockConversations.find(c => c.id === id)
    if (!found) throw new Error('Conversation not found')
    return { ...found, messages: [...(found.messages ?? [])] }
  },

  async renameConversation(id: string, title: string): Promise<ConversationOut> {
    await delay(200)
    const found = mockConversations.find(c => c.id === id)
    if (!found) throw new Error('Conversation not found')
    found.title = title.trim() || found.title
    return { ...found, messages: [...(found.messages ?? [])] }
  },

  async generateConversationTitle(id: string): Promise<ConversationOut> {
    await delay(400)
    const found = mockConversations.find(c => c.id === id)
    if (!found) throw new Error('Conversation not found')
    const firstUserMessage = (found.messages ?? []).find(m => m.role === 'user')
    if (firstUserMessage) {
      found.title = firstUserMessage.content.slice(0, 40)
    }
    return { ...found, messages: [...(found.messages ?? [])] }
  },

  async getProfile(): Promise<UserOut> {
    await delay(200)
    return { ...mockProfile }
  },

  async updateProfile(data: { username: string; email: string }): Promise<UserOut> {
    await delay(500)
    mockProfile = { ...mockProfile, ...data }
    return { ...mockProfile }
  },

  async updatePassword(_data: { current: string; next: string }): Promise<void> {
    await delay(600)
  },

  async getOrgSettings(): Promise<OrgSettings> {
    await delay(200)
    return { ...mockOrg }
  },

  async updateOrgSettings(data: OrgSettings): Promise<OrgSettings> {
    await delay(500)
    mockOrg = { ...data }
    return { ...mockOrg }
  },

  async listStacks(): Promise<StackOut[]> {
    await delay(200)
    return mockStacks.map(s => ({ ...s })).sort((a, b) => a.sort_order - b.sort_order)
  },

  async createStack(data: StackCreate): Promise<StackOut> {
    await delay(400)
    const created: StackOut = {
      id: `mock-stack-${++mockStackCounter}`,
      name: data.name,
      branch: data.branch ?? data.name,
      verify_before_pr: data.verify_before_pr ?? false,
      verify_max_attempts: data.verify_max_attempts ?? 3,
      module_version: data.module_version ?? MOCK_MODULE_VERSIONS[MOCK_MODULE_VERSIONS.length - 1].version,
      sort_order: mockStacks.length,
      is_default: false,
      warehouse: {
        type: data.warehouse?.type ?? 'snowflake',
        organization_name: data.warehouse?.organization_name ?? '',
        account_name: data.warehouse?.account_name ?? '',
        user: data.warehouse?.user ?? '',
        authenticator: data.warehouse?.authenticator ?? 'SNOWFLAKE_JWT',
        private_key_b64: data.warehouse?.private_key_b64 ?? null,
        database: data.warehouse?.database ?? null,
        schema_: data.warehouse?.schema_ ?? null,
        warehouse: data.warehouse?.warehouse ?? null,
        role: data.warehouse?.role ?? null,
      },
      cloud: {
        provider: data.cloud?.provider ?? 'aws',
        access_key_id: data.cloud?.access_key_id ?? '',
        secret_access_key: data.cloud?.secret_access_key ?? null,
        region: data.cloud?.region ?? 'us-east-1',
      },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    mockStacks = [...mockStacks, created]
    return { ...created }
  },

  async updateStack(id: string, data: StackUpdate): Promise<StackOut> {
    await delay(400)
    const index = mockStacks.findIndex(s => s.id === id)
    if (index === -1) throw new Error('Stack not found')
    const current = mockStacks[index]
    mockStacks[index] = {
      ...current,
      name: data.name ?? current.name,
      branch: data.branch ?? current.branch,
      verify_before_pr: data.verify_before_pr ?? current.verify_before_pr,
      verify_max_attempts: data.verify_max_attempts ?? current.verify_max_attempts,
      module_version: data.module_version ?? current.module_version,
      warehouse: { ...current.warehouse, ...data.warehouse },
      cloud: { ...current.cloud, ...data.cloud },
      updated_at: new Date().toISOString(),
    }
    return { ...mockStacks[index] }
  },

  async deleteStack(id: string): Promise<void> {
    await delay(300)
    const stack = mockStacks.find(s => s.id === id)
    if (stack?.is_default) throw new Error('Cannot delete the default stack')
    if (mockStacks.length <= 1) throw new Error('Cannot delete the last remaining stack')
    mockStacks = mockStacks.filter(s => s.id !== id)
  },

  async testStackConnection(_id: string, _data: StackUpdate): Promise<ConnectionTestResult> {
    await delay(1200)
    return { ok: true, message: 'Connected successfully to COMPUTE_WH' }
  },

  async testStackCloudConnection(_id: string, _data: StackUpdate): Promise<ConnectionTestResult> {
    await delay(1000)
    return { ok: true, message: 'Connected as arn:aws:iam::123456789012:user/svc-canary (account 123456789012)' }
  },

  async listModuleVersions(): Promise<ModuleVersion[]> {
    await delay(150)
    return MOCK_MODULE_VERSIONS.map(v => ({ ...v }))
  },

  async refreshStackModules(_id: string): Promise<ModuleRefreshResult> {
    await delay(1500)
    return { pr_url: null, files_removed: 0, files_added: 0, message: 'Already up to date' }
  },

  async reorderStacks(stackIds: string[]): Promise<StackOut[]> {
    await delay(300)
    const byId = new Map(mockStacks.map(s => [s.id, s]))
    mockStacks = stackIds.map((id, index) => ({ ...byId.get(id)!, sort_order: index }))
    return mockStacks.map(s => ({ ...s }))
  },

  async releaseStack(id: string, target: 'prod' | 'develop', _resolutions?: Record<string, 'ours' | 'theirs'>): Promise<ReleaseResult> {
    await delay(1500)
    const stack = mockStacks.find(s => s.id === id)
    if (!stack) throw new Error('Stack not found')
    return {
      pr_urls: [`https://github.com/${mockRepo?.repo_full_name ?? 'canary-demo/data-platform'}/pull/${Math.floor(Math.random() * 900) + 100}`],
      branch: target === 'prod' ? 'main' : stack.branch,
    }
  },

  async getStackTopology(_id: string, _refresh = false): Promise<Topology> {
    await delay(500)
    return { ...MOCK_TOPOLOGY, fetched_at: new Date().toISOString() }
  },

  async getLandingZoneAccessKeys(_stackId: string, _landingZoneName: string): Promise<AccessKeys> {
    await delay(300)
    return { ...MOCK_ACCESS_KEYS }
  },

  async listProjects(): Promise<ProjectOut[]> {
    await delay(200)
    return [{ ...mockProject }]
  },

  async connectRepo(data: GitHubRepoConnect): Promise<GitHubRepoOut> {
    await delay(700)
    mockRepo = {
      id: mockRepo?.id ?? 'mock-repo-1',
      project_name: mockProject.name,
      repo_full_name: data.repo_full_name,
      branch: data.branch || 'develop',
      api_url: data.api_url || 'https://api.github.com',
      infrastructure_base_path: data.infrastructure_base_path || 'infrastructure',
      auto_merge: data.auto_merge ?? false,
      create_cicd: data.create_cicd ?? true,
      skip_bootstrap: data.skip_bootstrap ?? false,
      skip_module_import: data.skip_module_import ?? false,
      created_at: mockRepo?.created_at ?? new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    mockProject = { ...mockProject, version_control_created: true }
    return { ...mockRepo }
  },

  async getRepo(): Promise<GitHubRepoOut> {
    await delay(200)
    if (!mockRepo) throw new Error('No GitHub repo connected for this account')
    return { ...mockRepo }
  },

  async disconnectRepo(): Promise<void> {
    await delay(300)
    mockRepo = null
    mockProject = { ...mockProject, version_control_created: false }
  },

  async connectDbtRepo(data: DbtRepoConnect): Promise<DbtRepoConnectResult> {
    await delay(700)
    const isFirstConnect = !mockDbtRepo
    mockDbtRepo = {
      id: mockDbtRepo?.id ?? 'mock-dbt-repo-1',
      repo_full_name: data.repo_full_name,
      branch: data.branch || 'main',
      api_url: data.api_url || 'https://api.github.com',
      dbt_base_path: data.dbt_base_path || '.',
      scaffold_version: mockDbtRepo?.scaffold_version ?? '1.0.0',
      created_at: mockDbtRepo?.created_at ?? new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    return {
      ...mockDbtRepo,
      scaffold_pr_url: isFirstConnect
        ? `https://github.com/${mockDbtRepo.repo_full_name}/pull/${Math.floor(Math.random() * 900) + 100}`
        : null,
    }
  },

  async getDbtRepo(): Promise<DbtRepoOut> {
    await delay(200)
    if (!mockDbtRepo) throw new Error('No dbt repo connected for this account')
    return { ...mockDbtRepo }
  },

  async disconnectDbtRepo(): Promise<void> {
    await delay(300)
    mockDbtRepo = null
  },

  async refreshDbtScaffold(): Promise<DbtScaffoldRefreshResult> {
    await delay(1200)
    return { pr_url: null, files_removed: 0, files_added: 0, message: 'Already up to date' }
  },
}
