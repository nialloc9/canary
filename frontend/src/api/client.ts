const BASE_URL = import.meta.env.VITE_API_URL ?? '/api/v1'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const error = await res.text()
    throw new Error(error || `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export interface ChatResponse {
  conversation_id: string
  reply: string
  tool_calls: Array<{ tool: string; input: Record<string, unknown>; result: string }> | null
}

export const api = {
  chat(message: string, conversationId?: string): Promise<ChatResponse> {
    return request('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, conversation_id: conversationId ?? null }),
    })
  },

  getConversations() {
    return request<Array<{ id: string; title: string | null; created_at: string }>>('/chat/conversations')
  },

  getConversation(id: string) {
    return request(`/chat/conversations/${id}`)
  },
}
