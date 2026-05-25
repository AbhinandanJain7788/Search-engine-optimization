"""Render FULL-AUDIT-REPORT.md to a styled A4 PDF via Playwright Chromium."""
import pathlib
import markdown
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).parent
MD = ROOT / "FULL-AUDIT-REPORT.md"
PDF = ROOT / "FULL-AUDIT-REPORT.pdf"

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
* { box-sizing: border-box; }
body {
  font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  font-size: 10.5pt; line-height: 1.45; color: #1a1a1a;
  -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
h1 { color: #1e3a5f; font-size: 22pt; margin: 0 0 6pt; padding-bottom: 6pt;
     border-bottom: 2.5pt solid #1e3a5f; }
h1:not(:first-of-type) { page-break-before: always; padding-top: 4pt; }
h2 { color: #1e3a5f; font-size: 15pt; margin: 18pt 0 6pt; padding-bottom: 3pt;
     border-bottom: 1pt solid #d4d4d4; }
h3 { color: #b8860b; font-size: 12pt; margin: 14pt 0 4pt; }
p { margin: 6pt 0; }
ul, ol { margin: 6pt 0 6pt 18pt; padding: 0; }
li { margin: 3pt 0; }
strong { color: #1e3a5f; }
code, pre {
  font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
  font-size: 9pt;
}
code { background: #f4f4f4; padding: 1pt 4pt; border-radius: 2pt; color: #c53030; }
pre { background: #f4f4f4; padding: 8pt; border-radius: 3pt; overflow-x: auto; }
pre code { background: transparent; color: #1a1a1a; padding: 0; }
hr { border: 0; border-top: 0.6pt dashed #c0c0c0; margin: 14pt 0; }
table {
  border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 9.5pt;
}
th, td {
  border: 0.5pt solid #c0c0c0; padding: 5pt 7pt; text-align: left;
  vertical-align: top;
}
th { background: #1e3a5f; color: #fff; font-weight: 600; }
tr:nth-child(even) td { background: #faf9f7; }
blockquote {
  border-left: 3pt solid #b8860b; margin: 6pt 0; padding: 4pt 10pt;
  color: #555; background: #fdf9ee;
}
em { color: #555; }
a { color: #1e3a5f; text-decoration: none; }

/* Special handling for the small ASCII arrows used in the report */
.report-meta { color: #555; font-size: 9.5pt; }

/* Footer/cover treatment for the very first H1 */
h1:first-of-type {
  border-bottom: 3pt solid #1e3a5f;
  font-size: 26pt;
}
"""

def main():
    md_text = MD.read_text(encoding="utf-8")
    body_html = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )
    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>SEO Audit — amazon.in</title>
<style>{CSS}</style>
</head>
<body>
{body_html}
</body>
</html>"""

    tmp_html = ROOT / "_report_render.html"
    tmp_html.write_text(html_doc, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(tmp_html.as_uri(), wait_until="domcontentloaded")
        page.pdf(
            path=str(PDF),
            format="A4",
            print_background=True,
            margin={"top": "18mm", "bottom": "18mm", "left": "16mm", "right": "16mm"},
            display_header_footer=True,
            header_template='<div></div>',
            footer_template=(
                '<div style="font-size:8pt;color:#888;width:100%;'
                'padding:0 16mm;display:flex;justify-content:space-between;">'
                '<span>SEO Audit — amazon.in — 2026-05-21</span>'
                '<span>Page <span class="pageNumber"></span> / '
                '<span class="totalPages"></span></span></div>'
            ),
        )
        browser.close()
    tmp_html.unlink(missing_ok=True)
    print(f"OK -> {PDF}  ({PDF.stat().st_size} bytes)")

if __name__ == "__main__":
    main()
