import { useState, useEffect, useRef, FormEvent, KeyboardEvent } from 'react'
import { api, ChatResponse, ConversationOut } from '../api/client'
import { AppLayout } from '../components/AppLayout'
import { Button } from '../components/ui/button'
import { Textarea } from '../components/ui/textarea'
import { ScrollArea } from '../components/ui/scroll-area'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

function CanaryLogo({ size = 20 }: { size?: number }) {
  return (
    <div
      className="rounded-xl bg-primary flex items-center justify-center shrink-0 shadow-md shadow-primary/30"
      style={{ width: size, height: size }}
    >
      <svg width={size * 0.55} height={size * 0.55} viewBox="0 0 32 32" fill="none">
        <path d="M10 22 L16 10 L22 22" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <path d="M12.5 18 L19.5 18" stroke="white" strokeWidth="3" strokeLinecap="round" />
      </svg>
    </div>
  )
}

export function ChatPage() {
  const [conversations, setConversations] = useState<ConversationOut[]>([])
  const [activeConvId, setActiveConvId] = useState<string | undefined>()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    api.getConversations().then(setConversations).catch(() => {})
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [input])

  async function send() {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setMessages(m => [...m, { role: 'user', content: text }])
    setSending(true)
    try {
      const res: ChatResponse = await api.chat(text, activeConvId)
      setActiveConvId(res.conversation_id)
      setMessages(m => [...m, { role: 'assistant', content: res.reply }])
      if (!activeConvId) {
        api.getConversations().then(setConversations).catch(() => {})
      }
    } catch (err) {
      setMessages(m => [
        ...m,
        {
          role: 'assistant',
          content: `Error: ${err instanceof Error ? err.message : 'Something went wrong'}`,
        },
      ])
    } finally {
      setSending(false)
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  function handleFormSubmit(e: FormEvent) {
    e.preventDefault()
    send()
  }

  const sidebarContent = (
    <>
      <div className="px-2 pt-2 pb-1">
        <Button
          variant="outline"
          size="sm"
          className="w-full h-8 text-xs justify-start gap-1.5 border-border/50 bg-transparent text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
          onClick={() => { setActiveConvId(undefined); setMessages([]) }}
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M6 1v10M1 6h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          New conversation
        </Button>
      </div>

      <ScrollArea className="flex-1 px-2 py-1">
        {conversations.length === 0 ? (
          <p className="text-xs text-muted-foreground/60 text-center py-6">No conversations yet</p>
        ) : (
          <div className="space-y-0.5">
            <p className="text-[10px] font-medium text-muted-foreground/50 uppercase tracking-widest px-2 py-1.5">
              Recent
            </p>
            {conversations.map(conv => (
              <button
                key={conv.id}
                onClick={() => { setActiveConvId(conv.id); setMessages([]) }}
                className={`w-full text-left px-2 py-1.5 rounded-md text-xs truncate transition-colors ${
                  conv.id === activeConvId
                    ? 'bg-primary/15 text-primary font-medium'
                    : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
                }`}
              >
                {conv.title || 'Untitled'}
              </button>
            ))}
          </div>
        )}
      </ScrollArea>
    </>
  )

  return (
    <AppLayout sidebarContent={sidebarContent}>
      {messages.length === 0 && !sending ? (
        <div className="relative flex-1 flex flex-col items-center justify-center gap-4 text-center px-8 overflow-hidden">
          <div className="pointer-events-none absolute inset-0">
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[300px] rounded-full bg-primary/8 blur-[100px]" />
          </div>
          <CanaryLogo size={48} />
          <div className="space-y-1.5">
            <h2 className="text-2xl font-bold tracking-tight">How can I help you?</h2>
            <p className="text-sm text-muted-foreground">
              Ask me anything about your data, pipelines, or infrastructure.
            </p>
          </div>
          <div className="flex flex-wrap gap-2 justify-center mt-2">
            {[
              'Summarise recent pipeline failures',
              'Show me anomalies in the last 24 hours',
              'Explain this Snowflake query',
            ].map(prompt => (
              <button
                key={prompt}
                onClick={() => setInput(prompt)}
                className="text-xs px-3 py-1.5 rounded-full border border-border/60 bg-muted/30 text-muted-foreground hover:bg-muted/60 hover:text-foreground hover:border-border transition-colors"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <ScrollArea className="flex-1">
          <div className="max-w-2xl mx-auto py-8 space-y-2 px-4">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex gap-3 px-4 py-3.5 rounded-xl ${
                  msg.role === 'assistant'
                    ? 'bg-muted/30 border border-border/40'
                    : ''
                }`}
              >
                <div className="mt-0.5 shrink-0">
                  {msg.role === 'assistant' ? (
                    <CanaryLogo size={22} />
                  ) : (
                    <div className="size-[22px] rounded-lg bg-muted border border-border/60 flex items-center justify-center">
                      <svg width="11" height="11" viewBox="0 0 20 20" fill="none">
                        <circle cx="10" cy="8" r="3.5" stroke="currentColor" strokeWidth="1.5" />
                        <path d="M3 18c0-3.9 3.1-7 7-7s7 3.1 7 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                      </svg>
                    </div>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[10px] font-semibold text-muted-foreground/60 mb-1.5 uppercase tracking-widest">
                    {msg.role === 'assistant' ? 'Canary' : 'You'}
                  </p>
                  <p className="text-sm leading-relaxed whitespace-pre-wrap text-foreground/90">
                    {msg.content}
                  </p>
                </div>
              </div>
            ))}

            {sending && (
              <div className="flex gap-3 px-4 py-3.5 rounded-xl bg-muted/30 border border-border/40">
                <div className="mt-0.5 shrink-0">
                  <CanaryLogo size={22} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[10px] font-semibold text-muted-foreground/60 mb-1.5 uppercase tracking-widest">Canary</p>
                  <div className="flex items-center gap-1 h-5">
                    {[0, 1, 2].map(i => (
                      <span
                        key={i}
                        className="size-1.5 rounded-full bg-primary/60 animate-bounce"
                        style={{ animationDelay: `${i * 0.15}s` }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>
      )}

      <div className="border-t border-border/50 bg-background/80 backdrop-blur-sm px-4 pt-3 pb-4">
        <form
          onSubmit={handleFormSubmit}
          className="max-w-2xl mx-auto flex items-end gap-2 rounded-xl border border-border/60 bg-muted/20 px-3 py-2.5 focus-within:border-primary/50 focus-within:bg-muted/30 transition-colors"
        >
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything about your data…"
            rows={1}
            disabled={sending}
            className="flex-1 resize-none border-0 bg-transparent shadow-none focus-visible:ring-0 min-h-0 py-0.5 text-sm placeholder:text-muted-foreground/50"
          />
          <Button
            type="submit"
            size="sm"
            disabled={!input.trim() || sending}
            className="shrink-0 h-8 w-8 p-0 shadow-md shadow-primary/20"
          >
            <svg width="14" height="14" viewBox="0 0 18 18" fill="none">
              <path d="M2 9h14M9 2l7 7-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Button>
        </form>
        <p className="text-center text-[10px] text-muted-foreground/40 mt-2 tracking-wide">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </AppLayout>
  )
}
