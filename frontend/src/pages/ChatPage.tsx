import { useState, useEffect, useRef, FormEvent, KeyboardEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ChatResponse, ConversationOut, StackOut, ReleaseResult, ReleaseConflict, ProjectOut } from '../api/client'
import { AppLayout } from '../components/AppLayout'
import { Button } from '../components/ui/button'
import { Textarea } from '../components/ui/textarea'
import { ScrollArea } from '../components/ui/scroll-area'
import { TopologyDiagram } from '../components/TopologyDiagram'
import { Markdown } from '../components/Markdown'

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
  const { conversationId: activeConvId } = useParams<{ conversationId?: string }>()
  const navigate = useNavigate()
  const [conversations, setConversations] = useState<ConversationOut[]>([])
  const [loadedConvId, setLoadedConvId] = useState<string | undefined>()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [stacks, setStacks] = useState<StackOut[]>([])
  const [selectedStackId, setSelectedStackId] = useState<string | undefined>()
  const [releaseStep, setReleaseStep] = useState<'idle' | 'confirm-dev' | 'choose-target'>('idle')
  const [releaseChoice, setReleaseChoice] = useState<'prod' | 'develop'>('prod')
  const [releasing, setReleasing] = useState(false)
  const [releaseResult, setReleaseResult] = useState<ReleaseResult | null>(null)
  const [releaseError, setReleaseError] = useState('')
  const [releaseTarget, setReleaseTarget] = useState<'prod' | 'develop'>('prod')
  const [conflicts, setConflicts] = useState<ReleaseConflict[] | null>(null)
  const [conflictChoices, setConflictChoices] = useState<Record<string, 'ours' | 'theirs'>>({})
  const [resolving, setResolving] = useState(false)
  const [showTopology, setShowTopology] = useState(false)
  const [projects, setProjects] = useState<ProjectOut[]>([])
  const [editingConvId, setEditingConvId] = useState<string | undefined>()
  const [editingTitle, setEditingTitle] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    api.getConversations().then(setConversations).catch(() => {})
    api.listStacks().then(list => {
      setStacks(list)
      setSelectedStackId(prev => prev ?? (list.find(s => s.is_default) ?? list[0])?.id)
    }).catch(() => {})
    api.listProjects().then(setProjects).catch(() => {})
  }, [])

  useEffect(() => {
    setReleaseStep('idle')
    setReleaseResult(null)
    setReleaseError('')
    setConflicts(null)
    setConflictChoices({})
    setShowTopology(false)
  }, [selectedStackId])

  const selectedStack = stacks.find(s => s.id === selectedStackId)

  const githubConnected = projects.some(p => p.version_control_created)
  const missingConfig: { label: string; href: string }[] = []
  if (selectedStack) {
    if (!githubConnected) {
      missingConfig.push({ label: 'a GitHub repository', href: '/admin?tab=projects' })
    }
    if (!selectedStack.cloud.access_key_id || !selectedStack.cloud.secret_access_key) {
      missingConfig.push({ label: 'cloud access', href: '/admin?tab=stacks' })
    }
    if (!selectedStack.warehouse.account_name || !selectedStack.warehouse.user || !selectedStack.warehouse.private_key_b64) {
      missingConfig.push({ label: 'a warehouse', href: '/admin?tab=stacks' })
    }
  }

  async function doRelease(target: 'prod' | 'develop') {
    if (!selectedStackId) return
    setReleaseStep('idle')
    setReleasing(true)
    setReleaseError('')
    setReleaseResult(null)
    setConflicts(null)
    setReleaseTarget(target)
    try {
      const result = await api.releaseStack(selectedStackId, target)
      if (result.conflicts && result.conflicts.length > 0) {
        setConflicts(result.conflicts)
        setConflictChoices(Object.fromEntries(result.conflicts.map(c => [c.path, 'ours' as const])))
      } else {
        setReleaseResult(result)
      }
    } catch (e) {
      setReleaseError(e instanceof Error ? e.message : 'Release failed')
    }
    setReleasing(false)
  }

  async function resolveConflicts() {
    if (!selectedStackId || !conflicts) return
    setResolving(true)
    setReleaseError('')
    try {
      const result = await api.releaseStack(selectedStackId, releaseTarget, conflictChoices)
      if (result.conflicts && result.conflicts.length > 0) {
        // Resolutions were incomplete or something changed upstream — show the fresh set.
        setConflicts(result.conflicts)
        setConflictChoices(Object.fromEntries(result.conflicts.map(c => [c.path, 'ours' as const])))
      } else {
        setConflicts(null)
        setReleaseResult(result)
      }
    } catch (e) {
      setReleaseError(e instanceof Error ? e.message : 'Failed to resolve conflicts')
    }
    setResolving(false)
  }

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [input])

  // The URL is the source of truth for which conversation is active — reload
  // its messages whenever it changes (including on first mount, e.g. after a
  // page refresh on /chat/:id), but skip refetching if we already have them
  // loaded (e.g. right after send() creates a new conversation).
  useEffect(() => {
    if (!activeConvId) {
      setMessages([])
      setLoadedConvId(undefined)
      return
    }
    if (activeConvId === loadedConvId) return
    setMessages([])
    api.getConversation(activeConvId).then(full => {
      setMessages((full.messages ?? []).map(m => ({ role: m.role, content: m.content })))
      if (full.stack_id) setSelectedStackId(full.stack_id)
      setLoadedConvId(activeConvId)
    }).catch(() => {
      navigate('/', { replace: true })
    })
  }, [activeConvId])

  // Auto-title the conversation being left behind, if it's still Untitled —
  // keyed on activeConvId itself (not tied to any one button) so it fires no
  // matter how the user navigates away: "New conversation", clicking a
  // different conversation in the sidebar, or the "Chat" nav link.
  const prevConvIdRef = useRef<string | undefined>(undefined)
  useEffect(() => {
    const prevId = prevConvIdRef.current
    prevConvIdRef.current = activeConvId
    if (!prevId || prevId === activeConvId) return

    const prevConv = conversations.find(c => c.id === prevId)
    if (prevConv && !prevConv.title) {
      api.generateConversationTitle(prevId)
        .then(updated => setConversations(cs => cs.map(c => (c.id === prevId ? { ...c, title: updated.title } : c))))
        .catch(() => {})
    }
  }, [activeConvId])

  function selectConversation(conv: ConversationOut) {
    navigate(`/chat/${conv.id}`)
  }

  function startNewConversation() {
    setSelectedStackId((stacks.find(s => s.is_default) ?? stacks[0])?.id)
    navigate('/')
  }

  function startRenaming(conv: ConversationOut) {
    setEditingConvId(conv.id)
    setEditingTitle(conv.title || '')
  }

  async function commitRename() {
    const id = editingConvId
    const title = editingTitle.trim()
    setEditingConvId(undefined)
    if (!id || !title) return
    try {
      const updated = await api.renameConversation(id, title)
      setConversations(cs => cs.map(c => (c.id === id ? { ...c, title: updated.title } : c)))
    } catch {}
  }

  async function send() {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setMessages(m => [...m, { role: 'user', content: text }])
    setSending(true)
    try {
      const res: ChatResponse = await api.chat(text, activeConvId, selectedStackId)
      setMessages(m => [...m, { role: 'assistant', content: res.reply }])
      setLoadedConvId(res.conversation_id)
      if (!activeConvId) {
        navigate(`/chat/${res.conversation_id}`, { replace: true })
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
          onClick={startNewConversation}
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M6 1v10M1 6h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          New conversation
        </Button>
      </div>

      <ScrollArea className="flex-1 min-h-0 px-2 py-1">
        {conversations.length === 0 ? (
          <p className="text-xs text-muted-foreground/60 text-center py-6">No conversations yet</p>
        ) : (
          <div className="space-y-0.5">
            <p className="text-[10px] font-medium text-muted-foreground/50 uppercase tracking-widest px-2 py-1.5">
              Recent
            </p>
            {conversations.map(conv =>
              editingConvId === conv.id ? (
                <input
                  key={conv.id}
                  autoFocus
                  value={editingTitle}
                  onChange={e => setEditingTitle(e.target.value)}
                  onBlur={commitRename}
                  onKeyDown={e => {
                    if (e.key === 'Enter') commitRename()
                    if (e.key === 'Escape') setEditingConvId(undefined)
                  }}
                  className="w-full px-2 py-1.5 rounded-md text-xs bg-sidebar-accent text-sidebar-accent-foreground outline-none ring-1 ring-primary/50"
                />
              ) : (
                <div
                  key={conv.id}
                  className={`group/conv flex items-center gap-1 rounded-md transition-colors ${
                    conv.id === activeConvId
                      ? 'bg-primary/15 text-primary font-medium'
                      : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
                  }`}
                >
                  <button
                    onClick={() => selectConversation(conv)}
                    className="flex-1 min-w-0 text-left px-2 py-1.5 text-xs truncate"
                  >
                    {conv.title || 'Untitled'}
                  </button>
                  <button
                    onClick={e => {
                      e.stopPropagation()
                      startRenaming(conv)
                    }}
                    aria-label="Rename conversation"
                    className="shrink-0 p-1 mr-1 rounded opacity-0 group-hover/conv:opacity-100 text-muted-foreground/60 hover:text-foreground transition-opacity"
                  >
                    <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                      <path d="M11 2l3 3-8 8-3.5 1 1-3.5 8-8z" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                </div>
              )
            )}
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
        <ScrollArea className="flex-1 min-h-0">
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
                  <Markdown content={msg.content} />
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
        {stacks.length > 0 && (
          <div className="max-w-2xl mx-auto mb-2 flex items-center gap-1.5">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" className="text-muted-foreground/50 shrink-0">
              <path d="M12 2v20M12 2l-3 3M12 2l3 3M12 22l-3-3M12 22l3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              <path d="M2 12h20M2 12l3-3M2 12l3 3M22 12l-3-3M22 12l-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <select
              value={selectedStackId ?? ''}
              onChange={e => setSelectedStackId(e.target.value || undefined)}
              aria-label="Stack this conversation is about"
              className="bg-transparent text-xs text-muted-foreground border border-border/50 rounded-md px-2 py-1 outline-none focus:border-primary/50 focus:text-foreground cursor-pointer"
            >
              <option value="">No stack selected</option>
              {stacks.map(s => (
                <option key={s.id} value={s.id}>
                  {s.name}{s.is_default ? ' (default)' : ''}
                </option>
              ))}
            </select>

            {selectedStack && selectedStack.name !== 'prod' && releaseStep === 'idle' && (
              <button
                type="button"
                onClick={() => setReleaseStep(selectedStack.name === 'dev' ? 'confirm-dev' : 'choose-target')}
                disabled={releasing}
                className="text-xs text-muted-foreground border border-border/50 rounded-md px-2 py-1 hover:text-foreground hover:border-primary/50 transition-colors"
              >
                Release
              </button>
            )}

            {selectedStack && (
              <button
                type="button"
                onClick={() => setShowTopology(v => !v)}
                className={`text-xs border rounded-md px-2 py-1 transition-colors ${
                  showTopology
                    ? 'text-foreground border-primary/50 bg-primary/10'
                    : 'text-muted-foreground border-border/50 hover:text-foreground hover:border-primary/50'
                }`}
              >
                {showTopology ? 'Hide infrastructure' : 'View infrastructure'}
              </button>
            )}
          </div>
        )}

        {selectedStack && missingConfig.length > 0 && (
          <div className="max-w-2xl mx-auto mb-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 space-y-1">
            <p className="text-xs text-amber-600 dark:text-amber-400">
              <strong>{selectedStack.name}</strong> hasn't been set up yet — some actions may fail until it is.
            </p>
            <div className="flex flex-wrap gap-x-3 gap-y-0.5">
              {missingConfig.map(item => (
                <Link
                  key={item.label}
                  to={item.href}
                  className="text-xs text-amber-600 dark:text-amber-400 underline underline-offset-2 hover:text-amber-500"
                >
                  Configure {item.label} →
                </Link>
              ))}
            </div>
          </div>
        )}

        {selectedStack && showTopology && (
          <div className="max-w-2xl mx-auto mb-2 rounded-lg border border-border/50 bg-muted/10 p-3.5">
            <TopologyDiagram stackId={selectedStack.id} bare />
          </div>
        )}

        {selectedStack && releaseStep !== 'idle' && (
          <div className="max-w-2xl mx-auto mb-2 rounded-lg border border-border/50 bg-muted/10 p-3.5 space-y-3">
            {releaseStep === 'confirm-dev' && (
              <>
                <p className="text-sm">Release dev to prod?</p>
                <p className="text-xs text-muted-foreground">
                  Opens a PR from a new branch based on <code className="font-mono">main</code> (merging
                  in <code className="font-mono">develop</code>'s changes) into <code className="font-mono">main</code>,
                  plus a companion PR into <code className="font-mono">develop</code> to keep it in sync.
                </p>
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => doRelease('prod')} className="shadow-md shadow-primary/20">
                    Release to prod
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setReleaseStep('idle')} className="border-border/60">
                    Cancel
                  </Button>
                </div>
              </>
            )}

            {releaseStep === 'choose-target' && (
              <>
                <p className="text-sm">Release {selectedStack.name} to:</p>
                <div className="flex gap-4 text-sm">
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="radio"
                      name="release-target"
                      checked={releaseChoice === 'develop'}
                      onChange={() => setReleaseChoice('develop')}
                    />
                    develop
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="radio"
                      name="release-target"
                      checked={releaseChoice === 'prod'}
                      onChange={() => setReleaseChoice('prod')}
                    />
                    main
                  </label>
                </div>
                {releaseChoice === 'prod' && (
                  <p className="text-xs text-muted-foreground">
                    Releasing to main also opens a companion PR into develop to keep it in sync.
                  </p>
                )}
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => doRelease(releaseChoice)} className="shadow-md shadow-primary/20">
                    Confirm
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setReleaseStep('idle')} className="border-border/60">
                    Cancel
                  </Button>
                </div>
              </>
            )}
          </div>
        )}

        {releasing && (
          <p className="max-w-2xl mx-auto mb-2 text-xs text-muted-foreground">Releasing…</p>
        )}

        {conflicts && conflicts.length > 0 && (
          <div className="max-w-2xl mx-auto mb-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3.5 space-y-3">
            <div>
              <p className="text-sm font-medium text-amber-700 dark:text-amber-400">
                {conflicts.length === 1 ? '1 file needs' : `${conflicts.length} files need`} manual resolution
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                These couldn't be auto-merged (e.g. one side deleted a file the other modified). Pick which
                version should win for each, then confirm.
              </p>
            </div>

            <div className="max-h-[45vh] overflow-y-auto space-y-2 pr-1 -mr-1">
              {conflicts.map(c => (
                <div key={c.path} className="rounded-md border border-border/50 bg-background/60 p-2.5 space-y-2">
                  <p className="text-xs font-mono font-medium">{c.path}</p>
                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    <label className={`flex flex-col gap-1 rounded border p-2 cursor-pointer transition-colors ${
                      conflictChoices[c.path] === 'ours' ? 'border-primary/60 bg-primary/8' : 'border-border/40 hover:bg-muted/30'
                    }`}>
                      <span className="flex items-center gap-1.5 font-medium">
                        <input
                          type="radio"
                          name={`conflict-${c.path}`}
                          checked={conflictChoices[c.path] === 'ours'}
                          onChange={() => setConflictChoices(cc => ({ ...cc, [c.path]: 'ours' }))}
                        />
                        Keep prod's version
                      </span>
                      <pre className="whitespace-pre-wrap break-all text-muted-foreground max-h-32 overflow-y-auto">
                        {c.ours ?? '(prod deleted this file)'}
                      </pre>
                    </label>
                    <label className={`flex flex-col gap-1 rounded border p-2 cursor-pointer transition-colors ${
                      conflictChoices[c.path] === 'theirs' ? 'border-primary/60 bg-primary/8' : 'border-border/40 hover:bg-muted/30'
                    }`}>
                      <span className="flex items-center gap-1.5 font-medium">
                        <input
                          type="radio"
                          name={`conflict-${c.path}`}
                          checked={conflictChoices[c.path] === 'theirs'}
                          onChange={() => setConflictChoices(cc => ({ ...cc, [c.path]: 'theirs' }))}
                        />
                        Keep {selectedStack?.name ?? 'source'}'s version
                      </span>
                      <pre className="whitespace-pre-wrap break-all text-muted-foreground max-h-32 overflow-y-auto">
                        {c.theirs ?? `(${selectedStack?.name ?? 'source'} deleted this file)`}
                      </pre>
                    </label>
                  </div>
                </div>
              ))}
            </div>

            <div className="flex gap-2">
              <Button size="sm" onClick={resolveConflicts} disabled={resolving} className="shadow-md shadow-primary/20">
                {resolving ? 'Resolving…' : 'Resolve & continue'}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => { setConflicts(null); setConflictChoices({}) }}
                disabled={resolving}
                className="border-border/60"
              >
                Cancel
              </Button>
            </div>
          </div>
        )}

        {releaseResult && (
          <div className="max-w-2xl mx-auto mb-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 space-y-1">
            <p className="text-xs font-medium text-emerald-600 dark:text-emerald-400">
              {releaseResult.pr_urls.length > 1 ? 'PRs opened' : 'PR opened'}
            </p>
            {releaseResult.pr_urls.map(url => (
              <a
                key={url}
                href={url}
                target="_blank"
                rel="noreferrer"
                className="block text-xs text-primary underline break-all"
              >
                {url}
              </a>
            ))}
          </div>
        )}

        {releaseError && (
          <p className="max-w-2xl mx-auto mb-2 text-xs text-destructive bg-destructive/10 border border-destructive/20 px-3 py-2 rounded-md">
            {releaseError}
          </p>
        )}

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
