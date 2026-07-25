from datetime import date, timedelta
import pytest
from wp_hunter.schema import Campaign, freshness_gate

def create_campaign(days_ago, is_template=False):
    added_date = date.today() - timedelta(days=days_ago)
    query = "select * from {{ template }}" if is_template else "select * from table"
    return Campaign(
        id="test-campaign",
        name="Test",
        family="TestFamily",
        added=added_date,
        stale_after_days=30,
        source_url="http://test.com",
        publicwww_query=query,
        location="test"
    )

def test_campaign_is_template():
    c_normal = create_campaign(0, is_template=False)
    assert not c_normal.is_template

    c_template = create_campaign(0, is_template=True)
    assert c_template.is_template

def test_campaign_is_stale():
    # Stale threshold is 30 days
    c_fresh = create_campaign(15)
    assert not c_fresh.is_stale

    c_stale = create_campaign(35)
    assert c_stale.is_stale

def test_freshness_gate_raises_on_stale():
    c_stale = create_campaign(35)
    with pytest.raises(ValueError, match="One or more campaigns are STALE"):
        freshness_gate([c_stale])

def test_freshness_gate_passes_on_force_stale():
    c_stale = create_campaign(35)
    # Should not raise exception
    freshness_gate([c_stale], force_stale=True)

def test_freshness_gate_raises_on_template():
    c_template = create_campaign(0, is_template=True)
    with pytest.raises(ValueError, match="One or more campaigns are templates"):
        freshness_gate([c_template])
