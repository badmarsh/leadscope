import requests
import json

try:
    resp = requests.post("http://localhost:8003/crawl", json={"url": "https://pottomcipo.hu/termekek", "extract_images": True, "force_playwright": True, "bypass_cache": True})
    data = resp.json()
    print("Success:", data.get("success"))
    print("Extracted Data:", data.get("extracted_data"))
    print("Error:", data.get("error"))
except Exception as e:
    print("Exception:", e)
