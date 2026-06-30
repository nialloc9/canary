import type { ChatResponse, TokenResponse, UserOut, ConversationOut, OrgSettings, WarehouseConfig, CloudConfig, ConnectionTestResult } from '../../api/client'
import {
  MOCK_TOKENS,
  MOCK_USER,
  MOCK_CONVERSATIONS,
  mockChatReply,
  MOCK_ORG,
  MOCK_WAREHOUSE,
  MOCK_CLOUD,
} from './data'

let mockProfile = { ...MOCK_USER }
let mockOrg = { ...MOCK_ORG }
let mockWarehouse = { ...MOCK_WAREHOUSE }
let mockCloud = { ...MOCK_CLOUD }

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

  async getWarehouseConfig(): Promise<WarehouseConfig> {
    await delay(200)
    return { ...mockWarehouse }
  },

  async updateWarehouseConfig(data: WarehouseConfig): Promise<WarehouseConfig> {
    await delay(500)
    mockWarehouse = { ...data }
    return { ...mockWarehouse }
  },

  async testWarehouseConnection(_data: WarehouseConfig): Promise<ConnectionTestResult> {
    await delay(1200)
    return { ok: true, message: 'Connected successfully to COMPUTE_WH' }
  },

  async getCloudConfig(): Promise<CloudConfig> {
    await delay(200)
    return { ...mockCloud }
  },

  async updateCloudConfig(data: CloudConfig): Promise<CloudConfig> {
    await delay(500)
    mockCloud = { ...data }
    return { ...mockCloud }
  },
}
