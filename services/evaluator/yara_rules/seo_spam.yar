rule Japanese_SEO_Spam {
    meta:
        description = "Japanese SEO Spam injection and hidden pharma links"
        malware_family = "seo_spam"
        sneakiness_tier = "A"
    strings:
        $jp_unicode = /[\xE3\x80-\xBF][\x80-\xBF]{2}/
        $hidden_wrapper = /(display\s*:\s*none|visibility\s*:\s*hidden)[^>]*>.*?(href=)/ nocase
        $pharma_words = /(viagra|cialis|pharmacy|levitra|xanax|tramadol|oxycodone)/ nocase
    condition:
        ($jp_unicode and $hidden_wrapper) or ($hidden_wrapper and $pharma_words)
}
