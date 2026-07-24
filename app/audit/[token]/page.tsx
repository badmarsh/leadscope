import { notFound } from "next/navigation"
import { query } from "@/lib/db"
import { ShieldAlert, ShieldCheck, ServerCrash, ExternalLink, Eye, ArrowRight } from "lucide-react"

export default async function AuditPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params
  
  if (!token || token.length < 32) {
    notFound()
  }

  // Fetch audit data
  const rows: any[] = await query(
    `SELECT c.domain, c.company_name, e.score, e.rationale, e.evidence_data, c.audit_view_count
     FROM candidates c
     JOIN evaluations e ON e.candidate_id = c.id
     WHERE c.audit_token = $1
     ORDER BY e.created_at DESC LIMIT 1`,
    [token]
  )

  if (rows.length === 0) {
    notFound()
  }

  const row = rows[0]
  const evidence = typeof row.evidence_data === "string" 
    ? JSON.parse(row.evidence_data) 
    : (row.evidence_data ?? {})
    
  // Increment view count in background
  query(
    `UPDATE candidates SET audit_viewed_at = now(), audit_view_count = audit_view_count + 1 WHERE audit_token = $1`,
    [token]
  ).catch(console.error)

  const hasCriticalExposure = evidence.exposure_scan?.critical_found
  const proof = evidence.proof_data

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-200 font-sans p-6 md:p-12">
      <div className="max-w-4xl mx-auto space-y-8">
        
        {/* Header */}
        <header className="border-b border-neutral-800 pb-6 flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white tracking-tight flex items-center gap-3">
              <ShieldAlert className="w-8 h-8 text-red-500" />
              Security Audit: {row.domain}
            </h1>
            <p className="text-neutral-400 mt-2">
              Confidential report generated for {row.company_name || "Website Owner"}
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs text-neutral-500 bg-neutral-900 px-3 py-1.5 rounded-full border border-neutral-800">
            <Eye className="w-4 h-4" /> Views: {(row.audit_view_count ?? 0) + 1}
          </div>
        </header>

        {/* Undeniable Proof Section */}
        {proof && (
          <section className="bg-neutral-900 border border-red-900/50 rounded-xl overflow-hidden shadow-2xl shadow-red-900/10">
            <div className="bg-red-950/30 border-b border-red-900/30 px-6 py-4 flex items-center gap-3">
              <span className="flex h-3 w-3 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-500 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
              </span>
              <h2 className="text-lg font-semibold text-red-400 uppercase tracking-wider">Active Exploitation Detected</h2>
            </div>
            
            <div className="p-6 space-y-6">
              <p className="text-lg font-medium text-white">
                {proof.evidence_text}
              </p>
              
              {proof.proof_type === "google_serp_spam" && (
                <div className="bg-neutral-950 rounded-lg p-5 font-mono text-sm border border-neutral-800 relative overflow-hidden">
                  <div className="text-neutral-500 mb-2">Google Index Result:</div>
                  <div className="text-blue-400 text-lg hover:underline mb-1 cursor-pointer">{proof.example_title}</div>
                  <div className="text-green-500 text-xs mb-2">{proof.example_url}</div>
                  <div className="text-neutral-300 line-clamp-2">{proof.example_snippet || "..."}</div>
                </div>
              )}
              
              {proof.proof_type === "cloaked_redirect" && proof.network_trace && (
                <div className="bg-neutral-950 rounded-lg p-5 font-mono text-sm border border-neutral-800 overflow-x-auto">
                  <div className="text-neutral-500 mb-4">Network Redirect Trace (Mobile Visitor):</div>
                  <div className="space-y-3">
                    {proof.network_trace.map((step: string, idx: number) => (
                      <div key={idx} className="flex gap-4 items-start">
                        <span className="text-neutral-600 shrink-0">[{idx+1}]</span>
                        <span className={idx === proof.network_trace.length - 1 ? "text-red-400 font-bold" : "text-neutral-300"}>
                          {step}
                        </span>
                        {idx < proof.network_trace.length - 1 && (
                          <ArrowRight className="w-4 h-4 text-neutral-600 shrink-0 mt-0.5" />
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

        {/* Zero-Day Exposure Section */}
        {evidence.exposure_scan?.exposures?.length > 0 && (
          <section className="bg-neutral-900 border border-orange-900/50 rounded-xl overflow-hidden">
            <div className="bg-orange-950/30 border-b border-orange-900/30 px-6 py-4 flex items-center gap-3">
              <ServerCrash className="w-5 h-5 text-orange-400" />
              <h2 className="text-lg font-semibold text-orange-400 uppercase tracking-wider">Configuration Exposure</h2>
            </div>
            <div className="p-6">
              <p className="text-neutral-300 mb-4">
                We detected sensitive configuration files publicly accessible on your server. This allows attackers to extract database passwords and API keys.
              </p>
              
              <div className="space-y-4">
                {evidence.exposure_scan.exposures.map((exp: any, i: number) => (
                  <div key={i} className="bg-neutral-950 border border-neutral-800 rounded-lg p-4">
                    <div className="flex justify-between items-center mb-2">
                      <code className="text-orange-300">{exp.url}</code>
                      <span className="bg-orange-900/50 text-orange-300 text-xs px-2 py-1 rounded">
                        {exp.severity}
                      </span>
                    </div>
                    <pre className="text-neutral-500 text-xs overflow-hidden text-ellipsis whitespace-nowrap bg-neutral-900 p-2 rounded border border-neutral-800/50">
                      {exp.snippet}
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        {/* Call to Action */}
        <section className="bg-neutral-900 border border-neutral-800 rounded-xl p-8 text-center space-y-6">
          <ShieldCheck className="w-12 h-12 text-blue-500 mx-auto" />
          <div>
            <h2 className="text-2xl font-bold text-white mb-2">Professional Remediation Available</h2>
            <p className="text-neutral-400 max-w-xl mx-auto">
              Our automated systems detected these threats passively from the outside. The infection is likely deeper. Install our remediation plugin to clean the database, patch the vulnerability, and restore your SEO standing.
            </p>
          </div>
          <button className="bg-white text-black hover:bg-neutral-200 px-8 py-3 rounded-lg font-bold transition-colors">
            Download Remediation Plugin
          </button>
        </section>

      </div>
    </div>
  )
}
