"use client"

import React, { useState, useEffect } from "react"
import { PipelineCampaign } from "./CampaignCard"
import { Edit3, Save, X, Plus, Hash, Tag, FileText, Globe, Clock, ExternalLink } from "lucide-react"

interface CampaignDetailDrawerProps {
  campaign: PipelineCampaign | null
  onSave: (campaignId: string, updatedFields: Partial<PipelineCampaign>) => Promise<void>
  onClose?: () => void
}

export function CampaignDetailDrawer({ campaign, onSave, onClose }: CampaignDetailDrawerProps) {
  const [name, setName] = useState("")
  const [notes, setNotes] = useState("")
  const [publicwwwQuery, setPublicwwwQuery] = useState("")
  const [urlscanPivot, setUrlscanPivot] = useState<string[]>([])
  const [newPivotTag, setNewPivotTag] = useState("")
  const [staleAfterDays, setStaleAfterDays] = useState<number>(30)
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    if (campaign) {
      setName(campaign.name || "")
      setNotes(campaign.notes || "")
      setPublicwwwQuery(campaign.publicwww_query || "")
      setUrlscanPivot(campaign.urlscan_pivot || [])
      setStaleAfterDays(campaign.stale_after_days || 30)
    }
  }, [campaign])

  if (!campaign) return null

  const isDirty =
    name !== (campaign.name || "") ||
    notes !== (campaign.notes || "") ||
    publicwwwQuery !== (campaign.publicwww_query || "") ||
    JSON.stringify(urlscanPivot) !== JSON.stringify(campaign.urlscan_pivot || []) ||
    staleAfterDays !== (campaign.stale_after_days || 30)

  const handleAddPivotTag = () => {
    if (!newPivotTag.trim()) return
    if (!urlscanPivot.includes(newPivotTag.trim())) {
      setUrlscanPivot([...urlscanPivot, newPivotTag.trim()])
    }
    setNewPivotTag("")
  }

  const handleRemovePivotTag = (index: number) => {
    setUrlscanPivot(urlscanPivot.filter((_, i) => i !== index))
  }

  const handleSave = async () => {
    if (!campaign) return
    setIsSaving(true)
    try {
      await onSave(campaign.id, {
        name,
        notes,
        publicwww_query: publicwwwQuery || null,
        urlscan_pivot: urlscanPivot,
        stale_after_days: Number(staleAfterDays),
      })
    } finally {
      setIsSaving(false)
    }
  }

  const handleCancel = () => {
    setName(campaign.name || "")
    setNotes(campaign.notes || "")
    setPublicwwwQuery(campaign.publicwww_query || "")
    setUrlscanPivot(campaign.urlscan_pivot || [])
    setStaleAfterDays(campaign.stale_after_days || 30)
  }

  return (
    <div className="rounded-xl border border-primary/30 bg-card p-5 shadow-sm space-y-4 transition-all">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
        <div className="flex items-center gap-2">
          <span className="rounded bg-primary/10 px-2 py-1 font-mono text-xs font-bold text-primary">
            {campaign.id}
          </span>
          <div className="flex items-center gap-1.5">
            <Edit3 className="size-3.5 text-muted-foreground" />
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="font-semibold text-sm bg-transparent border-b border-transparent hover:border-border focus:border-primary focus:outline-none px-1 text-foreground"
              placeholder="Campaign Name"
            />
          </div>
          <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-mono text-muted-foreground">
            {campaign.family}
          </span>
        </div>

        {campaign.source_url && (
          <a
            href={campaign.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-primary transition-colors"
          >
            <span>Research Reference</span>
            <ExternalLink className="size-3" />
          </a>
        )}
      </div>

      {/* Grid Controls */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
        {/* Left Column: Notes & Stale Days */}
        <div className="space-y-3">
          <div>
            <label className="flex items-center gap-1.5 font-semibold text-foreground mb-1">
              <FileText className="size-3.5 text-amber-500" />
              <span>Analyst Notes</span>
            </label>
            <textarea
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Enter notes or pivot instructions..."
              className="w-full rounded-lg border border-input bg-background p-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <div>
            <label className="flex items-center gap-1.5 font-semibold text-foreground mb-1">
              <Clock className="size-3.5 text-blue-500" />
              <span>Stale Threshold (Days)</span>
            </label>
            <input
              type="number"
              min={1}
              max={365}
              value={staleAfterDays}
              onChange={(e) => setStaleAfterDays(parseInt(e.target.value, 10) || 30)}
              className="w-32 rounded-lg border border-input bg-background px-3 py-1.5 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>

        {/* Right Column: PublicWWW & urlscan */}
        <div className="space-y-3">
          <div>
            <label className="flex items-center gap-1.5 font-semibold text-foreground mb-1">
              <Globe className="size-3.5 text-emerald-500" />
              <span>PublicWWW Query String</span>
            </label>
            <input
              type="text"
              value={publicwwwQuery}
              onChange={(e) => setPublicwwwQuery(e.target.value)}
              placeholder='e.g. "if(ndsw===undefined)" depth:all'
              className="w-full rounded-lg border border-input bg-background px-3 py-1.5 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <div>
            <label className="flex items-center gap-1.5 font-semibold text-foreground mb-1">
              <Tag className="size-3.5 text-purple-500" />
              <span>urlscan.io Pivots</span>
            </label>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {urlscanPivot.map((tag, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center gap-1 rounded bg-purple-500/15 border border-purple-500/30 px-2 py-0.5 font-mono text-[11px] text-purple-600 dark:text-purple-400"
                >
                  <span>{tag}</span>
                  <button
                    type="button"
                    onClick={() => handleRemovePivotTag(idx)}
                    className="hover:text-destructive text-muted-foreground ml-0.5"
                  >
                    <X className="size-3" />
                  </button>
                </span>
              ))}
            </div>

            <div className="flex gap-1.5">
              <input
                type="text"
                value={newPivotTag}
                onChange={(e) => setNewPivotTag(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault()
                    handleAddPivotTag()
                  }
                }}
                placeholder="Add urlscan pivot query..."
                className="flex-1 rounded-lg border border-input bg-background px-3 py-1 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <button
                type="button"
                onClick={handleAddPivotTag}
                className="px-2.5 py-1 bg-accent border border-border rounded-lg text-xs font-semibold text-foreground hover:bg-accent/80 transition-colors flex items-center gap-1"
              >
                <Plus className="size-3.5" />
                <span>Add</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Read-Only Hashes Section */}
      {campaign.virustotal_pivot?.hashes && campaign.virustotal_pivot.hashes.length > 0 && (
        <div className="border-t border-border pt-3 space-y-1.5">
          <span className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
            <Hash className="size-3.5 text-blue-500" />
            <span>VirusTotal IOC Hashes ({campaign.virustotal_pivot.hashes.length})</span>
          </span>
          <div className="flex flex-wrap gap-1.5 max-h-20 overflow-y-auto">
            {campaign.virustotal_pivot.hashes.map((hash, idx) => (
              <span
                key={idx}
                className="rounded bg-muted px-2 py-0.5 font-mono text-[10px] text-muted-foreground border border-border"
              >
                {hash}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Footer / Actions */}
      {isDirty && (
        <div className="flex items-center justify-end gap-2 border-t border-border pt-3">
          <button
            onClick={handleCancel}
            disabled={isSaving}
            className="px-3 py-1.5 rounded-lg border border-border bg-background text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-primary text-xs font-semibold text-primary-foreground hover:bg-primary/90 shadow transition-colors disabled:opacity-50"
          >
            <Save className="size-3.5" />
            <span>{isSaving ? "Saving..." : "Save Changes"}</span>
          </button>
        </div>
      )}
    </div>
  )
}
