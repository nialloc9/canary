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

export interface ConversationOut {
  id: string
  title: string | null
  created_at: string
}

export interface OrgSettings {
  name: string
  domain: string
}

export type WarehouseType = 'snowflake'

export interface WarehouseConfig {
  type: WarehouseType
  account: string
  username: string
  password?: string
  database: string
  schema: string
  warehouse: string
  role: string
}

export type CloudProvider = 'aws'

export interface CloudConfig {
  provider: CloudProvider
  accessKeyId: string
  secretAccessKey?: string
  region: string
}

export interface ConnectionTestResult {
  ok: boolean
  message: string
}

// ── HTTP helper ───────────────────────────────────────────────────────────────

function getToken(): string | null {
  return localStorage.getItem('access_token')
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string>),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${config.apiUrl}${path}`, { ...options, headers })
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
    logout(refresh_token: string): Promise<void> {
      if (config.mockApi) return mockApi.auth.logout(refresh_token)
      return request('/auth/logout', {
        method: 'POST',
        body: JSON.stringify({ refresh_token }),
      })
    },
  },

  chat(message: string, conversationId?: string): Promise<ChatResponse> {
    if (config.mockApi) return mockApi.chat(message, conversationId)
    return request('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, conversation_id: conversationId ?? null }),
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

  getWarehouseConfig(): Promise<WarehouseConfig> {
    if (config.mockApi) return mockApi.getWarehouseConfig()
    return request('/org/warehouse')
  },

  updateWarehouseConfig(data: WarehouseConfig): Promise<WarehouseConfig> {
    if (config.mockApi) return mockApi.updateWarehouseConfig(data)
    return request('/org/warehouse', { method: 'PUT', body: JSON.stringify(data) })
  },

  testWarehouseConnection(data: WarehouseConfig): Promise<ConnectionTestResult> {
    if (config.mockApi) return mockApi.testWarehouseConnection(data)
    return request('/org/warehouse/test', { method: 'POST', body: JSON.stringify(data) })
  },

  getCloudConfig(): Promise<CloudConfig> {
    if (config.mockApi) return mockApi.getCloudConfig()
    return request('/org/cloud')
  },

  updateCloudConfig(data: CloudConfig): Promise<CloudConfig> {
    if (config.mockApi) return mockApi.updateCloudConfig(data)
    return request('/org/cloud', { method: 'PUT', body: JSON.stringify(data) })
  },
}
