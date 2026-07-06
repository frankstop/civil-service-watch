"""Source-aware extraction helpers shared by fetch and report generation."""

from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

KEYWORDS = [
    "exam",
    "examination",
    "test",
    "schedule",
    "filing",
    "deadline",
    "closing date",
    "open competitive",
    "promotional",
    "eligible list",
    "notice of examination",
    "application period",
    "civil service",
    "posting",
    "vacancy",
    "announcement",
]

DATE_RE = re.compile(
    r"\b(?:"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"[\s.\-]+\d{1,2}(?:st|nd|rd|th)?[\s,.\-]+\d{4}"
    r"|"
    r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}"
    r"|"
    r"\d{4}[/\-]\d{2}[/\-]\d{2}"
    r")\b",
    re.IGNORECASE,
)
SALARY_AMOUNT_RE = re.compile(r"\$[\d,]+(?:\.\d{2})?")


def clean_text(text: str) -> str:
    """Collapse internal whitespace while preserving readable content."""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def dedupe(items: list[str]) -> list[str]:
    """Deduplicate while preserving order."""
    return list(dict.fromkeys(item for item in items if item))


def absolutize(base_url: str, href: str) -> str:
    """Resolve relative URLs against a base URL."""
    return urljoin(base_url, href.strip())


def soup_text(html: str) -> str:
    """Extract visible page text while removing obvious chrome."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "head", "noscript"]):
        tag.decompose()
    lines = [clean_text(line) for line in soup.get_text("\n").splitlines()]
    return "\n".join(line for line in lines if line)


def find_dates(text: str) -> list[str]:
    """Return date-like strings in the provided text."""
    return dedupe(DATE_RE.findall(text))


def find_keywords(text: str) -> list[str]:
    """Return keyword hits for the provided text."""
    lower = text.lower()
    return [kw for kw in KEYWORDS if kw in lower]


def row_signature(record: dict) -> str:
    """Build a stable record signature for comparisons and hashing."""
    important = [
        record.get("source_record_id", "") or record.get("job_id", ""),
        record.get("exam_number", ""),
        record.get("title", ""),
        record.get("department", ""),
        record.get("type", ""),
        record.get("job_type", ""),
        record.get("application_period", ""),
        record.get("deadline", ""),
        record.get("closing_text", ""),
        record.get("exam_date", ""),
        record.get("posted_date", ""),
        record.get("posted_text", ""),
        record.get("agency", ""),
        record.get("location", ""),
        record.get("salary", ""),
        record.get("fee", ""),
        record.get("status", ""),
        record.get("announcement_text", "") or record.get("detail", ""),
        record.get("detail_url", ""),
    ]
    return " | ".join(clean_text(value) for value in important if value)


def fingerprint_records(records: list[dict], summary_note: str = "") -> str:
    """Return a stable fingerprint of extracted records."""
    payload = "\n".join(row_signature(record) for record in records)
    if summary_note:
        payload = f"{payload}\n{clean_text(summary_note)}".strip()
    if not payload:
        return ""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def generic_links(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Return useful links from the document."""
    links = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        text = clean_text(anchor.get_text(" ", strip=True))
        href = absolutize(base_url, anchor["href"])
        if not text or text.lower() == "login":
            continue
        key = (text[:120], href[:180])
        if key in seen:
            continue
        seen.add(key)
        links.append({"text": text[:200], "href": href[:500]})
    return links[:100]


def extract_labeled_value(text: str, label: str, stop_labels: list[str]) -> str:
    """Extract text following *label* until one of *stop_labels* appears."""
    normalized = clean_text(text)
    upper = normalized.upper()
    label_upper = label.upper()
    start = upper.find(label_upper)
    if start == -1:
        return ""

    remainder = normalized[start + len(label) :].strip(" :-|")
    if not remainder:
        return ""

    stop_at = len(remainder)
    upper_remainder = remainder.upper()
    for stop_label in stop_labels:
        idx = upper_remainder.find(stop_label.upper())
        if idx != -1:
            stop_at = min(stop_at, idx)

    return clean_text(remainder[:stop_at].strip(" :-|"))


