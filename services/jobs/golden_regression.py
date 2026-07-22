import os
import sys
import json
import logging

# Add services/evaluator to path so we can import the scorers
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'evaluator'))

from scorers import content_relevance, image_quality, threat_intel

# Setup minimal logging
logging.basicConfig(level=logging.INFO)

# We define static fixtures that represent known-good and known-bad inputs.
# In a real environment, we'd use more realistic/longer HTML content or actual live URLs.
# But for a stable regression test, we pass mock data.
FIXTURES = [
    {
        "name": "JENEX - Good Content",
        "scorer": content_relevance.score,
        "campaign": {"evaluator_type": "content_relevance"},
        "icp": {
            "target_segments": ["HVAC wholesalers"],
            "keywords_en": ["HVAC", "ductwork"],
            "keywords_hu": ["légtechnika"]
        },
        "candidate": {
            "id": 9991,
            "domain": "good-hvac.hu",
            "company_name": "Good HVAC",
            "evidence_data": {
                "pages": [
                    {"url": "http://good-hvac.hu", "text": "We are the leading HVAC wholesaler in Hungary. We supply légtechnika products."}
                ]
            }
        },
        "few_shot": [],
        "expected_min_score": 70,
        "expected_max_score": 100
    },
    {
        "name": "JENEX - Bad Content",
        "scorer": content_relevance.score,
        "campaign": {"evaluator_type": "content_relevance"},
        "icp": {
            "target_segments": ["HVAC wholesalers"],
            "keywords_en": ["HVAC", "ductwork"],
            "keywords_hu": ["légtechnika"]
        },
        "candidate": {
            "id": 9992,
            "domain": "pet-shop.hu",
            "company_name": "Pet Shop",
            "evidence_data": {
                "pages": [
                    {"url": "http://pet-shop.hu", "text": "Welcome to our pet store. We sell dog food and cat toys."}
                ]
            }
        },
        "few_shot": [],
        "expected_min_score": 0,
        "expected_max_score": 40
    },
    # Note: image_quality and threat_intel require actual network fetches in the scorers themselves.
    # The Part 3 image_quality scorer uses Firecrawl to fetch images from the domain.
    # The threat_intel scorer uses Firecrawl to re-verify the signature.
    # This means those scorers are not purely pure functions; they do I/O based on candidate["domain"].
    # To run a stable regression test without mocking `requests`, we either need live URLs that 
    # reliably return bad photos/malware, or we just focus the regression suite on the prompt output.
    # For now, we will test content_relevance as the primary regression check, and add a simple 
    # threat_intel test with a local file URL if Firecrawl local read is supported.
]

def run_regression_suite():
    print("Running Golden Regression Suite...")
    passed = 0
    failed = 0

    for fix in FIXTURES:
        print(f"Testing: {fix['name']}...")
        try:
            # We call the scorer directly
            res = fix["scorer"](fix["candidate"], fix["campaign"], fix["icp"], fix["few_shot"])
            score = res["score"]
            if fix["expected_min_score"] <= score <= fix["expected_max_score"]:
                print(f"  [PASS] Score {score} in range [{fix['expected_min_score']}, {fix['expected_max_score']}]")
                passed += 1
            else:
                print(f"  [FAIL] Score {score} out of range [{fix['expected_min_score']}, {fix['expected_max_score']}]")
                print(f"         Rationale: {res.get('rationale')}")
                failed += 1
        except Exception as e:
            print(f"  [FAIL] Scorer threw exception: {e}")
            failed += 1

    print(f"\nRegression Suite Complete: {passed} passed, {failed} failed.")
    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    run_regression_suite()
