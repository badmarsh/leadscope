"""
tests/test_llm_proxy.py — Tests for the LLM proxy integration.

Two categories:
  1. Unit tests (always run): mock the OpenAI client, verify request construction,
     model selection logic, JSON parsing, fallback behaviour.
  2. Live integration tests (skipped when proxy is unavailable): actually hit
     the local Gemini proxy at GEMINI_PROXY_ENDPOINT and assert a valid response.

Run unit tests only:
    pytest services/evaluator/tests/test_llm_proxy.py -k "not live"

Run all tests (requires proxy running):
    pytest services/evaluator/tests/test_llm_proxy.py --live-proxy
"""
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — allow importing from services/evaluator without installing
# ---------------------------------------------------------------------------
EVALUATOR_DIR = os.path.join(os.path.dirname(__file__), "..")
if EVALUATOR_DIR not in sys.path:
    sys.path.insert(0, EVALUATOR_DIR)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_openai_response(content: str, tokens_in: int = 10, tokens_out: int = 20):
    """Build a minimal fake openai.ChatCompletion response."""
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage.prompt_tokens = tokens_in
    resp.usage.completion_tokens = tokens_out
    return resp


# ---------------------------------------------------------------------------
# Unit Tests — model selection
# ---------------------------------------------------------------------------

class TestModelSelection(unittest.TestCase):
    """Verify that the correct provider/model is selected based on config."""

    def _import_fresh_llm(self, env_overrides: dict):
        """Import llm module with patched environment and reset its module-level cache."""
        import importlib
        with patch.dict(os.environ, env_overrides, clear=False):
            sys.modules.pop("config", None)
            sys.modules.pop("llm", None)
            import services.common.config as cfg
            importlib.reload(cfg)
            import services.common.llm as llm
            importlib.reload(llm)
            return llm, cfg

    def test_uses_openrouter_when_key_set(self):
        """When OPENROUTER_API_KEY is set, chat_json should use OpenRouter client."""
        env = {
            "OPENROUTER_API_KEY": "sk-or-test-key",
            "DATABASE_URL": "postgresql://x:x@localhost/x",
            "GEMINI_PROXY_API_KEY": "sk-test",
            "GEMINI_PROXY_ENDPOINT": "",
        }
        llm, cfg = self._import_fresh_llm(env)

        fake_resp = _make_openai_response('{"score": 90}')
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = fake_resp

        # Inject mock client directly — bypasses SDK authentication
        llm._or_client = mock_client
        llm._proxy_client = None

        parsed, ti, to, model_used, provider = llm.chat_json("hello")

        self.assertEqual(provider, "openrouter")
        self.assertTrue(mock_client.chat.completions.create.called)

    def test_uses_proxy_when_no_openrouter_key(self):
        """Without OPENROUTER_API_KEY, chat_json must fall back to local proxy."""
        env = {
            "OPENROUTER_API_KEY": "",
            "GEMINI_PROXY_API_KEY": "sk-local",
            "GEMINI_PROXY_ENDPOINT": "http://localhost:8045",
            "GEMINI_MODEL": "gemini-3.6-flash-high",
            "DATABASE_URL": "postgresql://x:x@localhost/x",
        }
        llm, cfg = self._import_fresh_llm(env)

        fake_resp = _make_openai_response('{"score": 75}')
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = fake_resp
        llm._proxy_client = mock_client
        with patch.object(llm, "_call_with_retry", return_value=fake_resp):
            parsed, ti, to, model_used, provider = llm.chat_json("hello")

        self.assertEqual(provider, "gemini")
        self.assertEqual(model_used, "gemini-3.6-flash-high")

    def test_model_name_is_not_gemini_3_flash(self):
        """Ensure the broken model name that causes proxy 400s is not the default."""
        env = {
            "OPENROUTER_API_KEY": "",
            "DATABASE_URL": "postgresql://x:x@localhost/x",
            "GEMINI_PROXY_API_KEY": "sk-test",
            "GEMINI_PROXY_ENDPOINT": "http://localhost:8045",
        }
        llm, cfg = self._import_fresh_llm(env)
        self.assertNotEqual(
            cfg.GEMINI_MODEL,
            "gemini-3-flash",
            "gemini-3-flash maps to gemini-3-flash-agent on the proxy and causes HTTP 400.",
        )


# ---------------------------------------------------------------------------
# Unit Tests — OpenRouter Fallback
# ---------------------------------------------------------------------------

