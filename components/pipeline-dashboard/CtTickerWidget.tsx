"use client"

import React, { useState, useRef, useEffect } from "react"
import { Radio, Play, Square, Activity } from "lucide-react"

interface CtTickerWidgetProps {
  selectedCampaignId: string
  onFindingsUpdate?: () => void
}

export function CtTickerWidget({ selectedCampaignId, onFindingsUpdate }: CtTickerWidgetProps) {
  const [isRunning, setIsRunning] = useState(false)
  const [hitCount, setHitCount] = useState(0)
  const [lastHitDomain, setLastHitDomain] = useState<string | null>(null)
  const [isFlashing, setIsFlashing] = useState(false)
  const eventSourceRef = useRef<EventSource | null>(null)

  const stopStream = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setIsRunning(false)
  }

  useEffect(() => {
    return () => {
      stopStream()
    }
  }, [])

  const triggerHitFlash = () => {
    setIsFlashing(true)
    setTimeout(() => setIsFlashing(false), 800)
  }

  const startStream = () => {
    if (!selectedCampaignId || isRunning) return
    stopStream()

    setIsRunning(true)
    const params = new URLSearchParams({
      stage: "ct-monitor",
      campaignId: selectedCampaignId,
    })

    const es = new EventSource(`/api/seo-spam-hunter/run?${params.toString()}`)
    eventSourceRef.current = es

    es.onmessage = (event) => {
      const data = event.data
      if (data === "[DONE]") {
        stopStream()
        if (onFindingsUpdate) onFindingsUpdate()
        return
      }

      // Check if line indicates a CT match / hit
      // Format from stage0_ct.py: [HIT] match: ... domain: <domain>
      if (data.includes("[HIT]") || data.includes("match:")) {
        setHitCount((prev) => prev + 1)
        triggerHitFlash()

        // Extract domain from output line
        const domainMatch = data.match(/domain:\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/) || data.match(/([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/)
        if (domainMatch && domainMatch[1]) {
          setLastHitDomain(domainMatch[1])
        }
      }
    }

    es.onerror = () => {
      stopStream()
    }
  }

  return (
    <div
      className={`flex items-center justify-between gap-3 rounded-lg border px-3 py-1.5 transition-all text-xs ${
        isFlashing
          ? "border-emerald-500 bg-emerald-500/20 shadow-md shadow-emerald-500/20 ring-1 ring-emerald-500"
          : isRunning
          ? "border-violet-500/40 bg-violet-500/10"
          : "border-border bg-muted/40"
      }`}
    >
      <div className="flex items-center gap-2">
        <Radio
          className={`size-3.5 ${
            isRunning ? "text-violet-500 animate-pulse" : "text-muted-foreground"
          }`}
        />
        <span className="font-semibold text-foreground">CT Stream Monitor</span>
        <span
          className={`rounded-full px-2 py-0.5 font-mono text-[10px] font-bold ${
            isRunning
              ? "bg-violet-500/20 text-violet-600 dark:text-violet-400 border border-violet-500/30"
              : "bg-muted text-muted-foreground"
          }`}
        >
          {isRunning ? "STREAMING" : "IDLE"}
        </span>

        {hitCount > 0 && (
          <span className="font-mono font-bold text-emerald-600 dark:text-emerald-400">
            {hitCount} hits
          </span>
        )}

        {lastHitDomain && (
          <span className="hidden sm:inline text-muted-foreground truncate max-w-[180px]">
            Last hit: <code className="font-mono text-foreground font-semibold">{lastHitDomain}</code>
          </span>
        )}
      </div>

      <div className="flex items-center gap-1.5">
        {!isRunning ? (
          <button
            onClick={startStream}
            disabled={!selectedCampaignId}
            className="flex items-center gap-1 rounded bg-violet-600 px-2.5 py-1 text-[11px] font-semibold text-white shadow-sm hover:bg-violet-500 transition-colors disabled:opacity-50"
          >
            <Play className="size-3" />
            <span>Launch CT Stream</span>
          </button>
        ) : (
          <button
            onClick={stopStream}
            className="flex items-center gap-1 rounded bg-destructive/15 border border-destructive/30 px-2.5 py-1 text-[11px] font-semibold text-destructive hover:bg-destructive/25 transition-colors"
          >
            <Square className="size-3 fill-current" />
            <span>Stop</span>
          </button>
        )}
      </div>
    </div>
  )
}
