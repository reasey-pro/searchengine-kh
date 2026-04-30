"""JSONL storage for relevant crawled pages.

Append-only writer. Each record is one JSON object on its own line.
The class also exposes a `load_existing_urls()` method so the crawler
can skip URLs that were already stored in a previous run (resume).
"""

import json
import os
import threading
from typing import Set


class JsonlStorage:
    """Thread-safe append-only JSONL writer."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        # Make sure the parent directory exists.
        dirpath = os.path.dirname(self.path) or "."
        os.makedirs(dirpath, exist_ok=True)

    def save_page(self, record: dict) -> None:
        """Append a single page record as a JSON line (UTF-8, no escapes for non-ASCII)."""
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def load_existing_urls(self) -> Set[str]:
        """Return the set of URLs already stored in the output file (empty if file
        doesn't exist). Lines that fail to parse are ignored."""
        urls: Set[str] = set()
        if not os.path.exists(self.path):
            return urls
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                u = obj.get("url")
                if u:
                    urls.add(u)
        return urls

    def count(self) -> int:
        """Number of records currently in the file."""
        if not os.path.exists(self.path):
            return 0
        with open(self.path, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
