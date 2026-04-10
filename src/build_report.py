"""
build_report.py – Generate daily summary reports.

Reads  : history/<today>.json                (comparison results)
         data/normalized/<id>_extracted.json  (extraction results)
Writes : latest_report.md
         latest_report.json
         docs/latest.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import (
    DATA_NORM_DIR,
    DOCS_DIR,
    HISTORY_DIR,
    ROOT_DIR,
    load_sources,
    now_iso,
    safe_filename,
    today_str,
    read_json,
    write_json,
    write_text,
)


def load_today_history() -> dict | None:
    path = HISTORY_DIR / f"{today_str()}.json"
    return read_json(path)


def load_extraction(source_id: str) -> dict | None:
    path = DATA_NORM_DIR / f"{safe_filename(source_id)}_extracted.json"
    return read_json(path)


def status_emoji(record: dict) -> str:
    if record.get("status") == "error":
        return "❌"
    if record.get("changed"):
        return "🔔"
    return "✅"


def build_markdown(history: dict, sources_map: dict) -> str:
    date = history.get("date", today_str())
    generated_at = history.get("generated_at", now_iso())
    changed_count = history.get("changed_count", 0)
    total = history.get("total_sources", 0)

    lines = [
        f"# Civil Service Watch — Daily Report",
        f"",
        f"**Date:** {date}  ",
        f"**Generated:** {generated_at}  ",
        f"**Sources checked:** {total}  ",
        f"**Changes detected:** {changed_count}  ",
        f"",
        f"---",
        f"",
    ]

    # Changed sources first
    changed = [r for r in history["sources"] if r.get("changed")]
    errors = [r for r in history["sources"] if r.get("status") == "error"]
    unchanged = [r for r in history["sources"]
                 if not r.get("changed") and r.get("status") != "error"]

    if changed:
        lines.append("## 🔔 Changes Detected")
        lines.append("")
        for rec in changed:
            name = rec.get("name", rec["source_id"])
            url = rec.get("url", "")
            lines.append(f"### {name}")
            lines.append(f"- **URL:** {url}")
            diff = rec.get("diff")
            if diff:
                lines.append(f"- Lines added: {diff['added_lines']}")
                lines.append(f"- Lines removed: {diff['removed_lines']}")
                if diff.get("added_preview"):
                    lines.append("- **New content (preview):**")
                    for line in diff["added_preview"][:5]:
                        lines.append(f"  - `{line[:120]}`")
            # Extraction highlights
            extracted = load_extraction(rec["source_id"])
            if extracted:
                if extracted.get("exam_titles"):
                    lines.append("- **Exam titles found:**")
                    for t in extracted["exam_titles"][:5]:
                        lines.append(f"  - {t[:120]}")
                if extracted.get("dates"):
                    lines.append(f"- **Dates mentioned:** {', '.join(extracted['dates'][:5])}")
            lines.append("")

    if errors:
        lines.append("## ❌ Fetch Errors")
        lines.append("")
        for rec in errors:
            name = rec.get("name", rec["source_id"])
            lines.append(f"- **{name}** — check URL or network access")
        lines.append("")

    lines.append("## ✅ No Changes")
    lines.append("")
    for rec in unchanged:
        name = rec.get("name", rec["source_id"])
        lines.append(f"- {name}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "_Generated automatically by "
        "[civil-service-watch](https://github.com/frankstop/civil-service-watch)_"
    )
    lines.append("")

    return "\n".join(lines)


def build_json_report(history: dict) -> dict:
    sources_summary = []
    for rec in history.get("sources", []):
        extracted = load_extraction(rec["source_id"])
        entry = {
            "source_id": rec["source_id"],
            "name": rec.get("name", ""),
            "url": rec.get("url", ""),
            "status": rec.get("status", "unknown"),
            "changed": rec.get("changed", False),
            "content_hash": rec.get("content_hash", ""),
            "fetched_at": rec.get("fetched_at", ""),
        }
        if extracted:
            entry["exam_titles"] = extracted.get("exam_titles", [])[:10]
            entry["dates"] = extracted.get("dates", [])[:10]
            entry["keywords_found"] = extracted.get("keywords_found", [])
        sources_summary.append(entry)

    return {
        "date": history.get("date", today_str()),
        "generated_at": history.get("generated_at", now_iso()),
        "total_sources": history.get("total_sources", 0),
        "changed_count": history.get("changed_count", 0),
        "sources": sources_summary,
    }


def main() -> None:
    print("Building daily report …")

    history = load_today_history()
    if history is None:
        print("ERROR: no history file for today – run compare.py first")
        sys.exit(1)

    sources = load_sources()
    sources_map = {s["id"]: s for s in sources}

    # Markdown report
    md_text = build_markdown(history, sources_map)
    write_text(ROOT_DIR / "latest_report.md", md_text)

    # JSON report
    report_json = build_json_report(history)
    write_json(ROOT_DIR / "latest_report.json", report_json)

    # docs/latest.json (consumed by GitHub Pages dashboard)
    write_json(DOCS_DIR / "latest.json", report_json)

    print("Report build complete.")


if __name__ == "__main__":
    main()
