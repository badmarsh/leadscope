import sys
import os
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from stage5 import _enrich_info

def test_enrich_info_prompt(mocker):
    mock_chat = mocker.patch('stage5.llm.chat_json', return_value=({"email": "test@test.com"}, 10, 5))
    
    domain = "example.com"
    company_name = "Example Corp"
    offer_summary = "We sell AI software"
    page_text = "Welcome to Example Corp."
    pre_extracted = {}
    
    result = _enrich_info(domain, company_name, offer_summary, page_text, pre_extracted)
    
    assert result == {"email": "test@test.com"}
    mock_chat.assert_called_once()
    
    prompt_called = mock_chat.call_args[0][0]
    
    assert "Slovak language" in prompt_called
    assert "15 words" in prompt_called
    assert domain in prompt_called
    assert company_name in prompt_called
    assert offer_summary in prompt_called
    assert page_text in prompt_called
    assert "firmographics" in prompt_called
    assert "tech_stack" in prompt_called
    assert "buying_power_signals" in prompt_called


def test_enrich_info_returns_empty_dict_on_llm_failure(mocker):
    mocker.patch('stage5.llm.chat_json', side_effect=Exception("LLM Timeout"))
    result = _enrich_info("example.com", "Corp", "Offer", "Page", {})
    assert result == {}
