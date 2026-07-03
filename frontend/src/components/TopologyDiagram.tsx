import { useState, useEffect } from 'react'
import { api, Topology, TopologyNode, TopologyNodeType, AccessKeys } from '../api/client'
import { Button } from './ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card'

function extractErrorMessage(err: unknown): string {
  const raw = err instanceof Error ? err.message : 'Failed to fetch access keys'
  try {
    const parsed = JSON.parse(raw)
    return typeof parsed?.detail === 'string' ? parsed.detail : raw
  } catch {
    return raw
  }
}

// Canonical left-to-right order for rendering a landing zone's pipeline —
// only nodes that were actually parsed out of the repo's terraform are shown.
const TOPOLOGY_TYPE_ORDER: TopologyNodeType[] = [
  's3_bucket',
  'storage_integration',
  'snowflake_database',
  'medallion_schemas',
  'snowpipe',
]

const TOPOLOGY_TYPE_ICON: Record<TopologyNodeType, string> = {
  s3_bucket: '🪣',
  storage_integration: '🔌',
  snowflake_database: '❄️',
  medallion_schemas: '📚',
  snowpipe: '⛽',
}

const TOPOLOGY_FIELD_ORDER: Record<TopologyNodeType, string[]> = {
  s3_bucket: ['name', 'data_classification', 'retention_policy'],
  storage_integration: ['s3_stage_prefix', 'file_format_type'],
  snowflake_database: ['name'],
  medallion_schemas: ['schema_names', 'data_classification'],
  snowpipe: ['snowflake_database', 'snowflake_schema', 'target_table'],
}

function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function AccessKeysButton({ stackId, landingZone }: { stackId: string; landingZone: string }) {
  const [keys, setKeys] = useState<AccessKeys | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function reveal() {
    setLoading(true)
    setError('')
    try {
      setKeys(await api.getLandingZoneAccessKeys(stackId, landingZone))
    } catch (e) {
      setError(extractErrorMessage(e))
    }
    setLoading(false)
  }

  if (keys) {
    return (
      <div className="mt-1.5 space-y-1 rounded border border-border/50 bg-background/60 p-1.5">
        <p className="text-[10px] text-muted-foreground truncate" title={keys.access_key_id}>
          Access key ID: <span className="font-mono">{keys.access_key_id}</span>
        </p>
        <p className="text-[10px] text-muted-foreground truncate" title={keys.secret_access_key}>
          Secret key: <span className="font-mono">{keys.secret_access_key}</span>
        </p>
        <button
          onClick={() => setKeys(null)}
          className="text-[10px] text-muted-foreground/60 underline underline-offset-2 hover:text-foreground"
        >
          Hide
        </button>
      </div>
    )
  }

  return (
    <div className="mt-1.5">
      <button
        onClick={reveal}
        disabled={loading}
        className="text-[10px] text-muted-foreground/60 underline underline-offset-2 hover:text-foreground disabled:opacity-50"
      >
        {loading ? 'Fetching…' : 'Show access keys'}
      </button>
      {error && <p className="text-[10px] text-destructive mt-1">{error}</p>}
    </div>
  )
}

function TopologyNodeCard({ node, stackId }: { node: TopologyNode; stackId: string }) {
  const fieldKeys = TOPOLOGY_FIELD_ORDER[node.type].filter(k => node.fields[k])
  const hasAccessKeys = node.type === 's3_bucket' && node.fields.create_access_keys === 'true'
  return (
    <div className="rounded-lg border border-border/50 bg-muted/10 p-2.5 min-w-[150px] shrink-0">
      <p className="text-xs font-medium flex items-center gap-1.5">
        <span>{TOPOLOGY_TYPE_ICON[node.type]}</span>
        {node.label}
      </p>
      {fieldKeys.map(k => (
        <p key={k} className="text-[10px] text-muted-foreground truncate mt-0.5" title={node.fields[k]}>
          {k}: <span className="font-mono">{node.fields[k]}</span>
        </p>
      ))}
      {hasAccessKeys && <AccessKeysButton stackId={stackId} landingZone={node.landing_zone} />}
    </div>
  )
}

