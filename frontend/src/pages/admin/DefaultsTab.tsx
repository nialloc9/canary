import { useState, useEffect } from 'react'
import { api, DataClassificationOut, ProjectOut } from '../../api/client'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { Textarea } from '../../components/ui/textarea'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card'
import { FieldRow, NativeSelect, StatusMessage, SaveStatus } from '../../components/admin/shared'

const RETENTION_POLICIES = ['30-day', '90-day', '1-year', '7-year', 'indefinite']

export function DefaultsTab() {
  const [classifications, setClassifications] = useState<DataClassificationOut[]>([])
  const [loading, setLoading] = useState(true)
  const [newName, setNewName] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState('')
  const [savingId, setSavingId] = useState<string | undefined>()

  const [project, setProject] = useState<ProjectOut | undefined>()
  const [retentionStatus, setRetentionStatus] = useState<SaveStatus>('idle')

  useEffect(() => {
    api.listDataClassifications().then(setClassifications).catch(() => {}).finally(() => setLoading(false))
    api.listProjects().then(ps => setProject(ps[0])).catch(() => {})
  }, [])

  async function addClassification() {
    const name = newName.trim()
    if (!name) return
    setAdding(true)
    setAddError('')
    try {
      const created = await api.createDataClassification({ name, description: newDescription.trim() || null })
      setClassifications(cs => [...cs, created])
      setNewName('')
      setNewDescription('')
    } catch (e) {
      setAddError(e instanceof Error ? e.message : 'Failed to add classification')
    }
    setAdding(false)
  }

  async function updateDescription(id: string, description: string) {
    setClassifications(cs => cs.map(c => (c.id === id ? { ...c, description } : c)))
  }

  async function saveDescription(id: string) {
    const record = classifications.find(c => c.id === id)
    if (!record) return
    setSavingId(id)
    try {
      const updated = await api.updateDataClassification(id, { description: record.description })
      setClassifications(cs => cs.map(c => (c.id === id ? updated : c)))
    } catch {}
    setSavingId(undefined)
  }

  async function makeDefault(id: string) {
    setClassifications(cs => cs.map(c => ({ ...c, is_default: c.id === id })))
    try {
      await api.updateDataClassification(id, { is_default: true })
    } catch {
      api.listDataClassifications().then(setClassifications).catch(() => {})
    }
  }

  async function removeClassification(id: string) {
    setClassifications(cs => cs.filter(c => c.id !== id))
    try {
      await api.deleteDataClassification(id)
    } catch {
      api.listDataClassifications().then(setClassifications).catch(() => {})
    }
  }

  async function setDefaultRetentionPolicy(value: string) {
    if (!project) return
    const policy = value || null
    setProject({ ...project, default_retention_policy: policy })
    setRetentionStatus('saving')
    try {
      const updated = await api.updateProjectSettings({ default_retention_policy: policy })
      setProject(updated)
      setRetentionStatus('saved')
      setTimeout(() => setRetentionStatus('idle'), 1500)
    } catch {
      setRetentionStatus('error')
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Data classifications</CardTitle>
          <CardDescription>
            Used by create_landing_zone (and the table-drafting flow) to tag each landing zone/table.
            The default is applied automatically when the agent isn't told otherwise — mark one as
            default, and give each a description so the agent can judge whether data looks more
            sensitive than the default covers (e.g. an email column showing up under "internal").
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : classifications.length === 0 ? (
            <p className="text-sm text-muted-foreground">No classifications configured yet — add one below.</p>
          ) : (
            <div className="space-y-2.5">
              {classifications.map(c => (
                <div key={c.id} className="rounded-lg border border-border/50 bg-muted/10 p-3 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{c.name}</span>
                      {c.is_default && (
                        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full border border-primary/30 bg-primary/10 text-primary">
                          Default
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1">
                      {!c.is_default && (
                        <Button variant="ghost" size="xs" onClick={() => makeDefault(c.id)}>
                          Make default
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon-xs"
                        onClick={() => removeClassification(c.id)}
                        aria-label={`Remove ${c.name}`}
                        className="text-muted-foreground hover:text-destructive"
                      >
                        <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                          <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                        </svg>
                      </Button>
                    </div>
                  </div>
                  <Textarea
                    value={c.description ?? ''}
                    onChange={e => updateDescription(c.id, e.target.value)}
                    onBlur={() => saveDescription(c.id)}
                    placeholder="What kind of data belongs in this classification?"
                    rows={2}
                    className="text-sm"
                  />
                  {savingId === c.id && <p className="text-[11px] text-muted-foreground">Saving…</p>}
                </div>
              ))}
            </div>
          )}

          <div className="rounded-lg border border-dashed border-border/60 p-3 space-y-2">
            <div className="flex gap-2">
              <Input
                value={newName}
                onChange={e => setNewName(e.target.value)}
                placeholder="Classification name (e.g. confidential)"
              />
              <Button onClick={addClassification} disabled={adding || !newName.trim()} className="shrink-0">
                {adding ? 'Adding…' : 'Add'}
              </Button>
            </div>
            <Textarea
              value={newDescription}
              onChange={e => setNewDescription(e.target.value)}
              placeholder="Description (optional, but helps the agent judge fit)"
              rows={2}
              className="text-sm"
            />
            {addError && <p className="text-xs text-destructive">{addError}</p>}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Retention policy default</CardTitle>
          <CardDescription>
            Applied by create_landing_zone whenever the user doesn't specify a retention policy. Leave
            unset to have the agent ask every time.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <FieldRow label="Default retention policy" id="default-retention">
            <div className="flex items-center gap-2">
              <NativeSelect
                id="default-retention"
                value={project?.default_retention_policy ?? ''}
                onChange={setDefaultRetentionPolicy}
                className="max-w-xs"
              >
                <option value="">(none — always ask)</option>
                {RETENTION_POLICIES.map(p => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </NativeSelect>
              <StatusMessage status={retentionStatus} />
            </div>
          </FieldRow>
        </CardContent>
      </Card>
    </div>
  )
}
