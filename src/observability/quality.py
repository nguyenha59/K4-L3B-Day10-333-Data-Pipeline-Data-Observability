from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any

import great_expectations as gx
import great_expectations.expectations as gxe
import pandas as pd

from core.config import Settings
from core.utils import write_json

MIN_ROWS = 5
MAX_ROWS = 5000
MIN_SUMMARY_CHARS = 30
MIN_TITLE_CHARS = 8
MAX_STALE_RATIO = 0.25
NOT_NULL_COLUMNS = ["paper_id", "title", "text_for_embedding"]


def _build_suite(settings: Settings, suite_name: str) -> gx.ExpectationSuite:
    expectations: list[gxe.Expectation] = [
        # 1. Volume: record count must stay within the expected operating range.
        gxe.ExpectTableRowCountToBeBetween(min_value=MIN_ROWS, max_value=MAX_ROWS),
        # 2. Completeness: fields every document needs for identity and embedding.
        *[gxe.ExpectColumnValuesToNotBeNull(column=column) for column in NOT_NULL_COLUMNS],
        # 3. Uniqueness: document identity must be stable for ground-truth doc IDs.
        gxe.ExpectColumnValuesToBeUnique(column="paper_id"),
        # 4. Validity: blank/short abstracts make retrieval silently worse.
        gxe.ExpectColumnValueLengthsToBeBetween(column="summary", min_value=MIN_SUMMARY_CHARS),
        # Extra: truncated titles break exact-title lookup in the QA layer.
        gxe.ExpectColumnValueLengthsToBeBetween(column="title", min_value=MIN_TITLE_CHARS),
        # Extra: Freshness SLA inside the gate — at least 75% of papers must be <= threshold days old.
        gxe.ExpectColumnValuesToBeBetween(
            column="age_days",
            min_value=0,
            max_value=settings.freshness_threshold_days,
            mostly=1 - MAX_STALE_RATIO,
        ),
    ]
    return gx.ExpectationSuite(name=suite_name, expectations=expectations)


def _summarize_result(result: Any) -> dict[str, Any]:
    payload = result.to_json_dict()
    config = payload.get("expectation_config", {})
    details = payload.get("result", {}) or {}
    return {
        "expectation": config.get("type"),
        "column": config.get("kwargs", {}).get("column"),
        "kwargs": {k: v for k, v in config.get("kwargs", {}).items() if k not in {"column", "batch_id"}},
        "success": bool(payload.get("success")),
        "observed_value": details.get("observed_value"),
        "unexpected_count": details.get("unexpected_count"),
        "unexpected_percent": details.get("unexpected_percent"),
        "partial_unexpected_list": details.get("partial_unexpected_list", [])[:5],
    }


def _validation_frame(df: pd.DataFrame) -> pd.DataFrame:
    """GX works best with scalar columns: list columns are dropped, blank identity/text fields count as null."""
    scalar_columns = [c for c in df.columns if c not in {"authors", "categories"}]
    frame = df[scalar_columns].copy()
    for column in NOT_NULL_COLUMNS:
        if column in frame:
            frame[column] = frame[column].astype("object").where(frame[column].astype(str).str.strip() != "", None)
    if "summary" in frame:
        frame["summary"] = frame["summary"].fillna("").astype(str)
    if "age_days" in frame:
        frame["age_days"] = pd.to_numeric(frame["age_days"], errors="coerce").astype("float64")
    return frame


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, stage: str) -> dict[str, Any]:
    logging.getLogger("great_expectations").setLevel(logging.ERROR)
    context = gx.get_context(mode="ephemeral")
    data_source = context.data_sources.add_pandas(name="papers_source")
    data_asset = data_source.add_dataframe_asset(name="papers_asset")
    batch_def = data_asset.add_batch_definition_whole_dataframe("papers_batch")
    batch = batch_def.get_batch(batch_parameters={"dataframe": _validation_frame(df)})
    suite = context.suites.add(_build_suite(settings, f"papers_{stage}_suite"))
    result = batch.validate(suite)

    checks = [_summarize_result(item) for item in result.results]
    freshness = evaluate_freshness_sla(df, settings)
    report = {
        "stage": stage,
        "engine": f"great_expectations {gx.__version__}",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "row_count": int(len(df)),
        "success": bool(result.success),
        "is_fresh": freshness["is_fresh"],
        "statistics": {
            "evaluated_expectations": len(checks),
            "successful_expectations": sum(1 for c in checks if c["success"]),
            "unsuccessful_expectations": sum(1 for c in checks if not c["success"]),
        },
        "failed_checks": [f"{c['expectation']}({c['column'] or 'table'})" for c in checks if not c["success"]],
        "checks": checks,
        "freshness": freshness,
    }
    write_json(settings.paths.gx_dir / f"{suite.name}.json", suite.to_json_dict())
    write_json(settings.paths.quality_dir / f"{stage}_quality_report.json", report)
    return report


def evaluate_freshness_sla(df: pd.DataFrame, settings: Settings) -> dict[str, Any]:
    """Freshness SLA: is_fresh=False when more than 25% of papers have age_days > threshold (180)."""
    threshold = settings.freshness_threshold_days
    published = pd.to_datetime(df["published"], errors="coerce")
    age_days = pd.to_numeric(df["age_days"], errors="coerce")
    total_rows = int(len(df))
    stale_rows = int((age_days > threshold).sum())
    stale_ratio = stale_rows / total_rows if total_rows else 1.0
    return {
        "latest_published": published.max().strftime("%Y-%m-%d") if published.notna().any() else None,
        "oldest_published": published.min().strftime("%Y-%m-%d") if published.notna().any() else None,
        "median_age_days": float(age_days.median()) if age_days.notna().any() else None,
        "max_age_days": int(age_days.max()) if age_days.notna().any() else None,
        "threshold_days": threshold,
        "max_stale_ratio": MAX_STALE_RATIO,
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "stale_ratio": round(stale_ratio, 4),
        "is_fresh": bool(total_rows > 0 and stale_ratio <= MAX_STALE_RATIO),
    }


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    payload = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), **evaluate_freshness_sla(df, settings)}
    write_json(report_path, payload)
    return payload
