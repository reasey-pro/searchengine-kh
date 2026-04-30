"""Topic-focused BFS web crawler.

Given a list of seed URLs, crawl outward up to a maximum depth, score each
fetched page by how often the topic keywords appear (weighted by location),
and hand sufficiently relevant pages off to a storage backend.
"""

import logging
import re
import time
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Set, Tuple
from urllib import robotparser
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from utils import (
    absolute_url,
    get_domain,
    is_allowed_domain,
    is_html_url,
    is_http_url,
    matches_excluded_pattern,
    normalize_url,
)

logger = logging.getLogger(__name__)

# Cap on stored body text length per page (to keep JSONL reasonable).
MAX_CONTENT_CHARS = 20000


class TopicCrawler:
    """A simple BFS crawler that filters pages by topic keywords."""

    def __init__(
        self,
        seed_urls: List[str],
        topic_keywords: List[str],
        storage,
        max_depth: int = 2,
        max_pages: int = 100,
        request_delay_seconds: float = 1.0,
        user_agent: str = "TopicCrawler/1.0",
        allowed_domains: List[str] = None,
        excluded_url_patterns: List[str] = None,
        relevance_threshold: int = 2,
        request_timeout: int = 10,
        respect_robots: bool = True,
    ):
        self.seed_urls = [normalize_url(u) for u in seed_urls if u]
        self.topic_keywords = [k for k in topic_keywords if k]
        self.storage = storage
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.request_delay_seconds = request_delay_seconds
        self.user_agent = user_agent
        self.allowed_domains = allowed_domains or []
        self.excluded_url_patterns = excluded_url_patterns or []
        self.relevance_threshold = relevance_threshold
        self.request_timeout = request_timeout
        self.respect_robots = respect_robots

        # URLs we've already taken out of the queue (or stored from a previous run).
        self.visited: Set[str] = set()

        # robots.txt parsers cached per domain.
        self._robots_cache: Dict[str, robotparser.RobotFileParser] = {}

        # Reusable HTTP session for connection pooling.
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

        # Pre-compile case-insensitive patterns for each keyword.
        self._keyword_patterns = self._compile_keywords(self.topic_keywords)

        # Stats
        self.pages_fetched = 0
        self.pages_saved = 0
        self.pages_skipped = 0
        self.errors = 0

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _compile_keywords(keywords: List[str]):
        """Return a list of (keyword, compiled_regex) pairs.

        Pure word/space keywords get word-boundary matching (so "AI" doesn't
        match "PAID"). Anything else falls back to a plain substring match.
        """
        compiled = []
        for kw in keywords:
            kw_clean = kw.strip()
            if not kw_clean:
                continue
            if re.fullmatch(r"[\w\s]+", kw_clean):
                pattern = r"\b" + re.escape(kw_clean) + r"\b"
            else:
                pattern = re.escape(kw_clean)
            compiled.append((kw_clean, re.compile(pattern, re.IGNORECASE)))
        return compiled

    # ------------------------------------------------------------------
    # robots.txt
    # ------------------------------------------------------------------
    def _get_robots(self, url: str) -> robotparser.RobotFileParser:
        """Fetch and cache the RobotFileParser for the URL's domain."""
        domain = get_domain(url)
        if domain in self._robots_cache:
            return self._robots_cache[domain]

        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = robotparser.RobotFileParser()
        rp.set_url(robots_url)
        try:
            rp.read()
        except Exception as e:
            # If robots.txt can't be fetched, the parser will allow everything,
            # which matches common crawler behavior.
            logger.debug("robots.txt fetch failed for %s: %s", domain, e)
        self._robots_cache[domain] = rp
        return rp

    def _allowed_by_robots(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        try:
            rp = self._get_robots(url)
            return rp.can_fetch(self.user_agent, url)
        except Exception:
            # Be permissive if the check itself errors out.
            return True

    # ------------------------------------------------------------------
    # Fetch & parse
    # ------------------------------------------------------------------
    def _fetch(self, url: str):
        """GET a URL. Return (final_url, html_text), or (None, None) on failure."""
        try:
            resp = self.session.get(
                url, timeout=self.request_timeout, allow_redirects=True
            )
        except requests.exceptions.Timeout:
            logger.warning("Timeout: %s", url)
            self.errors += 1
            return None, None
        except requests.exceptions.TooManyRedirects:
            logger.warning("Too many redirects: %s", url)
            self.errors += 1
            return None, None
        except requests.exceptions.RequestException as e:
            logger.warning("Request error for %s: %s", url, e)
            self.errors += 1
            return None, None

        if resp.status_code != 200:
            logger.info("Non-200 (%d) for %s", resp.status_code, url)
            return None, None

        ctype = resp.headers.get("Content-Type", "").lower()
        if "html" not in ctype and "xhtml" not in ctype:
            logger.debug("Skipping non-HTML content (%s) at %s", ctype, url)
            return None, None

        return resp.url, resp.text

    @staticmethod
    def _parse_html(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    @staticmethod
    def _extract_meta(soup: BeautifulSoup) -> Tuple[str, str, List[str], str]:
        """Pull out (title, meta_description, headings, main_text) from the soup."""
        # Title
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # Meta description (try standard, then Open Graph)
        meta_desc = ""
        tag = soup.find("meta", attrs={"name": "description"})
        if tag and tag.get("content"):
            meta_desc = tag["content"].strip()
        else:
            tag = soup.find("meta", attrs={"property": "og:description"})
            if tag and tag.get("content"):
                meta_desc = tag["content"].strip()

        # Headings h1-h3
        headings = []
        for level in ("h1", "h2", "h3"):
            for h in soup.find_all(level):
                text = h.get_text(separator=" ", strip=True)
                if text:
                    headings.append(text)

        # Strip noise tags before grabbing body text
        for tag_name in ("script", "style", "noscript", "nav", "footer", "aside", "form"):
            for t in soup.find_all(tag_name):
                t.decompose()
        # Prefer the most "article-like" container if available
        main = soup.find("article") or soup.find("main") or soup.body or soup
        body_text = main.get_text(separator=" ", strip=True)
        body_text = re.sub(r"\s+", " ", body_text)

        return title, meta_desc, headings, body_text

    def _extract_links(self, base_url: str, soup: BeautifulSoup) -> List[str]:
        """Collect normalized absolute http(s) links from <a href>."""
        links = []
        seen_local: Set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue
            absolute = absolute_url(base_url, href)
            if not absolute or not is_http_url(absolute):
                continue
            normalized = normalize_url(absolute)
            if normalized and normalized not in seen_local:
                seen_local.add(normalized)
                links.append(normalized)
        return links

    # ------------------------------------------------------------------
    # Relevance scoring
    # ------------------------------------------------------------------
    def _score_page(
        self, title: str, meta: str, headings: List[str], body: str
    ) -> Tuple[int, List[str]]:
        """Compute a weighted keyword-frequency score for the page.

        Weights:
          * title    x3
          * meta     x2
          * heading  x2
          * body     x1

        Returns (score, list of matched keywords).
        """
        matched: List[str] = []
        score = 0
        heading_blob = " ".join(headings)
        for kw, pattern in self._keyword_patterns:
            t_count = len(pattern.findall(title))
            m_count = len(pattern.findall(meta))
            h_count = len(pattern.findall(heading_blob))
            b_count = len(pattern.findall(body))
            kw_score = 3 * t_count + 2 * m_count + 2 * h_count + b_count
            if kw_score > 0:
                matched.append(kw)
                score += kw_score
        return score, matched

    # ------------------------------------------------------------------
    # Filter helpers
    # ------------------------------------------------------------------
    def _passes_url_filters(self, url: str, is_seed: bool) -> bool:
        """Apply domain/pattern/extension filters. Seeds bypass domain & pattern checks."""
        if not is_html_url(url):
            return False
        if is_seed:
            return True
        if not is_allowed_domain(url, self.allowed_domains):
            return False
        if matches_excluded_pattern(url, self.excluded_url_patterns):
            return False
        return True

    # ------------------------------------------------------------------
    # Main BFS loop
    # ------------------------------------------------------------------
    def crawl(self) -> dict:
        """Run the crawl. Returns a dict of stats."""
        seed_set = set(self.seed_urls)

        # Pre-load already-stored URLs so a resumed run doesn't double-save.
        try:
            existing = self.storage.load_existing_urls()
            self.visited.update(existing)
            if existing:
                logger.info("Loaded %d previously stored URLs (resume).", len(existing))
        except Exception as e:
            logger.debug("load_existing_urls failed: %s", e)

        # Queue items: (url, depth, source_seed)
        queue = deque()
        for s in self.seed_urls:
            if not is_http_url(s):
                logger.warning("Skipping invalid seed URL: %s", s)
                continue
            queue.append((s, 0, s))

        while queue and self.pages_fetched < self.max_pages:
            url, depth, seed = queue.popleft()
            if url in self.visited:
                continue
            self.visited.add(url)

            if not self._passes_url_filters(url, is_seed=(url in seed_set)):
                continue

            if not self._allowed_by_robots(url):
                logger.info("Blocked by robots.txt: %s", url)
                continue

            logger.info("[d=%d] Fetching %s", depth, url)
            final_url, html = self._fetch(url)
            self.pages_fetched += 1

            # Rate limit between every request.
            time.sleep(self.request_delay_seconds)

            if not html:
                continue

            # Mark redirected target as visited too, to avoid duplicate work.
            if final_url:
                self.visited.add(normalize_url(final_url))

            try:
                soup = self._parse_html(html)
            except Exception as e:
                logger.warning("Parse failed for %s: %s", url, e)
                self.errors += 1
                continue

            title, meta_desc, headings, body_text = self._extract_meta(soup)
            score, matched = self._score_page(title, meta_desc, headings, body_text)

            if score >= self.relevance_threshold and matched:
                record = {
                    "url": final_url or url,
                    "title": title,
                    "meta_description": meta_desc,
                    "content": body_text[:MAX_CONTENT_CHARS],
                    "matched_keywords": matched,
                    "relevance_score": score,
                    "crawl_timestamp": datetime.now(timezone.utc).isoformat(),
                    "source_seed_url": seed,
                    "depth": depth,
                }
                try:
                    self.storage.save_page(record)
                    self.pages_saved += 1
                    logger.info(
                        "  -> SAVED (score=%d, keywords=%s)",
                        score, ", ".join(matched),
                    )
                except Exception as e:
                    logger.error("Failed to save %s: %s", url, e)
                    self.errors += 1
            else:
                self.pages_skipped += 1
                logger.info("  -> skipped (score=%d, below threshold)", score)

            # Enqueue children if depth allows.
            if depth < self.max_depth:
                for link in self._extract_links(final_url or url, soup):
                    if link in self.visited:
                        continue
                    if not self._passes_url_filters(link, is_seed=False):
                        continue
                    queue.append((link, depth + 1, seed))

        logger.info(
            "Done. fetched=%d saved=%d skipped=%d errors=%d",
            self.pages_fetched, self.pages_saved, self.pages_skipped, self.errors,
        )
        return {
            "fetched": self.pages_fetched,
            "saved": self.pages_saved,
            "skipped": self.pages_skipped,
            "errors": self.errors,
        }