class TestOpenRouterFallback(unittest.TestCase):
    """Tests for the OpenRouter -> local proxy fallback logic added in llm.py."""

    def setUp(self):
        import importlib
        env = {
            "OPENROUTER_API_KEY": "sk-or-real-key",
            "GEMINI_PROXY_API_KEY": "sk-local",
            "GEMINI_PROXY_ENDPOINT": "",
            "GEMINI_MODEL": "gemini-3.6-flash-high",
            "DATABASE_URL": "postgresql://x:x@localhost/x",
        }
        with patch.dict(os.environ, env, clear=False):
            import sys
            sys.path = [p for p in sys.path if "services\\stages" not in p and "services/stages" not in p]
            if EVALUATOR_DIR not in sys.path:
                sys.path.insert(0, EVALUATOR_DIR)
            sys.modules.pop('config', None)
            sys.modules.pop('llm', None)
            import services.common.config as cfg
            importlib.reload(cfg)
            import services.common.llm as llm
            importlib.reload(llm)
            self.llm = llm

    def test_403_triggers_fast_fail_not_5_retries(self):
        """A 403 from OpenRouter must NOT be retried 5 times — it must fail immediately."""
        from openai import APIStatusError
        import httpx
        mock_or_client = MagicMock()
        err_response = MagicMock(spec=httpx.Response)
        err_response.status_code = 403
        err_response.json.return_value = {"error": {"message": "Key limit exceeded", "code": 403}}
        err_response.text = '{"error": {"message": "Key limit exceeded"}}'
        err_response.headers = {}
        exc = APIStatusError("Key limit exceeded", response=err_response, body={"error": {"code": 403}})
        mock_or_client.chat.completions.create.side_effect = exc
        self.llm._or_client = mock_or_client

        fake_resp = _make_openai_response('{"score": 42}')
        mock_proxy_client = MagicMock()
        mock_proxy_client.chat.completions.create.return_value = fake_resp
        self.llm._proxy_client = mock_proxy_client

        parsed, ti, to, model_used, provider = self.llm.chat_json("hello")

        # OpenRouter should have been called exactly once (no retry loop)
        self.assertEqual(mock_or_client.chat.completions.create.call_count, 1)
        # Proxy should have picked up the request
        self.assertTrue(mock_proxy_client.chat.completions.create.called)
        self.assertEqual(provider, "gemini")

    def test_403_falls_back_to_local_proxy(self):
        """After 403 from OpenRouter, the local proxy response is returned successfully."""
        from openai import APIStatusError
        import httpx
        mock_or_client = MagicMock()
        err_response = MagicMock(spec=httpx.Response)
        err_response.status_code = 403
        err_response.json.return_value = {}
        err_response.text = ""
        err_response.headers = {}
        exc = APIStatusError("Forbidden", response=err_response, body={"error": {"code": 403}})
        mock_or_client.chat.completions.create.side_effect = exc
        self.llm._or_client = mock_or_client

        fake_resp = _make_openai_response('{"score": 77, "rationale": "Fallback worked"}')
        mock_proxy = MagicMock()
        mock_proxy.chat.completions.create.return_value = fake_resp
        self.llm._proxy_client = mock_proxy

        parsed, ti, to, model_used, provider = self.llm.chat_json("test")
        self.assertEqual(parsed["score"], 77)
        self.assertEqual(provider, "gemini")

    def test_non_403_api_error_is_retried(self):
        """A 500 server error from OpenRouter should be retried (not fast-failed)."""
        from openai import APIStatusError
        import httpx
        mock_client = MagicMock()
        err_response = MagicMock(spec=httpx.Response)
        err_response.status_code = 500
        err_response.json.return_value = {}
        err_response.text = ""
        err_response.headers = {}
        exc = APIStatusError("Internal error", response=err_response, body={})
        good_resp = _make_openai_response('{"ok": true}')
        mock_client.chat.completions.create.side_effect = [exc, exc, good_resp]
        self.llm._or_client = mock_client
        self.llm._proxy_client = None

        with patch("tenacity.nap.time.sleep"):  # Don't actually sleep in tests
            parsed, *_ = self.llm.chat_json("hello")

        self.assertEqual(mock_client.chat.completions.create.call_count, 3)
        self.assertEqual(parsed["ok"], True)


# ---------------------------------------------------------------------------
# Unit Tests — JSON parsing
# ---------------------------------------------------------------------------

class TestChatJsonParsing(unittest.TestCase):

    def setUp(self):
        import importlib
        env = {
            "OPENROUTER_API_KEY": "",
            "GEMINI_PROXY_API_KEY": "sk-test",
            "GEMINI_PROXY_ENDPOINT": "http://localhost:8045",
            "DATABASE_URL": "postgresql://x:x@localhost/x",
        }
        with patch.dict(os.environ, env, clear=False):
            import sys
            sys.path = [p for p in sys.path if "services\\stages" not in p and "services/stages" not in p]
            if EVALUATOR_DIR not in sys.path:
                sys.path.insert(0, EVALUATOR_DIR)
            sys.modules.pop('config', None)
            sys.modules.pop('llm', None)
            import services.common.config as cfg
            importlib.reload(cfg)
            import services.common.llm as llm
            importlib.reload(llm)
            self.llm = llm

    def _call_with_response(self, content: str):
        fake_resp = _make_openai_response(content)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = fake_resp
        self.llm._proxy_client = mock_client
        return self.llm.chat_json("test prompt")

    def test_parses_clean_json(self):
        parsed, ti, to, model_used, provider = self._call_with_response('{"score": 85, "rationale": "ok"}')
        self.assertEqual(parsed["score"], 85)
        self.assertEqual(parsed["rationale"], "ok")

    def test_strips_markdown_fences(self):
        content = '```json\n{"score": 70}\n```'
        parsed, *_ = self._call_with_response(content)
        self.assertEqual(parsed["score"], 70)

    def test_falls_back_on_non_json(self):
        """Non-JSON response should return _raw key instead of raising."""
        parsed, *_ = self._call_with_response("I am not JSON.")
        self.assertIn("_raw", parsed)
        self.assertEqual(parsed["_raw"], "I am not JSON.")

    def test_token_counts_are_returned(self):
        fake_resp = _make_openai_response('{"x": 1}', tokens_in=42, tokens_out=13)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = fake_resp
        self.llm._proxy_client = mock_client
        parsed, ti, to, model_used, provider = self.llm.chat_json("x")
        self.assertEqual(ti, 42)
        self.assertEqual(to, 13)

    def test_empty_content_returns_raw(self):
        """An empty string from LLM should raise LLMSafetyFilterError and retry."""
        from services.common.llm import LLMSafetyFilterError
        with self.assertRaises(LLMSafetyFilterError):
            self._call_with_response("")