def parse_salary_text(text: str) -> dict:
    """Return normalized salary fields parsed from free text."""
    salary_text = clean_text(text)
    if not salary_text:
        return {}

    amounts = []
    for match in SALARY_AMOUNT_RE.findall(salary_text):
        try:
            amounts.append(int(match.replace("$", "").replace(",", "").split(".")[0]))
        except ValueError:
            continue

    result = {"salary_text": salary_text}
    if amounts:
        result["salary_min"] = amounts[0]
        if len(amounts) > 1:
            result["salary_max"] = amounts[1]
    return result


def normalize_record(record: dict) -> dict:
    """Remove empty values and add derived normalized fields."""
    normalized = {}
    for key, value in record.items():
        if value is None:
            continue
        if isinstance(value, str):
            value = clean_text(value)
        if value in ("", [], {}):
            continue
        normalized[key] = value

    if normalized.get("job_id") and not normalized.get("source_record_id"):
        normalized["source_record_id"] = normalized["job_id"]

    salary_text = normalized.get("salary") or normalized.get("salary_text", "")
    if salary_text:
        normalized.setdefault("salary", salary_text)
        for key, value in parse_salary_text(salary_text).items():
            normalized.setdefault(key, value)

    return normalized


def record_fields_present(records: list[dict]) -> list[str]:
    """Return the ordered union of keys present across extracted records."""
    fields: list[str] = []
    seen = set()
    for record in records:
        for key in record:
            if key in seen:
                continue
            seen.add(key)
            fields.append(key)
    return fields


def map_header(header: str) -> str | None:
    """Map a source table header to a normalized record key."""
    normalized = clean_text(header).lower()
    mapping = {
        "title": "title",
        "title of exam": "title",
        "exam title": "title",
        "job title": "title",
        "position title": "title",
        "job name": "title",
        "exam no.": "exam_number",
        "exam no": "exam_number",
        "exam number": "exam_number",
        "examination number": "exam_number",
        "job id": "job_id",
        "posting id": "source_record_id",
        "job number": "source_record_id",
        "application period": "application_period",
        "last date to apply": "deadline",
        "deadline": "deadline",
        "closing date": "deadline",
        "date posted": "posted_date",
        "posted": "posted_date",
        "posting date": "posted_date",
        "exam date": "exam_date",
        "test date": "exam_date",
        "salary": "salary",
        "salary range": "salary",
        "annual salary": "salary",
        "minimum salary": "salary_min",
        "maximum salary": "salary_max",
        "salary grade": "salary_grade",
        "jurisdiction or agency": "agency",
        "agency": "agency",
        "department": "department",
        "location": "location",
        "type": "type",
        "exam type": "type",
        "job type": "job_type",
        "status": "status",
        "description": "detail",
        "non-refundable processing fee": "fee",
        "processing fee": "fee",
        "fee": "fee",
    }
    if normalized in mapping:
        return mapping[normalized]
    if "processing" in normalized and "fee" in normalized:
        return "fee"
    if "date" in normalized and "apply" in normalized:
        return "deadline"
    if "exam" in normalized and "title" in normalized:
        return "title"
    return None


