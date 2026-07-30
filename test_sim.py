import sys
sys.path.append('/app')
from scorers import image_quality

candidate = {'domain': 'pottomcipo.hu'}
product_paths = ['/products', '/shop', '/termekek']
pages_markdown = {}
all_images = []
for path in product_paths[:3]:
    url = f"https://{candidate['domain']}{path}"
    print(f"Crawling {url}...")
    md, html_content, extracted_data = image_quality._crawler_scrape(url, force_playwright=True)
    if md:
        pages_markdown[url] = md
    if extracted_data and 'urls' in extracted_data:
        all_images.extend(extracted_data['urls'])
        print(f"extracted_data for {url}: {extracted_data}")

print("all_images before filter:", all_images)
seen = set()
valid_urls = []
for u in all_images:
    if not u or not isinstance(u, str): continue
    if u.startswith('//'): u = 'https:' + u
    elif u.startswith('/'): u = f"https://{candidate['domain']}{u}"
    u = u.replace('%7Bwidth%7D', '800').replace('{width}', '800')
    u_lower = u.lower()
    if any(w in u_lower for w in ['banner', 'hero', 'footer', 'header', 'bg', 'background', 'menu', 'avatar', 'profile', 'logo', 'icon', 'svg', 'slider', 'carousel']):
        print('filtered:', u)
        continue
    if u not in seen and u.startswith('http'):
        seen.add(u)
        valid_urls.append(u)
print("valid_urls:", valid_urls)
