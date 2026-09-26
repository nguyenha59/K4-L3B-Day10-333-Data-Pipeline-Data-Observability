from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import html
import re
import time

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _strip_markup(value: str) -> str:
    """Remove JATS/HTML tags (e.g. <jats:p>) and collapse whitespace."""
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    return normalize_whitespace(html.unescape(without_tags))


def _date_from_parts(node: dict | None) -> str:
    parts = ((node or {}).get("date-parts") or [[]])[0]
    if not parts or parts[0] is None:
        return ""
    year, month, day = (list(parts) + [1, 1])[:3]
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _author_name(author: dict) -> str:
    name = author.get("name") or " ".join(part for part in (author.get("given"), author.get("family")) if part)
    return normalize_whitespace(name)


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    records: list[PaperRecord] = []
    seen: set[str] = set()
    for item in payload.get("message", {}).get("items", []):
        doi = normalize_whitespace(str(item.get("DOI", ""))).lower()
        titles = item.get("title") or []
        title = _strip_markup(titles[0]) if titles else ""
        summary = _strip_markup(item.get("abstract", ""))
        published = (
            _date_from_parts(item.get("published"))
            or _date_from_parts(item.get("published-online"))
            or _date_from_parts(item.get("published-print"))
            or _date_from_parts(item.get("issued"))
        )
        # A record without identity, title, abstract or date cannot be embedded or evaluated.
        if not doi or not title or not summary or not published or doi in seen:
            continue
        seen.add(doi)

        created = (item.get("created") or {}).get("date-time", "")
        updated = created[:10] if created else published
        authors = [name for name in (_author_name(a) for a in item.get("author") or []) if name]
        categories = [normalize_whitespace(s) for s in item.get("subject") or [] if normalize_whitespace(s)]
        url = item.get("URL") or f"https://doi.org/{doi}"
        pdf_links = [link.get("URL") for link in item.get("link") or [] if "pdf" in str(link.get("content-type", ""))]

        records.append(
            PaperRecord(
                paper_id=doi,
                title=title,
                summary=summary,
                authors=authors,
                categories=categories,
                primary_category=categories[0] if categories else "Uncategorized",
                published=published,
                updated=updated,
                abs_url=url,
                pdf_url=pdf_links[0] if pdf_links else url,
                comment=f"Crossref record {doi}",
            )
        )
    return records


def _request_crossref(settings: Settings) -> dict:
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
        "select": "DOI,title,abstract,author,subject,published,published-online,published-print,issued,created,URL,link",
    }
    headers = {"User-Agent": "day10-data-observability-lab/0.1 (mailto:student@example.com)"}
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = requests.get(CROSSREF_WORKS_URL, params=params, headers=headers, timeout=20)
            if response.status_code in RETRY_STATUS_CODES:
                raise requests.HTTPError(f"Crossref returned {response.status_code}", response=response)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            retry_after = getattr(getattr(exc, "response", None), "headers", {}).get("Retry-After")
            time.sleep(float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt)
    raise RuntimeError(f"Crossref request failed after {MAX_ATTEMPTS} attempts: {last_error}")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Fetch from Crossref when REFRESH_SOURCE=1, otherwise (or on failure) use the local snapshot."""
    paths = settings.paths
    payload: dict | None = None
    if settings.refresh_source or not paths.raw_api_response.exists():
        try:
            payload = _request_crossref(settings)
            write_json(paths.raw_api_response, payload)
            print(f"[ingestion] Fetched live Crossref payload -> {paths.raw_api_response.name}")
        except Exception as exc:
            print(f"[ingestion] Live fetch failed ({exc}); falling back to local snapshot.")
    if payload is None:
        if not paths.raw_api_response.exists():
            raise FileNotFoundError(f"No Crossref snapshot available at {paths.raw_api_response}")
        payload = read_json(paths.raw_api_response)

    records = parse_crossref_payload(payload)
    write_json(paths.raw_records_json, [asdict(record) for record in records])
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    return [PaperRecord(**row) for row in read_json(path)]