def extract_table_records(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Parse the first relevant table into normalized records."""
    all_records: list[dict] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        header_row_index = None
        headers = []
        for idx, row in enumerate(rows):
            candidate = [map_header(th.get_text(" ", strip=True)) for th in row.find_all(["th", "td"])]
            if any(candidate):
                headers = candidate
                header_row_index = idx
                break

        if header_row_index is None or not any(headers):
            continue

        for row in rows[header_row_index + 1 :]:
            cells = row.find_all(["th", "td"])
            if not cells:
                continue
            record: dict[str, str] = {}
            for key, cell in zip(headers, cells):
                if not key:
                    continue
                value = clean_text(cell.get_text(" ", strip=True))
                if not value:
                    continue
                record[key] = value
                link = cell.find("a", href=True)
                if link:
                    record.setdefault("detail_url", absolutize(base_url, link["href"]))
            exam_number = record.get("exam_number", "")
            if record.get("title") or (exam_number and len(exam_number) <= 20):
                all_records.append(normalize_record(record))

        if all_records:
            break

    return all_records[:100]


def parse_orange_text(text: str, base_url: str) -> list[dict]:
    """Parse the Orange portal's text-only listing into records."""
    lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]
    records: list[dict] = []

    def parse_rows(start_label: str, stop_labels: tuple[str, ...], row_width: int) -> None:
        try:
            start = lines.index(start_label)
        except ValueError:
            return

        i = start + 1
        while i < len(lines):
            line = lines[i]
            if line in stop_labels:
                break
            if row_width == 6 and re.fullmatch(r"\d{2,}", line):
                chunk = lines[i : i + row_width]
                if len(chunk) == row_width:
                    exam_number, title, exam_type, deadline, exam_date, _apply = chunk
                    records.append(
                        {
                            "exam_number": exam_number,
                            "title": title,
                            "type": exam_type,
                            "deadline": deadline,
                            "exam_date": exam_date,
                            "detail_url": base_url,
                        }
                    )
                    i += row_width
                    continue
            if row_width == 4 and re.fullmatch(r"\d{2,}", line):
                chunk = lines[i : i + row_width]
                if len(chunk) == row_width:
                    exam_number, title, exam_type, _apply = chunk
                    records.append(
                        {
                            "exam_number": exam_number,
                            "title": title,
                            "type": exam_type,
                            "detail_url": base_url,
                        }
                    )
                    i += row_width
                    continue
            i += 1

    parse_rows(
        "Scheduled Open Competitive Examinations",
        ("Continuous Recruitment Exams - Open Competitive Exams", "Promotional Announcements"),
        6,
    )
    parse_rows(
        "Continuous Recruitment Exams - Open Competitive Exams",
        ("Promotional Announcements", "Disclaimers"),
        4,
    )
    return records[:100]


def parse_usajobs_json(payload: dict, base_url: str) -> dict:
    """Extract normalized records from USAJOBS' first-party search payload."""
    records = []
    links = []
    seen = set()

    for job in payload.get("Jobs", []):
        job_id = clean_text(str(job.get("DocumentID", "")))
        detail_url = clean_text(job.get("PositionURI", ""))
        if job_id:
            detail_url = absolutize(base_url, f"/job/{job_id}")
        dedupe_key = job_id or detail_url
        if not dedupe_key or dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        date_text = clean_text(job.get("DateDisplay", ""))
        dates = find_dates(date_text)
        posted_text = dates[0] if dates else clean_text(job.get("PositionStartDate", ""))
        closing_text = dates[-1] if dates else clean_text(job.get("PositionEndDate", ""))
        job_type = "; ".join(
            value
            for value in (
                clean_text(job.get("WorkType", "")),
                clean_text(job.get("WorkSchedule", "")),
            )
            if value
        )
        announcement_text = " | ".join(
            value
            for value in (
                clean_text(job.get("Agency", "")),
                clean_text(job.get("Department", "")),
                clean_text(job.get("LocationDisplay", "") or job.get("Location", "")),
                date_text,
                clean_text(job.get("SalaryDisplay", "")),
                job_type,
            )
            if value
        )

        record = normalize_record(
            {
                "source_record_id": job_id,
                "job_id": job_id,
                "title": job.get("Title", ""),
                "agency": job.get("Agency", ""),
                "department": job.get("Department", ""),
                "location": job.get("LocationDisplay", "") or job.get("Location", ""),
                "salary": job.get("SalaryDisplay", ""),
                "posted_text": posted_text,
                "closing_text": closing_text,
                "deadline": dates[-1] if dates else closing_text,
                "job_type": job_type,
                "detail_url": detail_url,
                "announcement_text": announcement_text,
                "type": "Federal posting",
            }
        )
        if not record.get("title"):
            continue

        records.append(record)
        links.append({"text": record["title"][:200], "href": detail_url[:500]})
        if len(records) >= 100:
            break

    total_results = int(payload.get("Total", 0) or 0)
    if records and total_results > len(records):
        summary_note = (
            f"{len(records)} USAJOBS federal listings extracted from "
            f"{total_results:,} currently found for this search."
        )
    elif records:
        summary_note = f"{len(records)} USAJOBS federal listings currently found for this search."
    else:
        summary_note = "No matching USAJOBS listings found for the current search."

    return {
        "records": records,
        "summary_note": summary_note,
        "links": links,
    }


