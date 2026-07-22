import os
import sys
import pytest
from unittest.mock import MagicMock

# Path setup — allow importing from services/stages without installing
STAGES_DIR = os.path.join(os.path.dirname(__file__), "..")
if STAGES_DIR not in sys.path:
    sys.path.insert(0, STAGES_DIR)

from stage5 import _enrich_info

def test_enrich_info_prompt(mocker):
    # Mock llm.chat_json on the imported reference in stage5
    mock_chat = mocker.patch('stage5.llm.chat_json', return_value=({"email": "test@test.com"}, 10, 5))
    
    domain = "example.com"
    company_name = "Example Corp"
    offer_summary = "We sell AI software"
    page_text = "Welcome to Example Corp."
    
    result = _enrich_info(domain, company_name, offer_summary, page_text)
    
    assert result == {"email": "test@test.com"}
    mock_chat.assert_called_once()
    
    prompt_called = mock_chat.call_args[0][0]
    
    assert "Slovak language" in prompt_called
    assert "15 words" in prompt_called
    assert domain in prompt_called
    assert company_name in prompt_called
    assert offer_summary in prompt_called
    assert page_text in prompt_called
