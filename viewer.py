"""Local web viewer for the crawled JSONL results.

Run:
    python viewer.py
    # then your browser opens http://localhost:8000

Or with options:
    python viewer.py --port 9000 --output data/ai.jsonl --no-browser

This uses only the Python standard library — no Flask, no extra installs.
The page loads all results once and filters them client-side, which is fast
and snappy for any reasonable crawl size (thousands of pages).
"""

import argparse
import http.server
import json
import os
import socketserver
import sys
import threading
import time
import webbrowser
from urllib.parse import urlparse

import config


# ---------------------------------------------------------------------
# Embedded HTML page (single-file viewer, no external assets except fonts)
# ---------------------------------------------------------------------
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Topic Crawler — Results</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Newsreader:ital,wght@0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0e1116;
    --bg-elev: #161b22;
    --border: #232a36;
    --text: #e6e3d8;
    --text-mute: #8b96a6;
    --text-dim: #5a6373;
    --accent: #e8a547;
    --accent-soft: #e8a54722;
    --score-bg: #1a2230;
    --mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
    --serif: 'Newsreader', Georgia, 'Times New Roman', serif;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--serif);
    font-size: 16px;
    line-height: 1.5;
    min-height: 100vh;
    background-image:
      radial-gradient(circle at 15% -10%, #1a1f2a 0%, transparent 45%),
      radial-gradient(circle at 85% 110%, #1f1a14 0%, transparent 50%);
    background-attachment: fixed;
  }

  header {
    border-bottom: 1px solid var(--border);
    padding: 28px 40px 20px;
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 24px;
    flex-wrap: wrap;
  }
  .brand {
    font-family: var(--mono);
    font-weight: 700;
    font-size: 14px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--accent);
  }
  .brand .arrow { color: var(--text-dim); margin: 0 8px; }
  .brand .sub { color: var(--text); }
  .stats {
    font-family: var(--mono);
    font-size: 12px;
    color: var(--text-mute);
    letter-spacing: 0.05em;
  }
  .stats span { color: var(--text); margin: 0 2px; }

  .filters {
    position: sticky;
    top: 0;
    z-index: 10;
    background: rgba(14, 17, 22, 0.85);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
    padding: 16px 40px;
    display: grid;
    grid-template-columns: 2fr 1fr 1.2fr 1fr;
    gap: 12px;
  }
  .field { display: flex; flex-direction: column; gap: 4px; }
  .field label {
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--text-dim);
  }
  .field input, .field select {
    font-family: var(--mono);
    font-size: 13px;
    background: var(--bg-elev);
    color: var(--text);
    border: 1px solid var(--border);
    padding: 8px 10px;
    outline: none;
    transition: border-color 120ms;
  }
  .field input:focus, .field select:focus { border-color: var(--accent); }
  .field input::placeholder { color: var(--text-dim); }

  main {
    padding: 32px 40px 80px;
    max-width: 1200px;
    margin: 0 auto;
  }

  .empty {
    text-align: center;
    padding: 80px 20px;
    color: var(--text-mute);
    font-style: italic;
  }
  .empty code {
    font-family: var(--mono);
    color: var(--accent);
    background: var(--accent-soft);
    padding: 2px 8px;
    font-style: normal;
  }

  .result {
    display: grid;
    grid-template-columns: 110px 1fr;
    gap: 28px;
    padding: 28px 0;
    border-bottom: 1px solid var(--border);
    transition: background 200ms;
    opacity: 0;
    animation: fadeIn 400ms ease-out forwards;
  }
  .result:hover { background: rgba(255,255,255,0.018); }
  @keyframes fadeIn { to { opacity: 1; } }

  .result-meta {
    display: flex;
    flex-direction: column;
    gap: 10px;
    align-items: flex-start;
  }
  .score {
    font-family: var(--mono);
    font-weight: 700;
    font-size: 28px;
    color: var(--accent);
    line-height: 1;
    padding: 10px 14px;
    background: var(--score-bg);
    border-left: 2px solid var(--accent);
    min-width: 90px;
    text-align: center;
  }
  .score .label {
    display: block;
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.18em;
    color: var(--text-mute);
    margin-top: 6px;
  }
  .depth {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--text-dim);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    padding-left: 4px;
  }

  .result-body { min-width: 0; }
  .domain {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-mute);
    letter-spacing: 0.05em;
    margin-bottom: 6px;
  }
  .domain .date { color: var(--text-dim); }
  .title {
    font-family: var(--serif);
    font-weight: 600;
    font-size: 22px;
    line-height: 1.25;
    margin: 0 0 8px;
  }
  .title a {
    color: var(--text);
    text-decoration: none;
    background-image: linear-gradient(var(--accent), var(--accent));
    background-size: 0% 1px;
    background-repeat: no-repeat;
    background-position: 0 100%;
    transition: background-size 300ms;
  }
  .title a:hover { background-size: 100% 1px; }
  .desc {
    font-family: var(--serif);
    color: var(--text-mute);
    font-size: 15px;
    margin: 0 0 12px;
    font-style: italic;
  }
  .keywords {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 10px;
  }
  .kw {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--accent);
    background: var(--accent-soft);
    padding: 3px 8px;
    text-transform: lowercase;
  }
  .url {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-dim);
    text-decoration: none;
    word-break: break-all;
  }
  .url:hover { color: var(--text-mute); }

  @media (max-width: 720px) {
    header, .filters, main { padding-left: 20px; padding-right: 20px; }
    .filters { grid-template-columns: 1fr 1fr; }
    .result { grid-template-columns: 1fr; gap: 14px; }
    .result-meta { flex-direction: row; align-items: center; }
    .score { min-width: 80px; }
  }
