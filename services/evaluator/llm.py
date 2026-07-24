"""
llm.py — LLM client for the evaluator service.

Primary: OpenRouter (spec says evaluator uses OpenRouter).
Fallback: local Gemini proxy (same OpenAI-compat format).
"""
# HARDENING: This module's chat_json/chat_vision return 5-tuple:
# (parsed_obj, tokens_in, tokens_out, model_used, provider)
# Do NOT confuse with services/stages/llm.py which returns 3-tuple.
import base64
import json
import logging
import time as _time
import requests
from typing import Any, Optional

from openai import OpenAI, RateLimitError, APIStatusError

import config

logger = logging.getLogger(__name__)

import re

_or_client: Optional[OpenAI] = None
_proxy_client: Optional[OpenAI] = None
_consecutive_failures: int = 0


def _get_openrouter() -> OpenAI:
    global _or_client
    if _or_client is None:
        _or_client = OpenAI(
            api_key=config.OPENROUTER_API_KEY,
            base_url=config.OPENROUTER_BASE_URL,
            timeout=30.0,
        )
    return _or_client


def _get_proxy() -> OpenAI:
    global _proxy_client
    if _proxy_client is None:
        _proxy_client = OpenAI(
            api_key=config.GEMINI_PROXY_API_KEY,
            base_url=f"{config.GEMINI_PROXY_ENDPOINT.rstrip('/')}/v1",
            timeout=30.0,
        )
    return _proxy_client


def _call_with_retry(client: OpenAI, max_retries: int = 5, **kwargs):
    """
    Call client.chat.completions.create with exponential backoff retry.
    Raises the last exception if all retries are exhausted.
    NOTE: 403 (key limit exceeded) is NOT retried — it fails immediately
    so the caller can fall back to the local proxy without waiting 30s.
    """
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(**kwargs)
        except APIStatusError as exc:
            # 403 = key exhausted/forbidden — no point retrying, fail fast
            if exc.status_code == 403:
                logger.warning("LLM 403 key limit — failing fast (no retry): %s", exc)
                raise
            if attempt == max_retries - 1:
                logger.error("Max retries (%d) reached. Last error: %s", max_retries, exc)
                raise
            wait = 2 ** attempt
            logger.warning("LLM API error (attempt %d/%d): %s — retrying in %ds", attempt + 1, max_retries, exc, wait)
            _time.sleep(wait)
        except RateLimitError as exc:
            if attempt == max_retries - 1:
                logger.error("Max retries (%d) reached. Last error: %s", max_retries, exc)
                raise
            wait = 2 ** attempt
            logger.warning("LLM API error (attempt %d/%d): %s — retrying in %ds", attempt + 1, max_retries, exc, wait)
            _time.sleep(wait)


def _anchor_system_prompt(system_prompt: str, required_fields: list[str] | None) -> str:
    """Append required JSON schema reminder to END of system prompt for recency bias."""
    if not required_fields:
        return system_prompt
    fields_json = json.dumps({f: "..." for f in required_fields})
    anchor = (
        "\n\n"
        "=== MANDATORY JSON SCHEMA (READ LAST) ===\n"
        f"Your response MUST be a JSON object with ALL of these keys: {fields_json}\n"
        "Do NOT omit any key. Return ONLY raw JSON. No markdown fences.\n"
        "=== END MANDATORY JSON SCHEMA ==="
    )
    return system_prompt + anchor


