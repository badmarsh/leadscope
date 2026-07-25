import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from unittest.mock import patch, MagicMock
from stage2 import _llm_dedup

@patch('stage2.llm.chat_json')
def test_llm_dedup_ruthless_filtering(mock_chat_json):
    # Mock LLM response to return a filtered list
    mock_chat_json.return_value = ([{"domain": "szamicipo.hu", "company_name": "Szami Cipo"}], 100, 50, "gemini", "gemini")
    
    businesses = [
        {"url": "https://amazon.com", "title": "Amazon", "snippet": "Everything"},
        {"url": "https://lulus.com", "title": "Lulus", "snippet": "Womens clothing"},
        {"url": "https://szamicipo.hu", "title": "Szami Cipo", "snippet": "Gyakorikerdesek"},
        {"url": "https://facebook.com", "title": "Facebook", "snippet": "Social"}
    ]
    
    conn = MagicMock()
    result = _llm_dedup(businesses, conn, 1)
    
    # Assert the returned filtered list matches what the mock returns
    assert len(result) == 1
    assert result[0]["domain"] == "szamicipo.hu"
    
    # Assert that the prompt passed to LLM included our ruthless rules
    prompt = mock_chat_json.call_args[0][0]
    assert "CRITICAL DISQUALIFIERS" in prompt
    assert "global e-commerce marketplace" in prompt
    assert "Amazon, Walmart, eBay" in prompt
    
    # Assert the payload passed to the prompt contained our junk domains
    assert "amazon.com" in prompt
    assert "szamicipo.hu" in prompt