</style>
</head>
<body>
  <header>
    <div class="brand">
      Topic Crawler <span class="arrow">→</span> <span class="sub">Results</span>
    </div>
    <div class="stats" id="stats">loading…</div>
  </header>

  <section class="filters">
    <div class="field">
      <label for="search">Search</label>
      <input type="search" id="search" placeholder="title · keywords · content" autocomplete="off">
    </div>
    <div class="field">
      <label for="min-score">Min score</label>
      <input type="number" id="min-score" value="0" min="0">
    </div>
    <div class="field">
      <label for="domain">Domain</label>
      <select id="domain"><option value="">all</option></select>
    </div>
    <div class="field">
      <label for="sort">Sort by</label>
      <select id="sort">
        <option value="score-desc">score ↓</option>
        <option value="score-asc">score ↑</option>
        <option value="date-desc">newest first</option>
        <option value="date-asc">oldest first</option>
      </select>
    </div>
  </section>

  <main id="results"></main>

<script>
  let ALL = [];

  function domainOf(url) {
    try { return new URL(url).host; } catch { return ''; }
  }
  function fmtDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d)) return iso.slice(0, 10);
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  }
  function escapeHtml(s) {
    return (s == null ? '' : String(s)).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  function render() {
    const q = document.getElementById('search').value.trim().toLowerCase();
    const minScore = parseInt(document.getElementById('min-score').value || '0', 10) || 0;
    const domain = document.getElementById('domain').value;
    const sort = document.getElementById('sort').value;

    let rows = ALL.filter(r => (r.relevance_score || 0) >= minScore);
    if (domain) rows = rows.filter(r => domainOf(r.url) === domain);
    if (q) {
      rows = rows.filter(r => {
        const blob = (
          (r.title || '') + ' ' +
          (r.meta_description || '') + ' ' +
          (r.content || '').slice(0, 5000) + ' ' +
          (r.matched_keywords || []).join(' ')
        ).toLowerCase();
        return blob.includes(q);
      });
    }

    const cmp = {
      'score-desc': (a, b) => (b.relevance_score||0) - (a.relevance_score||0),
      'score-asc':  (a, b) => (a.relevance_score||0) - (b.relevance_score||0),
      'date-desc':  (a, b) => (b.crawl_timestamp || '').localeCompare(a.crawl_timestamp || ''),
      'date-asc':   (a, b) => (a.crawl_timestamp || '').localeCompare(b.crawl_timestamp || ''),
    }[sort];
    rows.sort(cmp);

    const totalDomains = new Set(ALL.map(r => domainOf(r.url)).filter(Boolean)).size;
    document.getElementById('stats').innerHTML =
      `<span>${rows.length}</span> shown · <span>${ALL.length}</span> total · <span>${totalDomains}</span> domains`;

    const main = document.getElementById('results');
    if (!ALL.length) {
      main.innerHTML = `<div class="empty">No results yet. Run <code>python run.py</code> to crawl, then refresh.</div>`;
      return;
    }
    if (!rows.length) {
      main.innerHTML = `<div class="empty">No results match the current filters.</div>`;
      return;
    }

    main.innerHTML = rows.map((r, i) => {
      const kw = (r.matched_keywords || [])
        .map(k => `<span class="kw">${escapeHtml(k)}</span>`).join('');
      const desc = r.meta_description
        ? `<p class="desc">${escapeHtml(r.meta_description)}</p>` : '';
      return `
        <article class="result" style="animation-delay:${Math.min(i*30, 600)}ms">
          <div class="result-meta">
            <div class="score">${r.relevance_score || 0}<span class="label">SCORE</span></div>
            <div class="depth">depth · ${r.depth ?? '?'}</div>
          </div>
          <div class="result-body">
            <div class="domain">${escapeHtml(domainOf(r.url))} <span class="date">· ${fmtDate(r.crawl_timestamp)}</span></div>
            <h2 class="title"><a href="${escapeHtml(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.title || '(untitled)')}</a></h2>
            ${desc}
            <div class="keywords">${kw}</div>
            <a class="url" href="${escapeHtml(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.url)}</a>
          </div>
        </article>
      `;
    }).join('');
  }

  function buildDomainSelect() {
    const sel = document.getElementById('domain');
    const counts = {};
    for (const r of ALL) {
      const d = domainOf(r.url);
      if (!d) continue;
      counts[d] = (counts[d] || 0) + 1;
    }
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    sel.innerHTML = '<option value="">all</option>' +
      entries.map(([d, c]) => `<option value="${escapeHtml(d)}">${escapeHtml(d)} (${c})</option>`).join('');
  }

  async function load() {
    try {
      const res = await fetch('/api/results');
      ALL = await res.json();
    } catch (e) {
      ALL = [];
    }
    buildDomainSelect();
    render();
  }

  ['search', 'min-score', 'domain', 'sort'].forEach(id => {
    const el = document.getElementById(id);
    el.addEventListener('input', render);
    el.addEventListener('change', render);
  });

  load();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------
class ViewerHandler(http.server.BaseHTTPRequestHandler):
    # Set by main()
    output_path = "data/results.jsonl"

    def log_message(self, format, *args):
        # Quiet logs: only show errors (4xx/5xx)
        if args and len(args) >= 2 and str(args[1]).startswith(("4", "5")):
            super().log_message(format, *args)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", INDEX_HTML.encode("utf-8"))
        elif path == "/api/results":
            data = self._load_results()
            body = json.dumps(data).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
        else:
            self._send(404, "text/plain; charset=utf-8", b"not found")

    def _send(self, status: int, ctype: str, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _load_results(self):
        results = []
        if not os.path.exists(self.output_path):
            return results
        with open(self.output_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return results


# ---------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Local web viewer for crawler results.")
    p.add_argument("--port", type=int, default=8000, help="Port to serve on (default: 8000).")
    p.add_argument("--output", default=config.OUTPUT_PATH, help="Path to JSONL results file.")
    p.add_argument("--no-browser", action="store_true", help="Don't auto-open the browser.")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    ViewerHandler.output_path = args.output

    addr = ("127.0.0.1", args.port)
    try:
        httpd = socketserver.ThreadingTCPServer(addr, ViewerHandler)
    except OSError as e:
        print(f"Could not bind to port {args.port}: {e}")
        return 1
    httpd.allow_reuse_address = True

    url = f"http://{addr[0]}:{args.port}"
    print(f"Topic Crawler viewer running at {url}")
    print(f"Reading: {args.output}")
    print("Press Ctrl+C to stop.\n")

    if not args.no_browser:
        # Slight delay so the server is ready before the browser hits it
        threading.Thread(
            target=lambda: (time.sleep(0.4), webbrowser.open(url)),
            daemon=True,
        ).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
