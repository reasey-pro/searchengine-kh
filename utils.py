"""Utility helpers for URL handling and content checks."""

import re
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

# File extensions that point to non-HTML resources we want to ignore.
NON_HTML_EXTENSIONS = {
    # Documents
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".odp", ".rtf",
    # Archives
    ".zip", ".tar", ".gz", ".bz2", ".rar", ".7z",
    # Images
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff",
    # Audio
    ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a",
    # Video
    ".mp4", ".avi", ".mov", ".wmv", ".webm", ".mkv", ".flv",
    # Executables / installers
    ".exe", ".dmg", ".iso", ".bin", ".apk", ".deb", ".rpm", ".msi",
    # Code / data assets we don't want to crawl as pages
    ".css", ".js", ".json", ".xml", ".rss", ".atom",
}


def normalize_url(url: str) -> str:
    """Normalize a URL for de-duplication.

    Steps:
      * Drop the #fragment.
      * Lowercase the scheme and host.
      * Strip default ports (80 for http, 443 for https).
      * Collapse repeated slashes in the path.
      * Default an empty path to "/".
    Note: query parameters are preserved as-is (their order can be meaningful).
    """
    if not url:
        return ""
    url, _ = urldefrag(url)
    parsed = urlparse(url)

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Strip default ports
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    path = parsed.path or "/"
    path = re.sub(r"/+", "/", path)

    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))


def is_http_url(url: str) -> bool:
    """True only for http(s) URLs with a host."""
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def is_html_url(url: str) -> bool:
    """Return False if the URL clearly points to a non-HTML file based on extension."""
    if not url:
        return False
    path = urlparse(url).path.lower()
    for ext in NON_HTML_EXTENSIONS:
        if path.endswith(ext):
            return False
    return True


def get_domain(url: str) -> str:
    """Lowercase host of a URL, with any :port stripped."""
    netloc = urlparse(url).netloc.lower()
    if ":" in netloc:
        netloc = netloc.split(":", 1)[0]
    return netloc


def is_allowed_domain(url: str, allowed_domains) -> bool:
    """If allowed_domains is empty, allow everything. Otherwise allow when the URL's
    domain matches an entry exactly OR is a subdomain of one."""
    if not allowed_domains:
        return True
    domain = get_domain(url)
    for entry in allowed_domains:
        entry = entry.lower().lstrip(".")
        if domain == entry or domain.endswith("." + entry):
            return True
    return False


def matches_excluded_pattern(url: str, patterns) -> bool:
    """True if any pattern substring appears in the URL's path or query string."""
    if not patterns:
        return False
    parsed = urlparse(url)
    target = (parsed.path or "")
    if parsed.query:
        target += "?" + parsed.query
    target_low = target.lower()
    return any(p.lower() in target_low for p in patterns)


def absolute_url(base: str, link: str) -> str:
    """Convert a possibly-relative link to absolute form using the base URL."""
    try:
        return urljoin(base, link)
    except Exception:
        return ""