def parse_usajobs(soup: BeautifulSoup, text: str, base_url: str) -> dict:
    """Extract federal job cards from a rendered USAJOBS search page."""
    no_results_messages = ("No jobs found", "We couldn't find any results.")
    visible_no_results = False
    for message in no_results_messages:
        message_node = soup.find(string=lambda value: value and message in value)
        if not message_node:
            continue
        if not any("hidden" in parent.get("class", []) for parent in message_node.parents):
            visible_no_results = True
            break
    if visible_no_results:
        return {
            "records": [],
            "summary_note": "No matching USAJOBS listings found for the current search.",
            "links": [],
        }

    labels = [
        "Department",
        "Agency",
        "Location",
        "Salary",
        "Open & closing dates",
        "Series & Grade",
        "Job type",
        "Remote job",
        "Telework eligible",
    ]
    semantic_hints = {
        "department": ("department",),
        "agency": ("agency",),
        "location": ("location",),
        "salary": ("salary",),
        "open_closing": ("open-closing", "open_closing", "openclosing"),
        "job_type": ("job-type", "job_type", "jobtype"),
    }

    def element_value(element, label: str) -> str:
        value = clean_text(element.get_text(" ", strip=True))
        if value.lower().rstrip(":") == label.lower():
            sibling = element.find_next_sibling()
            if sibling:
                return clean_text(sibling.get_text(" ", strip=True))
            return ""
        return clean_text(re.sub(rf"^{re.escape(label)}\s*:?\s*", "", value, flags=re.IGNORECASE))

    def semantic_value(card, key: str, label: str) -> str:
        hints = semantic_hints.get(key, ())
        for element in card.find_all(True):
            attributes = " ".join(
                [
                    str(element.get("data-test", "")),
                    str(element.get("data-testid", "")),
                    str(element.get("aria-label", "")),
                    str(element.get("id", "")),
                    " ".join(element.get("class", [])),
                ]
            ).lower()
            if any(hint in attributes for hint in hints):
                value = element_value(element, label)
                if value:
                    return value

        for element in card.find_all(["dt", "span", "div", "p", "strong", "b"]):
            element_text = clean_text(element.get_text(" ", strip=True))
            if (
                element_text.lower().rstrip(":") == label.lower()
                or re.match(rf"^{re.escape(label)}\s*:", element_text, re.IGNORECASE)
            ):
                value = element_value(element, label)
                if value:
                    return value

        card_text = clean_text(card.get_text(" ", strip=True))
        if re.search(rf"\b{re.escape(label)}\s*:", card_text, re.IGNORECASE):
            return extract_labeled_value(
                card_text,
                label,
                [candidate for candidate in labels if candidate != label],
            )
        return ""

    def listing_card(anchor):
        for parent in anchor.parents:
            if parent.name in {"body", "html"}:
                break
            classes = parent.get("class", [])
            if "page-section" in classes:
                return parent
            attributes = " ".join(
                [
                    str(parent.get("data-test", "")),
                    str(parent.get("data-testid", "")),
                    " ".join(classes),
                ]
            ).lower()
            if any(token in attributes for token in ("job-result", "search-result", "job-card", "result-card")):
                return parent
            if parent.name in {"article", "li"}:
                return parent
        return anchor.parent

    records: list[dict] = []
    links: list[dict] = []
    seen = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        job_match = re.search(r"/job/(\d+)(?:/|$)", href, re.IGNORECASE)
        if not job_match:
            continue

        job_id = job_match.group(1)
        detail_url = absolutize(base_url, href)
        dedupe_key = job_id or detail_url
        if dedupe_key in seen:
            continue

        card = listing_card(anchor)
        title = clean_text(anchor.get_text(" ", strip=True))
        if not title:
            continue
        seen.add(dedupe_key)

        card_text = clean_text(card.get_text(" ", strip=True))
        department = semantic_value(card, "department", "Department")
        agency = semantic_value(card, "agency", "Agency")
        if not agency:
            agency_element = card.find("strong") or card.find("h3")
            agency = clean_text(agency_element.get_text(" ", strip=True)) if agency_element else ""
            agency_line = (
                clean_text(agency_element.parent.get_text(" ", strip=True))
                if agency_element and agency_element.parent
                else ""
            )
            if not department and "•" in agency_line:
                department = clean_text(agency_line.split("•", 1)[1])

        date_text = semantic_value(card, "open_closing", "Open & closing dates")
        if not date_text and "Posted" in card_text and "Apply by" in card_text:
            date_text = card_text
        dates = find_dates(date_text)
        posted_text = dates[0] if dates else date_text
        closing_text = dates[-1] if dates else date_text

        location = semantic_value(card, "location", "Location")
        if not location:
            location_icon = card.find(
                "use",
                attrs={"xlink:href": re.compile("location_on", re.IGNORECASE)},
            ) or card.find("use", href=re.compile("location_on", re.IGNORECASE))
            location_container = location_icon.find_parent("div") if location_icon else None
            if location_container:
                location = clean_text(location_container.get_text(" ", strip=True))

        salary = semantic_value(card, "salary", "Salary")
        badge_values = [
            clean_text(badge.get_text(" ", strip=True))
            for badge in card.select("span.badge-secondary")
        ]
        if not salary:
            salary = next((value for value in badge_values if "$" in value), "")

        job_type = semantic_value(card, "job_type", "Job type")
        if not job_type:
            job_type_values = [value for value in badge_values if value and value != salary]
            job_type = "; ".join(job_type_values)

        record = normalize_record(
            {
                "source_record_id": job_id,
                "job_id": job_id,
                "title": title,
                "agency": agency,
                "department": department,
                "location": location,
                "salary": salary,
                "posted_text": posted_text,
                "closing_text": closing_text,
                "deadline": dates[-1] if dates else "",
                "job_type": job_type,
                "detail_url": detail_url,
                "announcement_text": card_text,
                "type": "Federal posting",
            }
        )
        records.append(record)
        links.append({"text": title[:200], "href": detail_url[:500]})

        if len(records) >= 100:
            break

    summary_note = ""
    if records:
        total_match = re.search(r"\bof\s+([\d,]+)\s+jobs\b", text, re.IGNORECASE)
        total_results = int(total_match.group(1).replace(",", "")) if total_match else len(records)
        if total_results > len(records):
            summary_note = (
                f"{len(records)} USAJOBS federal listings extracted from "
                f"{total_results:,} currently found for this search."
            )
        else:
            summary_note = f"{len(records)} USAJOBS federal listings currently found for this search."

    return {
        "records": records[:100],
        "summary_note": summary_note,
        "links": links[:100],
    }


