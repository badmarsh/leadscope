"use client"

import { useEffect, useRef, useState } from "react"
import { Database, Plus, Trash2, Edit2, Save, X } from "lucide-react"
import { useTranslation } from "@/lib/i18n"
import { cn } from "@/lib/utils"

interface Signature {
  id: number
  snippet: string
  malware_family: string
  source_url: string | null
  confidence: "low" | "medium" | "high"
  added_at: string
}

interface KnowledgeBaseModalProps {
  open: boolean
  campaignDbId: number
  onClose: () => void
}

export function KnowledgeBaseModal({ open, campaignDbId, onClose }: KnowledgeBaseModalProps) {
  const { t } = useTranslation()
  const [signatures, setSignatures] = useState<Signature[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  // Add state
  const [adding, setAdding] = useState(false)
  const [newSig, setNewSig] = useState<Partial<Signature>>({ confidence: "medium", malware_family: "" })
  const [addLoading, setAddLoading] = useState(false)

  // Edit state
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editSig, setEditSig] = useState<Partial<Signature>>({})
  const [actionLoading, setActionLoading] = useState<number | null>(null)

  const backdropRef = useRef<HTMLDivElement>(null)

  const fetchSignatures = async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await fetch(`/api/campaigns/${campaignDbId}/kb`)
      const data = await r.json()
      if (!r.ok || data.error) throw new Error(data.error)
      setSignatures(data.signatures ?? [])
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) fetchSignatures()
  }, [open, campaignDbId])

  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [open, onClose])

  const handleAdd = async () => {
    if (!newSig.snippet) return
    setAddLoading(true)
    setError(null)
    try {
      const r = await fetch(`/api/campaigns/${campaignDbId}/kb`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newSig),
      })
      const data = await r.json()
      if (!r.ok || data.error) throw new Error(data.error)
      setSignatures([data.signature, ...signatures])
      setAdding(false)
      setNewSig({ confidence: "medium", malware_family: "" })
    } catch (e: any) {
      setError(e.message)
    } finally {
      setAddLoading(false)
    }
  }

  const handleUpdate = async (id: number) => {
    if (!editSig.snippet) return
    setActionLoading(id)
    setError(null)
    try {
      const r = await fetch(`/api/campaigns/${campaignDbId}/kb`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, ...editSig }),
      })
      const data = await r.json()
      if (!r.ok || data.error) throw new Error(data.error)
      setSignatures(signatures.map(s => s.id === id ? data.signature : s))
      setEditingId(null)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionLoading(null)
    }
  }

  const handleDelete = async (id: number) => {
    if (!window.confirm("Are you sure you want to delete this signature?")) return
    setActionLoading(id)
    setError(null)
    try {
      const r = await fetch(`/api/campaigns/${campaignDbId}/kb?sig_id=${id}`, {
        method: "DELETE",
      })
      const data = await r.json()
      if (!r.ok || data.error) throw new Error(data.error)
      setSignatures(signatures.filter(s => s.id !== id))
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionLoading(null)
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
            <Database className="size-5 text-primary" />
            <div>
              <h2 className="text-lg font-semibold text-foreground">Knowledge Base</h2>
              <p className="text-xs text-muted-foreground">Manage malware signatures and rules for this campaign</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          >
            <X className="size-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 relative">
          {error && (
            <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive flex justify-between items-center">
              <span>{error}</span>
              <button onClick={() => setError(null)}><X className="size-4" /></button>
            </div>
          )}

          <div className="mb-4 flex justify-between items-center">
            <h3 className="text-sm font-medium">Signatures ({signatures.length})</h3>
            <button
              onClick={() => setAdding(!adding)}
              className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              <Plus className="size-4" /> Add Signature
            </button>
          </div>

          <div className="rounded-md border border-border overflow-hidden">
            <table className="w-full text-left text-sm">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium w-1/3">Snippet (Code/Query)</th>
                  <th className="px-4 py-3 font-medium">Malware Family</th>
                  <th className="px-4 py-3 font-medium">Confidence</th>
                  <th className="px-4 py-3 font-medium w-24 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {adding && (
                  <tr className="bg-accent/30">
                    <td className="px-4 py-2">
                      <input 
                        type="text" 
                        placeholder="e.g. eval(base64_decode" 
                        className="w-full bg-background border border-input rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                        value={newSig.snippet || ""}
                        onChange={e => setNewSig({...newSig, snippet: e.target.value})}
                      />
                    </td>
                    <td className="px-4 py-2">
                      <input 
                        type="text" 
                        placeholder="e.g. Balada Injector" 
                        className="w-full bg-background border border-input rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                        value={newSig.malware_family || ""}
                        onChange={e => setNewSig({...newSig, malware_family: e.target.value})}
                      />
                    </td>
                    <td className="px-4 py-2">
                      <select 
                        className="w-full bg-background border border-input rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                        value={newSig.confidence || "medium"}
                        onChange={e => setNewSig({...newSig, confidence: e.target.value as any})}
                      >
                        <option value="low">Low</option>
                        <option value="medium">Medium</option>
                        <option value="high">High</option>
                      </select>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <div className="flex justify-end gap-2">
                        <button 
                          onClick={handleAdd}
                          disabled={!newSig.snippet || addLoading}
                          className="text-emerald-500 hover:text-emerald-600 disabled:opacity-50"
                        >
                          <Save className="size-4" />
                        </button>
                        <button 
                          onClick={() => { setAdding(false); setNewSig({ confidence: "medium", malware_family: "" }) }}
                          className="text-muted-foreground hover:text-foreground"
                        >
                          <X className="size-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                )}
                
                {loading && signatures.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">Loading signatures...</td>
                  </tr>
                ) : signatures.length === 0 && !adding ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">No signatures found. Add one to get started.</td>
                  </tr>
                ) : (
                  signatures.map(sig => {
                    const isEditing = editingId === sig.id;
                    const isLoading = actionLoading === sig.id;

                    return (
                      <tr key={sig.id} className="hover:bg-muted/20 group">
                        <td className="px-4 py-3">
                          {isEditing ? (
                            <input 
                              type="text" 
                              className="w-full bg-background border border-input rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                              value={editSig.snippet || ""}
                              onChange={e => setEditSig({...editSig, snippet: e.target.value})}
                            />
                          ) : (
                            <code className="bg-muted px-1.5 py-0.5 rounded text-[13px] text-primary">{sig.snippet}</code>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {isEditing ? (
                            <input 
                              type="text" 
                              className="w-full bg-background border border-input rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                              value={editSig.malware_family || ""}
                              onChange={e => setEditSig({...editSig, malware_family: e.target.value})}
                            />
                          ) : (
                            <span className="text-foreground">{sig.malware_family || "Unknown"}</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {isEditing ? (
                            <select 
                              className="w-full bg-background border border-input rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                              value={editSig.confidence || "medium"}
                              onChange={e => setEditSig({...editSig, confidence: e.target.value as any})}
                            >
                              <option value="low">Low</option>
                              <option value="medium">Medium</option>
                              <option value="high">High</option>
                            </select>
                          ) : (
                            <span className={cn(
                              "px-2 py-0.5 rounded-full text-xs font-medium",
                              sig.confidence === "high" ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400" :
                              sig.confidence === "low" ? "bg-amber-500/15 text-amber-700 dark:text-amber-400" :
                              "bg-blue-500/15 text-blue-700 dark:text-blue-400"
                            )}>
                              {sig.confidence}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right">
                          {isEditing ? (
                            <div className="flex justify-end gap-2">
                              <button 
                                onClick={() => handleUpdate(sig.id)}
                                disabled={!editSig.snippet || isLoading}
                                className="text-emerald-500 hover:text-emerald-600 disabled:opacity-50"
                              >
                                <Save className="size-4" />
                              </button>
                              <button 
                                onClick={() => setEditingId(null)}
                                className="text-muted-foreground hover:text-foreground"
                              >
                                <X className="size-4" />
                              </button>
                            </div>
                          ) : (
                            <div className="flex justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                              <button 
                                onClick={() => { setEditingId(sig.id); setEditSig(sig); }}
                                disabled={isLoading}
                                className="text-muted-foreground hover:text-primary transition-colors disabled:opacity-50"
                                aria-label="Edit"
                              >
                                <Edit2 className="size-4" />
                              </button>
                              <button 
                                onClick={() => handleDelete(sig.id)}
                                disabled={isLoading}
                                className="text-muted-foreground hover:text-destructive transition-colors disabled:opacity-50"
                                aria-label="Delete"
                              >
                                <Trash2 className="size-4" />
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
