import urllib.request, json
url = 'https://firecrawl.dev.significa.sk/v1/scrape'
headers = {
    'Authorization': 'Bearer fc-a2153bb0154e45bb860c56d12e5010e6',
    'Content-Type': 'application/json'
}
data = json.dumps({"url": "https://docs.librefang.ai/api-reference", "formats": ["markdown"]}).encode('utf-8')
req = urllib.request.Request(url, data=data, headers=headers)
try:
    with urllib.request.urlopen(req) as response:
        with open('librefang_api_reference.md', 'w', encoding='utf-8') as f:
            f.write(response.read().decode())
except Exception as e:
    print(e)
