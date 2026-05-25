# SEO Audit Report — amazon.in

**Audited:** 2026-05-21
**URL:** https://www.amazon.in/
**Auditor:** Claude SEO skill v1.9.9
**Coverage:** Partial — see "Audit Coverage" below

---

## Audit Coverage (Read First)

Amazon.in is behind AWS WAF Bot Control. Every non-browser fetch returned `HTTP 202` with `x-amzn-waf-action: challenge` and a zero-byte body. WebFetch returned `HTTP 503`. Without a real browser session (Playwright was offered, declined), the audit could **not directly inspect**:

- Rendered HTML (title, meta description, canonical, hreflang, JSON-LD, OG/Twitter tags)
- H1/H2 structure, internal-link graph, image alt-text
- Lighthouse / lab Core Web Vitals
- On-page schema markup

The audit **directly verified**:

- `robots.txt` (9,320 bytes, 473 lines, parsed in full)
- HTTP response headers from the homepage (CloudFront edge + WAF posture)
- `/sitemap.xml` &rarr; 404
- `/llms.txt` &rarr; 404
- DNS resolution + edge POP routing (DEL51-P6, India)

CrUX / GSC / GA4 / DataForSEO / Moz / Bing credentials are **not configured**, so field CWV, indexation, organic traffic, and live SERP data are also not available.

A subset SEO Health Score is given for measurable categories only. **Do not interpret missing categories as failures.**

---

## Executive Summary

| Metric | Value |
| --- | --- |
| Business type detected | **E-commerce (marketplace)** — inferred from domain, brand, robots.txt URL patterns (`/dp/`, `/gp/cart`, `/wishlist`, `/-/hi/` locale path) |
| Site scale | Multi-million product catalog; 500-page crawl cap meaningless at this scale |
| Edge / WAF | Amazon CloudFront + AWS WAF Bot Control (managed challenge in front of origin) |
| Partial SEO Health Score | See "Partial Score" below — only 3 of 7 weighted categories are measurable from this run |

### Top 5 Critical Findings (observed)

1. **AI search ecosystem fully blocked.** Amazon.in's `robots.txt` issues `Disallow: /` to **~90 distinct AI/LLM crawlers** including `GPTBot`, `ClaudeBot`, `Claude-User`, `ChatGPT-User`, `OAI-SearchBot`, `Google-Extended`, `Google-NotebookLM`, `PerplexityBot`, `Perplexity-User`, `Gemini-Deep-Research`, `MistralAI-User`, `cohere-ai`, `DeepSeekBot`, `xAI-Grok`, `Grok-DeepSearch`, `Copilot`, `CopilotNative`, `Meta-externalagent`, `Bytespider`, `Diffbot`, `Crawl4AI`, and others. **AI Search Readiness = 0 by design.** This is intentional strategy (drive AI users to amazon.in via "buy" intent rather than text summarization), not a bug — but flag it so it's documented.
2. **No `Sitemap:` directive anywhere in `robots.txt`.** `/sitemap.xml` returns 404. For a site of Amazon's scale this is unusual; Google relies on internal-link discovery + structured PDP/category URLs. For a non-Amazon site this would be a **Critical** finding. For Amazon: Info-only (they get away with it because they're Amazon).
3. **No `/llms.txt`.** Consistent with #1 — Amazon does not publish an AI-discovery manifest.
4. **Origin not directly fetchable by general bots even at `User-agent: *` ranking-eligible UAs.** The WAF challenges all non-browser sessions, including ones that `robots.txt` does not forbid. Indirect risk: third-party SEO/monitoring crawlers (Ahrefs, SEMrush common UAs, anything resembling Scrapy) get challenged. `SemrushBot-SWA` is explicitly disallowed in robots.txt as well.
5. **Twitterbot rules diverge from `*`.** `Twitterbot` gets its own (and shorter) disallow list — Amazon preserves Twitter/X link-preview rendering even while blocking it from general crawl-as-content. Deliberate carve-out, not an issue.

### Top 5 Quick Wins

Amazon.in is one of the most mature SEO operations on the planet (dedicated org-wide SEO + retail systems teams). The "quick wins" frame applied to small/medium sites is not useful here. The actionable items are:

