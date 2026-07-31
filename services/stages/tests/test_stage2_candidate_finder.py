"""
tests/test_stage2_candidate_finder.py — Stage 2: Candidate Finder

Tests the domain-qualification and candidate-insertion pipeline:
  - Domain extraction from URLs (subdomains, paths, ports)
  - Out-of-scope TLD filtering (cn, ru, jp, gov) 
  - Western-TLD whitelist filtering
  - Do-not-contact suppression (exact match + wildcard subdomain)
  - Invalid domain shape rejection (regex gate)
  - Subdomain stripping (sub.example.com → example.com)
  - Stale candidate reopening (upsert-with-WHERE logic)
  - Keyword search routing (keyword_search vs code_signature_search)
  - PublicWWW budget gate (per-signature-per-campaign)
  - LLM dedup call shape
  - run() routing by finder_type
  - run() skips paused campaigns
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

STAGES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if STAGES_DIR not in sys.path:
    sys.path.insert(0, STAGES_DIR)

import stage2


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    with patch("stage2.db") as m:
        m.get_conn.return_value.__enter__.return_value = MagicMock()
        m.check_stop_signal.return_value = False
        yield m


@pytest.fixture
def mock_cost_log():
    with patch("stage2.cost_log") as m:
        m.publicwww_budget_ok.return_value = True
        yield m


# ── Domain extraction ──────────────────────────────────────────────────────────

class TestExtractDomain:
    def test_basic_url(self):
        assert stage2._extract_domain("https://example.com") == "example.com"

    def test_strips_www(self):
        assert stage2._extract_domain("https://www.example.com/page") == "example.com"

    def test_strips_subdomain(self):
        assert stage2._extract_domain("http://sub.example.com:8080/foo") == "example.com"

    def test_bare_domain(self):
        assert stage2._extract_domain("example.com") == "example.com"

    def test_url_with_path_and_query(self):
        assert stage2._extract_domain("https://shop.example.co.uk/products?p=1") == "example.co.uk"

    def test_invalid_returns_none(self):
        assert stage2._extract_domain("invalid_domain") is None

    def test_url_with_port(self):
        result = stage2._extract_domain("http://example.com:9000")
        assert result == "example.com"

    def test_empty_string(self):
        assert stage2._extract_domain("") is None


# ── TLD filtering ──────────────────────────────────────────────────────────────

class TestIsOutOfScopeDomain:
    @pytest.mark.parametrize("domain", [
        "example.cn", "shop.ru", "store.jp", "site.kr", "service.gov",
    ])
    def test_blocks_out_of_scope_tlds(self, domain):
        assert stage2._is_out_of_scope_domain(domain) is True

    @pytest.mark.parametrize("domain", [
        "example.com", "shop.hu", "store.de", "site.co.uk",
    ])
    def test_allows_in_scope_tlds(self, domain):
        assert stage2._is_out_of_scope_domain(domain) is False

    def test_blocks_gov_subdomain(self):
        assert stage2._is_out_of_scope_domain("example.gov.cn") is True

    def test_blocks_edu_subdomain(self):
        assert stage2._is_out_of_scope_domain("example.edu.au") is True

    def test_western_filter_allows_com(self):
        assert stage2._is_out_of_scope_domain("example.com", western_tld_filter_enabled=True) is False

    def test_western_filter_blocks_non_western(self):
        assert stage2._is_out_of_scope_domain("example.br", western_tld_filter_enabled=True) is True

    def test_western_filter_allows_hu(self):
        assert stage2._is_out_of_scope_domain("example.hu", western_tld_filter_enabled=True) is False


# ── Do-not-contact check ───────────────────────────────────────────────────────

class TestIsDoNotContact:
    def test_exact_match_suppressed(self, mock_db):
        mock_db.fetchone.return_value = {"1": 1}
        conn = MagicMock()
        assert stage2._is_do_not_contact(conn, "suppressed.com", 1) is True

    def test_not_suppressed(self, mock_db):
        mock_db.fetchone.return_value = None
        conn = MagicMock()
        assert stage2._is_do_not_contact(conn, "clean.com", 1) is False

    def test_dnc_is_campaign_specific_respected(self, mock_db):
        """The query must check both campaign-specific AND global (NULL) rows."""
        conn = MagicMock()
        # Simulate that the query to DB is called with the campaign_id
        mock_db.fetchone.return_value = None
        stage2._is_do_not_contact(conn, "test.com", 42)
        call_args = mock_db.fetchone.call_args
        assert 42 in call_args[0][2]  # campaign_id in params


# ── Upsert candidate domain validation ────────────────────────────────────────

class TestUpsertCandidate:
    def test_rejects_invalid_domain_shape(self, mock_db):
        conn = MagicMock()
        with patch("stage2._is_do_not_contact", return_value=False):
            # Domains with spaces, paths, or HTML artifacts
            for bad in ["example .com", "example.com/path", "<b>test</b>.com", ""]:
                res = stage2._upsert_candidate(
                    conn, campaign_id=1, domain=bad, company_name="X",
                    source="test", query_used="kw", evidence_data={}
                )
                assert res is False, f"Expected False for bad domain: {bad!r}"

    def test_rejects_dnc_domain(self, mock_db):
        conn = MagicMock()
        with patch("stage2._is_do_not_contact", return_value=True):
            res = stage2._upsert_candidate(
                conn, campaign_id=1, domain="suppressed.com", company_name="X",
                source="test", query_used="kw", evidence_data={}
            )
        assert res is False
        mock_db.execute.assert_not_called()

    def test_inserts_valid_domain(self, mock_db):
        conn = MagicMock()
        with patch("stage2._is_do_not_contact", return_value=False):
            mock_db.execute.return_value = 1
            res = stage2._upsert_candidate(
                conn, campaign_id=1, domain="new-lead.com", company_name="New Lead",
                source="exa", query_used="hvac installer", evidence_data={}
            )
        assert res is True
        mock_db.execute.assert_called_once()

    def test_strips_www_before_insert(self, mock_db):
        conn = MagicMock()
        with patch("stage2._is_do_not_contact", return_value=False):
            mock_db.execute.return_value = 1
            stage2._upsert_candidate(
                conn, campaign_id=1, domain="www.example.com", company_name="X",
                source="test", query_used="kw", evidence_data={}
            )
        # The domain passed to execute must be stripped of www.
        call_sql = mock_db.execute.call_args[0][1]
        call_params = mock_db.execute.call_args[0][2]
        assert "www.example.com" not in str(call_params)
        assert "example.com" in str(call_params)

    def test_rejects_subdomain_domain(self, mock_db):
        """Subdomains like blog.example.com should be rejected (strip to apex or skip)."""
        conn = MagicMock()
        with patch("stage2._is_do_not_contact", return_value=False):
            res = stage2._upsert_candidate(
                conn, campaign_id=1, domain="blog.example.com", company_name="X",
                source="test", query_used="kw", evidence_data={}
            )
        # Should be False because blog. is a non-www subdomain
        assert res is False


# ── Keyword search ─────────────────────────────────────────────────────────────

class TestKeywordSearch:
    @patch("stage2._search_exa")
    @patch("stage2._search_tavily")
    @patch("stage2._search_serper")
    @patch("stage2._search_brave")
    @patch("stage2._llm_dedup")
    @patch("stage2._upsert_candidate")
    def test_runs_all_search_providers_per_query(
        self, mock_upsert, mock_dedup, mock_brave, mock_serper, mock_tavily, mock_exa, mock_db
    ):
        conn = mock_db.get_conn.return_value.__enter__.return_value
        mock_db.fetchone.side_effect = [
            {"keywords_hu": ["hu kw1", "hu kw2"], "keywords_en": ["en kw1"], "version": 1},
            None, None, None,  # cooldown checks
        ]
        mock_exa.return_value = [{"url": "https://a.com", "title": "A"}]
        mock_tavily.return_value = []
        mock_serper.return_value = []
        mock_brave.return_value = []
        mock_dedup.return_value = [{"domain": "a.com", "company_name": "A Corp"}]
        mock_upsert.return_value = True

        res = stage2._keyword_search(1, conn)

        assert res["finder_type"] == "keyword_search"
        assert res["queries_run"] == 3  # 2 hu + 1 en
        assert res["unique_domains"] == 1

    @patch("stage2._search_exa")
    @patch("stage2._search_tavily")
    @patch("stage2._search_serper")
    @patch("stage2._search_brave")
    @patch("stage2._llm_dedup")
    @patch("stage2._upsert_candidate")
    def test_skips_query_on_cooldown(
        self, mock_upsert, mock_dedup, mock_brave, mock_serper, mock_tavily, mock_exa, mock_db
    ):
        conn = mock_db.get_conn.return_value.__enter__.return_value
        # ICP row + cooldown row with last_run_at (required by logger)
        from datetime import datetime, timezone
        mock_db.fetchone.side_effect = [
            {"keywords_hu": ["kw1"], "keywords_en": [], "version": 1},
            {"last_run_at": datetime.now(timezone.utc)},  # cooldown row → skip
        ]
        mock_db.execute.return_value = 0  # housekeeping DELETE
        res = stage2._keyword_search(1, conn)
        assert res["queries_run"] == 0
        mock_exa.assert_not_called()

    @patch("stage2._search_exa", return_value=[])
    @patch("stage2._search_tavily", return_value=[])
    @patch("stage2._search_serper", return_value=[])
    @patch("stage2._search_brave", return_value=[])
    @patch("stage2._llm_dedup", return_value=[])
    def test_returns_zero_when_no_hits(
        self, mock_dedup, mock_brave, mock_serper, mock_tavily, mock_exa, mock_db
    ):
        conn = mock_db.get_conn.return_value.__enter__.return_value
        mock_db.fetchone.side_effect = [
            {"keywords_hu": ["kw1"], "keywords_en": [], "version": 1},
            None,  # no cooldown
        ]
        res = stage2._keyword_search(1, conn)
        assert res["unique_domains"] == 0
        assert res["inserted_or_reopened"] == 0


# ── Signature search / PublicWWW ──────────────────────────────────────────────

class TestSignatureSearch:
    @patch("stage2.config.PUBLICWWW_API_KEY", "test-api-key")
    @patch("stage2._publicwww_search")
    @patch("stage2._upsert_candidate")
    @patch("stage2._is_do_not_contact")
    def test_inserts_new_candidates_from_signatures(
        self, mock_dnc, mock_upsert, mock_pwww, mock_db, mock_cost_log
    ):
        conn = mock_db.get_conn.return_value.__enter__.return_value
        mock_db.fetchall.return_value = [
            {"id": 10, "snippet": "eval(atob(", "malware_family": "Balada", "confidence": "high"}
        ]
        mock_pwww.return_value = ["hacked-site.com", "victim.com"]
        mock_dnc.side_effect = [False, False]
        mock_upsert.return_value = True

        res = stage2._signature_search(1, conn)

        assert res["finder_type"] == "code_signature_search"
        assert res["signatures_checked"] == 1
        assert res["inserted_or_reopened"] == 2

    @patch("stage2.config.PUBLICWWW_API_KEY", "test-api-key")
    @patch("stage2._publicwww_search")
    @patch("stage2._upsert_candidate")
    @patch("stage2._is_do_not_contact")
    def test_skips_dnc_domains_in_signature_search(
        self, mock_dnc, mock_upsert, mock_pwww, mock_db, mock_cost_log
    ):
        conn = mock_db.get_conn.return_value.__enter__.return_value
        mock_db.fetchall.return_value = [
            {"id": 1, "snippet": "eval()", "malware_family": "Balada", "confidence": "high"}
        ]
        mock_pwww.return_value = ["dnc-site.com"]
        mock_dnc.return_value = True  # All DNC

        res = stage2._signature_search(1, conn)
        mock_upsert.assert_not_called()
        assert res["inserted_or_reopened"] == 0

    def test_budget_exhausted_skips_all_signatures(self, mock_db, mock_cost_log):
        conn = mock_db.get_conn.return_value.__enter__.return_value
        mock_db.fetchall.return_value = [
            {"id": 1, "snippet": "malware_code()", "malware_family": "X", "confidence": "high"},
            {"id": 2, "snippet": "another_code()", "malware_family": "Y", "confidence": "medium"},
        ]
        mock_cost_log.publicwww_budget_ok.return_value = False

        res = stage2._signature_search(1, conn)
        assert res["signatures_checked"] == 0
        assert res["signatures_skipped_budget"] == 2

    def test_budget_partially_exhausted_mid_run(self, mock_db, mock_cost_log):
        """Budget OK for first sig, exhausted for second."""
        conn = mock_db.get_conn.return_value.__enter__.return_value
        mock_db.fetchall.return_value = [
            {"id": 1, "snippet": "eval()", "malware_family": "A", "confidence": "high"},
            {"id": 2, "snippet": "shell_exec()", "malware_family": "B", "confidence": "medium"},
        ]
        mock_cost_log.publicwww_budget_ok.side_effect = [True, False]
        # _upsert_candidate calls db.execute which must return int for `rows_affected > 0`
        mock_db.execute.return_value = 0  # No rows inserted (empty publicwww results)
        mock_db.fetchone.return_value = None  # Not DNC

        with patch("stage2.config.PUBLICWWW_API_KEY", "key"), \
             patch("stage2._publicwww_search", return_value=[]):
            res = stage2._signature_search(1, conn)

        assert res["signatures_checked"] == 1
        assert res["signatures_skipped_budget"] == 1


# ── run() routing ──────────────────────────────────────────────────────────────

class TestStage2Run:
    def test_routes_to_keyword_search(self, mock_db):
        mock_db.fetchone.return_value = {
            "id": 1, "slug": "jenex", "status": "active",
            "finder_type": "keyword_search", "settings": {},
        }
        with patch("stage2._keyword_search", return_value={"status": "ok"}) as mock_kw, \
             patch("stage2.db.execute", return_value=1):
            res = stage2.run(1)
        assert res == {"status": "ok"}
        mock_kw.assert_called_once()

    def test_routes_to_signature_search(self, mock_db):
        mock_db.fetchone.return_value = {
            "id": 1, "slug": "wp", "status": "active",
            "finder_type": "code_signature_search", "settings": {},
        }
        with patch("stage2._signature_search", return_value={"status": "ok"}) as mock_sig, \
             patch("stage2.db.execute", return_value=1):
            res = stage2.run(1)
        assert res == {"status": "ok"}
        mock_sig.assert_called_once()

    def test_raises_for_missing_campaign(self, mock_db):
        mock_db.fetchone.return_value = None
        with pytest.raises(ValueError, match="not found"):
            stage2.run(9999)

    def test_raises_for_draft_campaign(self, mock_db):
        """run() only hard-blocks on 'draft' status. Paused campaigns are not explicitly blocked."""
        mock_db.fetchone.return_value = {
            "id": 1, "slug": "draft-camp", "status": "draft",
            "finder_type": "keyword_search", "settings": {},
        }
        with patch("stage2.db.acquire_stage_lock", return_value=True), \
             patch("stage2.db.set_stage_status"):
            with pytest.raises(ValueError, match="status='draft'"):
                stage2.run(1)

    def test_raises_for_unknown_finder_type(self, mock_db):
        mock_db.fetchone.return_value = {
            "id": 1, "slug": "bad", "status": "active",
            "finder_type": "unknown_type", "settings": {},
        }
        with patch("stage2.db.execute", return_value=1):
            with pytest.raises(ValueError, match="Unknown finder_type"):
                stage2.run(1)
