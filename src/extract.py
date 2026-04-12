"""Extract structured records from normalized source snapshots."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_extractors import extract_source_data
from utils import (
    DATA_NORM_DIR,
    DATA_RAW_DIR,
    load_sources,
    now_iso,
    safe_filename,
    write_json,
)


def load_html_for_extraction(source_id: str) -> str:
    """Load the preferred raw HTML snapshot for extraction."""
    preferred_paths = [
        DATA_RAW_DIR / f"{safe_filename(source_id)}_listings.html",
        DATA_RAW_DIR / f"{safe_filename(source_id)}.html",
    ]
    for path in preferred_paths:
        if not path.exists():
            continue
        html = path.read_text(encoding="utf-8")
        if html.strip():
            return html
    return ""


def extract_source(source: dict) -> dict | None:
    """Run extraction on one source; return result dict or None on skip."""
    sid = source["id"]
    html_path = DATA_RAW_DIR / f"{safe_filename(sid)}.html"
    norm_path = DATA_NORM_DIR / f"{safe_filename(sid)}.json"

    if not html_path.exists() and not norm_path.exists():
        print(f"  skipping {sid} – no snapshot found")
        return None

    if norm_path.exists():
        with open(norm_path, "r", encoding="utf-8") as fh:
            norm = json.load(fh)
        if norm.get("status") == "error":
            print(f"  skipping {sid} – fetch error: {norm.get('error')}")
            return None
    else:
        norm = {"url": source["url"]}

    html = load_html_for_extraction(sid)
    extracted = extract_source_data(sid, html, norm.get("resolved_url") or source["url"])

    result = {
        "source_id": sid,
        "name": source["name"],
        "url": source["url"],
        "extracted_at": now_iso(),
        "links": extracted.get("links", []),
        "records": extracted.get("records", []),
        "record_count": extracted.get("record_count", 0),
        "record_fields_present": extracted.get("record_fields_present", []),
        "record_fingerprint": extracted.get("record_fingerprint", ""),
        "summary_note": extracted.get("summary_note", ""),
        "exam_titles": extracted.get("exam_titles", []),
        "dates": extracted.get("dates", []),
        "keywords_found": extracted.get("keywords_found", []),
        "normalized_text": extracted.get("normalized_text", ""),
    }

    out_path = DATA_NORM_DIR / f"{safe_filename(sid)}_extracted.json"
    write_json(out_path, result)
    print(
        f"  {sid}: {result['record_count']} records, "
        f"{len(result['dates'])} dates, {len(result['links'])} links"
    )
    return result


def main() -> None:
    sources = load_sources()
    print(f"Extracting from {len(sources)} sources …")
    for source in sources:
        extract_source(source)
    print("Extraction complete.")


if __name__ == "__main__":
    main()