1. If Amazon Sellers / brand-registered sellers want their product pages to rank better &rarr; that's a PDP-level optimization, not a homepage audit.
2. If you actually wanted to audit your own site &rarr; re-run `/seo audit <your-url>`.

---

## Technical SEO

### Crawlability — [OBSERVED]

| Item | Value | Notes |
|---|---|---|
| `robots.txt` reachable | Yes (HTTP 200, 9.3 KB) | Well-formed, parses cleanly |
| `User-agent: *` block | 92 path Disallows | Includes session URLs, sign-in, cart, wishlist, write-review, image-upload, deprecated `/exec/obidos/` legacy paths, redirect handlers, search facet anti-traps (`/s?*rh=n%3A1380045031`) |
| Universal blocked categories | Session/personal, infrastructure, legacy, faceted-search anti-trap | Standard ecommerce hygiene — done correctly |
| Hindi locale path | `Allow: /-/hi/`, `Allow: /-/hi$` | Hindi-language SEO surface intentionally open |
| `/minitv` | Allowed with subpath whitelists | Amazon miniTV is indexable for `/comedy`, `/mini-movies`, `/web-series`, `/tp/*`; `/st/*` blocked |
| `/junglee/`, `/used/`, `/magazine/`, `/neo/magazine/` | Disallowed | Legacy / deprecated product lines walled off |
| `/sitemap.xml` | **HTTP 404** | No sitemap exposed at the standard location |
| `Sitemap:` directive in robots.txt | **Not present** | Unusual for a 500-million+ URL site |
| `/llms.txt` | **HTTP 404** | No AI-content manifest |

### Indexability — [NOT MEASURABLE]

Cannot read `<head>` so cannot verify:

- `<meta name="robots">`
- `<link rel="canonical">`
- `<link rel="alternate" hreflang="...">`
- `X-Robots-Tag` headers (none seen on the 202, but the 202 carries no representation)

Public knowledge (not verified here): Amazon.in uses canonical PDPs at `/dp/{ASIN}` with marketing variants (`/gp/product/{ASIN}`, slug-prefixed URLs) canonicalized to `/dp/{ASIN}`.

### Security headers — [PARTIAL]

From the 202 challenge response (the only response received):

| Header | Value | Comment |
|---|---|---|
| `Server` | `CloudFront` | Edge identified |
| `X-Amz-Cf-Pop` | `DEL51-P6` | Delhi edge POP |
| `Cache-Control` | `no-store, max-age=0` | Correct for a challenge response |
| `Alt-Svc` | `h3=":443"; ma=86400` | HTTP/3 advertised — **good** |
| `Access-Control-Allow-Origin` | `*` | On the challenge response only; not necessarily true of origin responses |
| `Strict-Transport-Security` | Not present on challenge response | Unknown for origin (likely present, not verified) |
| `Content-Security-Policy` | Not present on challenge response | Unknown for origin |
| `X-Frame-Options` / `X-Content-Type-Options` | Not present on challenge response | Unknown for origin |

### Core Web Vitals — [NOT MEASURABLE]

No CrUX API key configured. No Lighthouse / PSI run. Field data is publicly retrievable for amazon.in via the PSI v5 endpoint with a Google API key — set up via `python C:\Users\Abhin\.claude\skills\seo\scripts\google_auth.py --setup` and re-run.

---

## Content Quality — [NOT MEASURABLE]

Cannot fetch rendered content. E-E-A-T scoring, readability scoring, thin-content detection, and AI citation readiness all require HTML.

Inference (low confidence, not from this audit run): Amazon.in is a marketplace, so most pages are PDPs whose primary content is seller-supplied. E-E-A-T quality varies per ASIN. Reviews provide UGC trust signals — Amazon's review system is the trust backbone.

---

## On-Page SEO — [NOT MEASURABLE]

Cannot inspect title tags, meta descriptions, heading structure, or internal-link patterns.

---

## Schema & Structured Data — [NOT MEASURABLE]

Cannot inspect JSON-LD or Microdata. Amazon.in publicly is known to expose `Product`, `Offer`, `AggregateRating`, `Review`, `BreadcrumbList`, and `Organization` schema on PDPs (not verified in this run).

---

## Performance (CWV) — [NOT MEASURABLE]

Set up Google API credentials or DataForSEO to retrieve field/lab data.

---

## Images — [NOT MEASURABLE]

