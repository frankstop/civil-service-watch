import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from source_extractors import extract_source_data


class SourceExtractorTests(unittest.TestCase):
    def read_fixture(self, name: str) -> str:
        return (Path(__file__).resolve().parent / "fixtures" / name).read_text(encoding="utf-8")

    def test_table_based_source_extracts_records(self) -> None:
        html = """
        <html><body>
          <table>
            <tr>
              <th>Title of Exam</th>
              <th>Exam No.</th>
              <th>Application Period</th>
            </tr>
            <tr>
              <td><a href="/exam-1">Administrative Horticulturist</a></td>
              <td>6005</td>
              <td>4/1/2026 – 4/21/2026</td>
            </tr>
          </table>
        </body></html>
        """
        extracted = extract_source_data(
            "nyc_dcas",
            html,
            "https://www.nyc.gov/site/dcas/employment/exam-schedules-open-competitive-exams.page",
        )

        self.assertEqual(extracted["record_count"], 1)
        self.assertEqual(extracted["records"][0]["title"], "Administrative Horticulturist")
        self.assertEqual(extracted["records"][0]["exam_number"], "6005")
        self.assertTrue(extracted["records"][0]["detail_url"].endswith("/exam-1"))

    def test_orange_portal_text_parser_reads_scheduled_rows(self) -> None:
        html = """
        <html><body>
          <div>
            Scheduled Open Competitive Examinations
            Exam #
            Exam Name
            Type
            Deadline
            Exam Date
            Apply
            60062760
            PROBATION OFFICER 1 TRAINEE
            OC
            04/29/2026
            06/27/2026
            Login
            Promotional Announcements
          </div>
        </body></html>
        """
        extracted = extract_source_data("orange_county", html, "https://orange-portal.mycivilservice.com/post/exams")

        self.assertEqual(extracted["record_count"], 1)
        self.assertEqual(extracted["records"][0]["title"], "PROBATION OFFICER 1 TRAINEE")
        self.assertEqual(extracted["records"][0]["deadline"], "04/29/2026")

    def test_usajobs_no_results_collapses_noise(self) -> None:
        html = """
        <html><body>
          <div>No jobs found</div>
          <div>Show all jobs including remote</div>
          <div>Add a resume to your profile</div>
        </body></html>
        """
        extracted = extract_source_data(
            "usajobs",
            html,
            "https://www.usajobs.gov/Search/Results?l=New+York%2C+NY",
        )

        self.assertEqual(extracted["record_count"], 0)
        self.assertIn("No matching USAJOBS listings found", extracted["summary_note"])
        self.assertEqual(extracted["normalized_text"], extracted["summary_note"])

    def test_nassau_listing_fixture_extracts_direct_records(self) -> None:
        extracted = extract_source_data(
            "nassau_county",
            self.read_fixture("nassau_county_listings.html"),
            "https://www.governmentjobs.com/careers/nassaucountyny",
        )

        self.assertEqual(extracted["record_count"], 3)
        self.assertEqual(extracted["records"][0]["job_id"], "3413083")
        self.assertEqual(extracted["records"][0]["agency"], "NASSAU HEALTH CARE CORPORATION")
        self.assertEqual(extracted["records"][0]["salary"], "$74,114 - $99,744")
        self.assertEqual(extracted["records"][0]["closing_text"], "Continuous")
        self.assertIn("source_record_id", extracted["record_fields_present"])
        self.assertIn("announcement_text", extracted["record_fields_present"])

    def test_real_nyc_fixture_extracts_pdf_detail_urls(self) -> None:
        extracted = extract_source_data(
            "nyc_dcas",
            self.read_fixture("nyc_dcas_table.html"),
            "https://www.nyc.gov/site/dcas/employment/exam-schedules-open-competitive-exams.page",
        )

        self.assertEqual(extracted["record_count"], 2)
        self.assertTrue(extracted["records"][0]["detail_url"].endswith("20266005000.pdf"))
        self.assertEqual(extracted["records"][1]["application_period"], "Postponed")

    def test_real_nys_fixture_extracts_fee_fields(self) -> None:
        extracted = extract_source_data(
            "nys_civil_service",
            self.read_fixture("nys_civil_service_table.html"),
            "https://www.cs.ny.gov/examannouncements/types/oc/",
        )

        self.assertEqual(extracted["record_count"], 1)
        self.assertEqual(extracted["records"][0]["fee"], "$0")
        self.assertEqual(extracted["records"][0]["salary"], "See Announcement")

    def test_real_westchester_fixture_extracts_agency_exam_date_and_fee(self) -> None:
        extracted = extract_source_data(
            "westchester_county",
            self.read_fixture("westchester_county_table.html"),
            "http://www.westchestergov.com/hr/onlineexam",
        )

        self.assertEqual(extracted["record_count"], 1)
        self.assertEqual(extracted["records"][0]["agency"], "BOCES #2")
        self.assertEqual(extracted["records"][0]["exam_date"], "06/27/2026")
        self.assertEqual(extracted["records"][0]["fee"], "$50.00")


if __name__ == "__main__":
    unittest.main()
