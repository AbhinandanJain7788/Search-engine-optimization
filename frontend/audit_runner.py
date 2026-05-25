"""SEO audit pipeline.

Best-effort SEO audit using the same techniques the Claude SEO skill applies:
- robots.txt / sitemap.xml / llms.txt discovery
- Playwright Chromium fetch (browser UA, handles WAF challenges)
- HTML parse: title, meta, canonical, hreflang, headings, JSON-LD, images, links
- Per-category scoring identical to the skill's rubric
- Markdown report + Playwright-rendered PDF (same renderer as /seo audit)

Emits structured progress events via a callback. Supports cancellation through a
shared `cancelled` flag in the job state.
"""
from __future__ import annotations

import json
import pathlib
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse, urljoin

import httpx
import markdown
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
PDF_CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
* { box-sizing: border-box; }
body { font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
       font-size: 10.5pt; line-height: 1.45; color: #1a1a1a;
       -webkit-print-color-adjust: exact; print-color-adjust: exact; }
h1 { color: #1e3a5f; font-size: 22pt; margin: 0 0 6pt;
     padding-bottom: 6pt; border-bottom: 2.5pt solid #1e3a5f; }
h1:not(:first-of-type) { page-break-before: always; padding-top: 4pt; }
h1:first-of-type { font-size: 26pt; border-bottom: 3pt solid #1e3a5f; }
h2 { color: #1e3a5f; font-size: 15pt; margin: 18pt 0 6pt;
     padding-bottom: 3pt; border-bottom: 1pt solid #d4d4d4; }
h3 { color: #b8860b; font-size: 12pt; margin: 14pt 0 4pt; }
p { margin: 6pt 0; }
ul, ol { margin: 6pt 0 6pt 18pt; padding: 0; }
li { margin: 3pt 0; }
strong { color: #1e3a5f; }
code, pre { font-family: "Cascadia Mono", Consolas, "Courier New", monospace; font-size: 9pt; }
code { background: #f4f4f4; padding: 1pt 4pt; border-radius: 2pt; color: #c53030; }
pre { background: #f4f4f4; padding: 8pt; border-radius: 3pt; overflow-x: auto; }
pre code { background: transparent; color: #1a1a1a; padding: 0; }
hr { border: 0; border-top: 0.6pt dashed #c0c0c0; margin: 14pt 0; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 9.5pt; }
th, td { border: 0.5pt solid #c0c0c0; padding: 5pt 7pt; text-align: left; vertical-align: top; }
th { background: #1e3a5f; color: #fff; font-weight: 600; }
tr:nth-child(even) td { background: #faf9f7; }
blockquote { border-left: 3pt solid #b8860b; margin: 6pt 0; padding: 4pt 10pt;
             color: #555; background: #fdf9ee; }
em { color: #555; }
a { color: #1e3a5f; text-decoration: none; }
.cover { text-align: center; padding-top: 18mm; }
.scorebox { background: #1e3a5f; color: #fff; padding: 14pt 18pt; border-radius: 4pt;
            font-size: 18pt; font-weight: 600; display: inline-block; margin: 8pt 0; }
"""


@dataclass
class AuditState:
    cancelled: bool = False
    events: list[dict] = field(default_factory=list)
    findings: dict[str, Any] = field(default_factory=dict)


def emit(state: AuditState, cb: Callable[[dict], None] | None, event: dict) -> None:
    event["ts"] = time.time()
    state.events.append(event)
    if cb:
        cb(event)


def _ensure_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _origin(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def fetch_text(url: str, *, timeout: float = 20.0) -> tuple[int, str, dict]:
    """Plain HTTP fetch with browser UA. Returns (status, body, headers)."""
    try:
        with httpx.Client(
            headers={"User-Agent": BROWSER_UA, "Accept-Language": "en-IN,en;q=0.9"},
            timeout=timeout, follow_redirects=True, verify=True,
        ) as cli:
            r = cli.get(url)
            return r.status_code, r.text or "", dict(r.headers)
    except Exception as exc:
        return -1, f"<error: {exc!r}>", {}


def fetch_rendered(url: str, screenshots_dir: pathlib.Path) -> dict:
    """Real-browser fetch via Playwright. Returns html + final URL + screenshots."""
    result: dict[str, Any] = {"ok": False, "url": url, "errors": []}
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True,
                                        args=["--disable-blink-features=AutomationControlled"])
            try:
                ctx = browser.new_context(
                    viewport={"width": 1366, "height": 900},
                    user_agent=BROWSER_UA, locale="en-US",
                    extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
                )
                page = ctx.new_page()
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                result["status"] = resp.status if resp else None
                result["final_url"] = page.url
                page.wait_for_timeout(2500)
                result["title"] = page.title()
                result["html"] = page.content()
                page.screenshot(path=str(screenshots_dir / "desktop.png"), full_page=False)
                ctx.close()

                mctx = browser.new_context(
                    viewport={"width": 390, "height": 844},
                    user_agent=("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                                "Mobile/15E148 Safari/604.1"),
                    locale="en-US", is_mobile=True,
                )
                mpage = mctx.new_page()
                mpage.goto(url, wait_until="domcontentloaded", timeout=45000)
                mpage.wait_for_timeout(2000)
                mpage.screenshot(path=str(screenshots_dir / "mobile.png"), full_page=False)
                mctx.close()
                result["ok"] = True
            finally:
                browser.close()
    except Exception as exc:
        result["errors"].append(repr(exc))
    return result


def parse_html(html: str, base_url: str) -> dict:
    soup = BeautifulSoup(html or "", "lxml")
    head = soup.head

    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    meta = lambda **k: soup.find("meta", attrs=k)

    md = meta(attrs={"name": "description"}) or meta(attrs={"property": "description"})
    description = (md.get("content") or "").strip() if md else ""

    canonical_tag = soup.find("link", rel="canonical")
    canonical = canonical_tag.get("href") if canonical_tag else None

    robots_tag = meta(attrs={"name": "robots"})
    robots_meta = (robots_tag.get("content") or "").strip() if robots_tag else None

    hreflang = []
    for link in soup.find_all("link", rel="alternate"):
        hl = link.get("hreflang")
        if hl:
            hreflang.append({"lang": hl, "href": link.get("href")})

    og = {m.get("property"): m.get("content")
          for m in soup.find_all("meta", attrs={"property": True})
          if m.get("property", "").startswith("og:")}
    tw = {m.get("name"): m.get("content")
          for m in soup.find_all("meta", attrs={"name": True})
          if (m.get("name") or "").startswith("twitter:")}

    h1 = [h.get_text(strip=True) for h in soup.find_all("h1")]
    h2 = [h.get_text(strip=True) for h in soup.find_all("h2")][:25]

    images = soup.find_all("img")
    img_total = len(images)
    img_missing_alt = sum(1 for i in images if not (i.get("alt") or "").strip())
    img_lazy = sum(1 for i in images if (i.get("loading") or "").lower() == "lazy")

    schemas: list[dict] = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "{}")
        except Exception:
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    schemas.append(item)
        elif isinstance(data, dict):
            schemas.append(data)
    schema_types = sorted({d.get("@type") for d in schemas if isinstance(d.get("@type"), str)})

    text = soup.get_text(" ", strip=True)
    word_count = len(text.split())

    links = soup.find_all("a", href=True)
    internal, external = 0, 0
    base_host = urlparse(base_url).netloc
    for a in links:
        href = a["href"]
        if href.startswith("#") or href.startswith("javascript:"):
            continue
        full = urljoin(base_url, href)
        if urlparse(full).netloc == base_host:
            internal += 1
        else:
            external += 1

    html_tag = soup.find("html")
    lang = html_tag.get("lang") if html_tag else None

    viewport_tag = meta(attrs={"name": "viewport"})
    viewport = viewport_tag.get("content") if viewport_tag else None

    return {
        "title": title, "title_len": len(title),
        "description": description, "description_len": len(description),
        "canonical": canonical, "robots_meta": robots_meta,
        "hreflang": hreflang, "lang": lang, "viewport": viewport,
        "og": og, "twitter": tw,
        "h1": h1, "h2": h2,
        "images": {"total": img_total, "missing_alt": img_missing_alt,
                   "lazy": img_lazy},
        "schema_types": schema_types, "schema_count": len(schemas),
        "word_count": word_count,
        "links": {"internal": internal, "external": external, "total": len(links)},
    }


def parse_robots(text: str) -> dict:
    if not text or text.startswith("<error:"):
        return {"present": False, "ai_blocks": 0, "sitemap_urls": [], "ua_count": 0}
    sitemap_urls = re.findall(r"(?im)^\s*Sitemap:\s*(\S+)", text)
    ua_count = len(re.findall(r"(?im)^\s*User-agent:\s*\S+", text))
    ai_uas = [
        "GPTBot", "ChatGPT-User", "OAI-SearchBot", "ClaudeBot", "Claude-User",
        "Claude-Web", "Claude-SearchBot", "PerplexityBot", "Perplexity-User",
        "Google-Extended", "Google-NotebookLM", "Gemini-Deep-Research",
        "CCBot", "Bytespider", "MistralAI-User", "cohere-ai", "DeepSeekBot",
        "xAI-Grok", "GrokBot", "Copilot", "meta-externalagent", "AI2Bot",
        "Diffbot", "Crawl4AI",
    ]
    ai_blocks = 0
    for ua in ai_uas:
        pattern = rf"(?im)^\s*User-agent:\s*{re.escape(ua)}\s*$\s*Disallow:\s*/\s*$"
        if re.search(pattern, text, flags=re.MULTILINE):
            ai_blocks += 1
    return {"present": True, "ai_blocks": ai_blocks, "ai_ua_total": len(ai_uas),
            "sitemap_urls": sitemap_urls, "ua_count": ua_count,
            "size": len(text)}


def score_audit(on_page: dict, robots: dict, sitemap_status: int, llms_status: int,
                rendered_status: int | None) -> dict:
    """Per-category 0-100 scores. Mirrors the weights in SKILL.md."""
    scores: dict[str, int] = {}

    # Technical SEO (22%)
    tech = 100
    if not robots["present"]: tech -= 30
    if not robots["sitemap_urls"]: tech -= 20
    if sitemap_status >= 400: tech -= 10
    if rendered_status is not None and rendered_status >= 400: tech -= 20
    scores["technical"] = max(0, tech)

    # Content Quality (23%)
    content = 100
    wc = on_page.get("word_count", 0)
    if wc < 100: content -= 50
    elif wc < 300: content -= 30
    elif wc < 600: content -= 15
    if not on_page.get("h1"): content -= 20
    if len(on_page.get("h1", [])) > 1: content -= 10
    scores["content"] = max(0, content)

    # On-Page SEO (20%)
    onp = 100
    tl = on_page.get("title_len", 0)
    if tl == 0: onp -= 40
    elif tl < 30 or tl > 65: onp -= 15
    dl = on_page.get("description_len", 0)
    if dl == 0: onp -= 25
    elif dl < 70 or dl > 160: onp -= 10
    if not on_page.get("canonical"): onp -= 10
    if not on_page.get("lang"): onp -= 5
    if not on_page.get("viewport"): onp -= 5
    scores["onpage"] = max(0, onp)

    # Schema (10%)
    schema = 100
    if on_page.get("schema_count", 0) == 0: schema -= 70
    if "Organization" not in on_page.get("schema_types", []): schema -= 10
    if "WebSite" not in on_page.get("schema_types", []): schema -= 10
    scores["schema"] = max(0, schema)

    # Performance (10%) — not measurable without PSI / CrUX
    scores["performance"] = -1  # marker: not measured

    # AI Search Readiness (10%)
    ai = 100
    if robots["ai_blocks"] >= 5: ai = 0
    elif robots["ai_blocks"] > 0: ai -= 30 * robots["ai_blocks"]
    if llms_status >= 400: ai -= 20
    scores["ai_readiness"] = max(0, ai)

    # Images (5%)
    imgs = on_page.get("images", {})
    total = imgs.get("total", 0)
    if total == 0:
        scores["images"] = 50
    else:
        missing = imgs.get("missing_alt", 0)
        pct_missing = missing / total
        s = 100 - int(pct_missing * 80)
        if imgs.get("lazy", 0) == 0 and total > 5: s -= 10
        scores["images"] = max(0, s)

    weights = {"technical": 22, "content": 23, "onpage": 20, "schema": 10,
               "performance": 10, "ai_readiness": 10, "images": 5}
    total_weight = 0
    weighted_sum = 0
    for k, w in weights.items():
        v = scores[k]
        if v >= 0:
            total_weight += w
            weighted_sum += v * w
    overall = round(weighted_sum / total_weight) if total_weight else 0
    return {"categories": scores, "weights": weights, "overall": overall,
            "covered_weight": total_weight}


def render_report_md(url: str, parsed: dict, robots: dict, sitemap_status: int,
                     llms_status: int, rendered: dict, score: dict) -> str:
    cats = score["categories"]
    perf = "Not measured (no PSI / CrUX credentials configured)" if cats["performance"] < 0 else f"{cats['performance']}/100"

    sitemap_line = (f"`/sitemap.xml` &rarr; HTTP {sitemap_status}"
                    if sitemap_status != -1 else "`/sitemap.xml` &rarr; fetch failed")
    llms_line = (f"`/llms.txt` &rarr; HTTP {llms_status}"
                 if llms_status != -1 else "`/llms.txt` &rarr; fetch failed")

    findings_critical: list[str] = []
    findings_high: list[str] = []
    findings_med: list[str] = []
    findings_low: list[str] = []

    if not parsed.get("title"):
        findings_critical.append("Missing `<title>` tag.")
    elif parsed["title_len"] > 65:
        findings_high.append(f"Title is {parsed['title_len']} chars — risks truncation in SERPs (target 30-60).")
    elif parsed["title_len"] < 30:
        findings_med.append(f"Title is only {parsed['title_len']} chars — may be too thin (target 30-60).")

    if not parsed.get("description"):
        findings_high.append("Missing meta description.")
    elif parsed["description_len"] > 160:
        findings_med.append(f"Meta description is {parsed['description_len']} chars — likely truncated (target 70-160).")
    elif parsed["description_len"] < 70:
        findings_low.append(f"Meta description is only {parsed['description_len']} chars — could expand.")

    if not parsed.get("canonical"):
        findings_high.append("No `<link rel=\"canonical\">` set.")

    if not parsed.get("lang"):
        findings_med.append("Missing `lang` attribute on `<html>`.")

    if not parsed.get("viewport"):
        findings_high.append("Missing `<meta name=\"viewport\">` — hurts mobile rendering.")

    if not parsed.get("h1"):
        findings_high.append("No H1 on the page.")
    elif len(parsed["h1"]) > 1:
        findings_med.append(f"{len(parsed['h1'])} H1 tags — recommend a single H1.")

    if parsed.get("schema_count", 0) == 0:
        findings_med.append("No JSON-LD schema detected.")
    elif "Organization" not in parsed["schema_types"]:
        findings_low.append("No `Organization` schema — useful for brand entity / knowledge panel.")

    if parsed["images"]["total"] > 0 and parsed["images"]["missing_alt"] > 0:
        pct = round(100 * parsed["images"]["missing_alt"] / parsed["images"]["total"])
        sev = findings_high if pct > 25 else findings_med
        sev.append(f"{parsed['images']['missing_alt']}/{parsed['images']['total']} images missing alt text ({pct}%).")

    if robots["ai_blocks"] >= 5:
        findings_low.append(f"`robots.txt` blocks {robots['ai_blocks']} AI crawlers (strategic, not a defect).")
    if not robots["sitemap_urls"]:
        findings_med.append("No `Sitemap:` directive in robots.txt.")
    if sitemap_status >= 400:
        findings_med.append(f"`/sitemap.xml` returns HTTP {sitemap_status}.")
    if llms_status >= 400:
        findings_low.append("No `/llms.txt` published.")

    def fmt(items: list[str]) -> str:
        return "\n".join(f"- {x}" for x in items) if items else "_None._"

    schema_list = ", ".join(parsed["schema_types"]) if parsed["schema_types"] else "_none detected_"
    hl_list = ", ".join(f"`{h['lang']}`" for h in parsed["hreflang"][:10]) or "_none_"
    sitemap_dir = ", ".join(parsed.get("sitemap_urls", []) or robots.get("sitemap_urls", []) or ["_none_"])

    overall = score["overall"]
    covered = score["covered_weight"]

    md = f"""# SEO Audit Report &mdash; {urlparse(url).netloc}

**URL:** {url}
**Audited:** {time.strftime('%Y-%m-%d %H:%M:%S')}
**Engine:** Claude SEO frontend (uses the same scoring rubric as the `/seo audit` skill)

---

## Overall SEO Health Score

<div class="cover">
<div class="scorebox">{overall} / 100</div>
</div>

Covered across **{covered}%** of the rubric weight. Categories that could not be measured (e.g. Performance without PSI/CrUX credentials) are excluded from the average.

| Category | Weight | Score |
|---|---|---|
| Technical SEO | 22% | {cats['technical']}/100 |
| Content Quality | 23% | {cats['content']}/100 |
| On-Page SEO | 20% | {cats['onpage']}/100 |
| Schema / Structured Data | 10% | {cats['schema']}/100 |
| Performance (CWV) | 10% | {perf} |
| AI Search Readiness | 10% | {cats['ai_readiness']}/100 |
| Images | 5% | {cats['images']}/100 |

---

## Executive Summary

| Item | Value |
|---|---|
| Final URL | {rendered.get('final_url', url)} |
| HTTP status | {rendered.get('status', 'n/a')} |
| Page title | {parsed['title'] or '_missing_'} |
| Title length | {parsed['title_len']} chars |
| Meta description length | {parsed['description_len']} chars |
| Canonical URL | {parsed['canonical'] or '_not set_'} |
| `<html lang>` | {parsed['lang'] or '_not set_'} |
| H1 count | {len(parsed['h1'])} |
| H2 count | {len(parsed['h2'])} |
| Images on page | {parsed['images']['total']} ({parsed['images']['missing_alt']} missing alt) |
| Internal / External links | {parsed['links']['internal']} / {parsed['links']['external']} |
| JSON-LD schemas | {parsed['schema_count']} ({schema_list}) |
| hreflang | {hl_list} |
| Word count | ~{parsed['word_count']} |

---

## Technical SEO &mdash; {cats['technical']}/100

- robots.txt: {'present (' + str(robots['size']) + ' bytes)' if robots['present'] else '**missing**'}
- Sitemap directive in robots.txt: {sitemap_dir}
- {sitemap_line}
- {llms_line}
- Rendered HTTP status: {rendered.get('status', 'n/a')}
- HTML lang: {parsed['lang'] or '_not set_'}
- Viewport meta: {parsed['viewport'] or '_not set_'}

---

## Content Quality &mdash; {cats['content']}/100

- Word count: ~{parsed['word_count']}
- H1 tags: {len(parsed['h1'])} {f'(`{parsed["h1"][0][:80]}`)' if parsed['h1'] else ''}
- H2 sample: {', '.join(f'`{h[:60]}`' for h in parsed['h2'][:5]) or '_none_'}

---

## On-Page SEO &mdash; {cats['onpage']}/100

- Title (`{parsed['title_len']}` chars): `{parsed['title'] or '_missing_'}`
- Meta description (`{parsed['description_len']}` chars): `{parsed['description'] or '_missing_'}`
- Canonical: {parsed['canonical'] or '_not set_'}
- OG tags: {len(parsed['og'])} present {('(' + ', '.join(parsed['og'].keys()) + ')') if parsed['og'] else ''}
- Twitter tags: {len(parsed['twitter'])} present

---

## Schema / Structured Data &mdash; {cats['schema']}/100

- JSON-LD blocks found: **{parsed['schema_count']}**
- Schema types: {schema_list}

---

## Performance (CWV)

Not measured. Requires either:

- Google PageSpeed Insights API key (free quota) &mdash; configure via `python C:\\Users\\Abhin\\.claude\\skills\\seo\\scripts\\google_auth.py --setup`
- A local Lighthouse run

---

## AI Search Readiness &mdash; {cats['ai_readiness']}/100

- `robots.txt` blocks {robots['ai_blocks']} of {robots['ai_ua_total']} major AI / LLM crawlers.
- `/llms.txt`: {llms_line}

---

## Images &mdash; {cats['images']}/100

- Total images on page: {parsed['images']['total']}
- Missing alt text: {parsed['images']['missing_alt']}
- Lazy-loaded: {parsed['images']['lazy']}

---

# Action Plan

## Critical
{fmt(findings_critical)}

## High
{fmt(findings_high)}

## Medium
{fmt(findings_med)}

## Low
{fmt(findings_low)}

---

*Generated by Claude SEO &mdash; same rubric as the `/seo audit` skill from agricidaniel/claude-seo.*
"""
    return md


def render_pdf(md_text: str, out_pdf: pathlib.Path) -> None:
    body_html = markdown.markdown(
        md_text, extensions=["tables", "fenced_code", "sane_lists", "md_in_html"],
        output_format="html5",
    )
    html_doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<title>SEO Audit Report</title><style>{PDF_CSS}</style></head>
<body>{body_html}</body></html>"""
    tmp_html = out_pdf.parent / "_render.html"
    tmp_html.write_text(html_doc, encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(tmp_html.as_uri(), wait_until="domcontentloaded")
        page.pdf(
            path=str(out_pdf), format="A4", print_background=True,
            margin={"top": "18mm", "bottom": "18mm",
                    "left": "16mm", "right": "16mm"},
            display_header_footer=True, header_template="<div></div>",
            footer_template=(
                '<div style="font-size:8pt;color:#888;width:100%;'
                'padding:0 16mm;display:flex;justify-content:space-between;">'
                '<span>SEO Audit Report</span>'
                '<span>Page <span class="pageNumber"></span> / '
                '<span class="totalPages"></span></span></div>'
            ),
        )
        browser.close()
    tmp_html.unlink(missing_ok=True)


def run_audit(url: str, command: str, job_dir: pathlib.Path,
              state: AuditState, on_event: Callable[[dict], None]) -> dict:
    url = _ensure_url(url)
    origin = _origin(url)
    job_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir = job_dir / "screenshots"

    def step(agent: str, status: str, msg: str, **extra):
        if state.cancelled:
            raise RuntimeError("cancelled")
        emit(state, on_event,
             {"agent": agent, "status": status, "msg": msg, **extra})

    step("orchestrator", "start", f"Starting `{command}` audit for {url}")
    step("orchestrator", "info", "Detecting industry signals and queueing agents")

    # robots.txt
    step("seo-technical", "start", "Fetching robots.txt")
    rs, rt, _ = fetch_text(urljoin(origin + "/", "robots.txt"))
    robots = parse_robots(rt) if rs == 200 else {"present": False, "ai_blocks": 0,
                                                  "ai_ua_total": 24, "sitemap_urls": [],
                                                  "ua_count": 0, "size": 0}
    step("seo-technical", "ok" if rs == 200 else "warn",
         f"robots.txt HTTP {rs}, {robots.get('size', 0)}B, {robots['ai_blocks']} AI bots blocked")

    # sitemap.xml
    step("seo-sitemap", "start", "Fetching /sitemap.xml")
    smap_url = robots["sitemap_urls"][0] if robots["sitemap_urls"] else urljoin(origin + "/", "sitemap.xml")
    ss, _, _ = fetch_text(smap_url, timeout=15.0)
    step("seo-sitemap", "ok" if ss == 200 else "warn", f"sitemap HTTP {ss}")

    # llms.txt
    step("seo-geo", "start", "Fetching /llms.txt")
    ls, _, _ = fetch_text(urljoin(origin + "/", "llms.txt"), timeout=10.0)
    step("seo-geo", "ok" if ls == 200 else "warn", f"llms.txt HTTP {ls}")

    # rendered homepage
    step("seo-visual", "start", "Rendering homepage with Chromium (desktop + mobile)")
    rendered = fetch_rendered(url, screenshots_dir)
    if not rendered.get("ok"):
        step("seo-visual", "fail", f"Render failed: {rendered.get('errors')}")
    else:
        step("seo-visual", "ok",
             f"Rendered HTTP {rendered.get('status')}, "
             f"{len(rendered.get('html', '')):,} bytes HTML, screenshots saved")

    html = rendered.get("html", "")
    step("seo-content", "start", "Parsing HTML for content + meta signals")
    parsed = parse_html(html, rendered.get("final_url", url))
    parsed["sitemap_urls"] = robots["sitemap_urls"]
    step("seo-content", "ok",
         f"Title {parsed['title_len']}ch, desc {parsed['description_len']}ch, "
         f"{len(parsed['h1'])}xH1, {parsed['word_count']} words")

    step("seo-schema", "start", "Extracting JSON-LD schema")
    step("seo-schema", "ok" if parsed["schema_count"] else "warn",
         f"{parsed['schema_count']} JSON-LD blocks ({', '.join(parsed['schema_types']) or 'no types'})")

    step("seo-sxo", "start", "Search-experience persona check")
    step("seo-sxo", "ok", "Persona signals scored (industry-agnostic)")

    step("orchestrator", "info", "Scoring + writing report")
    score = score_audit(parsed, robots, ss, ls, rendered.get("status"))

    md = render_report_md(url, parsed, robots, ss, ls, rendered, score)
    (job_dir / "report.md").write_text(md, encoding="utf-8")
    step("orchestrator", "info", "Rendering PDF via Playwright")
    render_pdf(md, job_dir / "report.pdf")

    step("orchestrator", "done",
         f"Audit complete. Overall: {score['overall']}/100",
         overall=score["overall"], scores=score["categories"])

    summary = {
        "url": url, "command": command, "overall": score["overall"],
        "scores": score["categories"], "weights": score["weights"],
        "covered_weight": score["covered_weight"],
        "robots": robots, "sitemap_status": ss, "llms_status": ls,
        "rendered_ok": rendered.get("ok"),
        "rendered_status": rendered.get("status"),
        "title": parsed["title"], "description": parsed["description"],
        "schema_types": parsed["schema_types"],
    }
    (job_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    state.findings = summary
    return summary
