"""
extract.py – Parse normalized snapshots for exam titles, dates, deadlines, and links.

Reads  : data/normalized/<source_id>.json
Writes : data/normalized/<source_id>_extracted.json
  {
    "source_id": "...",
    "extracted_at": "ISO timestamp",
    "links": [{"text": "...", "href": "..."}],
    "exam_titles": ["..."],
    "dates": ["..."],
    "keywords_found": ["..."]
  }
"""

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import (
    DATA_NORM_DIR,
    DATA_RAW_DIR,
    load_sources,
    now_iso,
    safe_filename,
    write_json,
)

# Civil-service keywords to flag
KEYWORDS = [
    "exam",
    "examination",
    "test",
    "schedule",
    "filing",
    "deadline",
    "closing date",
    "open competitive",
    "promotional",
    "eligible list",
    "notice of examination",
    "application period",
    "civil service",
    "posting",
    "vacancy",
    "announcement",
]

# Broad date patterns: "April 10, 2026", "04/10/2026", "2026-04-10", "Apr 10 2026"
DATE_RE = re.compile(
    r"\b(?:"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"[\s.\-]+\d{1,2}(?:st|nd|rd|th)?[\s,.\-]+\d{4}"
    r"|"
    r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}"
    r"|"
    r"\d{4}[/\-]\d{2}[/\-]\d{2}"
    r")\b",
    re.IGNORECASE,
)


def extract_links_from_html(html: str, base_url: str = "") -> list[dict]:
    """Return list of {text, href} dicts from <a> tags in *html*."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(separator=" ").strip()
        if not text or not href or href.startswith("#"):
            continue
        # Make relative URLs absolute (best-effort)
        if href.startswith("/") and base_url:
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            href = f"{parsed.scheme}://{parsed.netloc}{href}"
        key = (text[:80], href[:120])
        if key not in seen:
            seen.add(key)
            links.append({"text": text[:200], "href": href[:500]})
    return links


def find_exam_titles(text: str) -> list[str]:
    """Heuristic: lines that look like exam titles."""
    titles = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if any(kw in lower for kw in ("exam", "test", "notice of examination", "eligible list")):
            # Keep reasonably short lines; skip pure noise
            if 8 < len(stripped) < 300:
                titles.append(stripped)
    return list(dict.fromkeys(titles))  # dedup while preserving order


def find_dates(text: str) -> list[str]:
    """Return all date-like strings found in *text*."""
    return list(dict.fromkeys(DATE_RE.findall(text)))


def find_keywords(text: str) -> list[str]:
    """Return which civil-service keywords appear in *text*."""
    lower = text.lower()
    return [kw for kw in KEYWORDS if kw in lower]


def extract_source(source: dict) -> dict | None:
    """Run extraction on one source; return result dict or None on skip."""
    sid = source["id"]
    html_path = DATA_RAW_DIR / f"{safe_filename(sid)}.html"
    norm_path = DATA_NORM_DIR / f"{safe_filename(sid)}.json"

    if not html_path.exists() and not norm_path.exists():
        print(f"  skipping {sid} – no snapshot found")
        return None

    # Load visible text from normalised record (preferred)
    text = ""
    if norm_path.exists():
        import json
        with open(norm_path, "r", encoding="utf-8") as fh:
            norm = json.load(fh)
        if norm.get("status") == "error":
            print(f"  skipping {sid} – fetch error: {norm.get('error')}")
            return None
        text = norm.get("text", "")

    # Load raw HTML for link extraction
    html = html_path.read_text(encoding="utf-8") if html_path.exists() else ""

    result = {
        "source_id": sid,
        "name": source["name"],
        "url": source["url"],
        "extracted_at": now_iso(),
        "links": extract_links_from_html(html, source["url"])[:100],
        "exam_titles": find_exam_titles(text)[:50],
        "dates": find_dates(text)[:30],
        "keywords_found": find_keywords(text),
    }

    out_path = DATA_NORM_DIR / f"{safe_filename(sid)}_extracted.json"
    write_json(out_path, result)
    print(f"  {sid}: {len(result['exam_titles'])} titles, {len(result['dates'])} dates, "
          f"{len(result['links'])} links")
    return result


def main() -> None:
    sources = load_sources()
    print(f"Extracting from {len(sources)} sources …")
    for source in sources:
        extract_source(source)
    print("Extraction complete.")


if __name__ == "__main__":
    main()
