import urllib.request
import json
import time
import os

TOKEN = '9f35ad6c45c3138cf14f9ffa9811c8e7ee0280da621b1ef533971df958fd96b7'
CAMPAIGN_ID = 3

def call_api(endpoint, payload=None):
    url = f'http://localhost:{8001 if "score" in endpoint else 8002}{endpoint}'
    headers = {
        'Content-Type': 'application/json',
        'X-Internal-Token': TOKEN
    }
    
    data = json.dumps(payload).encode('utf-8') if payload else None
    
    try:
        print(f"\n🚀 Calling {endpoint}...")
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read().decode('utf-8'))
        print(f"✅ Success: {result}")
        return result
    except Exception as e:
        print(f"❌ Error calling {endpoint}: {e}")
        if hasattr(e, 'read'):
            print(e.read().decode('utf-8'))
        return None

if __name__ == '__main__':
    print(f"Starting E2E pipeline test for Campaign {CAMPAIGN_ID}")
    
    # 1. KB Ingest
    call_api('/kb/ingest')
    
    # 2. Stage 1 (ICP Definition)
    call_api('/stage1/run', {'campaign_id': CAMPAIGN_ID})
    
    # 3. Stage 2 (Target Finder)
    call_api('/stage2/run', {'campaign_id': CAMPAIGN_ID})
    
    # 4. Evaluator (Scorer)
    call_api('/score/trigger')
    
    # 5. Stage 5 (Enrichment)
    call_api('/stage5/run')
    
    print("\n🎉 Pipeline run complete!")
