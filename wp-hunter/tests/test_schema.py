from datetime import date, timedelta
from pathlib import Path
import pytest
from pydantic import ValidationError
from wp_hunter.schema import Campaign, freshness_gate, load_campaigns


def test_freshness_gate_rejects_templates():
    template_camp = Campaign(
        id="template-camp",
        name="Template Campaign",
        family="Test",
        added=date.today(),
        stale_after_days=30,
        source_url="https://example.com",
        publicwww_query="{{KEYWORD}}",
        location="html_body",
    )
    with pytest.raises(ValueError) as excinfo:
        freshness_gate([template_camp], force_stale=False)
    assert "templates" in str(excinfo.value)

def test_campaign_staleness():
    camp = Campaign(
        id="test-camp",
        name="Test Campaign",
        family="Test",
        added=date.today() - timedelta(days=40),
        stale_after_days=30,
        source_url="https://example.com",
        publicwww_query="test",
        location="js_file",
    )
    assert camp.is_stale is True
    assert camp.days_old == 40


def test_freshness_gate_raises_on_stale():
    stale_camp = Campaign(
        id="stale-camp",
        name="Stale Campaign",
        family="Test",
        added=date.today() - timedelta(days=50),
        stale_after_days=30,
        source_url="https://example.com",
        publicwww_query="test",
        location="js_file",
    )
    with pytest.raises(ValueError) as excinfo:
        freshness_gate([stale_camp], force_stale=False)
    assert "One or more campaigns are STALE" in str(excinfo.value)


def test_freshness_gate_bypassed_with_force():
    stale_camp = Campaign(
        id="stale-camp",
        name="Stale Campaign",
        family="Test",
        added=date.today() - timedelta(days=50),
        stale_after_days=30,
        source_url="https://example.com",
        publicwww_query="test",
        location="js_file",
    )
    # Should not raise exception when force_stale=True
    freshness_gate([stale_camp], force_stale=True)
