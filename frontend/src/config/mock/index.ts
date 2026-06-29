import type { ChatResponse, TokenResponse, UserOut, ConversationOut } from '../../api/client'
import {
  MOCK_TOKENS,
  MOCK_USER,
  MOCK_CONVERSATIONS,
  mockChatReply,
} from './data'

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
}