def parse_mta(soup: BeautifulSoup, _text: str, base_url: str) -> dict:
    """Extract the most actionable MTA exam and hiring links."""
    records = []
    wanted = {
        "See all open MTA positions.": "Job listings",
        "Find out more about upcoming exams.": "Exam information",
        "Find out more about becoming a police officer": "Police officer process",
        "See current skilled trade jobs": "Skilled trades",
        "MTA Careers site": "Internships",
    }
    seen = set()
    for anchor in soup.find_all("a", href=True):
        text = clean_text(anchor.get_text(" ", strip=True))
        if text not in wanted or text in seen:
            continue
        seen.add(text)
        records.append(
            {
                "title": wanted[text],
                "detail": text,
                "detail_url": absolutize(base_url, anchor["href"]),
            }
        )
    return {
        "records": records,
        "summary_note": "Career center links and exam-specific entry points.",
        "links": [],
    }


def parse_nassau_listings(soup: BeautifulSoup, base_url: str) -> dict:
    """Extract Nassau County's listing cards returned by the first-party XHR."""
    records = []
    links = []

    for item in soup.select("li.list-item[data-job-id]"):
        anchor = item.select_one("a.item-details-link[href]")
        if not anchor:
            continue

        title = clean_text(anchor.get_text(" ", strip=True))
        announcement_text = clean_text(item.select_one(".list-entry").get_text(" ", strip=True)) if item.select_one(".list-entry") else ""
        posted_text = clean_text(item.select_one(".list-entry-starts").get_text(" ", strip=True)) if item.select_one(".list-entry-starts") else ""
        closing_text = clean_text(item.select_one(".list-entry-ends").get_text(" ", strip=True)) if item.select_one(".list-entry-ends") else ""
        detail_url = absolutize(base_url, anchor["href"])

        salary_text = extract_labeled_value(
            announcement_text,
            "SALARY",
            [
                "REISSUED ANNOUNCEMENT",
                "THIS EXAMINATION",
                "APPLICATIONS WILL",
                "NAMES OF SUCCESSFUL",
                "CANDIDATES MAY",
            ],
        ).strip(":")
        agency = extract_labeled_value(
            announcement_text,
            "ANNOUNCED FOR",
            [
                "SALARY",
                "REISSUED ANNOUNCEMENT",
                "THIS EXAMINATION",
            ],
        ).strip(":")

        record = normalize_record(
            {
                "source_record_id": item.get("data-job-id", ""),
                "job_id": item.get("data-job-id", ""),
                "title": title,
                "department": anchor.get("data-department-name", ""),
                "agency": agency,
                "salary": salary_text,
                "announcement_text": announcement_text,
                "posted_text": posted_text,
                "closing_text": closing_text,
                "detail_url": detail_url,
                "type": "Open Competitive",
                "status": "continuous" if closing_text.lower() == "continuous" else "",
            }
        )
        if record.get("department", "").lower() == "see below":
            record.pop("department", None)
        if closing_text and closing_text.lower() != "continuous":
            closing_dates = find_dates(closing_text)
            if closing_dates:
                record["deadline"] = closing_dates[0]

        if not record.get("title"):
            continue

        links.append({"text": title[:200], "href": detail_url[:500]})
        records.append(record)

    summary_note = ""
    if records:
        summary_note = f"{len(records)} Nassau County open competitive announcements currently listed."

    return {
        "records": records[:100],
        "summary_note": summary_note,
        "links": links[:100],
    }


