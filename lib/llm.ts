/**
 * lib/llm.ts — Shared LLM client for Next.js API routes.
 * Mirrors the Python llm.py pattern: uses OPENROUTER_API_KEY if set,
 * falls back to the local Gemini proxy at GEMINI_PROXY_ENDPOINT.
 */

export interface ChatResponse {
  text: string
  tokensIn: number
  tokensOut: number
}

export async function chatText(
  userPrompt: string,
  systemPrompt = "You are a helpful assistant.",
  options: { temperature?: number; maxTokens?: number; model?: string } = {},
): Promise<ChatResponse> {
  const { temperature = 0.2, maxTokens = 4096 } = options

  const orKey = process.env.OPENROUTER_API_KEY
  const proxyEndpoint = process.env.GEMINI_PROXY_ENDPOINT ?? "http://localhost:8046"
  const proxyKey = process.env.GEMINI_PROXY_API_KEY ?? "dummy"

  const apiKey = orKey || proxyKey
  const baseUrl = orKey
    ? "https://openrouter.ai/api/v1/chat/completions"
    : `${proxyEndpoint.replace(/\/$/, "")}/v1/chat/completions`
  const model =
    options.model ??
    (orKey ? "google/gemini-2.5-flash" : (process.env.GEMINI_MODEL ?? "gemini-2.5-flash"))

  const response = await fetch(baseUrl, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      ...(orKey
        ? { "HTTP-Referer": "https://jenex.ai", "X-Title": "Jenex AI" }
        : {}),
    },
    body: JSON.stringify({
      model,
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userPrompt },
      ],
      temperature,
      max_tokens: maxTokens,
    }),
  })

  if (!response.ok) {
    const errBody = await response.text()
    throw new Error(`LLM API error ${response.status}: ${errBody.slice(0, 200)}`)
  }

  const data = await response.json()
  return {
    text: data.choices?.[0]?.message?.content ?? "",
    tokensIn: data.usage?.prompt_tokens ?? 0,
    tokensOut: data.usage?.completion_tokens ?? 0,
  }
}
