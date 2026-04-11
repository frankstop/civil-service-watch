"""Source-aware extraction helpers shared by fetch and report generation."""

from __future__ import annotations

import hashlib
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
        record.get("exam_number", ""),
        record.get("title", ""),
        record.get("type", ""),
        record.get("application_period", ""),
        record.get("deadline", ""),
        record.get("exam_date", ""),
        record.get("agency", ""),
        record.get("salary", ""),
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


def map_header(header: str) -> str | None:
    """Map a source table header to a normalized record key."""
    normalized = clean_text(header).lower()
    mapping = {
        "title of exam": "title",
        "exam title": "title",
        "exam no.": "exam_number",
        "exam no": "exam_number",
        "exam number": "exam_number",
        "application period": "application_period",
        "last date to apply": "deadline",
        "deadline": "deadline",
        "exam date": "exam_date",
        "test date": "exam_date",
        "salary": "salary",
        "jurisdiction or agency": "agency",
        "agency": "agency",
        "type": "type",
        "non-refundable processing fee": "fee",
        "processing fee": "fee",
    }
    return mapping.get(normalized)


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
                all_records.append(record)

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


def parse_usajobs(soup: BeautifulSoup, text: str, base_url: str) -> dict:
    """Return a compact result for USAJOBS search pages."""
    summary_note = ""
    records: list[dict] = []
    if "No jobs found" in text or "We couldn't find any results." in text:
        summary_note = "No matching USAJOBS listings found for the current search."
    return {
        "records": records,
        "summary_note": summary_note,
        "links": [],
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
    soup = BeautifulSoup(html, "html.parser")
    text = soup_text(html)

    if source_id == "usajobs":
        parsed = parse_usajobs(soup, text, base_url)
    elif source_id == "mta":
        parsed = parse_mta(soup, text, base_url)
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
    for record in records:
        for key in ("application_period", "deadline", "exam_date"):
            if record.get(key):
                record_dates.append(record[key])
    dates = dedupe(record_dates + find_dates(summary_note))[:30]

    if records:
        normalized_text = "\n".join(row_signature(record) for record in records if row_signature(record))
    else:
        normalized_text = summary_note or text[:2000]

    keywords_found = find_keywords("\n".join([normalized_text, summary_note]))
    return {
        "links": links[:100],
        "records": records[:100],
        "record_count": len(records),
        "exam_titles": exam_titles,
        "dates": dates,
        "keywords_found": keywords_found,
        "summary_note": summary_note,
        "normalized_text": normalized_text.strip(),
        "record_fingerprint": fingerprint_records(records, summary_note),
    }
