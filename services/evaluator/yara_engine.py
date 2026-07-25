import logging
import os
import re
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger(__name__)

RULES_DIR = Path(__file__).parent / "yara_rules"

_YARA_AVAILABLE = False
_compiled_rules: Optional[Any] = None

try:
    import yara
    _YARA_AVAILABLE = True
except ImportError:
    _YARA_AVAILABLE = False
    logger.warning("yara-python package not found. YARA engine falling back to regex matcher.")

def get_compiled_rules():
    global _compiled_rules
    if not _YARA_AVAILABLE:
        return None
    if _compiled_rules is None:
        try:
            rule_files = {f.stem: str(f) for f in RULES_DIR.glob("*.yar")}
            if rule_files:
                _compiled_rules = yara.compile(filepaths=rule_files)
        except Exception as e:
            logger.error("Failed to compile YARA rules: %s", e)
            _compiled_rules = None
    return _compiled_rules

def scan_content(content: str | bytes, domain: str = "") -> list[dict]:
    """
    Scan content against YARA rules. Returns list of dicts with match details.
    Falls back to regex scanning if YARA is unavailable.
    """
    if isinstance(content, str):
        data_bytes = content.encode("utf-8", errors="ignore")
        data_str = content
    else:
        data_bytes = content
        data_str = content.decode("utf-8", errors="ignore")

    rules = get_compiled_rules()
    if rules is not None:
        try:
            matches = rules.match(data=data_bytes, timeout=5)
            return [
                {
                    "rule": m.rule,
                    "tags": m.tags,
                    "meta": m.meta,
                    "strings": [
                        (hex(s.offset), s.identifier, s.plaintext()[:80].decode("utf-8", errors="ignore"))
                        for s in m.strings
                    ],
                }
                for m in matches
            ]
        except Exception as e:
            logger.error("YARA scan error for domain %s: %s", domain, e)

    # Fallback regex scanning when yara-python is not installed locally
    fallback_hits = []
    
    # SocGholish b64 loader pattern
    if re.search(r"eval\(atob\([\"'][A-Za-z0-9+/]{30,}[\"']\)\)", data_str):
        fallback_hits.append({"rule": "SocGholish_FakeUpdate", "meta": {"malware_family": "socgholish"}})
        
    # Balada iframe / String.fromCharCode pattern
    if re.search(r"<iframe[^>]+src=[\"'][^\"']{0,10}(trck|stat|cdn)\.[^\"']+", data_str, re.IGNORECASE) or \
       re.search(r"String\.fromCharCode\(\s*\d+(\s*,\s*\d+){15,}\s*\)", data_str):
        fallback_hits.append({"rule": "Balada_Injector", "meta": {"malware_family": "balada"}})

    # Japanese SEO Spam / hidden wrapper
    if (re.search(r"[\u3040-\u30FF\u4E00-\u9FFF]", data_str) and re.search(r"(display\s*:\s*none|visibility\s*:\s*hidden)[^>]*>.*?(href=)", data_str, re.IGNORECASE)) or \
       (re.search(r"(display\s*:\s*none|visibility\s*:\s*hidden)[^>]*>", data_str, re.IGNORECASE) and re.search(r"(viagra|cialis|pharmacy|levitra)", data_str, re.IGNORECASE)):
        fallback_hits.append({"rule": "Japanese_SEO_Spam", "meta": {"malware_family": "seo_spam"}})

    return fallback_hits
