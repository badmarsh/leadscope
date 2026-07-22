import { describe, it, expect, vi, beforeEach } from "vitest"

const mockFetch = vi.fn()
global.fetch = mockFetch

describe("chatText", () => {
  beforeEach(() => {
    mockFetch.mockReset()
    delete process.env.OPENROUTER_API_KEY
    process.env.GEMINI_PROXY_ENDPOINT = "http://localhost:8046"
    process.env.GEMINI_PROXY_API_KEY = "test-key"
    vi.resetModules()
  })

  it("routes to OpenRouter when OPENROUTER_API_KEY is set", async () => {
    process.env.OPENROUTER_API_KEY = "sk-or-test"
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        choices: [{ message: { content: "Hello" } }],
        usage: { prompt_tokens: 10, completion_tokens: 5 },
      }),
    })
    const { chatText } = await import("@/lib/llm")
    const result = await chatText("test prompt")
    expect(mockFetch).toHaveBeenCalledWith(
      "https://openrouter.ai/api/v1/chat/completions",
      expect.objectContaining({ method: "POST" }),
    )
    expect(result.text).toBe("Hello")
    expect(result.tokensIn).toBe(10)
    expect(result.tokensOut).toBe(5)
  })

  it("falls back to the local proxy when OPENROUTER_API_KEY is absent", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        choices: [{ message: { content: "Proxy response" } }],
        usage: { prompt_tokens: 20, completion_tokens: 10 },
      }),
    })
    const { chatText } = await import("@/lib/llm")
    await chatText("test prompt")
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8046/v1/chat/completions",
      expect.anything(),
    )
  })

  it("throws on a non-OK API response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 429,
      text: async () => "Rate limited",
    })
    const { chatText } = await import("@/lib/llm")
    await expect(chatText("test")).rejects.toThrow("429")
  })

  it("returns empty text when choices is missing", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ choices: [], usage: {} }),
    })
    const { chatText } = await import("@/lib/llm")
    const result = await chatText("test")
    expect(result.text).toBe("")
  })
})
