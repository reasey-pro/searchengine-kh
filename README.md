# Topic Crawler

A lightweight, topic-focused web crawler in pure Python. It starts from seed
URLs, crawls outward breadth-first up to a configurable depth, scores each
page by topic-keyword frequency, and stores only the relevant pages as JSONL.

## Features

- BFS crawling with configurable max depth and total-page cap
- Topic-keyword filtering with weighted relevance scoring (title / meta / headings / body)
- URL normalization and de-duplication (visited set)
- `robots.txt` compliance (toggleable)
- Configurable request delay (rate limiting)
- Skips non-HTML files (PDF, images, video, archives, executables, etc.)
- Optional domain allow-list and URL-pattern excludes
- Graceful handling of timeouts, redirects, broken links, parse errors
- Resume-friendly: existing JSONL records are loaded, so re-running won't double-save

## Project layout

```
topic_crawler/
├── README.md
├── requirements.txt
├── config.py        # default settings
├── utils.py         # URL helpers
├── storage.py       # JSONL writer
├── crawler.py       # crawling, parsing, filtering
├── run.py           # CLI entry point — runs the crawler
├── viewer.py        # local web UI to browse & filter results
├── data/
│   └── results.jsonl  # local output (created on first save)
├── docs/                       # ── GitHub Pages site ──
│   ├── index.html              #    static viewer
│   └── results.jsonl           #    public copy of the data
└── .github/
    └── workflows/
        └── crawl.yml           # scheduled crawl + auto-publish
```

## Installation

```bash
cd topic_crawler
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Python 3.8+ is recommended.

## Usage

Run with the defaults defined in `config.py`:

```bash
python run.py
```

### Common overrides

```bash
# Smaller, faster crawl
python run.py --max-depth 1 --max-pages 30 --delay 1.5

# Custom output file
python run.py --output data/ai.jsonl

# Custom seeds (flag is repeatable)
python run.py --seed https://example.com/ai --seed https://blog.example.org/ml

# Tighter relevance threshold
python run.py --threshold 5

# Verbose logging
python run.py --verbose
```

### Example: minimal AI-articles run

```bash
python run.py \
  --seed https://techcrunch.com/category/artificial-intelligence/ \
  --max-depth 1 \
  --max-pages 25 \
  --delay 1 \
  --threshold 3 \
  --output data/ai.jsonl
