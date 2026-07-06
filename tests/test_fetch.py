import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import fetch


class FetchTests(unittest.TestCase):
    def test_usajobs_fetch_uses_first_party_listing_payload(self) -> None:
        main_response = Mock()
        main_response.status_code = 200
        main_response.url = "https://www.usajobs.gov/Search/Results?hp=public"
        main_response.text = """
        <html><body>
          <div id="no-search-results" class="hidden">No jobs found</div>
          <div id="search-results"></div>
        </body></html>
        """

        listing_response = Mock()
        listing_response.json.return_value = {
            "Total": "8005",
            "Jobs": [
                {
                    "Title": "Cyber Threat Analyst",
                    "Agency": "Central Intelligence Agency",
                    "Department": "Other Agencies and Independent Organizations",
                    "SalaryDisplay": "Starting at $63,940 Per year (GS 8-15)",
                    "DocumentID": "722102800",
                    "LocationDisplay": "Washington, District of Columbia",
                    "DateDisplay": "Open 10/01/2025 to 09/30/2026",
                    "WorkSchedule": "Full-time",
                    "WorkType": "Permanent",
                    "PositionURI": "https://www.usajobs.gov:443/job/722102800",
                }
            ],
        }
        source = {
            "id": "usajobs",
            "name": "USAJOBS",
            "url": main_response.url,
            "region": "Federal",
            "tags": ["postings", "federal"],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            raw_dir = Path(temp_dir)
            with (
                patch.object(fetch, "DATA_RAW_DIR", raw_dir),
                patch.object(fetch.requests, "get", return_value=main_response),
                patch.object(fetch.requests, "post", return_value=listing_response) as post_mock,
            ):
                result = fetch.fetch_source(source)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["record_count"], 1)
            self.assertIn("extracted from 8,005", result["summary_note"])
            self.assertTrue((raw_dir / "usajobs_listings.json").exists())
            post_mock.assert_called_once()
            self.assertEqual(
                post_mock.call_args.kwargs["json"],
                {"HiringPath": ["public"], "Page": 1},
            )

    def test_nassau_listing_payload_failure_is_explicit(self) -> None:
        main_response = Mock()
        main_response.status_code = 200
        main_response.url = "https://www.governmentjobs.com/careers/nassaucountyny"
        main_response.text = "<html><body>Nassau County careers</body></html>"

        source = {
            "id": "nassau_county",
            "name": "Nassau County Civil Service",
            "url": main_response.url,
            "region": "Nassau County",
            "tags": ["county"],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            raw_dir = Path(temp_dir)
            listing_path = raw_dir / "nassau_county_listings.html"
            listing_path.write_text("last known valid listing payload", encoding="utf-8")

            with (
                patch.object(fetch, "DATA_RAW_DIR", raw_dir),
                patch.object(fetch, "extract_source_data") as extract_mock,
                patch.object(
                    fetch.requests,
                    "get",
                    side_effect=[
                        main_response,
                        requests.RequestException("listing endpoint timed out"),
                    ],
                ),
            ):
                result = fetch.fetch_source(source)

            extract_mock.assert_not_called()
            self.assertNotEqual(result["status"], "ok")
            self.assertEqual(result["status_detail"], "listing_payload_failed")
            self.assertIn("listing endpoint timed out", result["error"])
            self.assertEqual(result["record_count"], 0)
            self.assertEqual(
                result["summary_note"],
                "Nassau County page loaded, but the listing payload could not be fetched.",
            )
            self.assertEqual(result["text"], "")
            self.assertEqual(
                listing_path.read_text(encoding="utf-8"),
                "last known valid listing payload",
            )


if __name__ == "__main__":
    unittest.main()
