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
    """
    Returns LLM client. Priority:
      1. Local Gemini proxy (GEMINI_PROXY_ENDPOINT) — free, no key limits
      2. OpenRouter (OPENROUTER_API_KEY) — fallback only
    """
    global _client
    if _client is None:
        if config.GEMINI_PROXY_ENDPOINT and config.GEMINI_PROXY_API_KEY:
            logger.info("LLM client: local proxy at %s", config.GEMINI_PROXY_ENDPOINT)
            _client = OpenAI(
                api_key=config.GEMINI_PROXY_API_KEY,
                base_url=f"{config.GEMINI_PROXY_ENDPOINT.rstrip('/')}/v1",
            )
        elif config.OPENROUTER_API_KEY:
            logger.info("LLM client: OpenRouter (local proxy not configured)")
            _client = OpenAI(
                api_key=config.OPENROUTER_API_KEY,
                base_url="https://openrouter.ai/api/v1",
            )
        else:
            raise RuntimeError("No LLM backend configured: set GEMINI_PROXY_ENDPOINT or OPENROUTER_API_KEY")
    return _client


class LLMSafetyFilterError(Exception):
    """Raised when the LLM returns an empty response due to content safety filtering."""
    pass


def chat_text(
    user_prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    temperature: float = 0.2,
    max_tokens: int = 4096,
    model: Optional[str] = None,
) -> tuple[str, int, int]:
    """
    Call the LLM and return (text_response, tokens_in, tokens_out).
    Raises on API error or safety filter block.
    """
    client = _get_client()
    use_model = model or config.GEMINI_MODEL
    import time
    from openai import RateLimitError, APIStatusError

    max_retries = 5
    resp = None
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=use_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            break
        except (RateLimitError, APIStatusError) as e:
            if attempt == max_retries - 1:
                logger.error("Max retries reached for LLM call.")
                raise
            logger.warning(f"LLM API Error: {e}. Retrying {attempt + 1}/{max_retries}...")
            time.sleep(2 ** attempt)

    if not resp or not resp.choices:
        raise LLMSafetyFilterError("LLM returned no choices (possible safety filter block)")

    text = resp.choices[0].message.content or ""
    # STABILIZATION FIX: Detect empty content caused by Gemini safety blocks when scanning malware text
    if not text.strip() and resp.choices[0].finish_reason in ("safety", "recitation", "FILTERED"):
        logger.warning("LLM response blocked by safety filter: finish_reason=%s", resp.choices[0].finish_reason)
        raise LLMSafetyFilterError(f"LLM content blocked by safety filter ({resp.choices[0].finish_reason})")

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
    # HARDENING: This module's chat_json returns 3-tuple:
    # (parsed_obj, tokens_in, tokens_out)
    # Do NOT confuse with services/evaluator/llm.py which returns 5-tuple.
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
        logger.error(
            "LLM_JSON_PARSE_FAILURE model=%s tokens_in=%d tokens_out=%d preview=%r",
            model or config.GEMINI_MODEL,  # HARDENING: use_model not in scope here
            ti,
            to,
            text[:200],
        )
        # Callers MUST check for '_raw' key — this is an error condition,
        # not a silent degradation. Do not treat it as a valid empty response.
        return {"_raw": text}, ti, to
