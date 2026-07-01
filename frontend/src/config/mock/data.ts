import type { TokenResponse, UserOut, ConversationOut, OrgSettings, StackOut } from '../../api/client'

export const MOCK_TOKENS: TokenResponse = {
  access_token: 'mock-access-token',
  refresh_token: 'mock-refresh-token',
  token_type: 'bearer',
}

export const MOCK_USER: UserOut = {
  id: 'mock-user-1',
  email: 'demo@canary.ai',
  username: 'demo',
  is_active: true,
  created_at: new Date().toISOString(),
}

export let MOCK_PROFILE: UserOut = { ...MOCK_USER }

export const MOCK_ORG: OrgSettings = {
  name: 'Canary Demo Org',
  domain: 'canary.ai',
}

export const MOCK_STACKS: StackOut[] = [
  {
    id: 'mock-stack-main',
    name: 'main',
    branch: 'main',
    sort_order: 0,
    is_default: true,
    warehouse: {
      type: 'snowflake',
      organization_name: 'DEMO_ORG',
      account_name: 'demo-org.us-east-1',
      user: 'svc_canary',
      authenticator: 'SNOWFLAKE_JWT',
      private_key_b64: 'mock-key',
      database: 'ANALYTICS',
      schema_: 'PUBLIC',
      warehouse: 'COMPUTE_WH',
      role: 'SYSADMIN',
    },
    cloud: {
      provider: 'aws',
      access_key_id: 'AKIAIOSFODNN7EXAMPLE',
      secret_access_key: 'mock-secret',
      region: 'us-east-1',
    },
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
]

export const MOCK_CONVERSATIONS: ConversationOut[] = [
  {
    id: 'conv-1',
    title: 'Pipeline failure investigation',
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
  },
  {
    id: 'conv-2',
    title: 'Snowflake query optimisation',
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(),
  },
  {
    id: 'conv-3',
    title: 'Anomaly detection setup',
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 48).toISOString(),
  },
]

// Keyword-matched responses for the chat mock
const CHAT_RESPONSES: Array<{ keywords: string[]; reply: string }> = [
  {
    keywords: ['pipeline', 'failure', 'fail', 'error', 'broken'],
    reply:
      'I found 3 pipeline failures in the last 24 hours:\n\n• **ingest_events_v2** — failed at 03:14 UTC due to schema drift on the `user_id` column\n• **dbt_transform_hourly** — timed out after 30 min; upstream source table was locked\n• **snowflake_sync_prod** — authentication error; the service account token expired\n\nWould you like me to generate a remediation plan for any of these?',
  },
  {
    keywords: ['anomaly', 'anomalies', 'outlier', 'spike', 'unusual'],
    reply:
      'I detected 2 anomalies in the last 24 hours:\n\n• **events.page_view** — 340% spike at 18:00 UTC (likely a marketing campaign; confirm with the growth team)\n• **orders.checkout_started** — 60% drop at 22:30 UTC (correlates with a deploy at 22:28; possible regression)\n\nShall I create an alert rule for either of these patterns going forward?',
  },
  {
    keywords: ['snowflake', 'query', 'sql', 'optimis', 'slow', 'perf'],
    reply:
      "Here's a quick analysis of your query:\n\n```sql\nSELECT * FROM events WHERE DATE(created_at) = CURRENT_DATE\n```\n\n**Issues found:**\n1. `SELECT *` fetches all columns — specify only what you need\n2. `DATE(created_at)` prevents partition pruning — use a range predicate instead\n\n**Suggested rewrite:**\n```sql\nSELECT user_id, event_name, created_at\nFROM events\nWHERE created_at >= CURRENT_DATE\n  AND created_at < CURRENT_DATE + INTERVAL '1 day'\n```\n\nEstimated improvement: ~8× faster, 90% less bytes scanned.",
  },
  {
    keywords: ['schema', 'drift', 'column', 'table', 'field'],
    reply:
      'Schema drift detected on **3 tables** since last week:\n\n| Table | Change | Impact |\n|---|---|---|\n| `events` | `session_id` added (nullable) | Low |\n| `users` | `deleted_at` type changed `TIMESTAMP → DATE` | High |\n| `orders` | `metadata` column removed | Critical |\n\nThe `orders.metadata` removal will break 2 downstream dbt models. I can open a pull request to update them — want me to proceed?',
  },
  {
    keywords: ['cost', 'spend', 'credit', 'billing', 'expensive'],
    reply:
      'Snowflake spend this month: **$4,820** (↑ 23% vs last month)\n\nTop cost drivers:\n1. `TRANSFORM_XL` warehouse — 840 credits ($1,260) — 3 runaway queries identified\n2. Storage costs up 18% — 4.2 TB of uncompressed staging tables older than 30 days\n3. `ANALYST_M` warehouse idle 40% of the time during business hours\n\nQuick wins: drop stale staging tables (saves ~$340/mo), auto-suspend idle warehouses (saves ~$190/mo). Want a detailed breakdown?',
  },
  {
    keywords: ['data', 'quality', 'freshness', 'stale', 'missing'],
    reply:
      "Data quality summary as of now:\n\n✅ **Freshness** — 94% of monitored tables updated within SLA\n⚠️ **Completeness** — `users.email` is null on 2.3% of rows (up from 0.8% last week)\n❌ **Accuracy** — `orders.total_amount` doesn't match `order_items.sum` on 142 records today\n\nThe accuracy issue looks like a rounding bug introduced in the v2.4.1 ETL release. I've linked the relevant commit.",
  },
]

const FALLBACK_REPLY =
  "I'm your Canary AI assistant. I can help you investigate pipeline failures, detect anomalies, optimise queries, track schema drift, and monitor data quality. What would you like to explore?"

export function mockChatReply(message: string): string {
  const lower = message.toLowerCase()
  const match = CHAT_RESPONSES.find(r => r.keywords.some(k => lower.includes(k)))
  return match?.reply ?? FALLBACK_REPLY
}
