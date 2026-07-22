"""
scorers/threat_intel.py — Scorer C: WP-remediation (threat_intel).

Re-verification scorer: Stage 2 detected a PublicWWW hit against a known
malware signature. This scorer's job is FRESH RE-VERIFICATION — confirm
the snippet is STILL PRESENT on the live site via Firecrawl, then score.

A high score means "confirmed active compromise, strong remediation lead".
Requires fresh re-verification before a candidate reaches approved.
"""
import json
import logging

import config
import firecrawl_client
import llm

logger = logging.getLogger(__name__)

SCORING_PROMPT = """
You are a WordPress security analyst evaluating a website for active malware
infection. A previous automated scan (PublicWWW) detected suspicious code
signatures on this site. Your job is to RE-VERIFY whether the infection is
still active.

## Malware signatures detected in Stage 2
{signatures_json}

## Fresh scrape of the site (re-verification)
{scraped_content}

## Re-verification result
Snippet still present in fresh scrape: {snippet_confirmed}

## Past feedback (few-shot)
{few_shot_examples}

## Instructions
Score 0-100 where:
- 90-100: Confirmed active infection — signature found in fresh scrape,
  site is a strong remediation lead
- 70-89: Likely infected — partial match or obfuscated variant found
- 50-69: Inconclusive — site was scraped but signature not found in this
  fetch (could be intermittent or behind JS)
- 30-49: Unlikely — site appears clean in fresh scrape
- 0-29: Confirmed clean or site is down/not WordPress

A mistaken "you're hacked" is costlier here than a mediocre lead elsewhere.
Err on the side of lower scores when the evidence is ambiguous.

Return JSON with:
- "score": integer 0-100
- "rationale": 2-3 sentences — which malware family, which signature,
  confirmed present as of when. Be specific.
- "snippet_confirmed": boolean — was the exact snippet found in fresh scrape?
- "malware_family": string — the malware family name
- "confidence": "high" | "medium" | "low"
- "recommendation": "remediation_candidate" | "needs_manual_check" | "likely_clean"
"""


def _check_snippet_present(scraped_content: str, snippets: list[str]) -> tuple[bool, list[str]]:
    """Check if any malware snippets are still present in the scraped content."""
    found = []
    content_lower = scraped_content.lower()
    for snippet in snippets:
        # Check for exact match or close match (some obfuscation may vary whitespace)
        snippet_clean = snippet.strip().lower()
        if snippet_clean in content_lower:
            found.append(snippet)
        # Also check key parts (first 20 chars)
        elif len(snippet_clean) > 20 and snippet_clean[:20] in content_lower:
            found.append(snippet + " (partial match)")
    return len(found) > 0, found


def score(candidate: dict, campaign: dict, icp: dict, few_shot: list[dict]) -> dict:
    """
    Score a candidate using threat_intel (re-verification) strategy.
    """
    domain = candidate["domain"]
    evidence = candidate.get("evidence_data", {})
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except json.JSONDecodeError:
            evidence = {}

    # Extract signatures from evidence_data
    matched_sigs = evidence.get("matched_signatures", [])
    snippets = [s.get("snippet", "") for s in matched_sigs if s.get("snippet")]

    # Fresh Firecrawl re-verification
    pages = firecrawl_client.scrape_domain_pages(domain, paths=["", "/wp-content/", "/wp-includes/"])
    scraped = "\n\n".join(
        f"### {url}\n{text[:3000]}" for url, text in list(pages.items())[:3]
    )
    if not scraped:
        scraped = "(No content could be scraped — site may be down)"

    # Check snippets against fresh content
    snippet_confirmed, found_snippets = _check_snippet_present(scraped, snippets)

    # Build few-shot
    few_shot_str = ""
    if few_shot:
        examples = []
        for fb in few_shot:
            examples.append(
                f"- Domain: {fb.get('domain', '?')} | Decision: {fb['decision']} | "
                f"Note: {fb.get('note', 'N/A')}"
            )
        few_shot_str = "\n".join(examples)
    else:
        few_shot_str = "(No prior feedback available)"

    prompt = SCORING_PROMPT.format(
        signatures_json=json.dumps(matched_sigs, indent=2, ensure_ascii=False)[:2000],
        scraped_content=scraped[:5000],
        snippet_confirmed="YES — found: " + str(found_snippets) if snippet_confirmed else "NO — not found in fresh scrape",
        few_shot_examples=few_shot_str,
    )

    result, ti, to, model, provider = llm.chat_json(prompt, temperature=0.1, model=config.SCORER_TEXT_MODEL)

    if "_raw" in result:
        logger.warning("threat_intel scorer got non-JSON response")
        return {
            "score": 30,  # Conservative — err on side of lower scores
            "rationale": "LLM returned non-parseable response; defaulting to low score for safety",
            "evidence_urls": list(pages.keys()),
            "evidence_data": {
                "snippet_confirmed": snippet_confirmed,
                "raw_response": result["_raw"][:500],
            },
            "model_used": model, "provider": provider,
            "tokens_in": ti, "tokens_out": to,
        }

    return {
        "score": max(0, min(100, int(result.get("score", 30)))),
        "rationale": result.get("rationale", ""),
        "evidence_urls": list(pages.keys()),
        "evidence_data": {
            "snippet_confirmed": result.get("snippet_confirmed", snippet_confirmed),
            "malware_family": result.get("malware_family", "unknown"),
            "confidence": result.get("confidence", "low"),
            "recommendation": result.get("recommendation", "needs_manual_check"),
            "matched_signatures": matched_sigs,
            "found_in_fresh_scrape": found_snippets,
            "pages_scraped": list(pages.keys()),
        },
        "model_used": model,
        "provider": provider,
        "tokens_in": ti,
        "tokens_out": to,
    }
