import type { ChatResponse, TokenResponse, UserOut, ConversationOut, OrgSettings, StackOut, StackCreate, StackUpdate, ConnectionTestResult } from '../../api/client'
import {
  MOCK_TOKENS,
  MOCK_USER,
  MOCK_CONVERSATIONS,
  mockChatReply,
  MOCK_ORG,
  MOCK_STACKS,
} from './data'

let mockProfile = { ...MOCK_USER }
let mockOrg = { ...MOCK_ORG }
let mockStacks: StackOut[] = MOCK_STACKS.map(s => ({ ...s, warehouse: { ...s.warehouse }, cloud: { ...s.cloud } }))
let mockStackCounter = mockStacks.length

function delay(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

let convCounter = MOCK_CONVERSATIONS.length

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
    async logout(_refresh_token: string): Promise<void> {
      await delay(200)
    },
  },

  async chat(message: string, conversationId?: string): Promise<ChatResponse> {
    await delay(900 + Math.random() * 600)
    const id = conversationId ?? `conv-${++convCounter}`
    return {
      conversation_id: id,
      reply: mockChatReply(message),
      tool_calls: null,
    }
  },

  async getConversations(): Promise<ConversationOut[]> {
    await delay(300)
    return [...MOCK_CONVERSATIONS]
  },

  async getConversation(id: string): Promise<ConversationOut> {
    await delay(200)
    const found = MOCK_CONVERSATIONS.find(c => c.id === id)
    if (!found) throw new Error('Conversation not found')
    return { ...found }
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

  async reorderStacks(stackIds: string[]): Promise<StackOut[]> {
    await delay(300)
    const byId = new Map(mockStacks.map(s => [s.id, s]))
    mockStacks = stackIds.map((id, index) => ({ ...byId.get(id)!, sort_order: index }))
    return mockStacks.map(s => ({ ...s }))
  },
}
