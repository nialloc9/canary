import { Label } from '../ui/label'

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

export function InfoTooltip({ text }: { text: string }) {
  return (
    <span className="relative inline-flex items-center group/tooltip normal-case tracking-normal font-normal">
      <svg
        width="12"
        height="12"
        viewBox="0 0 16 16"
        fill="none"
        className="text-muted-foreground/50 hover:text-muted-foreground cursor-help shrink-0"
      >
        <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.3" />
        <path d="M8 7.2v4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        <circle cx="8" cy="4.8" r="0.8" fill="currentColor" />
      </svg>
      <span className="pointer-events-none absolute left-1/2 -translate-x-1/2 bottom-full mb-1.5 w-max max-w-[240px] rounded-md bg-popover border border-border/60 px-2.5 py-1.5 text-[11px] leading-snug text-popover-foreground opacity-0 shadow-lg transition-opacity group-hover/tooltip:opacity-100 z-50">
        {text}
      </span>
    </span>
  )
}

export function StatusMessage({ status, savedText = 'Saved', errorText = 'Failed to save' }: {
  status: SaveStatus
  savedText?: string
  errorText?: string
}) {
  if (status === 'saved') return <span className="text-xs text-green-500">{savedText}</span>
  if (status === 'error') return <span className="text-xs text-destructive">{errorText}</span>
  return null
}

export function FieldRow({ id, label, hint, children }: { id?: string; label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-xs font-medium text-muted-foreground uppercase tracking-wide inline-flex items-center gap-1.5">
        {label}
        {hint && <InfoTooltip text={hint} />}
      </Label>
      {children}
    </div>
  )
}

export const AWS_REGIONS = [
  'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
  'eu-west-1', 'eu-west-2', 'eu-central-1',
  'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1',
  'ca-central-1', 'sa-east-1',
]

export function NativeSelect({ id, value, onChange, children, className = '' }: {
  id?: string
  value: string
  onChange: (v: string) => void
  children: React.ReactNode
  className?: string
}) {
  return (
    <select
      id={id}
      value={value}
      onChange={e => onChange(e.target.value)}
      className={`h-8 w-full min-w-0 rounded-lg border border-input bg-input/30 px-2.5 py-1 text-sm text-foreground outline-none transition-colors focus:border-ring focus:ring-3 focus:ring-ring/50 dark:bg-input/30 ${className}`}
    >
      {children}
    </select>
  )
}

export function ConnectionStatus({ status, message }: { status: 'idle' | 'testing' | 'ok' | 'fail'; message: string }) {
  if (status === 'idle') return null
  return (
    <div className={`flex items-center gap-2 text-xs px-3 py-2 rounded-md border ${
      status === 'testing' ? 'border-border/40 bg-muted/20 text-muted-foreground'
      : status === 'ok' ? 'border-green-500/30 bg-green-500/10 text-green-500'
      : 'border-destructive/30 bg-destructive/10 text-destructive'
    }`}>
      {status === 'testing' && <span className="size-3 rounded-full border-2 border-current border-t-transparent animate-spin" />}
      {status === 'ok' && <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.4" /><path d="M4.5 7l2 2 3-3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>}
      {status === 'fail' && <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.4" /><path d="M9 5L5 9M5 5l4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>}
      {status === 'testing' ? 'Testing connection…' : message}
    </div>
  )
}

export function Toggle({
  id,
  checked,
  onChange,
  label,
  hint,
}: {
  id: string
  checked: boolean
  onChange: (v: boolean) => void
  label: string
  hint?: string
}) {
  return (
    <label htmlFor={id} className="flex items-start gap-3 cursor-pointer group">
      <div className="relative mt-0.5 shrink-0">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={e => onChange(e.target.checked)}
          className="sr-only"
        />
        <div
          className={`w-8 h-4.5 rounded-full transition-colors ${checked ? 'bg-primary' : 'bg-muted border border-border/60'}`}
          style={{ height: '18px' }}
        >
          <div
            className={`absolute top-0.5 size-3.5 rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-[18px]' : 'translate-x-0.5'}`}
          />
        </div>
      </div>
      <div>
        <p className="text-sm font-medium leading-none">{label}</p>
        {hint && <p className="text-xs text-muted-foreground/70 mt-0.5">{hint}</p>}
      </div>
    </label>
  )
}

export function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full border ${
      ok
        ? 'bg-green-500/10 border-green-500/30 text-green-600 dark:text-green-400'
        : 'bg-muted/40 border-border/40 text-muted-foreground/60'
    }`}>
      <span className={`size-1.5 rounded-full ${ok ? 'bg-green-500' : 'bg-muted-foreground/30'}`} />
      {label}
    </span>
  )
}
