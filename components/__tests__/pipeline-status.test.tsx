import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, waitFor, fireEvent } from "@testing-library/react"
import { PipelineStatus } from "../pipeline-status"

describe("PipelineStatus", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal("fetch", vi.fn())
  })

  it("renders pipeline stage statuses correctly", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        status: {
          stage1_status: "idle",
          stage1_last_run: "2026-01-01T10:00:00Z",
          stage2_status: "running",
          stage2_last_run: null,
          stage3_status: "failed",
          stage3_last_run: null,
          stage5_status: "idle",
          stage5_last_run: null,
        },
      }),
    } as any)

    render(<PipelineStatus campaignId={1} />)

    await waitFor(() => {
      expect(screen.getByText("Pipeline Status")).toBeInTheDocument()
      expect(screen.getByText("Brief Analysis")).toBeInTheDocument()
      expect(screen.getByText("Candidate Finder")).toBeInTheDocument()
      expect(screen.getByText("Running now...")).toBeInTheDocument()
    })
  })

  it("handles start action on stage button click", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          status: {
            stage1_status: "idle",
            stage1_last_run: null,
            stage2_status: "idle",
            stage2_last_run: null,
            stage3_status: "idle",
            stage3_last_run: null,
            stage5_status: "idle",
            stage5_last_run: null,
          },
        }),
      } as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ok: true }),
      } as any)

    render(<PipelineStatus campaignId={1} />)

    await waitFor(() => {
      expect(screen.getByText("Pipeline Status")).toBeInTheDocument()
    })

    const startButtons = screen.getAllByTitle("Start")
    expect(startButtons.length).toBeGreaterThan(0)
    fireEvent.click(startButtons[0])

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith("/api/campaigns/1/pipeline", expect.anything())
    })
  })
})
