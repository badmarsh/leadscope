"""
services/common/image_filters.py — Single source of truth for "is this a real
product photo, or site furniture" filtering. Used by the evaluator's
image_quality scorer, firecrawl_client's grid extraction, and stage5's
crawler_client. Do not duplicate this list elsewhere.
"""
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

# Merge of the two existing blocklists from image_quality.py and
# firecrawl_client.py — keep this the ONLY copy going forward.
IGNORE_TERMS = [
    "logo", "icon", "banner", "avatar", "badge", "trust", "hero", "slider",
    "carousel", "sponsor", "client", "thumb_brand", "swiper", "spinner",
    "loader", "social", "support", "shipping", "payment", "secure",
    "guarantee", "return", "header", "footer", "menu", "partner", "layout",
    "element", "blog", "poster", "advert", "reklaam",
    # payment / carrier logos (HU/SK/CZ market specific — keep, don't remove)
    "gls", "packeta", "szepkartya", "dpd", "mpl-", "foxpost", "cetelem",
    "mastercard", "maestro", "visa", "paypal", "apple-pay", "google-pay",
    "alipay", "barion", "simplepay", "stripe",
    # promo/marketing banners, not product photos
    "vasar", "kedvezmeny", "akcio", "sale", "promo", "discount",
    "szallitas", "off-",
    # analytics / social trackers that sometimes appear as <img> pixels
    "bat.bing.com", "google-analytics.com", "facebook.com", "twitter.com",
    "instagram.com", "x.com", "linkedin.com", "youtube.com", "tiktok.com",
    "pinterest.com", "pixel", "tracker",
]

MIN_DIMENSION_PX = 150   # below this on either axis, treat as icon/UI chrome
VALID_EXTENSIONS = (".jpg", ".jpeg", ".webp", ".avif", ".png")
CDN_HINTS = ("cdn", "image", "media", "upload", "gallery", "large", "zoom", "thumb")


def is_probably_decorative(url: str) -> bool:
    """True if the URL matches a known non-product pattern."""
    if not url:
        return True
    u = url.lower()
    if u.endswith(".svg") or u.endswith(".gif"):
        return True
    if any(term in u for term in IGNORE_TERMS):
        return True
    return False


def passes_dimension_gate(width: int | None, height: int | None) -> bool:
    """Reject anything that looks like an icon/UI element by size.
    Unknown dimensions (None) pass through — we only reject when we KNOW
    it's small, never reject for missing metadata."""
    if width is None or height is None:
        return True
    return width >= MIN_DIMENSION_PX and height >= MIN_DIMENSION_PX


def normalize_for_dedup(url: str) -> str:
    """Strip cache-busting / tracking query params so the same image at
    different query strings dedupes correctly."""
    try:
        parsed = urlparse(url)
        # Keep only query params that plausibly affect the actual image
        # (e.g. Shopify/Cloudinary width/format params); drop the rest.
        keep_keys = {"w", "width", "h", "height", "format", "fm", "q", "quality"}
        kept = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() in keep_keys]
        return urlunparse(parsed._replace(query=urlencode(kept)))
    except Exception:
        return url


def filter_and_dedupe_images(
    candidates: list[dict],
    max_results: int = 10,
) -> list[str]:
    """
    candidates: list of dicts with at least {"src": str}, optionally
    {"width": int, "height": int, "score": float}.
    Returns a deduped, filtered, best-first list of image URLs (strings).
    """
    scored: list[tuple[float, str]] = []
    seen_norm: set[str] = set()

    for c in candidates:
        src = c.get("src")
        if not src or not isinstance(src, str) or not src.startswith("http"):
            continue
        if is_probably_decorative(src):
            continue
        if not passes_dimension_gate(c.get("width"), c.get("height")):
            continue
        if not any(ext in src.lower() for ext in VALID_EXTENSIONS):
            if not any(hint in src.lower() for hint in CDN_HINTS):
                continue

        norm = normalize_for_dedup(src)
        if norm in seen_norm:
            continue
        seen_norm.add(norm)

        base_score = float(c.get("score", 0) or 0)
        scored.append((base_score, src))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [src for _, src in scored[:max_results]]
