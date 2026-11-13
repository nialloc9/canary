import { useState } from 'react'
import { DataClassificationOut } from '../api/client'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Textarea } from './ui/textarea'
import { FieldRow, NativeSelect } from './admin/shared'

export interface DraftColumn {
  name: string
  type?: string
  description?: string
  example?: string
}

export interface DraftTable {
  name: string
  description: string
  owner: string
  refresh_rate: string
  data_classification: string
  s3_prefix: string
  filter_suffix: string
  file_format_type: string
  columns: DraftColumn[]
  expected_size_bytes: number | null
  min_size_bytes: number | null
  max_size_bytes: number | null
  sample_files: Array<{ filename?: string; content: string }>
}

const FILE_FORMATS = ['JSON', 'CSV', 'PARQUET', 'AVRO', 'ORC', 'XML']

function blankTable(defaultClassification: string): DraftTable {
  return {
    name: '',
    description: '',
    owner: '',
    refresh_rate: '',
    data_classification: defaultClassification,
    s3_prefix: '',
    filter_suffix: '',
    file_format_type: 'JSON',
    columns: [],
    expected_size_bytes: null,
    min_size_bytes: null,
    max_size_bytes: null,
    sample_files: [],
  }
}

export function TableDraftForm({
  tables: initialTables,
  classifications,
  onConfirm,
  disabled = false,
}: {
  tables: DraftTable[]
  classifications: DataClassificationOut[]
  onConfirm: (tables: DraftTable[]) => void
  disabled?: boolean
}) {
  const defaultClassification = classifications.find(c => c.is_default)?.name ?? ''
  const [tables, setTables] = useState<DraftTable[]>(() =>
    initialTables.map(t => ({ ...t, data_classification: t.data_classification || defaultClassification }))
  )

  function updateTable(i: number, patch: Partial<DraftTable>) {
    setTables(ts => ts.map((t, idx) => (idx === i ? { ...t, ...patch } : t)))
  }

  function removeTable(i: number) {
    setTables(ts => ts.filter((_, idx) => idx !== i))
  }

  function addTable() {
    setTables(ts => [...ts, blankTable(defaultClassification)])
  }

  function updateColumn(i: number, ci: number, patch: Partial<DraftColumn>) {
    updateTable(i, {
      columns: tables[i].columns.map((c, idx) => (idx === ci ? { ...c, ...patch } : c)),
    })
  }

  function removeColumn(i: number, ci: number) {
    updateTable(i, { columns: tables[i].columns.filter((_, idx) => idx !== ci) })
  }

  function addColumn(i: number) {
    updateTable(i, { columns: [...tables[i].columns, { name: '', description: '' }] })
  }

  const canConfirm = !disabled && tables.length > 0 && tables.every(t => t.name.trim())

  return (
    <div className="mt-3 space-y-3">
      {tables.map((t, i) => (
        <div key={i} className="rounded-lg border border-border/50 bg-background/60 p-3.5 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <FieldRow label="Table name" id={`t-${i}-name`}>
              <Input
                id={`t-${i}-name`}
                value={t.name}
                disabled={disabled}
                onChange={e => updateTable(i, { name: e.target.value })}
                placeholder="RAW_EVENTS"
              />
            </FieldRow>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              disabled={disabled}
              onClick={() => removeTable(i)}
              aria-label="Remove table"
              className="mt-4 shrink-0 text-muted-foreground hover:text-destructive"
            >
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </Button>
          </div>

          <FieldRow label="Description" id={`t-${i}-desc`}>
            <Textarea
              id={`t-${i}-desc`}
              value={t.description}
              disabled={disabled}
              onChange={e => updateTable(i, { description: e.target.value })}
              rows={2}
              className="text-sm"
            />
          </FieldRow>

          <div className="grid grid-cols-2 gap-2.5">
            <FieldRow label="Owner" id={`t-${i}-owner`}>
              <Input
                id={`t-${i}-owner`}
                value={t.owner}
                disabled={disabled}
                onChange={e => updateTable(i, { owner: e.target.value })}
              />
            </FieldRow>
            <FieldRow label="Refresh rate" id={`t-${i}-refresh`}>
              <Input
                id={`t-${i}-refresh`}
                value={t.refresh_rate}
                disabled={disabled}
                onChange={e => updateTable(i, { refresh_rate: e.target.value })}
                placeholder="hourly"
              />
            </FieldRow>
            <FieldRow label="Data classification" id={`t-${i}-class`}>
              <NativeSelect
                id={`t-${i}-class`}
                value={t.data_classification}
                onChange={v => updateTable(i, { data_classification: v })}
              >
                {!t.data_classification && <option value="">(select one)</option>}
                {classifications.length === 0 && t.data_classification && (
                  <option value={t.data_classification}>{t.data_classification}</option>
                )}
                {classifications.map(c => (
                  <option key={c.id} value={c.name}>
                    {c.name}{c.is_default ? ' (default)' : ''}
                  </option>
                ))}
              </NativeSelect>
            </FieldRow>
            <FieldRow label="File format" id={`t-${i}-format`}>
              <NativeSelect
                id={`t-${i}-format`}
                value={t.file_format_type}
                onChange={v => updateTable(i, { file_format_type: v })}
              >
                {FILE_FORMATS.map(f => (
                  <option key={f} value={f}>{f}</option>
                ))}
              </NativeSelect>
            </FieldRow>
          </div>

          <FieldRow
            label="S3 prefix"
            id={`t-${i}-prefix`}
            hint="Where this table's files land, nested under the landing zone's own s3_stage_prefix."
          >
            <Input
              id={`t-${i}-prefix`}
              value={t.s3_prefix}
              disabled={disabled}
              onChange={e => updateTable(i, { s3_prefix: e.target.value })}
              placeholder={`${t.name || 'table'}/`}
            />
          </FieldRow>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Columns</p>
              <Button type="button" variant="ghost" size="xs" disabled={disabled} onClick={() => addColumn(i)}>
                + Add column
              </Button>
            </div>
            {t.columns.length === 0 ? (
              <p className="text-xs text-muted-foreground/60">No columns yet.</p>
            ) : (
              <div className="space-y-1.5">
                {t.columns.map((c, ci) => (
                  <div key={ci} className="flex gap-1.5 items-start">
                    <Input
                      value={c.name}
                      disabled={disabled}
                      onChange={e => updateColumn(i, ci, { name: e.target.value })}
                      placeholder="column_name"
                      className="w-36 shrink-0"
                    />
                    <Input
                      value={c.type ?? ''}
                      disabled={disabled}
                      onChange={e => updateColumn(i, ci, { type: e.target.value })}
                      placeholder="type"
                      className="w-24 shrink-0"
                    />
                    <Input
                      value={c.description ?? ''}
                      disabled={disabled}
                      onChange={e => updateColumn(i, ci, { description: e.target.value })}
                      placeholder="description"
                      className="flex-1 min-w-0"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      disabled={disabled}
                      onClick={() => removeColumn(i, ci)}
                      aria-label="Remove column"
                      className="shrink-0 text-muted-foreground hover:text-destructive"
                    >
                      <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                        <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                      </svg>
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {t.sample_files.length > 0 && (
            <p className="text-[11px] text-muted-foreground/60">
              {t.sample_files.length} sample file{t.sample_files.length > 1 ? 's' : ''} attached from the original message.
            </p>
          )}
        </div>
      ))}

      <div className="flex items-center gap-2">
        <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={addTable} className="border-border/60">
          + Add another table
        </Button>
        <Button
          type="button"
          size="sm"
          disabled={!canConfirm}
          onClick={() => onConfirm(tables)}
          className="shadow-md shadow-primary/20"
        >
          {disabled ? 'Confirmed' : 'Confirm & create landing zone'}
        </Button>
      </div>
    </div>
  )
}