```

## Browsing results in the browser

After a crawl, launch the local web viewer:

```bash
python viewer.py
```

This starts a small server at <http://localhost:8000> and opens it in your
browser. The page loads `data/results.jsonl` and lets you:

- **Search** across title, meta description, content, and matched keywords
- Filter by **minimum relevance score**
- Filter by **domain** (auto-populated from the data, with counts)
- **Sort** by score or crawl date

Filtering happens entirely in the browser, so it's instant. The viewer uses
only Python's standard library — no Flask, no extra installs.

Options:

```bash
python viewer.py --port 9000              # custom port
python viewer.py --output data/ai.jsonl   # custom JSONL file
python viewer.py --no-browser             # don't auto-open the browser
```

Re-run a crawl while the viewer is open and just **refresh the page** to see
the new results.

## Configuration

Edit `config.py` to change defaults:

| Setting                  | Description                                                  |
| ------------------------ | ------------------------------------------------------------ |
| `SEED_URLS`              | List of URLs to start from                                   |
| `TOPIC_KEYWORDS`         | Keywords / phrases that define relevance                     |
| `MAX_DEPTH`              | How many link-hops away from seeds to crawl                  |
| `MAX_PAGES`              | Hard cap on total pages fetched per run                      |
| `REQUEST_DELAY_SECONDS`  | Delay between requests (rate limiting)                       |
| `USER_AGENT`             | UA string sent with each request                             |
| `OUTPUT_PATH`            | Where to write the JSONL output                              |
| `ALLOWED_DOMAINS`        | Optional domain allow-list (empty list = no restriction)     |
| `EXCLUDED_URL_PATTERNS`  | Substrings that cause a non-seed URL to be skipped           |
| `RELEVANCE_THRESHOLD`    | Minimum score required to save a page                        |
| `REQUEST_TIMEOUT`        | Per-request timeout in seconds                               |
| `RESPECT_ROBOTS`         | Whether to consult `robots.txt`                              |

## Output format

Each line of `data/results.jsonl` is a single JSON object:

```json
{
  "url": "https://example.com/some-article",
  "title": "How LLMs are reshaping software",
  "meta_description": "A look at the way large language models...",
  "content": "main article text, whitespace-collapsed (capped at 20k chars)...",
  "matched_keywords": ["AI", "large language model", "LLM"],
  "relevance_score": 14,
  "crawl_timestamp": "2025-05-12T14:08:31.412903+00:00",
  "source_seed_url": "https://example.com/seed",
  "depth": 1
}
```

## Scoring

For each keyword we count case-insensitive matches and apply a weight:

| Location          | Weight |
| ----------------- | ------ |
| `<title>`         | 3×     |
| `<meta description>` | 2×  |
| `<h1>`–`<h3>` headings | 2× |
| body text         | 1×     |

The page's `relevance_score` is the sum across all keywords. A page is
saved only if `relevance_score >= RELEVANCE_THRESHOLD`. Single-word
keywords made of letters/digits (e.g. `AI`, `LLM`) are matched on word
boundaries to avoid partial-word noise; multi-word phrases are matched
literally as case-insensitive phrases.

## Notes & politeness

- Keep `REQUEST_DELAY_SECONDS` at 1s or higher when crawling sites you
  don't own. Leave `RESPECT_ROBOTS = True`.
- Storage is append-only and resume-aware. Re-running on the same output
  file picks up where the previous run left off (URLs already saved are
  skipped automatically).
- This crawler is intentionally simple. For large-scale or distributed
  crawling, look at [Scrapy](https://scrapy.org/).

## Publishing to GitHub Pages (auto-refreshing)

The project ships with everything you need to host a public, automatically
updated version of your crawl results on GitHub Pages — for free, with no
server. The crawl runs on a schedule inside GitHub Actions, commits the
new `results.jsonl` to the repo, and Pages serves the static viewer.

### One-time setup

1. **Push the project to a GitHub repo** (public, or private with Pages
   enabled on a paid plan):

   ```bash
   git init
   git add .
   git commit -m "Initial topic crawler"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/topic-crawler.git
   git push -u origin main
   ```

2. **Enable GitHub Pages**: in your repo, go to
   **Settings → Pages → Source: Deploy from a branch**, set
   **Branch: `main`** and **Folder: `/docs`**, then **Save**.

3. **Allow Actions to push**: go to
   **Settings → Actions → General → Workflow permissions** and select
   **Read and write permissions**. (This lets the workflow commit the
   updated `results.jsonl` back to the repo.)

After about 30–60 seconds your site is live at:

```
https://YOUR_USERNAME.github.io/topic-crawler/
```

### How the auto-refresh works

The workflow at `.github/workflows/crawl.yml` runs:

- **Daily at 06:00 UTC** (cron schedule — change in the workflow YAML).
- **Manually**, via the **Actions tab → "Crawl and publish" → Run workflow**.
- **On any push** that changes the crawler code or config.

Each run:

1. Restores the previous `docs/results.jsonl` so the crawler resumes
   instead of starting from scratch.
2. Runs `python run.py` with conservative defaults (50 pages, 2s delay).
3. Copies the new JSONL into `docs/results.jsonl`.
4. Commits and pushes if anything changed.

GitHub Pages then serves the updated file the next time someone visits.

### Customizing the schedule

Edit `.github/workflows/crawl.yml`. The cron lives near the top:

```yaml
schedule:
  - cron: "0 6 * * *"   # daily at 06:00 UTC
```

Some examples:

- `"0 */6 * * *"` — every 6 hours
- `"0 6 * * 1"` — every Monday at 06:00 UTC
- `"0 6,18 * * *"` — twice a day (06:00 and 18:00 UTC)

You can also tune the `python run.py ...` line in the workflow to change
`--max-pages`, `--delay`, or pass `--seed` URLs.

### Caveats

- For **public repos**, GitHub disables scheduled workflows after **60 days
  of inactivity**. Any push or manual run re-enables them.
- The crawler will keep accumulating results in `docs/results.jsonl` over
  time. If you ever want to start fresh, just delete the file and push.
- GitHub Actions has a free monthly minute quota (very generous for this
  workload — a daily 50-page crawl uses a couple of minutes).
