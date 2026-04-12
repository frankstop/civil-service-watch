"""
fetch.py – Download each source URL and save raw + normalized snapshots.

Raw snapshot : data/raw/<source_id>.html
Normalized   : data/normalized/<source_id>.json
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
from urllib.parse import urlparse

import requests

# Allow running as a script from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_extractors import extract_source_data
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
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}
TIMEOUT = 30  # seconds
DELAY_BETWEEN_REQUESTS = 2  # seconds – be polite to servers


def request_headers(source_id: str) -> dict:
    """Return headers tuned for the requested source."""
    if source_id == "mta":
        return {
            "User-Agent": (
                "Mozilla/5.0 (compatible; CivilServiceWatch/1.0; "
                "+https://github.com/frankstop/civil-service-watch)"
            )
        }
    return HEADERS


def classify_error(status_code: int | None, html: str, message: str) -> str:
    """Classify an HTTP failure into a more useful status detail."""
    body = html.lower()
    text = message.lower()
    if status_code == 404:
        return "not_found"
    if status_code == 403 and ("enable javascript and cookies to continue" in body or "just a moment" in body):
        return "bot_blocked"
    if status_code == 403:
        return "forbidden"
    if "failed to resolve" in text:
        return "dns_error"
    if "timed out" in text:
        return "timeout"
    return "fetch_failed"


def fetch_nassau_listing_html(source_url: str) -> str:
    """Fetch Nassau's first-party listing XHR response."""
    agency = urlparse(source_url).path.rstrip("/").split("/")[-1]
    response = requests.get(
        "https://www.governmentjobs.com/careers/home/index",
        params={
            "agency": agency,
            "sort": "PositionTitle",
            "isDescendingSort": "false",
        },
        headers={
            **request_headers("nassau_county"),
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.text


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
        "status_detail": "ok",
        "http_status": None,
        "resolved_url": url,
        "content_hash": "",
        "text": "",
        "summary_note": "",
        "record_count": 0,
        "error": None,
    }

    try:
        resp = requests.get(url, headers=request_headers(sid), timeout=TIMEOUT)
        result["http_status"] = resp.status_code
        result["resolved_url"] = resp.url
        html = resp.text

        # Save raw HTML
        raw_path = DATA_RAW_DIR / f"{safe_filename(sid)}.html" 
        raw_path.write_text(html, encoding="utf-8")

        if resp.status_code >= 400:
            result["status"] = "error"
            result["status_detail"] = classify_error(resp.status_code, html, f"HTTP {resp.status_code}")
            result["error"] = f"{resp.status_code} response returned from source URL"
            return result

        extraction_html = html
        if sid == "nassau_county":
            listing_path = DATA_RAW_DIR / f"{safe_filename(sid)}_listings.html"
            try:
                extraction_html = fetch_nassau_listing_html(resp.url)
                listing_path.write_text(extraction_html, encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                log.warning("Unable to fetch Nassau listing payload: %s", exc)
                listing_path.write_text("", encoding="utf-8")

        extracted = extract_source_data(sid, extraction_html, resp.url)
        text = extracted["normalized_text"]
        result["content_hash"] = hash_text(text) if text else ""
        result["text"] = text
        result["summary_note"] = extracted.get("summary_note", "")
        result["record_count"] = extracted.get("record_count", 0)

    except Exception as exc:  # noqa: BLE001
        log.warning("Error fetching %s: %s", sid, exc)
        result["status"] = "error"
        result["status_detail"] = classify_error(None, "", str(exc))
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
