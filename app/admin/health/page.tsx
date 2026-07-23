"use client"

import { useEffect, useState } from "react"

export default function AdminHealthDashboard() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch("/api/admin/health")
      .then(res => res.json())
      .then(json => {
        if (json.ok) setData(json.data)
        setLoading(false)
      })
      .catch(e => {
        console.error(e)
        setLoading(false)
      })
  }, [])

  if (loading) return <div className="p-8">Loading...</div>
  if (!data) return <div className="p-8">Failed to load health data</div>

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <div className="max-w-6xl mx-auto p-8">
        <h1 className="text-3xl font-bold mb-8">System Health Dashboard</h1>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white p-6 rounded-lg shadow">
            <h2 className="text-lg font-semibold text-gray-700">Cost (Today)</h2>
            <p className="text-3xl font-bold mt-2">${data.cost?.today?.toFixed(2)}</p>
          </div>
          <div className="bg-white p-6 rounded-lg shadow">
            <h2 className="text-lg font-semibold text-gray-700">Cost (Week)</h2>
            <p className="text-3xl font-bold mt-2">${data.cost?.week?.toFixed(2)}</p>
          </div>
          <div className="bg-white p-6 rounded-lg shadow border-l-4 border-red-500">
            <h2 className="text-lg font-semibold text-gray-700">Stuck Enrichments</h2>
            <p className="text-3xl font-bold mt-2">{data.stuckEnrichments}</p>
          </div>
        </div>

        <h2 className="text-2xl font-bold mb-4">Pipeline Volumes</h2>
        <div className="bg-white rounded-lg shadow overflow-hidden mb-8">
          <table className="w-full text-left">
            <thead className="bg-gray-100">
              <tr>
                <th className="p-4 font-semibold">Status</th>
                <th className="p-4 font-semibold">Count</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.statusCounts || {}).map(([status, count]) => (
                <tr key={status} className="border-t border-gray-100">
                  <td className="p-4">{status}</td>
                  <td className="p-4">{String(count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h2 className="text-2xl font-bold mb-4">Campaign Stage Statuses</h2>
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="w-full text-left">
            <thead className="bg-gray-100">
              <tr>
                <th className="p-4 font-semibold">Campaign</th>
                <th className="p-4 font-semibold">Stage 1</th>
                <th className="p-4 font-semibold">Stage 2</th>
                <th className="p-4 font-semibold">Stage 3</th>
                <th className="p-4 font-semibold">Stage 5</th>
              </tr>
            </thead>
            <tbody>
              {data.campaigns?.map((camp: any) => (
                <tr key={camp.id} className="border-t border-gray-100">
                  <td className="p-4 font-medium">{camp.slug}</td>
                  <td className="p-4">{camp.stage1_status}</td>
                  <td className="p-4">{camp.stage2_status}</td>
                  <td className="p-4">{camp.stage3_status}</td>
                  <td className="p-4">{camp.stage5_status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
