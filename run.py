"""Entry point: configure logging, instantiate the crawler, and run it.

Run with no arguments to use the defaults from config.py, or pass flags to
override them. Example:

    python run.py --max-depth 1 --max-pages 30 --output data/ai.jsonl
"""

import argparse
import logging
import sys

import config
from crawler import TopicCrawler
from storage import JsonlStorage


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Topic-focused web crawler")
    p.add_argument(
        "--seed", action="append", metavar="URL",
        help="Seed URL (repeatable). Overrides config.SEED_URLS.",
    )
    p.add_argument("--max-depth", type=int, help="Maximum crawl depth.")
    p.add_argument("--max-pages", type=int, help="Maximum pages to fetch.")
    p.add_argument("--delay", type=float, help="Delay between requests in seconds.")
    p.add_argument("--output", help="Output JSONL path.")
    p.add_argument("--threshold", type=int, help="Relevance score threshold.")
    p.add_argument(
        "--no-robots", action="store_true",
        help="Disable robots.txt checking (use only on sites you own).",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    seed_urls = args.seed if args.seed else config.SEED_URLS
    output_path = args.output or config.OUTPUT_PATH

    storage = JsonlStorage(output_path)

    crawler = TopicCrawler(
        seed_urls=seed_urls,
        topic_keywords=config.TOPIC_KEYWORDS,
        storage=storage,
        max_depth=args.max_depth if args.max_depth is not None else config.MAX_DEPTH,
        max_pages=args.max_pages if args.max_pages is not None else config.MAX_PAGES,
        request_delay_seconds=(
            args.delay if args.delay is not None else config.REQUEST_DELAY_SECONDS
        ),
        user_agent=config.USER_AGENT,
        allowed_domains=config.ALLOWED_DOMAINS,
        excluded_url_patterns=config.EXCLUDED_URL_PATTERNS,
        relevance_threshold=(
            args.threshold if args.threshold is not None else config.RELEVANCE_THRESHOLD
        ),
        request_timeout=config.REQUEST_TIMEOUT,
        respect_robots=False if args.no_robots else config.RESPECT_ROBOTS,
    )

    try:
        stats = crawler.crawl()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return 130

    print("\nCrawl complete:")
    print(f"  fetched: {stats['fetched']}")
    print(f"  saved:   {stats['saved']}")
    print(f"  skipped: {stats['skipped']}")
    print(f"  errors:  {stats['errors']}")
    print(f"  output:  {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
