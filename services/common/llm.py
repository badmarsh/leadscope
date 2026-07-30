"""
llm.py — Common LLM client for the leadscope pipeline.
"""
import base64
import json
import threading
import logging
import re
from typing import Any, Optional, Type, TypeVar
import requests

from openai import OpenAI, RateLimitError, APIStatusError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, retry_if_exception

import services.common.config as config

logger = logging.getLogger(__name__)

_or_client: Optional[OpenAI] = None
_proxy_client: Optional[OpenAI] = None
_consecutive_failures: int = 0
_failure_lock = threading.Lock()
_client_lock = threading.Lock()

def _get_openrouter() -> OpenAI:
    global _or_client
    with _client_lock:
        if _or_client is None:
            _or_client = OpenAI(
                api_key=config.OPENROUTER_API_KEY,
                base_url=config.OPENROUTER_BASE_URL,
                timeout=30.0,
            )
        return _or_client

def _get_proxy() -> OpenAI:
    global _proxy_client
    with _client_lock:
        if _proxy_client is None:
            _proxy_client = OpenAI(
                api_key=config.GEMINI_PROXY_API_KEY,
                base_url=f"{config.GEMINI_PROXY_ENDPOINT.rstrip('/')}/v1",
                timeout=30.0,
            )
        return _proxy_client

class LLMSafetyFilterError(Exception):
    """Raised when the LLM returns an empty response due to content safety filtering."""
    pass

def should_retry(retry_state):
    import tenacity
    if not retry_state.outcome.failed:
        return False
    exc = retry_state.outcome.exception()
    if isinstance(exc, APIStatusError) and exc.status_code == 403:
        return False
    return isinstance(exc, (RateLimitError, APIStatusError, LLMSafetyFilterError))

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    retry=retry_if_exception(lambda exc: isinstance(exc, (RateLimitError, APIStatusError, LLMSafetyFilterError)) and getattr(exc, "status_code", 0) != 403),
    reraise=True
)
def _call_with_retry(client: OpenAI, provider: str, **kwargs):
    """
    Call client.chat.completions.create with exponential backoff retry via tenacity.
    NOTE: 403 (key limit exceeded) is NOT retried — it fails immediately.
    """
    try:
        resp = client.chat.completions.create(**kwargs)
        if not resp or not resp.choices:
            raise LLMSafetyFilterError("LLM returned no choices (possible safety filter block)")
        
        finish_reason = getattr(resp.choices[0], "finish_reason", "unknown")
        text = resp.choices[0].message.content or ""
        
        if not text.strip():
            if finish_reason in ("safety", "recitation", "FILTERED", "block"):
                logger.warning("LLM response blocked by safety filter: finish_reason=%s", finish_reason)
                raise LLMSafetyFilterError(f"LLM content blocked by safety filter ({finish_reason})")
            else:
                raise LLMSafetyFilterError(f"LLM returned empty response (finish_reason={finish_reason})")
        return resp
    except APIStatusError as exc:
        if exc.status_code == 403:
            logger.warning("LLM 403 key limit — failing fast (no retry): %s", exc)
            raise
        raise

def _anchor_system_prompt(system_prompt: str, required_fields: list[str] | None) -> str:
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


