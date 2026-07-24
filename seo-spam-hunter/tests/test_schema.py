import pytest
from pydantic import ValidationError
from seo_spam_hunter.schema import Campaign, load_campaigns, freshness_gate
from datetime import date, timedelta


def test_placeholder_rejection():
    with pytest.raises(ValidationError) as exc_info:
        Campaign(
            id="test",
            name="test",
            family="test",
            added=date.today(),
            stale_after_days=30,
            source_url="http://example.com",
            publicwww_query='"{{PLACEHOLDER}}" filetype:html',
            location="body",
        )
    assert "unresolved placeholder" in str(exc_info.value)


def test_stale_logic():
    c = Campaign(
        id="test",
        name="test",
        family="test",
        added=date.today() - timedelta(days=40),
        stale_after_days=30,
        source_url="http://example.com",
        location="body",
    )
    assert c.is_stale is True

    c2 = Campaign(
        id="test",
        name="test",
        family="test",
        added=date.today() - timedelta(days=20),
        stale_after_days=30,
        source_url="http://example.com",
        location="body",
    )
    assert c2.is_stale is False


def test_freshness_gate():
    stale_campaign = Campaign(
        id="test",
        name="test",
        family="test",
        added=date.today() - timedelta(days=40),
        stale_after_days=30,
        source_url="http://example.com",
        location="body",
    )
    with pytest.raises(ValueError, match="Expired campaigns present"):
        freshness_gate([stale_campaign], force_stale=False)
        
    # Should not raise if forced
    freshness_gate([stale_campaign], force_stale=True)