def parse_generic_page(soup: BeautifulSoup, text: str, base_url: str) -> dict:
    """Use table extraction first, then fall back to page links and summary text."""
    records = extract_table_records(soup, base_url)
    summary_note = ""

    if not records and "Open Competitive Examination Announcements" in text:
        summary_note = "Open competitive examination announcements are available on the linked application site."
    elif not records and "Civil Service Exams" in text:
        summary_note = "Civil service exam information is available on this source page."

    return {
        "records": records,
        "summary_note": summary_note,
        "links": generic_links(soup, base_url),
    }


def extract_source_data(source_id: str, html: str, base_url: str) -> dict:
    """Return structured data for a source HTML document."""
    if source_id == "usajobs" and html.lstrip().startswith("{"):
        try:
            payload = json.loads(html)
        except json.JSONDecodeError:
            payload = {}
        parsed = parse_usajobs_json(payload, base_url)
        soup = BeautifulSoup("", "html.parser")
        text = ""
    else:
        soup = BeautifulSoup(html, "html.parser")
        text = soup_text(html)

    if source_id == "usajobs":
        if not html.lstrip().startswith("{"):
            parsed = parse_usajobs(soup, text, base_url)
    elif source_id == "mta":
        parsed = parse_mta(soup, text, base_url)
    elif source_id == "nassau_county" and soup.select("li.list-item[data-job-id]"):
        parsed = parse_nassau_listings(soup, base_url)
    elif source_id == "orange_county":
        parsed = {
            "records": parse_orange_text(text, base_url),
            "summary_note": "Open competitive and continuous recruitment exam listings.",
            "links": generic_links(soup, base_url),
        }
    else:
        parsed = parse_generic_page(soup, text, base_url)

    records = parsed.get("records", [])
    summary_note = parsed.get("summary_note", "")
    links = parsed.get("links", generic_links(soup, base_url))

    exam_titles = dedupe([record.get("title", "") for record in records])[:20]
    record_dates = []
    record_fragments = []
    for record in records:
        for key in ("application_period", "deadline", "exam_date", "posted_date", "opening_date"):
            if record.get(key):
                record_dates.append(record[key])
        for key, value in record.items():
            if isinstance(value, str) and key != "detail_url":
                record_fragments.append(value)
    dates = dedupe(record_dates + find_dates("\n".join(record_fragments + [summary_note])))[:30]

    if records:
        normalized_text = "\n".join(row_signature(record) for record in records if row_signature(record))
    else:
        normalized_text = summary_note or text[:2000]

    keywords_found = find_keywords("\n".join([normalized_text, summary_note, "\n".join(record_fragments)]))
    return {
        "links": links[:100],
        "records": records[:100],
        "record_count": len(records),
        "record_fields_present": record_fields_present(records),
        "exam_titles": exam_titles,
        "dates": dates,
        "keywords_found": keywords_found,
        "summary_note": summary_note,
        "normalized_text": normalized_text.strip(),
        "record_fingerprint": fingerprint_records(records, summary_note),
    }
