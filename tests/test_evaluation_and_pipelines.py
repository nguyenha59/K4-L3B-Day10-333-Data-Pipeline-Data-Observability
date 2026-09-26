from __future__ import annotations

from collections import Counter

import pytest

from core.utils import read_json
from evaluation.metrics import _judge_answer, _run_ragas, _token_f1
from evaluation.testset import build_test_set
from observability.reporting import METRIC_KEYS, _fmt, _recovery, generate_phase1_report

# ---------------------------------------------------------------- testset.py
def test_test_set_has_ten_questions_across_four_types(clean_df, tmp_path):
    path = tmp_path / "test_set.json"
    test_set = build_test_set(clean_df, path)
    assert len(test_set) == 10
    assert read_json(path) == test_set
    assert Counter(item["question_type"] for item in test_set) == {
        "summary": 3,
        "authors": 3,
        "date": 2,
        "categories": 2,
    }
    assert [item["id"] for item in test_set] == [f"eval_{n:03d}" for n in range(1, 11)]
    ids = set(clean_df["paper_id"])
    for item in test_set:
        assert set(item) == {"id", "question_type", "question", "ground_truth", "ground_truth_doc_ids"}
        assert item["ground_truth"] and item["ground_truth_doc_ids"][0] in ids
    assert len({item["ground_truth_doc_ids"][0] for item in test_set}) == 10


def test_test_set_requires_enough_documents(clean_df, tmp_path):
    with pytest.raises(ValueError, match="at least 10"):
        build_test_set(clean_df.head(5), tmp_path / "t.json")


# ---------------------------------------------------------------- metrics.py
def test_token_f1():
    assert _token_f1("Minh Nguyen, Hoang Le", "minh nguyen, hoang le") == 1.0
    assert _token_f1("a b", "c d") == 0.0
    assert _token_f1("", "anything") == 0.0
    assert 0 < _token_f1("a b c d", "a b") < 1


def test_judge_falls_back_to_heuristic_with_mock_llm(settings):
    exact = _judge_answer(settings, "q", "2026-06-03", "2026-06-03")
    wrong = _judge_answer(settings, "q", "2026-06-03", "2025-06-03")
    assert (exact.score, exact.correct) == (5, True)
    assert (wrong.score, wrong.correct) == (1, False)


def test_ragas_is_opt_in(settings):
    assert "skipped" in _run_ragas(settings, [])


# ---------------------------------------------------------------- reporting.py
def test_report_helpers():
    assert _fmt(None) == "N/A" and _fmt(True) == "PASS" and _fmt(0.5) == "0.5000"
    assert _recovery(1.0, 0.8, 1.0) == "100%"
    assert _recovery(1.0, 1.0, 1.0) == "no drop"
    assert _recovery(None, 0.8, 1.0) == "—"


def test_phase1_report_contents(tmp_path):
    path = tmp_path / "phase1_report.md"
    quality = {"success": True, "statistics": {}, "checks": [], "engine": "gx"}
    freshness = {"is_fresh": True, "stale_rows": 1, "total_rows": 24, "threshold_days": 180}
    generate_phase1_report(path, {"source": "Crossref"}, {k: 1.0 for k in METRIC_KEYS}, quality, freshness)
    text = path.read_text(encoding="utf-8")
    assert "Baseline evaluation metrics" in text and "Freshness SLA" in text and "Crossref" in text


# ---------------------------------------------------------------- end-to-end pipelines
def test_phase1_produces_all_baseline_artifacts(e2e):
    paths = e2e["settings"].paths
    for path in (
        paths.raw_api_response,
        paths.raw_records_json,
        paths.clean_csv,
        paths.clean_json,
        paths.embeddings_json,
        paths.eval_testset,
        paths.baseline_metrics,
        paths.baseline_answers,
        paths.baseline_quality_report,
        paths.freshness_report,
        paths.baseline_report,
        paths.demo_answers,
    ):
        assert path.exists(), path
    metrics = e2e["phase1"]["metrics"]
    assert metrics["samples"] == 10
    assert metrics["retrieval_hit_rate"] == 1.0
    assert e2e["phase1"]["quality"]["success"] is True
    assert e2e["phase1"]["freshness"]["is_fresh"] is True


def test_corruption_degrades_and_repair_restores(e2e):
    flow = e2e["flow"]
    baseline, corrupted, repaired = flow["baseline"], flow["corrupted"], flow["repaired"]
    assert corrupted["retrieval_hit_rate"] < baseline["retrieval_hit_rate"]
    assert corrupted["mean_token_f1"] < baseline["mean_token_f1"]
    for key in METRIC_KEYS:
        assert repaired[key] == baseline[key]
    assert flow["idempotent_repair"] is True


def test_corruption_flow_artifacts_and_report(e2e):
    paths = e2e["settings"].paths
    for path in (
        paths.corruption_log,
        paths.corrupted_metrics,
        paths.repaired_metrics,
        paths.corrupted_quality_report,
        paths.repaired_clean_json,
    ):
        assert path.exists(), path
    assert read_json(paths.corrupted_quality_report)["success"] is False
    assert read_json(paths.quality_dir / "repaired_quality_report.json")["success"] is True
    report = paths.comparison_report.read_text(encoding="utf-8")
    assert "| Metric / signal | Baseline | Corrupted | Repaired |" in report
    assert "drop_latest_records" in report and "duplicate_rows" in report


def test_corruption_flow_requires_baseline(settings):
    from pipelines.corruption_flow import run_corruption_flow_pipeline

    with pytest.raises(SystemExit, match="run_phase1"):
        run_corruption_flow_pipeline(settings)
