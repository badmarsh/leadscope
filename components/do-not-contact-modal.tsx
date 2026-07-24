"use client"

import { useEffect, useRef, useState } from "react"
import { ShieldBan, Plus, Trash2, X } from "lucide-react"

interface Exclusion {
  id: number
  domain: string
  reason: string | null
  added_at: string
}

interface DoNotContactModalProps {
  open: boolean
  campaignDbId: number
  onClose: () => void
}

export function DoNotContactModal({ open, campaignDbId, onClose }: DoNotContactModalProps) {
  const [exclusions, setExclusions] = useState<Exclusion[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  const [adding, setAdding] = useState(false)
  const [newDomain, setNewDomain] = useState("")
  const [newReason, setNewReason] = useState("")
  const [addLoading, setAddLoading] = useState(false)

  const [deletingId, setDeletingId] = useState<number | null>(null)
  const backdropRef = useRef<HTMLDivElement>(null)

  const fetchExclusions = async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await fetch(`/api/campaigns/${campaignDbId}/dnc`)
      const data = await r.json()
      if (!r.ok || data.error) throw new Error(data.error)
      setExclusions(data.exclusions ?? [])
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) fetchExclusions()
  }, [open, campaignDbId])

  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [open, onClose])

  const handleAdd = async () => {
    if (!newDomain) return
    setAddLoading(true)
    setError(null)
    try {
      const r = await fetch(`/api/campaigns/${campaignDbId}/dnc`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain: newDomain, reason: newReason }),
      })
      const data = await r.json()
      if (!r.ok || data.error) throw new Error(data.error)
      setExclusions([data.exclusion, ...exclusions])
      setAdding(false)
      setNewDomain("")
      setNewReason("")
    } catch (e: any) {
      setError(e.message)
    } finally {
      setAddLoading(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!window.confirm("Remove this domain from the exclusion list?")) return
    setDeletingId(id)
    setError(null)
    try {
      const r = await fetch(`/api/campaigns/${campaignDbId}/dnc?id=${id}`, {
        method: "DELETE",
      })
      const data = await r.json()
      if (!r.ok || data.error) throw new Error(data.error)
      setExclusions(exclusions.filter(e => e.id !== id))
    } catch (e: any) {
      setError(e.message)
    } finally {
      setDeletingId(null)
    }
  }

  if (!open) return null

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      onClick={(e) => { if (e.target === backdropRef.current) onClose() }}
      aria-modal="true"
      role="dialog"
    >
      <div className="flex h-full max-h-[90vh] w-full max-w-5xl flex-col bg-background shadow-2xl rounded-xl overflow-hidden border border-border">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4 bg-muted/30">
          <div className="flex items-center gap-2">
            <ShieldBan className="size-5 text-destructive" />
            <div>
              <h2 className="text-lg font-semibold text-foreground">Exclusions List (Do Not Contact)</h2>
              <p className="text-xs text-muted-foreground">Manage domains that the AI agent should skip or filter out (e.g. security blogs, news sites)</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          >
            <X className="size-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {error && (
            <div className="mb-4 rounded-md bg-destructive/10 p-3 text-sm text-destructive border border-destructive/20">
              {error}
            </div>
          )}

          <div className="mb-6 flex items-center justify-between">
            <h3 className="text-sm font-medium">Excluded Domains</h3>
            {!adding && (
              <button
                onClick={() => setAdding(true)}
                className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                <Plus className="size-4" />
                Add Domain
              </button>
            )}
          </div>

          {adding && (
            <div className="mb-6 rounded-lg border border-border bg-muted/30 p-4 animate-in fade-in slide-in-from-top-4">
              <h4 className="mb-3 text-sm font-medium">Add New Exclusion</h4>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground">Domain (e.g. wordfence.com)</label>
                  <input
                    type="text"
                    value={newDomain}
                    onChange={(e) => setNewDomain(e.target.value)}
                    placeholder="example.com"
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                    autoFocus
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground">Reason (Optional)</label>
                  <input
                    type="text"
                    value={newReason}
                    onChange={(e) => setNewReason(e.target.value)}
                    placeholder="Security blog, do not scan..."
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                </div>
              </div>
              <div className="mt-4 flex justify-end gap-2">
                <button
                  onClick={() => { setAdding(false); setNewDomain(""); setNewReason("") }}
                  className="rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                  disabled={addLoading}
                >
                  Cancel
                </button>
                <button
                  onClick={handleAdd}
                  disabled={!newDomain || addLoading}
                  className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  {addLoading ? "Saving..." : "Save Domain"}
                </button>
              </div>
            </div>
          )}

          {loading ? (
            <div className="py-12 text-center text-sm text-muted-foreground animate-pulse">Loading exclusions...</div>
          ) : exclusions.length === 0 && !adding ? (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-12 text-center">
              <ShieldBan className="mb-3 size-8 text-muted-foreground/50" />
              <p className="text-sm font-medium text-muted-foreground">No excluded domains found.</p>
              <p className="mt-1 text-xs text-muted-foreground/70">Add domains here to block them from being scanned or contacted.</p>
            </div>
          ) : (
            <div className="rounded-lg border border-border overflow-hidden">
              <table className="w-full text-left text-sm">
                <thead className="bg-muted/50 text-xs text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">Domain</th>
                    <th className="px-4 py-3 font-medium">Reason</th>
                    <th className="px-4 py-3 font-medium">Added</th>
                    <th className="px-4 py-3 font-medium text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {exclusions.map((exc) => (
                    <tr key={exc.id} className="hover:bg-muted/30 transition-colors group">
                      <td className="px-4 py-3 font-medium text-foreground">{exc.domain}</td>
                      <td className="px-4 py-3 text-muted-foreground">{exc.reason || "—"}</td>
                      <td className="px-4 py-3 text-muted-foreground text-xs">{new Date(exc.added_at).toLocaleDateString()}</td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => handleDelete(exc.id)}
                          disabled={deletingId === exc.id}
                          className="p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive rounded-md transition-colors opacity-0 group-hover:opacity-100 disabled:opacity-50"
                          title="Delete Exclusion"
                        >
                          <Trash2 className="size-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
