"use client"

import { useCallback, useEffect, useState } from "react"
import { PlayCircle, CheckCircle2, XCircle, Clock, Play, Square, Loader2 } from "lucide-react"

type StageStatus = "idle" | "running" | "failed"

type PipelineState = {
  stage1_status: StageStatus
  stage1_last_run: string | null
  stage2_status: StageStatus
  stage2_last_run: string | null
  stage3_status: StageStatus
  stage3_last_run: string | null
  stage5_status: StageStatus
  stage5_last_run: string | null
}

export function PipelineStatus({ campaignId }: { campaignId: number }) {
  const [state, setState] = useState<PipelineState | null>(null)

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`/api/campaigns/${campaignId}/status`)
      if (res.ok) {
        const data = await res.json()
        if (data.status) setState(data.status)
      }
    } catch (err) {
      // silently fail polling
    }
  }, [campaignId])

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, 15000) // Poll every 15s
    return () => clearInterval(interval)
  }, [fetchStatus])

  if (!state) return null

  return (
    <div className="flex flex-col gap-2 rounded-lg border bg-card p-4 text-card-foreground shadow-sm">
      <h3 className="text-sm font-medium leading-none">Pipeline Status</h3>
      <div className="mt-2 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatusItem campaignId={campaignId} stageKey="stage1" name="Brief Analysis" status={state.stage1_status} lastRun={state.stage1_last_run} onStatusChange={fetchStatus} />
        <StatusItem campaignId={campaignId} stageKey="stage2" name="Candidate Finder" status={state.stage2_status} lastRun={state.stage2_last_run} onStatusChange={fetchStatus} />
        <StatusItem campaignId={campaignId} stageKey="stage3" name="AI Evaluator" status={state.stage3_status} lastRun={state.stage3_last_run} onStatusChange={fetchStatus} />
        <StatusItem campaignId={campaignId} stageKey="stage5" name="Enrichment" status={state.stage5_status} lastRun={state.stage5_last_run} onStatusChange={fetchStatus} />
      </div>
    </div>
  )
}

function StatusItem({ campaignId, stageKey, name, status, lastRun, onStatusChange }: { campaignId: number; stageKey: string; name: string; status: StageStatus | "stopping"; lastRun: string | null, onStatusChange: () => void }) {
  const [loading, setLoading] = useState(false)

  const handleAction = async (action: "start" | "stop") => {
    setLoading(true)
    try {
      await fetch(`/api/campaigns/${campaignId}/pipeline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, stage: stageKey })
      })
      // Trigger a poll immediately for snappy UI updates (and to fix E2E flakiness)
      onStatusChange()
    } finally {
      setTimeout(() => setLoading(false), 2000) // fake loading state to prevent spam
    }
  }

  const isRunning = status === "running" || status === "stopping"
  const Icon = isRunning ? PlayCircle : status === "failed" ? XCircle : status === "idle" && lastRun ? CheckCircle2 : Clock
  const color = isRunning ? "text-blue-500 animate-pulse" : status === "failed" ? "text-red-500" : status === "idle" && lastRun ? "text-green-500" : "text-muted-foreground"
  
  return (
    <div className="flex items-center justify-between gap-2 p-2 rounded-md hover:bg-muted/50 group">
      <div className="flex items-center gap-2">
        <Icon className={`h-4 w-4 ${color}`} />
        <div className="flex flex-col">
          <span className="text-xs font-medium">{name}</span>
          <span className="text-[10px] text-muted-foreground">
            {status === "stopping" ? "Stopping..." : status === "running" ? "Running now..." : lastRun ? new Date(lastRun).toLocaleString(undefined, {
              month: "short", day: "numeric", hour: "numeric", minute: "2-digit"
            }) : "Not run yet"}
          </span>
        </div>
      </div>
      
      <div className="opacity-0 group-hover:opacity-100 transition-opacity">
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        ) : isRunning ? (
          <button onClick={() => handleAction("stop")} className="p-1 hover:bg-red-100 hover:text-red-600 rounded text-muted-foreground" title="Stop">
            <Square className="h-3 w-3 fill-current" />
          </button>
        ) : (
          <button onClick={() => handleAction("start")} className="p-1 hover:bg-blue-100 hover:text-blue-600 rounded text-muted-foreground" title="Start">
            <Play className="h-3 w-3 fill-current" />
          </button>
        )}
      </div>
    </div>
  )
}
