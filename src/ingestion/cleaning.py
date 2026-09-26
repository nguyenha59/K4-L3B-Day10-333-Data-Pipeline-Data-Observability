from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import html
import re

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord

CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "abs_url",
    "pdf_url",
    "comment",
    "age_days",
    "authors_joined",
    "categories_joined",
    "summary_chars",
    "text_for_embedding",
]


def clean_text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    without_tags = re.sub(r"<[^>]+>", " ", str(value))
    return normalize_whitespace(html.unescape(without_tags))


def _clean_list(values: object) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    cleaned: list[str] = []
    for value in values:
        text = clean_text(value)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def build_text_for_embedding(row: pd.Series | dict) -> str:
    """Five-part document text: title, authors, published, categories, summary."""
    return "\n".join(
        [
            f"Title: {row['title']}",
            f"Authors: {row['authors_joined']}",
            f"Published: {row['published']}",
            f"Categories: {row['categories_joined']}",
            f"Summary: {row['summary']}",
        ]
    )


def add_derived_columns(df: pd.DataFrame, run_date: datetime) -> pd.DataFrame:
    """(Re)compute every derived column from the base columns. Reused by corruption/repair flows."""
    df = df.copy()
    published = pd.to_datetime(df["published"], errors="coerce")
    run_day = pd.Timestamp(run_date.date())
    df["age_days"] = (run_day - published).dt.days.astype("Int64")
    df["authors_joined"] = df["authors"].apply(compact_join)
    df["categories_joined"] = df["categories"].apply(compact_join)
    df["summary_chars"] = df["summary"].fillna("").str.len().astype(int)
    df["text_for_embedding"] = df.apply(build_text_for_embedding, axis=1)
    return df


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    df = pd.DataFrame([asdict(record) for record in records])
    if df.empty:
        return pd.DataFrame(columns=CLEAN_COLUMNS)

    df["paper_id"] = df["paper_id"].apply(clean_text).str.lower()
    for column in ("title", "summary", "primary_category", "abs_url", "pdf_url", "comment"):
        df[column] = df[column].apply(clean_text)
    df["authors"] = df["authors"].apply(_clean_list)
    df["categories"] = df["categories"].apply(_clean_list)
    df["primary_category"] = df.apply(
        lambda row: row["primary_category"] or (row["categories"][0] if row["categories"] else "Uncategorized"),
        axis=1,
    )

    published = pd.to_datetime(df["published"], errors="coerce")
    updated = pd.to_datetime(df["updated"], errors="coerce").fillna(published)
    df["published"] = published.dt.strftime("%Y-%m-%d")
    df["updated"] = updated.dt.strftime("%Y-%m-%d")

    # Filter rows that cannot serve retrieval: missing identity, title, abstract or a parseable date.
    valid = (df["paper_id"] != "") & (df["title"] != "") & (df["summary"] != "") & published.notna()
    df = df.loc[valid]

    # Keep the most recently updated version of each paper.
    df = df.sort_values(["paper_id", "updated"], ascending=[True, False]).drop_duplicates("paper_id", keep="first")

    df = add_derived_columns(df, run_date)
    df = df.sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
    return df[CLEAN_COLUMNS]
