"""
llm.py — LLM client for the evaluator service.

Primary: OpenRouter (spec says evaluator uses OpenRouter).
Fallback: local Gemini proxy (same OpenAI-compat format).
"""
import base64
import json
import logging
import requests
from typing import Any, Optional

from openai import OpenAI

import config

logger = logging.getLogger(__name__)

_or_client: Optional[OpenAI] = None
_proxy_client: Optional[OpenAI] = None


def _get_openrouter() -> OpenAI:
    global _or_client
    if _or_client is None:
        _or_client = OpenAI(
            api_key=config.OPENROUTER_API_KEY,
            base_url=config.OPENROUTER_BASE_URL,
        )
    return _or_client


def _get_proxy() -> OpenAI:
    global _proxy_client
    if _proxy_client is None:
        _proxy_client = OpenAI(
            api_key=config.GEMINI_PROXY_API_KEY,
            base_url=f"{config.GEMINI_PROXY_ENDPOINT.rstrip('/')}/v1",
        )
    return _proxy_client


def chat_json(
    user_prompt: str,
    system_prompt: str = "You are a helpful assistant. Return only valid JSON.",
    temperature: float = 0.1,
    max_tokens: int = 4096,
    model: Optional[str] = None,
) -> tuple[Any, int, int, str, str]:
    """
    Call LLM expecting JSON output.
    Returns (parsed_obj, tokens_in, tokens_out, model_used, provider).
    Tries OpenRouter first, falls back to local proxy.
    """
    # Choose provider
    if config.OPENROUTER_API_KEY:
        client = _get_openrouter()
        use_model = model or config.OPENROUTER_MODEL
        provider = "openrouter"
    else:
        client = _get_proxy()
        use_model = model or config.GEMINI_MODEL
        provider = "gemini"

    system = system_prompt + "\nReturn ONLY valid JSON. No markdown fences, no prose outside the JSON."
    resp = client.chat.completions.create(
        model=use_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
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
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON; returning raw. First 200: %s", text[:200])
        parsed = {"_raw": text}

    return parsed, ti, to, use_model, provider


def chat_vision(
    text_prompt: str,
    image_urls: list[str],
    system_prompt: str = "You are an expert image analyst.",
    temperature: float = 0.1,
    max_tokens: int = 4096,
    model: Optional[str] = None,
) -> tuple[Any, int, int, str, str]:
    """
    Call a vision-capable LLM with image URLs.
    Returns (parsed_json, tokens_in, tokens_out, model_used, provider).
    """
    if config.OPENROUTER_API_KEY:
        client = _get_openrouter()
        use_model = model or config.VISION_MODEL
        provider = "openrouter"
    else:
        client = _get_proxy()
        use_model = model or config.GEMINI_MODEL
        provider = "gemini"

    # Build content with images
    content = [{"type": "text", "text": text_prompt}]
    print(f"DEBUG: Downloading and converting image URLs to Base64: {image_urls[:10]}", flush=True)
    logger.debug("Downloading and converting %d image URLs to base64", len(image_urls))
    for url in image_urls[:10]:  # cap at 10 images
        try:
            # Try to fetch the image ourselves, handling redirects and preventing LLM fetching errors
            resp = requests.get(url, timeout=10, allow_redirects=True)
            if resp.status_code == 200:
                content_type = resp.headers.get('Content-Type', '').lower()
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
    resp = client.chat.completions.create(
        model=use_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = resp.choices[0].message.content or ""
    ti = resp.usage.prompt_tokens if resp.usage else 0
    to = resp.usage.completion_tokens if resp.usage else 0

    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = {"_raw": text}

    return parsed, ti, to, use_model, provider
