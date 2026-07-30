import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, waitFor, fireEvent } from "@testing-library/react"
import { SettingsModal } from "../settings-modal"

describe("SettingsModal", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal("fetch", vi.fn())
  })

  it("does not render when closed", () => {
    render(<SettingsModal open={false} campaignDbId={1} onClose={() => {}} />)
    expect(screen.queryByText("Campaign Settings")).toBeNull()
  })

  it("fetches and renders settings when open", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        schema: {
          search_cooldown_days: {
            label: "Search Cooldown",
            description: "Days before re-running",
            unit: "days",
            default: 30,
            min: 1,
            max: 365,
          },
        },
        settings: {
          search_cooldown_days: 15,
        },
        business_brief: "Our target audience is IT directors.",
      }),
    } as any)

    render(<SettingsModal open={true} campaignDbId={1} onClose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText("Campaign Settings")).toBeInTheDocument()
      expect(screen.getByText("Search Cooldown")).toBeInTheDocument()
      expect(screen.getByDisplayValue("Our target audience is IT directors.")).toBeInTheDocument()
    })
  })

  it("handles save action", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          schema: {
            search_cooldown_days: {
              label: "Search Cooldown",
              description: "Days before re-running",
              unit: "days",
              default: 30,
              min: 1,
              max: 365,
            },
          },
          settings: { search_cooldown_days: 30 },
          business_brief: "",
        }),
      } as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          settings: { search_cooldown_days: 30 },
        }),
      } as any)

    render(<SettingsModal open={true} campaignDbId={1} onClose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText("Campaign Settings")).toBeInTheDocument()
    })

    const saveBtn = screen.getByText("Save")
    fireEvent.click(saveBtn)

    await waitFor(() => {
      expect(screen.getByText("Saved ✓")).toBeInTheDocument()
    })
  })
})
