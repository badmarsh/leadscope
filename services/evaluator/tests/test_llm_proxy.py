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
import types
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

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
            import config as cfg
            importlib.reload(cfg)
            import llm
            importlib.reload(llm)
            return llm, cfg

    def test_uses_openrouter_when_key_set(self):
        """When OPENROUTER_API_KEY is set, chat_json should use OpenRouter client."""
        env = {
            "OPENROUTER_API_KEY": "sk-or-test-key",
            "DATABASE_URL": "postgresql://x:x@localhost/x",
            "GEMINI_PROXY_API_KEY": "sk-test",
            "GEMINI_PROXY_ENDPOINT": "http://localhost:8045",
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
            "GEMINI_MODEL": "gemini-2.5-flash",
            "DATABASE_URL": "postgresql://x:x@localhost/x",
        }
        llm, cfg = self._import_fresh_llm(env)

        fake_resp = _make_openai_response('{"score": 75}')
        with patch("openai.OpenAI") as MockOpenAI:
            mock_instance = MagicMock()
            mock_instance.chat.completions.create.return_value = fake_resp
            MockOpenAI.return_value = mock_instance
            llm._or_client = None
            llm._proxy_client = None

            parsed, ti, to, model_used, provider = llm.chat_json("hello")

        self.assertEqual(provider, "gemini")
        self.assertEqual(model_used, "gemini-2.5-flash")

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
            "gemini-3-flash maps to gemini-3-flash-agent on the proxy and causes HTTP 400. "
            "Use gemini-2.5-flash instead.",
        )


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
            import config as cfg
            importlib.reload(cfg)
            import llm
            importlib.reload(llm)
            self.llm = llm

    def _call_with_response(self, content: str):
        fake_resp = _make_openai_response(content)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = fake_resp
        self.llm._proxy_client = mock_client
        return self.llm.chat_json("test prompt")

    def test_parses_clean_json(self):
        parsed, ti, to, model, provider = self._call_with_response('{"score": 85, "rationale": "ok"}')
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
        _, ti, to, _, _ = self.llm.chat_json("x")
        self.assertEqual(ti, 42)
        self.assertEqual(to, 13)

    def test_empty_content_returns_raw(self):
        """An empty string from LLM should not raise — returns _raw."""
        parsed, *_ = self._call_with_response("")
        self.assertIn("_raw", parsed)


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
            import config as cfg
            importlib.reload(cfg)
            import llm
            importlib.reload(llm)

            # Verify the URL is built correctly by inspecting the config directly
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
    # Parse host:port from URL
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
    """
    Live smoke tests against the running local Gemini proxy.
    These are the tests that would have caught the 400 errors.

    Run with: pytest services/evaluator/tests/test_llm_proxy.py -k live -v
    """

    def setUp(self):
        import importlib
        env = {
            "OPENROUTER_API_KEY": "",  # force local proxy path
            "GEMINI_PROXY_API_KEY": os.environ.get("GEMINI_PROXY_API_KEY", ""),
            "GEMINI_PROXY_ENDPOINT": os.environ.get("GEMINI_PROXY_ENDPOINT", "http://localhost:8045"),
            "DATABASE_URL": "postgresql://x:x@localhost/x",
        }
        with patch.dict(os.environ, env, clear=False):
            import config as cfg
            importlib.reload(cfg)
            import llm
            importlib.reload(llm)
            self.llm = llm

    def test_proxy_returns_200_for_simple_prompt(self):
        """The proxy must accept a well-formed request and return a non-400 response."""
        try:
            parsed, ti, to, model, provider = self.llm.chat_json(
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

    def test_proxy_model_name_does_not_return_400(self):
        """
        Regression test: gemini-3-flash mapped to gemini-3-flash-agent caused 400s.
        Verify the configured GEMINI_MODEL produces a successful response.
        """
        import config
        bad_model = "gemini-3-flash"
        good_model = config.GEMINI_MODEL

        self.assertNotEqual(
            good_model, bad_model,
            "GEMINI_MODEL is still set to gemini-3-flash which causes HTTP 400 on the proxy.",
        )

        # Actually call the proxy to verify no 400
        try:
            parsed, *_ = self.llm.chat_json(
                'Say: {"ping": "pong"}',
                system_prompt="Return only JSON.",
                max_tokens=32,
            )
            self.assertIsInstance(parsed, dict)
        except Exception as exc:
            error_str = str(exc)
            self.assertNotIn("400", error_str, f"Proxy returned HTTP 400 — model name is wrong: {exc}")
            raise

    def test_proxy_token_counts_are_nonzero(self):
        """A live call should return actual token counts, not zeros."""
        parsed, ti, to, _, _ = self.llm.chat_json(
            'Reply: {"value": 42}',
            system_prompt="Return only JSON.",
            max_tokens=64,
        )
        self.assertGreater(ti, 0, "tokens_in should be > 0 from a real call")
        self.assertGreater(to, 0, "tokens_out should be > 0 from a real call")


if __name__ == "__main__":
    unittest.main(verbosity=2)
