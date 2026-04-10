"""
compare.py – Diff today's normalised snapshot against the previous run.

Reads  : data/normalized/<source_id>.json  (current)
         history/<last_date>.json           (previous run's snapshot index)
Writes : history/<today>.json              (index of today's snapshots + diff)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import (
    DATA_NORM_DIR,
    HISTORY_DIR,
    hash_text,
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
    added = [l for l in new_lines - old_lines if l.strip()]
    removed = [l for l in old_lines - new_lines if l.strip()]
    return {
        "added_lines": len(added),
        "removed_lines": len(removed),
        "added_preview": added[:10],
        "removed_preview": removed[:10],
    }


def compare_source(source: dict, prev_index: dict | None) -> dict:
    """Compare current snapshot for *source* against previous run."""
    sid = source["id"]
    norm_path = DATA_NORM_DIR / f"{safe_filename(sid)}.json"

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

    curr_hash = current.get("content_hash", "")
    prev_hash = prev_record.get("content_hash", "") if prev_record else ""

    changed = curr_hash != prev_hash and curr_hash != ""

    result: dict = {
        "source_id": sid,
        "name": source["name"],
        "url": source["url"],
        "status": current.get("status", "unknown"),
        "content_hash": curr_hash,
        "fetched_at": current.get("fetched_at", ""),
        "changed": changed,
        "diff": None,
    }

    if changed and prev_record and current.get("text"):
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
