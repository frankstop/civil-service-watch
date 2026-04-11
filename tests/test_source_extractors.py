import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from source_extractors import extract_source_data


class SourceExtractorTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
