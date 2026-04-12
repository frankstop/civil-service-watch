import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from build_report import build_history_export, flatten_delta_summary, load_all_history


class BuildReportHistoryTests(unittest.TestCase):
    def test_flatten_delta_summary_handles_record_text_and_restricted_cases(self) -> None:
        self.assertEqual(
            flatten_delta_summary(
                {
                    "status": "ok",
                    "changed": True,
                    "record_diff": {"added_count": 2, "removed_count": 1},
                }
            ),
            {
                "delta_kind": "records",
                "added_count": 2,
                "removed_count": 1,
                "added_lines": 0,
                "removed_lines": 0,
            },
        )
        self.assertEqual(
            flatten_delta_summary(
                {
                    "status": "ok",
                    "changed": True,
                    "diff": {"added_lines": 4, "removed_lines": 3},
                }
            ),
            {
                "delta_kind": "text",
                "added_count": 0,
                "removed_count": 0,
                "added_lines": 4,
                "removed_lines": 3,
            },
        )
        self.assertEqual(
            flatten_delta_summary({"status": "error", "changed": False}),
            {
                "delta_kind": "restricted",
                "added_count": 0,
                "removed_count": 0,
                "added_lines": 0,
                "removed_lines": 0,
            },
        )

    def test_build_history_export_normalizes_mixed_history_shapes(self) -> None:
        old_run = {
            "date": "2026-04-10",
            "generated_at": "2026-04-10T21:23:34Z",
            "total_sources": 2,
            "changed_count": 1,
            "sources": [
                {
                    "source_id": "legacy_source",
                    "name": "Legacy Source",
                    "url": "https://example.com/legacy",
                    "status": "error",
                    "content_hash": "",
                    "fetched_at": "2026-04-10T21:20:00Z",
                    "changed": False,
                    "diff": None,
                },
                {
                    "source_id": "text_source",
                    "name": "Text Source",
                    "url": "https://example.com/text",
                    "status": "ok",
                    "content_hash": "abc123",
                    "fetched_at": "2026-04-10T21:21:00Z",
                    "changed": True,
                    "diff": {"added_lines": 5, "removed_lines": 2},
                },
            ],
        }
        new_run = {
            "date": "2026-04-12",
            "generated_at": "2026-04-12T02:12:00Z",
            "total_sources": 2,
            "changed_count": 1,
            "sources": [
                {
                    "source_id": "record_source",
                    "name": "Record Source",
                    "url": "https://example.com/records",
                    "status": "ok",
                    "status_detail": "ok",
                    "changed": True,
                    "record_count": 10,
                    "content_hash": "def456",
                    "summary_note": "10 records found",
                    "error": None,
                    "record_diff": {"added_count": 3, "removed_count": 1},
                },
                {
                    "source_id": "blocked_source",
                    "name": "Blocked Source",
                    "url": "https://example.com/blocked",
                    "status": "error",
                    "status_detail": "bot_blocked",
                    "changed": False,
                    "record_count": 0,
                    "content_hash": "",
                    "summary_note": "",
                    "error": "403 response returned from source URL",
                },
            ],
        }

        export = build_history_export([old_run, new_run])

        self.assertEqual(export["schema_version"], 1)
        self.assertEqual(export["total_days"], 2)
        self.assertEqual(export["date_range"]["first_date"], "2026-04-10")
        self.assertEqual(export["date_range"]["last_date"], "2026-04-12")
        self.assertEqual(export["source_ids"], ["blocked_source", "legacy_source", "record_source", "text_source"])
        self.assertEqual([run["date"] for run in export["runs"]], ["2026-04-12", "2026-04-10"])

        newest_run = export["runs"][0]
        self.assertEqual(newest_run["health_summary"]["ok"], 1)
        self.assertEqual(newest_run["health_summary"]["error"], 1)
        self.assertEqual(newest_run["health_summary"]["bot_blocked"], 1)
        self.assertEqual(newest_run["sources"][0]["delta_kind"], "records")
        self.assertEqual(newest_run["sources"][0]["added_count"], 3)
        self.assertEqual(newest_run["sources"][1]["delta_kind"], "restricted")

        older_run = export["runs"][1]
        self.assertEqual(older_run["sources"][0]["status_detail"], "error")
        self.assertEqual(older_run["sources"][0]["record_count"], 0)
        self.assertEqual(older_run["sources"][1]["delta_kind"], "text")
        self.assertEqual(older_run["sources"][1]["added_lines"], 5)
        self.assertEqual(older_run["sources"][1]["removed_lines"], 2)

    def test_load_all_history_reads_and_sorts_history_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history_dir = Path(tmpdir)
            (history_dir / "2026-04-11.json").write_text(
                json.dumps({"date": "2026-04-11", "sources": []}),
                encoding="utf-8",
            )
            (history_dir / "2026-04-09.json").write_text(
                json.dumps({"date": "2026-04-09", "sources": []}),
                encoding="utf-8",
            )
            (history_dir / "notes.txt").write_text("ignore me", encoding="utf-8")

            history_entries = load_all_history(history_dir)

        self.assertEqual([entry["date"] for entry in history_entries], ["2026-04-11", "2026-04-09"])


if __name__ == "__main__":
    unittest.main()