def chat_text(
    user_prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    temperature: float = 0.2,
    max_tokens: int = 4096,
    model: Optional[str] = None,
) -> tuple[str, int, int]:
    """Call the LLM and return (text_response, tokens_in, tokens_out)."""
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

    resp = _call_with_retry(
        client,
        provider=provider,
        model=use_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    text = resp.choices[0].message.content or ""
    ti = resp.usage.prompt_tokens if resp.usage else 0
    to = resp.usage.completion_tokens if resp.usage else 0
    return text, ti, to


T = TypeVar("T")

def chat_json(
    user_prompt: str,
    system_prompt: str = "You are a helpful assistant. Return only valid JSON.",
    temperature: float = 0.1,
    max_tokens: int = 4096,
    model: Optional[str] = None,
    required_fields: list[str] | None = None,
    response_model: Optional[Type[T]] = None,
) -> tuple[Any, int, int, str, str]:
    """
    Call LLM expecting JSON output. Returns (parsed_obj, tokens_in, tokens_out, model_used, provider).
    If response_model (a Pydantic BaseModel) is provided, uses beta.chat.completions.parse for strict adherence.
    """
    global _consecutive_failures, _or_client, _proxy_client, _failure_lock
    
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

    # Strict Structured Output
    if response_model:
        system_prompt += "\n\nCRITICAL: Return ONLY raw JSON. Do NOT wrap your response in ```json ... ``` markdown fences!"
        try:
            resp = client.beta.chat.completions.parse(
                model=use_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_model,
            )
            parsed = resp.choices[0].message.parsed.model_dump() if resp.choices[0].message.parsed else {"_raw": "Parsed model was None"}
            ti = resp.usage.prompt_tokens if resp.usage else 0
            to = resp.usage.completion_tokens if resp.usage else 0
            with _failure_lock:
                _consecutive_failures = 0
            return parsed, ti, to, use_model, provider
        except Exception as e:
            logger.error("Structured output parsing failed: %s", e)
            with _failure_lock:
                _consecutive_failures += 1
                if _consecutive_failures >= config.LLM_DEGRADATION_RESET_THRESHOLD:
                    _or_client, _proxy_client, _consecutive_failures = None, None, 0
            return {"_raw": str(e)}, 0, 0, use_model, provider

    # Legacy JSON parsing
    system_prompt = _anchor_system_prompt(system_prompt, required_fields)
    system = system_prompt + "\nReturn ONLY valid JSON. No markdown fences, no prose outside the JSON."

    try:
        resp = _call_with_retry(
            client,
            provider=provider,
            model=use_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except (APIStatusError, RateLimitError) as primary_exc:
        status_code = getattr(primary_exc, "status_code", 429)
        if status_code in (401, 403, 429):
            if provider == "gemini" and config.OPENROUTER_API_KEY:
                logger.warning("Gemini proxy quota/rate-limited (%s) — falling back to OpenRouter", primary_exc)
                client = _get_openrouter()
                use_model = config.OPENROUTER_MODEL
                provider = "openrouter"
                resp = _call_with_retry(
                    client,
                    provider=provider,
                    model=use_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            elif provider == "openrouter" and config.GEMINI_PROXY_API_KEY:
                logger.warning("OpenRouter failed (%s) — falling back to local Gemini proxy", primary_exc)
                client = _get_proxy()
                use_model = config.GEMINI_MODEL
                provider = "gemini"
                resp = _call_with_retry(
                    client,
                    provider=provider,
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
        with _failure_lock:
            _consecutive_failures = 0
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', stripped, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                with _failure_lock:
                    _consecutive_failures = 0
            except json.JSONDecodeError:
                parsed = {"_raw": text}
                _consecutive_failures += 1
        else:
            parsed = {"_raw": text}
            _consecutive_failures += 1
            
        if _consecutive_failures >= config.LLM_DEGRADATION_RESET_THRESHOLD:
            logger.error("Cognitive Continuity: Client context reset triggered due to consecutive failures")
            _or_client, _proxy_client, _consecutive_failures = None, None, 0

    if required_fields and parsed and "_raw" not in parsed:
        missing = [f for f in required_fields if f not in parsed]
        if missing:
            logger.warning("LLM response missing required fields %s", missing)
            with _failure_lock:
                _consecutive_failures += 1
                if _consecutive_failures >= config.LLM_DEGRADATION_RESET_THRESHOLD:
                    _or_client, _proxy_client, _consecutive_failures = None, None, 0

    return parsed, ti, to, use_model, provider


def chat_vision(
    text_prompt: str,
    image_urls: list[str],
    system_prompt: str = "You are an expert image analyst.",
    temperature: float = 0.1,
    max_tokens: int = 4096,
    model: Optional[str] = None,
    required_fields: list[str] | None = None,
    response_model: Optional[Type[T]] = None,
) -> tuple[Any, int, int, str, str]:
    """Call a vision-capable LLM with image URLs."""
    global _consecutive_failures, _or_client, _proxy_client, _failure_lock
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

    content = [{"type": "text", "text": text_prompt}]
    for url in image_urls[:10]:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
            resp = requests.get(url, timeout=10, allow_redirects=True, headers=headers)
            if resp.status_code == 200:
                b64 = base64.b64encode(resp.content).decode("utf-8")
                mime = resp.headers.get("Content-Type", "image/jpeg")
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"}
                })
        except Exception as e:
            logger.warning("Failed to fetch image %s: %s", url, e)

    # Strict Structured Output
    if response_model:
        system_prompt += "\n\nCRITICAL: Return ONLY raw JSON. Do NOT wrap your response in ```json ... ``` markdown fences!"
        try:
            resp = client.beta.chat.completions.parse(
                model=use_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_model,
            )
            parsed = resp.choices[0].message.parsed.model_dump() if resp.choices[0].message.parsed else {"_raw": "Parsed model was None"}
            ti = resp.usage.prompt_tokens if resp.usage else 0
            to = resp.usage.completion_tokens if resp.usage else 0
            with _failure_lock:
                _consecutive_failures = 0
            return parsed, ti, to, use_model, provider
        except Exception as e:
            logger.error("Structured output parsing failed: %s", e)
            with _failure_lock:
                _consecutive_failures += 1
                if _consecutive_failures >= config.LLM_DEGRADATION_RESET_THRESHOLD:
                    _or_client, _proxy_client, _consecutive_failures = None, None, 0
            return {"_raw": str(e)}, 0, 0, use_model, provider

    system = system_prompt + "\nReturn ONLY valid JSON. No markdown fences, no prose outside the JSON."

    try:
        resp = _call_with_retry(
            client,
            provider=provider,
            model=use_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except APIStatusError as primary_exc:
        if provider == "openrouter" and config.GEMINI_PROXY_API_KEY and primary_exc.status_code in (401, 403, 429):
            client = _get_proxy()
            use_model = config.GEMINI_MODEL
            provider = "gemini"
            resp = _call_with_retry(
                client,
                provider=provider,
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
        with _failure_lock:
            _consecutive_failures = 0
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', stripped, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                with _failure_lock:
                    _consecutive_failures = 0
            except json.JSONDecodeError:
                parsed = {"_raw": text}
                _consecutive_failures += 1
        else:
            parsed = {"_raw": text}
            _consecutive_failures += 1
            
        with _failure_lock:
            if _consecutive_failures >= config.LLM_DEGRADATION_RESET_THRESHOLD:
                _or_client, _proxy_client, _consecutive_failures = None, None, 0

    if required_fields and parsed and "_raw" not in parsed:
        missing = [f for f in required_fields if f not in parsed]
        if missing:
            with _failure_lock:
                _consecutive_failures += 1
                if _consecutive_failures >= config.LLM_DEGRADATION_RESET_THRESHOLD:
                    _or_client, _proxy_client, _consecutive_failures = None, None, 0

    return parsed, ti, to, use_model, provider
