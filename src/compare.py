"""
compare.py – Diff today's normalized snapshot against the previous run.

Reads  : data/normalized/<source_id>.json  (current)
         history/<last_date>.json           (previous run's snapshot index)
Writes : history/<today>.json              (index of today's snapshots + diff)
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_extractors import row_signature
from utils import (
    DATA_NORM_DIR,
    HISTORY_DIR,
    load_sources,
    now_iso,
    safe_filename,
    today_str,
    read_json,
    write_json,
)


def find_previous_history() -> dict | None:
    """Return the most-recent history entry, or None if there is none."""
    history_files = sorted(HISTORY_DIR.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"))
    if not history_files:
        return None
    return read_json(history_files[-1])


def diff_texts(old_text: str, new_text: str) -> dict:
    """
    Very simple line-level diff.
    Returns counts of added / removed lines and a brief preview.
    """
    old_lines = set(old_text.splitlines())
    new_lines = set(new_text.splitlines())
    added = sorted(l for l in new_lines - old_lines if l.strip())
    removed = sorted(l for l in old_lines - new_lines if l.strip())
    return {
        "added_lines": len(added),
        "removed_lines": len(removed),
        "added_preview": added[:10],
        "removed_preview": removed[:10],
    }


def read_git_json(repo_path: Path, rel_path: str) -> dict | None:
    """Read a committed JSON file from HEAD, if present."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "show", f"HEAD:{rel_path}"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def build_record_index(records: list[dict]) -> dict[str, dict]:
    """Index records by their stable signature."""
    index = {}
    for record in records:
        signature = row_signature(record)
        if signature:
            index[signature] = record
    return index


def summarize_record(record: dict) -> dict:
    """Return a compact, PR-friendly record summary."""
    summary = {}
    for key in (
        "source_record_id",
        "job_id",
        "exam_number",
        "title",
        "department",
        "agency",
        "type",
        "job_type",
        "deadline",
        "closing_text",
        "exam_date",
        "salary",
        "detail_url",
    ):
        value = record.get(key)
        if value in ("", None, [], {}):
            continue
        summary[key] = value
    return summary


def diff_records(previous: list[dict], current: list[dict]) -> dict | None:
    """Return a compact diff between previous and current records."""
    prev_index = build_record_index(previous)
    curr_index = build_record_index(current)
    if not prev_index and not curr_index:
        return None

    added_keys = sorted(curr_index.keys() - prev_index.keys())
    removed_keys = sorted(prev_index.keys() - curr_index.keys())
    added = [curr_index[key] for key in added_keys]
    removed = [prev_index[key] for key in removed_keys]
    return {
        "added_count": len(added),
        "removed_count": len(removed),
        "added_titles": [record.get("title", record.get("exam_number", "")) for record in added[:5]],
        "removed_titles": [record.get("title", record.get("exam_number", "")) for record in removed[:5]],
        "added_records": [summarize_record(record) for record in added[:5]],
        "removed_records": [summarize_record(record) for record in removed[:5]],
    }


def compare_source(source: dict, prev_index: dict | None) -> dict:
    """Compare current snapshot for *source* against previous run."""
    sid = source["id"]
    norm_path = DATA_NORM_DIR / f"{safe_filename(sid)}.json"
    extracted_path = DATA_NORM_DIR / f"{safe_filename(sid)}_extracted.json"
    repo_root = Path(__file__).resolve().parent.parent

    current = read_json(norm_path)
    if current is None:
        return {
            "source_id": sid,
            "name": source["name"],
            "status": "missing",
            "changed": False,
            "diff": None,
        }

    prev_record = None
    if prev_index:
        for entry in prev_index.get("sources", []):
            if entry["source_id"] == sid:
                prev_record = entry
                break

    current_extracted = read_json(extracted_path) or {}
    previous_extracted = read_git_json(repo_root, f"data/normalized/{safe_filename(sid)}_extracted.json") or {}

    curr_hash = current_extracted.get("record_fingerprint") or current.get("content_hash", "")
    prev_hash = prev_record.get("content_hash", "") if prev_record else ""
    if previous_extracted.get("record_fingerprint"):
        prev_hash = previous_extracted["record_fingerprint"]

    changed = curr_hash != prev_hash and curr_hash != ""

    result: dict = {
        "source_id": sid,
        "name": source["name"],
        "url": source["url"],
        "status": current.get("status", "unknown"),
        "status_detail": current.get("status_detail", current.get("status", "unknown")),
        "error": current.get("error"),
        "content_hash": curr_hash,
        "fetched_at": current.get("fetched_at", ""),
        "changed": changed,
        "diff": None,
        "summary_note": current_extracted.get("summary_note", current.get("summary_note", "")),
        "record_count": current_extracted.get("record_count", current.get("record_count", 0)),
        "records": current_extracted.get("records", [])[:10],
        "record_diff": None,
    }

    if changed and previous_extracted.get("records") is not None:
        result["record_diff"] = diff_records(previous_extracted.get("records", []), current_extracted.get("records", []))
    elif changed and prev_record and current.get("text"):
        prev_text = prev_record.get("text", "")
        curr_text = current.get("text", "")
        result["diff"] = diff_texts(prev_text, curr_text)

    if changed:
        tag = "NEW (first run)" if not prev_record else "CHANGED"
        print(f"  {sid}: {tag}")
    else:
        print(f"  {sid}: no change")

    return result


def main() -> None:
    sources = load_sources()
    print(f"Comparing snapshots for {len(sources)} sources …")

    prev_index = find_previous_history()
    if prev_index:
        print(f"  previous run: {prev_index.get('date', 'unknown')}")
    else:
        print("  no previous history found – this is the first run")

    comparisons = [compare_source(s, prev_index) for s in sources]

    changed_count = sum(1 for c in comparisons if c["changed"])
    history_entry = {
        "date": today_str(),
        "generated_at": now_iso(),
        "total_sources": len(sources),
        "changed_count": changed_count,
        "sources": comparisons,
    }

    out_path = HISTORY_DIR / f"{today_str()}.json"
    write_json(out_path, history_entry)
    print(f"Compare complete: {changed_count}/{len(sources)} sources changed.")


if __name__ == "__main__":
    main()