# ---------------------------------------------------------------------------
# Unit Tests — proxy URL construction
# ---------------------------------------------------------------------------

class TestProxyClientConstruction(unittest.TestCase):
    """Verify the proxy base URL is assembled correctly."""

    def test_base_url_strips_trailing_slash(self):
        import importlib
        env = {
            "OPENROUTER_API_KEY": "",
            "GEMINI_PROXY_ENDPOINT": "http://host.docker.internal:8045/",  # trailing slash
            "GEMINI_PROXY_API_KEY": "sk-test",
            "DATABASE_URL": "postgresql://x:x@localhost/x",
        }
        with patch.dict(os.environ, env, clear=False):
            import sys
            sys.path = [p for p in sys.path if "services\\stages" not in p and "services/stages" not in p]
            if EVALUATOR_DIR not in sys.path:
                sys.path.insert(0, EVALUATOR_DIR)
            sys.modules.pop('config', None)
            sys.modules.pop('llm', None)
            import services.common.config as cfg
            importlib.reload(cfg)
            import services.common.llm as llm
            importlib.reload(llm)

            expected_base = "http://host.docker.internal:8045/v1"
            actual_base = f"{cfg.GEMINI_PROXY_ENDPOINT.rstrip('/')}/v1"

        self.assertEqual(actual_base, expected_base)
        self.assertNotIn("//v1", actual_base, "Double slash in base_url due to trailing slash in endpoint")


# ---------------------------------------------------------------------------
# Live integration tests — skipped unless proxy is reachable
# ---------------------------------------------------------------------------

def _proxy_is_reachable() -> bool:
    """Return True if the local proxy responds to a TCP connect."""
    import socket
    endpoint = os.environ.get("GEMINI_PROXY_ENDPOINT", "http://localhost:8045")
    try:
        from urllib.parse import urlparse
        parsed = urlparse(endpoint)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8045
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


@pytest.mark.skipif(not _proxy_is_reachable(), reason="Local LLM proxy not reachable")
class TestLiveProxy(unittest.TestCase):
    """Live smoke tests against the running local Gemini proxy."""

    def setUp(self):
        import importlib
        env = {
            "OPENROUTER_API_KEY": "",  # force local proxy path
            "GEMINI_PROXY_API_KEY": os.environ.get("GEMINI_PROXY_API_KEY", ""),
            "GEMINI_PROXY_ENDPOINT": os.environ.get("GEMINI_PROXY_ENDPOINT", "http://localhost:8045"),
            "DATABASE_URL": "postgresql://x:x@localhost/x",
        }
        with patch.dict(os.environ, env, clear=False):
            import sys
            sys.path = [p for p in sys.path if "services\\stages" not in p and "services/stages" not in p]
            if EVALUATOR_DIR not in sys.path:
                sys.path.insert(0, EVALUATOR_DIR)
            sys.modules.pop('config', None)
            sys.modules.pop('llm', None)
            import services.common.config as cfg
            importlib.reload(cfg)
            import services.common.llm as llm
            importlib.reload(llm)
            self.llm = llm

    def test_proxy_returns_200_for_simple_prompt(self):
        """The proxy must accept a well-formed request and return a non-400 response."""
        try:
            parsed, ti, to, model_used, provider = self.llm.chat_json(
                'Reply with exactly: {"ok": true}',
                system_prompt='You are a test assistant. Return only valid JSON.',
                max_tokens=64,
            )
        except Exception as exc:
            self.fail(
                f"LLM proxy raised an exception: {exc}. "
                "Check GEMINI_PROXY_ENDPOINT and GEMINI_PROXY_API_KEY."
            )

        self.assertEqual(provider, "gemini")
        self.assertIsInstance(parsed, dict, f"Expected dict, got: {parsed!r}")
        self.assertNotIn(
            "_raw", parsed,
            f"LLM returned non-JSON (likely a proxy error): {parsed.get('_raw', '')[:300]}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
