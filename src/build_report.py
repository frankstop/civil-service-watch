"""
build_report.py – Generate daily summary reports.

Reads  : history/<today>.json                (comparison results)
         history/<date>.json                 (historical run archive)
         data/normalized/<id>_extracted.json  (extraction results)
Writes : latest_report.md
         latest_report.json
         docs/latest.json
         docs/history.json
"""

import sys
from collections import Counter
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

HISTORY_SCHEMA_VERSION = 1


def load_today_history() -> dict | None:
    path = HISTORY_DIR / f"{today_str()}.json"
    return read_json(path)


def load_all_history(history_dir: Path = HISTORY_DIR) -> list[dict]:
    """Load every committed daily history snapshot sorted newest first."""
    history_entries = []
    for path in sorted(history_dir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json")):
        payload = read_json(path)
        if isinstance(payload, dict):
            history_entries.append(payload)
    history_entries.sort(key=lambda entry: entry.get("date", ""), reverse=True)
    return history_entries


def load_extraction(source_id: str) -> dict | None:
    path = DATA_NORM_DIR / f"{safe_filename(source_id)}_extracted.json"
    return read_json(path)


def status_emoji(record: dict) -> str:
    if record.get("status") == "error":
        return "❌"
    if record.get("changed"):
        return "🔔"
    return "✅"


def build_health_summary(history: dict) -> dict:
    """Return compact source-health counts for reports."""
    sources = history.get("sources", [])
    status_counts = Counter(rec.get("status", "unknown") for rec in sources)
    detail_counts = Counter(rec.get("status_detail", rec.get("status", "unknown")) for rec in sources)
    return {
        "ok": status_counts.get("ok", 0),
        "error": status_counts.get("error", 0),
        "changed": sum(1 for rec in sources if rec.get("changed")),
        "unchanged": sum(1 for rec in sources if not rec.get("changed")),
        "bot_blocked": detail_counts.get("bot_blocked", 0),
        "forbidden": detail_counts.get("forbidden", 0),
        "not_found": detail_counts.get("not_found", 0),
        "timeout": detail_counts.get("timeout", 0),
    }


def flatten_delta_summary(rec: dict) -> dict:
    """Normalize source delta metadata into a compact flat shape."""
    record_diff = rec.get("record_diff") or {}
    diff = rec.get("diff") or {}
    status = rec.get("status", "unknown")
    changed = rec.get("changed", False)

    if changed and record_diff:
        delta_kind = "records"
    elif changed and diff:
        delta_kind = "text"
    elif status == "error":
        delta_kind = "restricted"
    else:
        delta_kind = "none"

    return {
        "delta_kind": delta_kind,
        "added_count": record_diff.get("added_count", 0),
        "removed_count": record_diff.get("removed_count", 0),
        "added_lines": diff.get("added_lines", 0),
        "removed_lines": diff.get("removed_lines", 0),
    }


def normalize_history_source(rec: dict) -> dict:
    """Normalize mixed historical source shapes into one export schema."""
    normalized = {
        "source_id": rec.get("source_id", ""),
        "name": rec.get("name", rec.get("source_id", "")),
        "url": rec.get("url", ""),
        "status": rec.get("status", "unknown"),
        "status_detail": rec.get("status_detail", rec.get("status", "unknown")),
        "changed": rec.get("changed", False),
        "record_count": rec.get("record_count", 0),
        "content_hash": rec.get("content_hash", ""),
        "summary_note": rec.get("summary_note", ""),
        "error": rec.get("error"),
    }
    normalized.update(flatten_delta_summary(rec))
    return normalized


def build_daily_deltas(history: dict) -> list[dict]:
    """Return per-source delta summaries optimized for PR/report consumption."""
    deltas = []
    for rec in history.get("sources", []):
        record_diff = rec.get("record_diff") or {}
        diff = rec.get("diff") or {}
        flat_delta = flatten_delta_summary(rec)
        delta = {
            "source_id": rec["source_id"],
            "name": rec.get("name", rec["source_id"]),
            "url": rec.get("url", ""),
            "status": rec.get("status", "unknown"),
            "status_detail": rec.get("status_detail", rec.get("status", "unknown")),
            "changed": rec.get("changed", False),
            "record_count": rec.get("record_count", 0),
            "summary_note": rec.get("summary_note", ""),
            "added_count": flat_delta["added_count"],
            "removed_count": flat_delta["removed_count"],
            "added_records": record_diff.get("added_records", []),
            "removed_records": record_diff.get("removed_records", []),
            "added_lines": flat_delta["added_lines"],
            "removed_lines": flat_delta["removed_lines"],
            "delta_kind": flat_delta["delta_kind"],
        }
        deltas.append(delta)
    return deltas


def build_history_export(history_entries: list[dict]) -> dict:
    """Return a machine-friendly export covering every committed run."""
    runs_desc = sorted(history_entries, key=lambda entry: entry.get("date", ""), reverse=True)
    runs_asc = list(reversed(runs_desc))
    source_ids = sorted(
        {
            rec.get("source_id", "")
            for entry in runs_desc
            for rec in entry.get("sources", [])
            if rec.get("source_id")
        }
    )

    runs = []
    for history_entry in runs_desc:
        normalized_sources = [
            normalize_history_source(rec)
            for rec in history_entry.get("sources", [])
        ]
        runs.append(
            {
                "date": history_entry.get("date", ""),
                "generated_at": history_entry.get("generated_at", ""),
                "total_sources": history_entry.get("total_sources", len(normalized_sources)),
                "changed_count": history_entry.get(
                    "changed_count",
                    sum(1 for rec in normalized_sources if rec.get("changed")),
                ),
                "health_summary": build_health_summary({"sources": normalized_sources}),
                "sources": normalized_sources,
            }
        )

    first_date = runs_asc[0].get("date", "") if runs_asc else ""
    last_date = runs_desc[0].get("date", "") if runs_desc else ""
    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "total_days": len(runs),
        "date_range": {
            "first_date": first_date,
            "last_date": last_date,
        },
        "source_ids": source_ids,
        "runs": runs,
    }


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

    health = build_health_summary(history)
    restricted = [
        r
        for r in history["sources"]
        if r.get("status_detail") in {"bot_blocked", "forbidden", "not_found", "timeout"}
    ]

    lines.append("## Source Health")
    lines.append("")
    lines.append(f"- Accessible sources: {health['ok']}")
    lines.append(f"- Sources with fetch errors: {health['error']}")
    lines.append(f"- Sources changed today: {health['changed']}")
    lines.append(f"- Sources unchanged today: {health['unchanged']}")
    lines.append(f"- Bot-blocked sources: {health['bot_blocked']}")
    lines.append(f"- Forbidden sources: {health['forbidden']}")
    if restricted:
        lines.append(
            "- Blocked or restricted sources are reported as-is. We do not recover them with alternate endpoints or browser-assisted fetching; the official links stay in the report for human follow-up."
        )
        for rec in restricted:
            lines.append(f"- {rec.get('name', rec['source_id'])} — {rec.get('status_detail', rec.get('status', 'unknown'))} — {rec.get('url', '')}")
    lines.append("")

    lines.append("## Daily Deltas")
    lines.append("")
    for delta in build_daily_deltas(history):
        name = delta["name"]
        url = delta["url"]
        status_detail = delta["status_detail"]
        if delta["delta_kind"] == "records":
            lines.append(
                f"- **{name}** — records `+{delta['added_count']}` / `-{delta['removed_count']}` — {url}"
            )
        elif delta["delta_kind"] == "text":
            lines.append(
                f"- **{name}** — lines `+{delta['added_lines']}` / `-{delta['removed_lines']}` — {url}"
            )
        elif delta["status"] == "error":
            lines.append(f"- **{name}** — {status_detail} — {url}")
        else:
            lines.append(f"- **{name}** — no change — {url}")
    lines.append("")

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
            if rec.get("summary_note"):
                lines.append(f"- **Summary:** {rec['summary_note']}")
            record_diff = rec.get("record_diff")
            diff = rec.get("diff")
            if record_diff:
                lines.append(
                    f"- Records added: {record_diff['added_count']} · "
                    f"removed: {record_diff['removed_count']}"
                )
                if record_diff.get("added_titles"):
                    lines.append(f"- **Added titles:** {', '.join(record_diff['added_titles'])}")
                if record_diff.get("removed_titles"):
                    lines.append(f"- **Removed titles:** {', '.join(record_diff['removed_titles'])}")
                for added_record in record_diff.get("added_records", [])[:3]:
                    record_title = added_record.get("title", added_record.get("exam_number", "Record"))
                    record_bits = [
                        added_record.get("source_record_id") or added_record.get("exam_number", ""),
                        added_record.get("department", ""),
                        added_record.get("agency", ""),
                        added_record.get("deadline", "") or added_record.get("closing_text", ""),
                    ]
                    detail = " — ".join(bit for bit in record_bits if bit)
                    lines.append(f"- Added record: {record_title}" + (f" — {detail}" if detail else ""))
                for removed_record in record_diff.get("removed_records", [])[:3]:
                    record_title = removed_record.get("title", removed_record.get("exam_number", "Record"))
                    record_bits = [
                        removed_record.get("source_record_id") or removed_record.get("exam_number", ""),
                        removed_record.get("department", ""),
                        removed_record.get("agency", ""),
                        removed_record.get("deadline", "") or removed_record.get("closing_text", ""),
                    ]
                    detail = " — ".join(bit for bit in record_bits if bit)
                    lines.append(f"- Removed record: {record_title}" + (f" — {detail}" if detail else ""))
            elif diff:
                lines.append(f"- Lines added: {diff['added_lines']}")
                lines.append(f"- Lines removed: {diff['removed_lines']}")
                if diff.get("added_preview"):
                    lines.append("- **New content (preview):**")
                    for line in diff["added_preview"][:5]:
                        lines.append(f"  - `{line[:120]}`")
            if rec.get("records"):
                lines.append("- **Top records:**")
                for record in rec["records"][:5]:
                    parts = [record.get("title") or record.get("detail") or record.get("exam_number")]
                    extras = [record.get("exam_number"), record.get("deadline"), record.get("exam_date")]
                    parts.extend(extra for extra in extras if extra)
                    lines.append(f"  - {' — '.join(part for part in parts if part)[:160]}")
            lines.append("")

    if errors:
        lines.append("## ❌ Fetch Errors")
        lines.append("")
        for rec in errors:
            name = rec.get("name", rec["source_id"])
            detail = rec.get("status_detail", "fetch_failed")
            message = rec.get("error", "fetch failed")
            lines.append(f"- **{name}** — {detail}: {message}")
        lines.append("")

    lines.append("## ✅ No Changes")
    lines.append("")
    for rec in unchanged:
        name = rec.get("name", rec["source_id"])
        lines.append(f"- {name} — {rec.get('url', '')}")
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
    health_summary = build_health_summary(history)
    daily_deltas = build_daily_deltas(history)
    sources_summary = []
    for rec in history.get("sources", []):
        extracted = load_extraction(rec["source_id"])
        entry = {
            "source_id": rec["source_id"],
            "name": rec.get("name", ""),
            "url": rec.get("url", ""),
            "status": rec.get("status", "unknown"),
            "status_detail": rec.get("status_detail", rec.get("status", "unknown")),
            "changed": rec.get("changed", False),
            "content_hash": rec.get("content_hash", ""),
            "fetched_at": rec.get("fetched_at", ""),
            "error": rec.get("error"),
            "summary_note": rec.get("summary_note", ""),
            "record_count": rec.get("record_count", 0),
            "record_diff": rec.get("record_diff"),
            "records": rec.get("records", [])[:10],
        }
        if extracted:
            entry["summary_note"] = extracted.get("summary_note", entry["summary_note"])
            entry["record_count"] = extracted.get("record_count", entry["record_count"])
            entry["records"] = extracted.get("records", entry["records"])[:10]
            entry["exam_titles"] = extracted.get("exam_titles", [])[:10]
            entry["dates"] = extracted.get("dates", [])[:10]
            entry["keywords_found"] = extracted.get("keywords_found", [])
            entry["links"] = extracted.get("links", [])[:10]
            entry["record_fields_present"] = extracted.get("record_fields_present", [])
        sources_summary.append(entry)

    return {
        "date": history.get("date", today_str()),
        "generated_at": history.get("generated_at", now_iso()),
        "total_sources": history.get("total_sources", 0),
        "changed_count": history.get("changed_count", 0),
        "health_summary": health_summary,
        "daily_deltas": daily_deltas,
        "policy_notes": {
            "restricted_sources": "Blocked or forbidden sources are reported as-is. No alternate endpoints or browser-assisted fetching are used; source links remain for manual follow-up."
        },
        "sources": sources_summary,
    }


def main() -> None:
    print("Building daily report …")

    history = load_today_history()
    if history is None:
        print("ERROR: no history file for today – run compare.py first")
        sys.exit(1)
    all_history = load_all_history()

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
    write_json(DOCS_DIR / "history.json", build_history_export(all_history))

    print("Report build complete.")


if __name__ == "__main__":
    main()