function LandingZoneFlow({ landingZone, nodes, stackId }: { landingZone: string; nodes: TopologyNode[]; stackId: string }) {
  const ordered = TOPOLOGY_TYPE_ORDER.map(t => nodes.find(n => n.type === t)).filter((n): n is TopologyNode => !!n)
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-semibold text-muted-foreground/80">{landingZone}</p>
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {ordered.map((node, i) => (
          <div key={node.id} className="flex items-center gap-2 shrink-0">
            {i > 0 && <span className="text-muted-foreground/40 text-sm">→</span>}
            <TopologyNodeCard node={node} stackId={stackId} />
          </div>
        ))}
      </div>
    </div>
  )
}

export function TopologyDiagram({ stackId, bare = false }: { stackId: string; bare?: boolean }) {
  const [topology, setTopology] = useState<Topology | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function load(refresh: boolean) {
    setLoading(true)
    setError('')
    try {
      setTopology(await api.getStackTopology(stackId, refresh))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load deployed infrastructure')
    }
    setLoading(false)
  }

  useEffect(() => {
    load(false)
  }, [stackId])

  const groups = topology
    ? Object.entries(
        topology.nodes.reduce<Record<string, TopologyNode[]>>((acc, n) => {
          ;(acc[n.landing_zone] ??= []).push(n)
          return acc
        }, {})
      )
    : []

  const body = (
    <>
      {error && (
        <p className="text-xs text-destructive bg-destructive/10 border border-destructive/20 px-3 py-2 rounded-md">
          {error}
        </p>
      )}
      {!error && topology && !topology.connected && (
        <p className="text-xs text-muted-foreground">No GitHub repo connected yet.</p>
      )}
      {!error && topology?.error && (
        <p className="text-xs text-destructive bg-destructive/10 border border-destructive/20 px-3 py-2 rounded-md">
          Couldn't read from GitHub: {topology.error}
        </p>
      )}
      {!error && topology && topology.connected && !topology.error && groups.length === 0 && (
        <p className="text-xs text-muted-foreground">Nothing deployed to this stack yet.</p>
      )}
      {groups.map(([landingZone, nodes]) => (
        <LandingZoneFlow key={landingZone} landingZone={landingZone} nodes={nodes} stackId={stackId} />
      ))}
      {!error && topology && topology.skipped.length > 0 && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 space-y-1">
          <p className="text-xs text-amber-600 dark:text-amber-400">
            Found {topology.skipped.length} director{topology.skipped.length > 1 ? 'ies' : 'y'} that couldn't be
            recognized as infrastructure — not shown above:
          </p>
          {topology.skipped.map(s => (
            <p key={s.dir} className="text-[10px] text-amber-600/80 dark:text-amber-400/80 font-mono">
              {s.dir}: <span className="font-sans italic">{s.reason}</span>
            </p>
          ))}
        </div>
      )}
    </>
  )

  const refreshButton = (
    <div className="flex items-center gap-2">
      {topology && !loading && (
        <span className="text-[10px] text-muted-foreground/60">{timeAgo(topology.fetched_at)}</span>
      )}
      <Button size="sm" variant="outline" onClick={() => load(true)} disabled={loading} className="border-border/60">
        {loading ? 'Refreshing…' : 'Refresh'}
      </Button>
    </div>
  )

  if (bare) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold text-muted-foreground/80">Deployed Infrastructure</p>
          {refreshButton}
        </div>
        {body}
      </div>
    )
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle>Deployed Infrastructure</CardTitle>
          <CardDescription>Read directly from this stack's terraform in GitHub</CardDescription>
        </div>
        {refreshButton}
      </CardHeader>
      <CardContent className="space-y-4">{body}</CardContent>
    </Card>
  )
}
