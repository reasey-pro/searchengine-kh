"""Default configuration for the topic-focused web crawler.

Edit values here to change defaults, or override most of them on the
command line via run.py.
"""

# ---------------------------------------------------------------------
# Seed URLs to start crawling from
# ---------------------------------------------------------------------
SEED_URLS = [
    "https://techcrunch.com/category/artificial-intelligence/",
    "https://www.theverge.com/ai-artificial-intelligence",
    "https://www.wired.com/tag/artificial-intelligence/",
]

# ---------------------------------------------------------------------
# Topic keywords used to determine page relevance (case-insensitive).
# Multi-word phrases are matched as phrases.
# ---------------------------------------------------------------------
TOPIC_KEYWORDS = [
    "artificial intelligence",
    "AI",
    "machine learning",
    "deep learning",
    "generative AI",
    "large language model",
    "LLM",
    "neural network",
    "automation",
    "OpenAI",
    "chatbot",
]

# ---------------------------------------------------------------------
# Crawl shape
# ---------------------------------------------------------------------
# Maximum link depth from the seed URLs (seeds are depth 0).
MAX_DEPTH = 2

# Hard cap on total pages fetched in a single run.
MAX_PAGES = 100

# Delay between consecutive HTTP requests (seconds). Be polite.
REQUEST_DELAY_SECONDS = 1.0

# Per-request timeout (seconds).
REQUEST_TIMEOUT = 10

# ---------------------------------------------------------------------
# HTTP & politeness
# ---------------------------------------------------------------------
USER_AGENT = "TopicCrawler/1.0 (+https://example.com/bot)"

# Whether to consult robots.txt before fetching a URL.
RESPECT_ROBOTS = True

# ---------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------
# Output JSONL file path (one relevant page per line).
OUTPUT_PATH = "data/results.jsonl"

# ---------------------------------------------------------------------
# Optional crawl filters
# ---------------------------------------------------------------------
# If non-empty, only URLs on these domains (or their subdomains) will be
# crawled. Empty list = no domain restriction.
ALLOWED_DOMAINS = []  # e.g. ["techcrunch.com", "theverge.com", "wired.com"]

# Skip any URL whose path or query contains one of these substrings
# (case-insensitive). Seed URLs are always allowed even if they match.
EXCLUDED_URL_PATTERNS = [
    "/login", "/signin", "/signup", "/register",
    "/cart", "/checkout", "/subscribe",
    "/share/", "?share=",
]

# ---------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------
# Minimum weighted keyword score required to store a page.
# Weights used by the scorer: title=3, meta=2, heading=2, body=1.
RELEVANCE_THRESHOLD = 2
