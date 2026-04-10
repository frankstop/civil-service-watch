"""
fetch.py – Download each source URL and save raw + normalised snapshots.

Raw snapshot  : data/raw/<source_id>.html
Normalised    : data/normalized/<source_id>.json
  {
    "source_id": "...",
    "url": "...",
    "fetched_at": "ISO timestamp",
    "status": "ok" | "error",
    "content_hash": "<16-char hex>",
    "text": "<visible text extracted from HTML>",
    "error": "<message if status==error>"
  }
"""

import sys
import time
import json
import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Allow running as a script from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import (
    DATA_RAW_DIR,
    DATA_NORM_DIR,
    hash_text,
    load_sources,
    now_iso,
    safe_filename,
    write_json,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; CivilServiceWatch/1.0; "
        "+https://github.com/frankstop/civil-service-watch)"
    )
}
TIMEOUT = 30  # seconds
DELAY_BETWEEN_REQUESTS = 2  # seconds – be polite to servers


def extract_visible_text(html: str) -> str:
    """Return clean visible text from raw HTML."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove script / style / nav noise
    for tag in soup(["script", "style", "nav", "footer", "head"]):
        tag.decompose()
    lines = (line.strip() for line in soup.get_text(separator="\n").splitlines())
    return "\n".join(line for line in lines if line)


def fetch_source(source: dict) -> dict:
    """Fetch a single source and return a normalised record."""
    sid = source["id"]
    url = source["url"]
    log.info("Fetching %s  %s", sid, url)

    result: dict = {
        "source_id": sid,
        "name": source["name"],
        "url": url,
        "region": source.get("region", ""),
        "tags": source.get("tags", []),
        "fetched_at": now_iso(),
        "status": "ok",
        "content_hash": "",
        "text": "",
        "error": None,
    }

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        html = resp.text

        # Save raw HTML
        raw_path = DATA_RAW_DIR / f"{safe_filename(sid)}.html"
        raw_path.write_text(html, encoding="utf-8")

        text = extract_visible_text(html)
        result["content_hash"] = hash_text(text)
        result["text"] = text

    except Exception as exc:  # noqa: BLE001
        log.warning("Error fetching %s: %s", sid, exc)
        result["status"] = "error"
        result["error"] = str(exc)

    return result


def main() -> None:
    sources = load_sources()
    log.info("Starting fetch for %d sources", len(sources))

    all_results = []
    for i, source in enumerate(sources):
        record = fetch_source(source)
        all_results.append(record)

        # Save individual normalised snapshot
        norm_path = DATA_NORM_DIR / f"{safe_filename(source['id'])}.json"
        write_json(norm_path, record)

        # Polite delay between requests (skip after last)
        if i < len(sources) - 1:
            time.sleep(DELAY_BETWEEN_REQUESTS)

    ok_count = sum(1 for r in all_results if r["status"] == "ok")
    err_count = len(all_results) - ok_count
    log.info("Fetch complete: %d ok, %d errors", ok_count, err_count)


if __name__ == "__main__":
    main()
