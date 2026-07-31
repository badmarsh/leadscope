import pytest
from services.common.image_filters import (
    is_probably_decorative,
    passes_dimension_gate,
    normalize_for_dedup,
    filter_and_dedupe_images,
)


def test_logo_url_rejected():
    assert is_probably_decorative("https://example.com/images/brand_logo.png") is True
    res = filter_and_dedupe_images([{"src": "https://example.com/images/brand_logo.png"}])
    assert len(res) == 0


def test_small_dimension_rejected():
    assert passes_dimension_gate(40, 40) is False
    res = filter_and_dedupe_images([{"src": "https://example.com/products/shoe.jpg", "width": 40, "height": 40}])
    assert len(res) == 0


test_missing_dimensions_not_rejected_data = [
    {"src": "https://example.com/products/shoe.jpg"},
]


def test_missing_dimensions_not_rejected():
    assert passes_dimension_gate(None, None) is True
    res = filter_and_dedupe_images([{"src": "https://example.com/products/shoe.jpg"}])
    assert len(res) == 1
    assert res[0] == "https://example.com/products/shoe.jpg"


def test_cache_busting_param_deduplication():
    url1 = "https://example.com/products/shoe.jpg?v=12345"
    url2 = "https://example.com/products/shoe.jpg?v=67890"
    norm1 = normalize_for_dedup(url1)
    norm2 = normalize_for_dedup(url2)
    assert norm1 == norm2

    res = filter_and_dedupe_images([{"src": url1}, {"src": url2}])
    assert len(res) == 1
    assert res[0] == url1


def test_max_results_and_score_ordering():
    candidates = [
        {"src": f"https://example.com/products/item{i}.jpg", "score": float(i)}
        for i in range(15)
    ]
    res = filter_and_dedupe_images(candidates, max_results=5)
    assert len(res) == 5
    # Highest score first (14.0 -> item14.jpg)
    assert res[0] == "https://example.com/products/item14.jpg"
    assert res[4] == "https://example.com/products/item10.jpg"
