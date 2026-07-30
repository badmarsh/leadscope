import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import { Dashboard } from "../dashboard"

vi.mock("@/lib/hooks/useLeads", () => ({
  useLeads: () => ({
    leads: [],
    stats: { newCount: 0, reviewCount: 0, totalCount: 0, pendingReview: 0, approved: 0, rejected: 0, totalCandidates: 0 },
    loading: false,
    error: null,
    refetch: vi.fn(),
  }),
}))

vi.mock("@/lib/hooks/useUsage", () => ({
  useUsage: () => ({
    spend: [],
    budgets: [],
    loading: false,
  }),
}))

describe("Dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal("localStorage", {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
    })
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/api/session")) {
        return { ok: true, json: async () => ({ loggedIn: true }) }
      }
      return { ok: true, json: async () => ({}) }
    }))
  })

  it("renders main dashboard header when authenticated", async () => {
    render(<Dashboard />)

    await waitFor(() => {
      expect(screen.getAllByText("WP Malware Remediation")[0]).toBeInTheDocument()
    })
  })
})
