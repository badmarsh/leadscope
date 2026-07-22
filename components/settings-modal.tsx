"use client"

import { useEffect, useRef, useState } from "react"
import { Settings, RotateCcw, X, Save } from "lucide-react"
import { useTranslation } from "@/lib/i18n"
import { cn } from "@/lib/utils"

interface SettingField {
  label: string
  description: string
  unit: string
  default: number
  min: number
  max: number
}

interface SettingsModalProps {
  open: boolean
  campaignDbId: number
  onClose: () => void
}

const FIELD_ORDER = [
  "search_cooldown_days",
  "keyword_min_hits",
  "min_score_for_review",
  "evaluator_batch_size",
  "max_enrichment_attempts",
  "enrichment_retry_hours",
  "stale_reopen_days",
]

export function SettingsModal({ open, campaignDbId, onClose }: SettingsModalProps) {
  const { t } = useTranslation()
  const [schema, setSchema] = useState<Record<string, SettingField>>({})
  const [values, setValues] = useState<Record<string, number>>({})
  const [brief, setBrief] = useState<string>("")
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const backdropRef = useRef<HTMLDivElement>(null)

  // Load settings when modal opens
  useEffect(() => {
    if (!open) return
    setLoading(true)
    setError(null)
    setSaved(false)
    fetch(`/api/campaigns/${campaignDbId}/settings`)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) throw new Error(data.error)
        setSchema(data.schema ?? {})
        setValues(data.settings ?? {})
        setBrief(data.business_brief ?? "")
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [open, campaignDbId])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [open, onClose])

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      const r = await fetch(`/api/campaigns/${campaignDbId}/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...values, business_brief: brief }),
      })
      const data = await r.json()
      if (!r.ok || data.error) throw new Error(data.error ?? "Save failed")
      setValues(data.settings)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error")
    } finally {
      setSaving(false)
    }
  }

  function handleReset() {
    const defaults: Record<string, number> = {}
    for (const [key, s] of Object.entries(schema)) defaults[key] = s.default
    setValues(defaults)
    setSaved(false)
  }

  if (!open) return null

  const fields = FIELD_ORDER.filter((k) => schema[k])

  return (
    // Backdrop
    <div
      ref={backdropRef}
      className="fixed inset-0 z-50 flex items-start justify-end bg-black/50 backdrop-blur-sm"
      onClick={(e) => { if (e.target === backdropRef.current) onClose() }}
      aria-modal="true"
      role="dialog"
      aria-label="Campaign Settings"
    >
      {/* Panel */}
      <div className="flex h-full w-full max-w-md flex-col bg-background shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-2">
            <Settings className="size-4 text-primary" />
            <h2 className="text-sm font-semibold text-foreground">Campaign Settings</h2>
          </div>
          <button
            onClick={onClose}
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            aria-label="Close settings"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {loading && (
            <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
              Loading settings…
            </div>
          )}
          {!loading && error && (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          )}
          {!loading && !error && (
            <div className="flex flex-col gap-6">
              <div>
                <div className="flex items-baseline justify-between gap-2">
                  <label htmlFor="setting-brief" className="text-sm font-medium text-foreground">
                    Business Brief
                  </label>
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  The core prompt detailing your business, offer, and target market. Used by all AI stages.
                </p>
                <textarea
                  id="setting-brief"
                  value={brief}
                  onChange={(e) => setBrief(e.target.value)}
                  rows={8}
                  className="mt-2 w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder="Describe your business and ideal customer profile..."
                />
              </div>

              <hr className="border-border" />

              {fields.map((key) => {
                const s = schema[key]
                const val = values[key] ?? s.default
                return (
                  <div key={key}>
                    <div className="flex items-baseline justify-between gap-2">
                      <label
                        htmlFor={`setting-${key}`}
                        className="text-sm font-medium text-foreground"
                      >
                        {s.label}
                      </label>
                      <span className="font-mono text-xs text-muted-foreground">{s.unit}</span>
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground">{s.description}</p>
                    <div className="mt-2 flex items-center gap-3">
                      <input
                        id={`setting-${key}`}
                        type="range"
                        min={s.min}
                        max={s.max}
                        value={val}
                        onChange={(e) =>
                          setValues((prev) => ({ ...prev, [key]: Number(e.target.value) }))
                        }
                        className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-muted accent-primary"
                      />
                      <input
                        type="number"
                        min={s.min}
                        max={s.max}
                        value={val}
                        onChange={(e) => {
                          const n = Number(e.target.value)
                          if (n >= s.min && n <= s.max)
                            setValues((prev) => ({ ...prev, [key]: n }))
                        }}
                        className="w-16 rounded-md border border-input bg-card px-2 py-1 text-center font-mono text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                      />
                    </div>
                    <div className="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground/60">
                      <span>{s.min}</span>
                      <span className="text-primary/60">default: {s.default}</span>
                      <span>{s.max}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border px-6 py-4">
          <button
            onClick={handleReset}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-foreground transition-colors disabled:opacity-50"
          >
            <RotateCcw className="size-3.5" />
            Reset to defaults
          </button>
          <button
            id="settings-save-btn"
            onClick={handleSave}
            disabled={saving || loading}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-4 py-1.5 text-sm font-medium transition-colors disabled:opacity-50",
              saved
                ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                : "bg-primary text-primary-foreground hover:bg-primary/90",
            )}
          >
            {saved ? (
              "Saved ✓"
            ) : (
              <>
                <Save className="size-3.5" />
                {saving ? "Saving…" : "Save"}
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
