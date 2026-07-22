import { X, Webhook, ExternalLink, RefreshCw } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "@/lib/i18n"
import { cn } from "@/lib/utils"

interface N8nModalProps {
  isOpen: boolean
  onClose: () => void
}

interface Workflow {
  id: string
  name: string
  nodes: any[]
  connections: any
}

export function N8nModal({ isOpen, onClose }: N8nModalProps) {
  const { t } = useTranslation()
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    if (isOpen) window.addEventListener("keydown", handleEscape)
    return () => window.removeEventListener("keydown", handleEscape)
  }, [isOpen, onClose])

  useEffect(() => {
    if (!isOpen) return
    setLoading(true)
    fetch("/api/n8n/workflows")
      .then(res => res.json())
      .then(data => {
        if (data.workflows) {
          setWorkflows(data.workflows)
          if (data.workflows.length > 0) setActiveId(data.workflows[0].id)
        }
      })
      .finally(() => setLoading(false))
  }, [isOpen])

  if (!isOpen) return null

  const activeWorkflow = workflows.find(w => w.id === activeId)

  // Parse n8n nodes and connections into Mermaid.js format
  let mermaidBase64 = ""
  if (activeWorkflow) {
    let mermaid = "graph LR\n"
    const nodes = Array.isArray(activeWorkflow.nodes) ? activeWorkflow.nodes : JSON.parse(activeWorkflow.nodes || "[]")
    const connections = typeof activeWorkflow.connections === "string" ? JSON.parse(activeWorkflow.connections || "{}") : activeWorkflow.connections
    
    nodes.forEach((node: any) => {
      const cleanName = node.name.replace(/[^a-zA-Z0-9\s]/g, "").trim()
      const isTrigger = node.type.includes("Trigger")
      if (isTrigger) {
        mermaid += `  ${node.id}(["${cleanName}"]):::trigger\n`
      } else {
        mermaid += `  ${node.id}["${cleanName}"]\n`
      }
    })

    // Add edges
    for (const [sourceName, sourceConns] of Object.entries(connections)) {
      const sourceNode = nodes.find((n: any) => n.name === sourceName)
      if (!sourceNode) continue

      const outputs = (sourceConns as any).main || []
      outputs.forEach((outputList: any[]) => {
        outputList.forEach((conn: any) => {
          const targetNode = nodes.find((n: any) => n.name === conn.node)
          if (targetNode) {
            mermaid += `  ${sourceNode.id} --> ${targetNode.id}\n`
          }
        })
      })
    }

    mermaid += "\n  classDef trigger fill:#f97316,stroke:#ea580c,stroke-width:2px,color:white,font-weight:bold,rx:8px,ry:8px;"

    // Base64 encode for Mermaid.ink
    try {
      mermaidBase64 = btoa(unescape(encodeURIComponent(mermaid)))
    } catch (e) {
      console.error("Base64 encode error", e)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div 
        className="relative w-full max-w-4xl max-h-[85vh] overflow-hidden rounded-xl bg-card border border-border shadow-2xl flex flex-col"
        role="dialog"
      >
        <div className="flex items-center justify-between border-b border-border px-6 py-3 bg-muted/50 shrink-0">
          <div className="flex items-center gap-3">
            <div className="flex size-8 items-center justify-center rounded-md bg-orange-500/10 text-orange-500">
              <Webhook className="size-5" />
            </div>
            <h2 className="text-xl font-semibold">Live n8n Pipelines</h2>
            {workflows.length > 0 && (
              <select
                className="ml-4 bg-background border border-border rounded-md px-3 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500"
                value={activeId || ""}
                onChange={(e) => setActiveId(e.target.value)}
              >
                {workflows.map(w => (
                  <option key={w.id} value={w.id}>{w.name}</option>
                ))}
              </select>
            )}
          </div>
          <div className="flex items-center gap-3">
            <a 
              href="http://localhost:5678" 
              target="_blank" 
              rel="noopener noreferrer"
              onClick={onClose}
              className="inline-flex items-center justify-center px-4 py-1.5 text-xs font-medium transition-colors bg-orange-500 hover:bg-orange-600 text-white rounded shadow"
            >
              Open Native Editor
              <ExternalLink className="ml-2 size-3" />
            </a>
            <button
              onClick={onClose}
              className="rounded-full p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <X className="size-5" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto bg-slate-50 flex flex-col items-center justify-center p-8 relative">
          {loading ? (
            <div className="flex items-center gap-2 text-slate-400">
              <RefreshCw className="size-5 animate-spin" />
              Loading live diagrams...
            </div>
          ) : activeWorkflow && mermaidBase64 ? (
            <img 
              src={`https://mermaid.ink/svg/${mermaidBase64}`} 
              alt={`Pipeline diagram for ${activeWorkflow.name}`}
              className="max-w-full max-h-full object-contain" 
            />
          ) : (
            <div className="text-slate-400">No pipelines found.</div>
          )}
        </div>
      </div>
    </div>
  )
}
