from __future__ import annotations

import pandas as pd

from core.utils import read_json
from ingestion.corruption import STALE_SHIFT_DAYS, corrupt_clean_dataframe
from observability.quality import build_freshness_report, evaluate_freshness_sla, run_data_quality_checks

from conftest import RUN_DATE

EXPECTED_SCENARIOS = [
    "drop_latest_records",
    "blank_summary",
    "inject_noise",
    "truncate_title",
    "stale_date",
    "duplicate_rows",
]


# ---------------------------------------------------------------- quality.py (GX 1.x)
def test_quality_gate_passes_on_clean_data(clean_df, settings):
    report = run_data_quality_checks(clean_df, settings, "baseline")
    assert report["success"] is True
    assert report["engine"].startswith("great_expectations 1.")
    types = {check["expectation"] for check in report["checks"]}
    assert {
        "expect_table_row_count_to_be_between",
        "expect_column_values_to_not_be_null",
        "expect_column_values_to_be_unique",
        "expect_column_value_lengths_to_be_between",
    } <= types
    assert (settings.paths.quality_dir / "baseline_quality_report.json").exists()
    assert (settings.paths.gx_dir / "papers_baseline_suite.json").exists()


def test_quality_gate_catches_each_defect(clean_df, settings):
    bad = clean_df.copy()
    bad.loc[0, "summary"] = "too short"
    bad.loc[1, "title"] = "Tiny"
    bad.loc[2, "paper_id"] = None
    bad = pd.concat([bad, bad.iloc[[3]]], ignore_index=True)
    report = run_data_quality_checks(bad, settings, "broken")
    assert report["success"] is False
    assert set(report["failed_checks"]) == {
        "expect_column_value_lengths_to_be_between(summary)",
        "expect_column_value_lengths_to_be_between(title)",
        "expect_column_values_to_not_be_null(paper_id)",
        "expect_column_values_to_be_unique(paper_id)",
    }


def test_quality_gate_row_count_bounds(clean_df, settings):
    report = run_data_quality_checks(clean_df.head(3), settings, "tiny")
    assert "expect_table_row_count_to_be_between(table)" in report["failed_checks"]


def test_freshness_sla_threshold(clean_df, settings):
    fresh = evaluate_freshness_sla(clean_df, settings)
    assert fresh["is_fresh"] is True
    assert fresh["total_rows"] == 24 and fresh["stale_rows"] == 1

    stale = clean_df.copy()
    stale.loc[:6, "age_days"] = 500  # 7 new + 1 already stale = 8/24 = 33% > 25%
    result = evaluate_freshness_sla(stale, settings)
    assert result["stale_rows"] == 8 and result["is_fresh"] is False

    report = build_freshness_report(stale, settings, settings.paths.freshness_report)
    assert read_json(settings.paths.freshness_report)["is_fresh"] is False
    assert report["latest_published"] == clean_df["published"].max()


def test_freshness_on_empty_frame(settings):
    empty = pd.DataFrame({"published": [], "age_days": []})
    assert evaluate_freshness_sla(empty, settings)["is_fresh"] is False


# ---------------------------------------------------------------- corruption.py
def test_corruption_injects_six_logged_scenarios(clean_df, tmp_path):
    log_path = tmp_path / "corruption_log.json"
    corrupted = corrupt_clean_dataframe(clean_df, log_path, RUN_DATE)
    log = read_json(log_path)

    assert [s["scenario"] for s in log["scenarios"]] == EXPECTED_SCENARIOS
    assert log["rows_before"] == 24 and log["rows_after"] == len(corrupted) == 21
    for scenario in log["scenarios"]:
        assert scenario["rows_affected"] == len(scenario["changes"]) > 0

    by_name = {s["scenario"]: s for s in log["scenarios"]}
    assert not corrupted["paper_id"].is_unique
    assert (corrupted["summary"] == "").sum() >= 3
    assert (corrupted["title"].str.len() < 8).sum() >= 3
    stale_change = by_name["stale_date"]["changes"][0]
    shift = pd.Timestamp(stale_change["before"]) - pd.Timestamp(stale_change["after"])
    assert shift.days == STALE_SHIFT_DAYS
    dropped = {c["paper_id"] for c in by_name["drop_latest_records"]["changes"]}
    assert dropped.isdisjoint(set(corrupted["paper_id"]))


def test_corruption_is_deterministic_and_rebuilds_text(clean_df, tmp_path):
    first = corrupt_clean_dataframe(clean_df, tmp_path / "a.json", RUN_DATE)
    second = corrupt_clean_dataframe(clean_df, tmp_path / "b.json", RUN_DATE)
    pd.testing.assert_frame_equal(first, second)
    assert all(f"Title: {t}" in text for t, text in zip(first["title"], first["text_for_embedding"]))
    assert len(clean_df) == 24  # input dataframe is not mutated


def test_quality_gate_fails_on_corrupted_data(clean_df, settings, tmp_path):
    corrupted = corrupt_clean_dataframe(clean_df, tmp_path / "log.json", RUN_DATE)
    report = run_data_quality_checks(corrupted, settings, "corrupted")
    assert report["success"] is False
    assert report["is_fresh"] is False
    assert "expect_column_values_to_be_unique(paper_id)" in report["failed_checks"]
