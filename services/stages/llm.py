"""
llm.py — Shared LLM client for the stages service.

The local Gemini proxy at GEMINI_PROXY_ENDPOINT speaks the OpenAI API
format (/v1/chat/completions) — it is NOT Gemini's native REST API.
We therefore use the openai SDK with a custom base_url pointing at the proxy.

Usage:
    from llm import chat_json, chat_text
    result = chat_json(prompt, system="You are...")   # returns parsed dict/list
    text   = chat_text(prompt)                        # returns raw string
"""
import json
import logging
from typing import Any, Optional

from openai import OpenAI

import config

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if config.OPENROUTER_API_KEY:
            _client = OpenAI(
                api_key=config.OPENROUTER_API_KEY,
                base_url="https://openrouter.ai/api/v1",
            )
        else:
            _client = OpenAI(
                api_key=config.GEMINI_PROXY_API_KEY,
                base_url=f"{config.GEMINI_PROXY_ENDPOINT.rstrip('/')}/v1",
            )
    return _client


def chat_text(
    user_prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    temperature: float = 0.2,
    max_tokens: int = 4096,
    model: Optional[str] = None,
) -> tuple[str, int, int]:
    """
    Call the LLM and return (text_response, tokens_in, tokens_out).
    Raises on API error.
    """
    client = _get_client()
    use_model = model or ("google/gemini-2.5-flash" if config.OPENROUTER_API_KEY else config.GEMINI_MODEL)
    resp = client.chat.completions.create(
        model=use_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = resp.choices[0].message.content or ""
    tokens_in  = resp.usage.prompt_tokens if resp.usage else 0
    tokens_out = resp.usage.completion_tokens if resp.usage else 0
    return text, tokens_in, tokens_out


def chat_json(
    user_prompt: str,
    system_prompt: str = "You are a helpful assistant. Return only valid JSON.",
    temperature: float = 0.1,
    max_tokens: int = 4096,
    model: Optional[str] = None,
) -> tuple[Any, int, int]:
    """
    Call the LLM expecting JSON output, parse it, and return (parsed_obj, tokens_in, tokens_out).
    Falls back to raw text in a dict if JSON parse fails.
    """
    system = system_prompt + "\nReturn ONLY valid JSON. No markdown fences, no prose outside the JSON."
    text, ti, to = chat_text(user_prompt, system_prompt=system, temperature=temperature, max_tokens=max_tokens, model=model)

    # Strip ```json ... ``` fences if the model added them anyway
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        return json.loads(stripped), ti, to
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON; returning raw text. First 200 chars: %s", text[:200])
        return {"_raw": text}, ti, to
