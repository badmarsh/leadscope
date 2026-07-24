import psycopg2
import os

DATABASE_URL = "postgresql://leadscope:leadscope_dev@localhost:5432/leadscope"

NEW_SIGS = [
    {
        "snippet": "uph-analytics.com",
        "malware_family": "Analytics Injection",
        "confidence": "high",
        "sneakiness_tier": "S",
        "proof_method": "google_serp_spam",
        "outreach_hook": "We detected a malicious tracking script (uph-analytics) intercepting your visitor data.",
        "outbreak_scope": "Active script injection campaign",
        "publicwww_expected_results": "low",
        "false_positive_risk": "low"
    },
    {
        "snippet": "awebstats.com",
        "malware_family": "Analytics Injection",
        "confidence": "high",
        "sneakiness_tier": "S",
        "proof_method": "google_serp_spam",
        "outreach_hook": "Your site is loading an unauthorized script (awebstats) that Google blocks.",
        "outbreak_scope": "Active script injection campaign",
        "publicwww_expected_results": "low",
        "false_positive_risk": "low"
    },
    {
        "snippet": "brazilc.com",
        "malware_family": "Malicious Ad Injector",
        "confidence": "high",
        "sneakiness_tier": "S",
        "proof_method": "google_serp_spam",
        "outreach_hook": "Your WordPress theme has been modified to inject ads via brazilc.com.",
        "outbreak_scope": "Known WP Ad injector",
        "publicwww_expected_results": "low",
        "false_positive_risk": "low"
    },
    {
        "snippet": "cloudflare.solutions",
        "malware_family": "Fake Cloudflare Keylogger",
        "confidence": "high",
        "sneakiness_tier": "A",
        "proof_method": "file_scan",
        "outreach_hook": "Your site is loading a fake Cloudflare script known to steal passwords and credit cards.",
        "outbreak_scope": "Massive credential harvesting campaign",
        "publicwww_expected_results": "medium",
        "false_positive_risk": "low"
    },
    {
        "snippet": "cyber_insect99",
        "malware_family": "Hidden Admin Backdoor",
        "confidence": "high",
        "sneakiness_tier": "B",
        "proof_method": "wp_admin_check",
        "outreach_hook": "We found evidence of a hidden admin account backdoor (cyber_insect99) in your site code.",
        "outbreak_scope": "Widespread PHP backdoor",
        "publicwww_expected_results": "low",
        "false_positive_risk": "low"
    },
    {
        "snippet": "34d1f91fb2e514b8576fab1a75a89a6b",
        "malware_family": "MD5 Admin Backdoor",
        "confidence": "high",
        "sneakiness_tier": "B",
        "proof_method": "wp_admin_check",
        "outreach_hook": "We found a known malicious MD5 hash backdoor used to bypass your admin login.",
        "outbreak_scope": "Common webshell component",
        "publicwww_expected_results": "low",
        "false_positive_risk": "low"
    },
    {
        "snippet": "e9787adc5271cb0f765294503da3f2dc",
        "malware_family": "POST-based Webshell",
        "confidence": "high",
        "sneakiness_tier": "C",
        "proof_method": "file_scan",
        "outreach_hook": "We detected a hidden webshell accepting remote commands via your site.",
        "outbreak_scope": "File dropper webshell",
        "publicwww_expected_results": "low",
        "false_positive_risk": "low"
    }
]

def run():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        # Get WP campaign ID
        cur.execute("SELECT id FROM campaigns WHERE slug = 'wp-remediation'")
        row = cur.fetchone()
        if not row:
            print("Campaign not found.")
            return
        campaign_id = row[0]
        
        inserted = 0
        for sig in NEW_SIGS:
            try:
                cur.execute(
                    """
                    INSERT INTO malware_signatures 
                    (campaign_id, snippet, malware_family, confidence, sneakiness_tier, 
                     proof_method, outreach_hook, outbreak_scope, 
                     publicwww_expected_results, false_positive_risk)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        campaign_id, sig["snippet"], sig["malware_family"], sig["confidence"], 
                        sig["sneakiness_tier"], sig["proof_method"], sig["outreach_hook"], 
                        sig["outbreak_scope"], sig["publicwww_expected_results"], sig["false_positive_risk"]
                    )
                )
                inserted += 1
            except Exception as e:
                print(f"Skipping {sig['snippet']}: {e}")
                
        print(f"Successfully inserted {inserted} new signatures from Perplexity research.")

if __name__ == "__main__":
    run()
