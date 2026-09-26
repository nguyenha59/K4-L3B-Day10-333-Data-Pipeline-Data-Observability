from __future__ import annotations

import pandas as pd
import pytest
import requests

from core.utils import read_json
from ingestion import crossref
from ingestion.cleaning import CLEAN_COLUMNS, build_clean_dataframe
from ingestion.crossref import PaperRecord, fetch_source_records, load_raw_records, parse_crossref_payload

from conftest import RAW_DIR, RUN_DATE


def _item(**overrides) -> dict:
    item = {
        "DOI": "10.1/ABC",
        "title": ["  A   Title  "],
        "abstract": "<jats:p>Some <jats:italic>abstract</jats:italic> text &amp; more.</jats:p>",
        "author": [{"given": "Minh", "family": "Nguyen"}, {"name": "Org Consortium"}, {}],
        "subject": ["AI", " IR "],
        "published": {"date-parts": [[2026, 5]]},
        "created": {"date-time": "2026-05-20T10:00:00Z"},
        "URL": "https://doi.org/10.1/abc",
    }
    item.update(overrides)
    return item


# ---------------------------------------------------------------- crossref.py
def test_parse_payload_normalizes_fields():
    [record] = parse_crossref_payload({"message": {"items": [_item()]}})
    assert record.paper_id == "10.1/abc"
    assert record.title == "A Title"
    assert record.summary == "Some abstract text & more."
    assert "<" not in record.summary
    assert record.authors == ["Minh Nguyen", "Org Consortium"]
    assert record.categories == ["AI", "IR"]
    assert record.primary_category == "AI"
    assert record.published == "2026-05-01"
    assert record.updated == "2026-05-20"


def test_parse_payload_drops_invalid_and_duplicate_items():
    items = [
        _item(),
        _item(),  # duplicate DOI
        _item(DOI="10.1/no-title", title=[]),
        _item(DOI="10.1/no-abstract", abstract=""),
        _item(DOI="10.1/no-date", published=None),
        _item(DOI="", title=["No DOI"]),
    ]
    assert [r.paper_id for r in parse_crossref_payload({"message": {"items": items}})] == ["10.1/abc"]


def test_parse_payload_date_fallbacks_and_defaults():
    item = _item(published=None, issued={"date-parts": [[2025, 1, 2]]}, subject=[], created={})
    item["link"] = [{"URL": "https://x/paper.pdf", "content-type": "application/pdf"}]
    [record] = parse_crossref_payload({"message": {"items": [item]}})
    assert record.published == "2025-01-02"
    assert record.updated == "2025-01-02"
    assert record.primary_category == "Uncategorized"
    assert record.pdf_url == "https://x/paper.pdf"


def test_snapshot_parses_to_shipped_records():
    payload = read_json(RAW_DIR / "crossref_response.json")
    records = parse_crossref_payload(payload)
    assert len(records) == 24
    assert all("<" not in r.summary for r in records)


def test_fetch_uses_local_snapshot_by_default(settings):
    records = fetch_source_records(settings)
    assert len(records) == 24
    assert load_raw_records(settings.paths.raw_records_json) == records


def test_fetch_falls_back_to_snapshot_when_api_fails(settings, monkeypatch):
    settings = type(settings)(**{**settings.__dict__, "refresh_source": True})
    calls = []

    def failing_get(*args, **kwargs):
        calls.append(1)
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(crossref.requests, "get", failing_get)
    monkeypatch.setattr(crossref.time, "sleep", lambda _: None)
    assert len(fetch_source_records(settings)) == 24
    assert len(calls) == crossref.MAX_ATTEMPTS


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)

    def json(self):
        return self._payload


def test_fetch_retries_429_then_saves_live_payload(settings, monkeypatch):
    settings = type(settings)(**{**settings.__dict__, "refresh_source": True})
    live = {"message": {"items": [_item()]}}
    responses = [_FakeResponse(429, headers={"Retry-After": "1"}), _FakeResponse(200, live)]
    sleeps = []
    monkeypatch.setattr(crossref.requests, "get", lambda *a, **k: responses.pop(0))
    monkeypatch.setattr(crossref.time, "sleep", sleeps.append)

    records = fetch_source_records(settings)
    assert [r.paper_id for r in records] == ["10.1/abc"]
    assert sleeps == [1.0]
    assert read_json(settings.paths.raw_api_response) == live


def test_fetch_without_any_snapshot_raises(settings, monkeypatch):
    settings.paths.raw_api_response.unlink()
    monkeypatch.setattr(crossref, "_request_crossref", lambda s: (_ for _ in ()).throw(RuntimeError("down")))
    with pytest.raises(FileNotFoundError):
        fetch_source_records(settings)


# ---------------------------------------------------------------- cleaning.py
def test_clean_dataframe_schema_and_rows(clean_df):
    assert len(clean_df) == 24
    assert list(clean_df.columns) == CLEAN_COLUMNS
    assert clean_df["paper_id"].is_unique
    assert clean_df["published"].is_monotonic_decreasing


def test_age_days_and_text_for_embedding(clean_df):
    row = clean_df.iloc[0]
    expected_age = (pd.Timestamp("2026-09-26") - pd.Timestamp(row["published"])).days
    assert row["age_days"] == expected_age
    parts = row["text_for_embedding"].split("\n")
    assert [p.split(":")[0] for p in parts] == ["Title", "Authors", "Published", "Categories", "Summary"]
    assert row["summary_chars"] == len(row["summary"])


def test_clean_dedups_and_filters_bad_rows(raw_records):
    base = raw_records[0]
    older = PaperRecord(**{**base.__dict__, "paper_id": base.paper_id.upper(), "updated": "2000-01-01", "title": "Old"})
    blank = PaperRecord(**{**raw_records[1].__dict__, "paper_id": "10.9/blank", "summary": "  "})
    bad_date = PaperRecord(**{**raw_records[2].__dict__, "paper_id": "10.9/date", "published": "not-a-date"})
    df = build_clean_dataframe([older, base, blank, bad_date], RUN_DATE)
    assert df["paper_id"].tolist() == [base.paper_id]
    assert df.iloc[0]["title"] == base.title  # most recently updated version wins


def test_clean_empty_input():
    df = build_clean_dataframe([], RUN_DATE)
    assert df.empty and list(df.columns) == CLEAN_COLUMNS