def chat_json(
    user_prompt: str,
    system_prompt: str = "You are a helpful assistant. Return only valid JSON.",
    temperature: float = 0.1,
    max_tokens: int = 4096,
    model: Optional[str] = None,
    required_fields: list[str] | None = None,
) -> tuple[Any, int, int, str, str]:
    """
    Call LLM expecting JSON output.
    Returns (parsed_obj, tokens_in, tokens_out, model_used, provider).
    Tries OpenRouter first, falls back to local proxy.
    """
    global _consecutive_failures, _or_client, _proxy_client
    system_prompt = _anchor_system_prompt(system_prompt, required_fields)
    # Choose primary provider (prioritize local proxy if configured)
    if config.GEMINI_PROXY_ENDPOINT:
        client = _get_proxy()
        use_model = model or config.GEMINI_MODEL
        provider = "gemini"
    elif config.OPENROUTER_API_KEY:
        client = _get_openrouter()
        use_model = model or config.OPENROUTER_MODEL
        provider = "openrouter"
    else:
        client = _get_proxy()
        use_model = model or config.GEMINI_MODEL
        provider = "gemini"

    system = system_prompt + "\nReturn ONLY valid JSON. No markdown fences, no prose outside the JSON."

    try:
        resp = _call_with_retry(
            client,
            model=use_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except (RateLimitError, APIStatusError) as primary_exc:
        # OpenRouter key exhausted or forbidden — fall back to local Gemini proxy
        if provider == "openrouter" and config.GEMINI_PROXY_API_KEY:
            logger.warning(
                "OpenRouter failed (%s) — falling back to local Gemini proxy", primary_exc
            )
            client = _get_proxy()
            use_model = config.GEMINI_MODEL
            provider = "gemini"
            resp = _call_with_retry(
                client,
                model=use_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            raise

    text = resp.choices[0].message.content or ""
    ti = resp.usage.prompt_tokens if resp.usage else 0
    to = resp.usage.completion_tokens if resp.usage else 0

    # Strip markdown fences
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        parsed = json.loads(stripped)
        _consecutive_failures = 0
    except json.JSONDecodeError:
        # Regex fallback
        match = re.search(r'\{.*\}', stripped, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                _consecutive_failures = 0
            except json.JSONDecodeError:
                logger.warning("LLM returned non-JSON (regex fallback failed). First 200: %s", text[:200])
                parsed = {"_raw": text}
                _consecutive_failures += 1
        else:
            logger.warning("LLM returned non-JSON; returning raw. First 200: %s", text[:200])
            parsed = {"_raw": text}
            _consecutive_failures += 1
            
        if _consecutive_failures >= config.LLM_DEGRADATION_RESET_THRESHOLD:
            logger.error("Cognitive Continuity: Client context reset triggered due to consecutive failures")
            _or_client = None
            _proxy_client = None
            _consecutive_failures = 0

    if required_fields and parsed and "_raw" not in parsed:
        missing = [f for f in required_fields if f not in parsed]
        if missing:
            logger.warning("LLM response missing required fields %s — treating as partial failure", missing)
            _consecutive_failures += 1
            if _consecutive_failures >= config.LLM_DEGRADATION_RESET_THRESHOLD:
                logger.error("Cognitive Continuity: Client context reset triggered due to consecutive failures")
                _or_client = None
                _proxy_client = None
                _consecutive_failures = 0

    return parsed, ti, to, use_model, provider


def chat_vision(
    text_prompt: str,
    image_urls: list[str],
    system_prompt: str = "You are an expert image analyst.",
    temperature: float = 0.1,
    max_tokens: int = 4096,
    model: Optional[str] = None,
    required_fields: list[str] | None = None,
) -> tuple[Any, int, int, str, str]:
    """
    Call a vision-capable LLM with image URLs.
    Returns (parsed_json, tokens_in, tokens_out, model_used, provider).
    """
    global _consecutive_failures, _or_client, _proxy_client
    system_prompt = _anchor_system_prompt(system_prompt, required_fields)
    if config.GEMINI_PROXY_ENDPOINT:
        client = _get_proxy()
        use_model = model or config.SCORER_VISION_MODEL
        provider = "gemini"
    elif config.OPENROUTER_API_KEY:
        client = _get_openrouter()
        use_model = model or config.OPENROUTER_MODEL
        provider = "openrouter"
    else:
        client = _get_proxy()
        use_model = model or config.GEMINI_MODEL
        provider = "gemini"
    _vision_primary_provider = provider

    # Build content with images
    content = [{"type": "text", "text": text_prompt}]
    logger.debug("Downloading and converting %d image URLs to base64", len(image_urls))
    for url in image_urls[:10]:  # cap at 10 images
        try:
            # Try to fetch the image ourselves, handling redirects and preventing LLM fetching errors
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
            resp = requests.get(url, timeout=10, allow_redirects=True, headers=headers)
            if resp.status_code == 200 and len(resp.content) > 0:
                content_type = resp.headers.get('Content-Type', '').lower()
                # Strip parameters like charset and normalize jpg to jpeg
                content_type = content_type.split(';')[0].strip()
                if content_type == 'image/jpg':
                    content_type = 'image/jpeg'

                # Only process supported image formats (Gemini does not support SVG)
                allowed_types = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
                if content_type in allowed_types:
                    b64_data = base64.b64encode(resp.content).decode('utf-8')
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{content_type};base64,{b64_data}"}
                    })
                else:
                    logger.warning("URL did not return a supported image format (got %s): %s", content_type, url)
            else:
                logger.warning("Failed to fetch image %s: HTTP %s", url, resp.status_code)
        except Exception as e:
            logger.warning("Error fetching image %s: %s", url, e)

    # If no images could be fetched, just return a default empty JSON or let the LLM handle text-only
    if len(content) == 1:
        logger.warning("No valid images could be fetched for prompt, falling back to text-only.")

    system = system_prompt + "\nReturn ONLY valid JSON. No markdown fences."

    try:
        resp = _call_with_retry(
            client,
            model=use_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except (RateLimitError, APIStatusError) as primary_exc:
        if _vision_primary_provider == "openrouter" and config.GEMINI_PROXY_API_KEY:
            logger.warning(
                "OpenRouter vision failed (%s) — falling back to local Gemini proxy", primary_exc
            )
            client = _get_proxy()
            use_model = config.GEMINI_MODEL
            provider = "gemini"
            resp = _call_with_retry(
                client,
                model=use_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            raise
    text = resp.choices[0].message.content or ""
    ti = resp.usage.prompt_tokens if resp.usage else 0
    to = resp.usage.completion_tokens if resp.usage else 0

    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        parsed = json.loads(stripped)
        _consecutive_failures = 0
    except json.JSONDecodeError:
        # Regex fallback
        match = re.search(r'\{.*\}', stripped, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                _consecutive_failures = 0
            except json.JSONDecodeError:
                logger.warning("LLM vision returned non-JSON (regex fallback failed). First 200: %s", text[:200])
                parsed = {"_raw": text}
                _consecutive_failures += 1
        else:
            logger.warning("LLM vision returned non-JSON; returning raw. First 200: %s", text[:200])
            parsed = {"_raw": text}
            _consecutive_failures += 1

        if _consecutive_failures >= config.LLM_DEGRADATION_RESET_THRESHOLD:
            logger.error("Cognitive Continuity: Client context reset triggered due to consecutive failures")
            _or_client = None
            _proxy_client = None
            _consecutive_failures = 0

    if required_fields and parsed and "_raw" not in parsed:
        missing = [f for f in required_fields if f not in parsed]
        if missing:
            logger.warning("LLM response missing required fields %s — treating as partial failure", missing)
            _consecutive_failures += 1
            if _consecutive_failures >= config.LLM_DEGRADATION_RESET_THRESHOLD:
                logger.error("Cognitive Continuity: Client context reset triggered due to consecutive failures")
                _or_client = None
                _proxy_client = None
                _consecutive_failures = 0

    return parsed, ti, to, use_model, provider