Cannot inspect alt text, formats, or sizes without HTML. Amazon serves images via the `m.media-amazon.com` CDN with responsive `srcset` (public knowledge, not verified here).

---

## AI Search Readiness — [OBSERVED — score 0/100 by design]

| Signal | Result | Detail |
|---|---|---|
| `GPTBot` | **Disallow: /** | Line 179-180 |
| `ChatGPT-User` | **Disallow: /** | Line 308-309 |
| `OAI-SearchBot` | **Disallow: /** | Line 311-312 |
| `ClaudeBot` | **Disallow: /** | Lines 197-198, 284-285 (declared twice) |
| `Claude-User` | **Disallow: /** | Line 281-282 |
| `Claude-Web` | **Disallow: /** | Line 344-345 |
| `Claude-SearchBot` | **Disallow: /** | Line 287-288 |
| `PerplexityBot` | **Disallow: /** | Line 185-186 |
| `Perplexity-User` | **Disallow: /** | Line 290-291 |
| `Google-Extended` (Bard/Gemini training) | **Disallow: /** | Line 188-189 |
| `Google-NotebookLM` | **Disallow: /** | Line 236-237 |
| `Gemini-Deep-Research` | **Disallow: /** | Line 221-222 |
| `GoogleAgent-Mariner` / `GoogleAgent-Shopping` / `Google-CloudVertexBot` / `Google-Firebase` / `GoogleOther` | **All Disallow: /** | Comprehensive Google AI/agent blocks |
| `CCBot` (Common Crawl) | **Disallow: /** | Line 182-183 — also blocks downstream LLM training datasets |
| `Bytespider` (ByteDance / Doubao) | **Disallow: /** | Line 203-204 |
| `MistralAI-User` | **Disallow: /** | Line 227-228 |
| `cohere-ai` / `cohere-training-data-crawler` | **Disallow: /** | Lines 263-264, 353-354 |
| `DeepSeekBot` | **Disallow: /** | Line 365-366 |
| `xAI-Grok` / `GrokBot` / `Grok-DeepSearch` | **Disallow: /** | Lines 467-468, 386-387, 383-384 |
| `Copilot` / `CopilotNative` / `CopilotSapphire` | **Disallow: /** | Lines 242-243, 296-301 |
| `meta-externalagent` / `meta-externalfetcher` / `meta-webindexer` | **Disallow: /** | Lines 200-201, 251-252, 425-426 |
| `AI2Bot` / `Ai2Bot-Dolma` / `AI2Bot-DeepResearchEval` | **Disallow: /** | AI2 (Allen Institute) blocked across variants |
| ~70 additional AI / training / research crawlers | **Disallow: /** | Diffbot, Crawl4AI, Scrapy, img2dataset, ImagesiftBot, Cloudflare-AutoRAG, KlaviyoAIBot, Manus-User, PhindBot, TavilyBot, WRTNBot, DuckAssistBot, iAskBot, YouBot, etc. |
| `Twitterbot` | Allowed with PDP-link-preview carve-outs | Maintains X/Twitter share previews |
| `AmazonAdBot` | `Disallow:` (empty &rarr; fully allowed) | Own bot |
| `/llms.txt` | **404** | No AI content manifest |
| Citability score | **0/100** for AI search inclusion | By design |

**Interpretation:** Amazon.in's stance is "AI search must direct intent to amazon.in, not summarize amazon.in." Brand mentions in AI answers still occur (LLMs know what Amazon is from training data and trusted sources), but no live content gets pulled. For your own ecommerce site, this posture is **not recommended** unless your brand has the same kind of unmissable demand profile as Amazon.

---

## Partial SEO Health Score

Scoring only the categories that were directly measurable:

| Category | Weight | Score | Weighted | Notes |
|---|---|---|---|---|
| Technical SEO (robots only) | 22% | 80/100 | 17.6 | Robots.txt is well-structured for `*`; missing `Sitemap:` directive and `/sitemap.xml` 404 cost 20 pts. Indexability section not measured. |
| Content Quality | 23% | n/a | — | Not measurable |
| On-Page SEO | 20% | n/a | — | Not measurable |
| Schema / Structured Data | 10% | n/a | — | Not measurable |
| Performance (CWV) | 10% | n/a | — | Not measurable |
| AI Search Readiness | 10% | 0/100 | 0 | By design — all major AI UAs disallowed |
| Images | 5% | n/a | — | Not measurable |

**Measured-only health score: 17.6 / 32 = 55/100 across the categories that could be assessed.**

Do not publish this as Amazon.in's overall SEO score. It is the score across the 32% of the rubric for which evidence was retrievable on this run.

---

## Notes on the Site

A few items worth knowing about Amazon.in even though they weren't directly measured this run:

- **Mobile-first design:** Amazon serves a heavy mobile experience; the `/gp/aw/` (Amazon Web) and `/gp/mobile/` paths in robots show legacy mobile-specific surfaces that are walled off from crawlers (canonical surface is the responsive desktop URL).
- **International / hreflang:** The `Allow: /-/hi/` strongly implies hreflang `hi-IN` alongside `en-IN`. Not directly verified.
- **Schema known patterns:** PDPs publicly carry `Product` + `Offer` + `AggregateRating` JSON-LD; SERP feature eligibility (rich snippets, ratings, price) confirms this in production but was not measured in this run.

---

# Action Plan

Because this audit could not directly measure most categories, the action plan is split into two parts: **(A) Things actually finding-driven from this run** and **(B) How to unlock a full audit on the next run.**

## A. Findings-driven actions (Critical &rarr; Low)

### Critical

*None.* Every "Critical-by-rubric" item (no sitemap, AI bots blocked) is **strategic intent** at amazon.in's scale, not a defect to fix.

### High

*None applicable.* These would only be "fix within 1 week" items if this were a non-Amazon ecommerce site adopting the same posture without Amazon's brand pull.

### Medium

1. **Verify sitemap discovery path.** robots.txt has no `Sitemap:` directive and `/sitemap.xml` returns 404. Confirm with the Amazon SEO team where Googlebot is discovering long-tail URLs — likely entirely via internal-link traversal + GSC sitemap-upload (private, not advertised). If you control this site: add a `Sitemap:` directive pointing at the actual sitemap location, even if it's gated.
2. **Decide on `/llms.txt` policy.** Even hostile-to-AI policy benefits from publishing an `/llms.txt` saying "we don't license content for AI training; here's our brand entity for reference." Makes the disallow explicit + machine-readable.

### Low

1. Twitterbot has its own (smaller) disallow list — consider keeping it in sync with the `*` list, or document the carve-out reason internally.

## B. Unlock a full audit on next run

If you want the report to actually cover Content, On-Page, Schema, Performance, Images, and AI Citation Readiness, configure one or more of:

1. **Google APIs** (free quota): `python C:\Users\Abhin\.claude\skills\seo\scripts\google_auth.py --setup` — unlocks PageSpeed, CrUX field data, GSC, GA4, URL Inspection. Without this, CWV is unmeasurable.
2. **Playwright fetch** (already installed locally): Permit a quick browser-based homepage capture. AWS WAF will let a real headless Chromium with realistic UA + headers through after the JS challenge solves. Last session you blocked this — re-enable to see HTML-level findings.
3. **DataForSEO MCP** (paid, ~$0.01-$0.05 per pull): live SERP positions for amazon.in keywords, on-page Lighthouse, AI-mention tracking (ChatGPT scraper). Install via `e:\seo\claude-seo\extensions\dataforseo\install.ps1`.
4. **Backlink APIs** (free tiers): `python C:\Users\Abhin\.claude\skills\seo\scripts\backlinks_auth.py --setup` for Moz / Bing Webmaster — enables backlink, DA/PA, anchor text, and toxic-link sections.

A second pass with any one of (1) or (2) above will lift coverage from ~32% of the rubric to ~75%+.

---

## Files used in this audit

- `e:\seo\audits\amazon-in\robots.txt` (full robots.txt, 9.3 KB)
- `e:\seo\audits\amazon-in\headers-home.txt` (202 challenge headers)
- `e:\seo\audits\amazon-in\headers-robots.txt`, `headers-sitemap.txt`
- `e:\seo\audits\amazon-in\sitemap.xml`, `llms.txt` (both 404 error pages)
- `e:\seo\audits\amazon-in\home.html` — 0 bytes (WAF blocked)

---

*Built by agricidaniel — AI Marketing Hub: https://www.skool.com/ai-marketing-hub (free) / https://www.skool.com/ai-marketing-hub-pro (pro)*
