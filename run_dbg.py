import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'services', 'evaluator')))

from unittest.mock import patch

try:
    from scorers.threat_intel import score, _check_snippet_present
except ImportError:
    pass

CANDIDATE_WITH_SIG = {
    "domain": "evil-wp.com",
    "evidence_data": {
        "matched_signatures": [
            {"snippet": "eval(base64_decode(", "malware_family": "Generic.Backdoor", "confidence": "high"}
        ]
    }
}
CAMPAIGN = {"id": 3}
ICP = {"version": 1}

@patch("scorers.threat_intel._check_virustotal", return_value={})
@patch("scorers.threat_intel._check_safe_browsing", return_value={})
@patch("scorers.threat_intel._crawl4ai_scrape")
@patch("scorers.threat_intel.llm")
def dbg(mock_llm, mock_crawl, mock_sb, mock_vt):
    mock_crawl.return_value = "some malicious eval(base64_decode('QWxhZGRpbg==')) code injected into the website body to compromise the site completely."
    mock_llm.chat_json.return_value = (
        {"score": 90, "snippet_confirmed": True, "malware_family": "Generic.Backdoor",
         "confidence": "high", "recommendation": "remediation_candidate", "rationale": "Found it."},
        10, 5, "gemini-2.5-flash", "gemini"
    )
    result = score(CANDIDATE_WITH_SIG, CAMPAIGN, ICP, [])
    print(result)

if __name__ == "__main__":
    dbg()
