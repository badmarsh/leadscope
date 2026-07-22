import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services', 'evaluator'))
from firecrawl_client import extract_product_grid_images

ignore_patterns = [
        "bat.bing.com", "google-analytics.com", "facebook.com", "twitter.com", "instagram.com", 
        "x.com", "linkedin.com", "youtube.com", "tiktok.com", "pinterest.com",
        "pixel", "tracker", ".svg", ".gif", "logo", "icon", "spinner", "loader", "social",
        "badge", "trust", "support", "shipping", "payment", "secure", "guarantee", "return",
        "header", "footer", "banner", "hero", "avatar", "profile", "menu",
        "partner", "layout", "element", "blog", "gls", "packeta", "szepkartya",
        "dpd", "mpl", "foxpost", "cetelem", "mastercard", "visa", "barion", "simplepay",
        "mastercard", "maestro", "paypal", "apple-pay", "google-pay", "alipay"
    ]

src_lower = "https://example.com/shoe1.jpg"
for p in ignore_patterns:
    if p in src_lower:
        print("MATCHED PATTERN:", p)
