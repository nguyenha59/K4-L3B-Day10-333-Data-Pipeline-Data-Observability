from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import CLEAN_COLUMNS, build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records, parse_crossref_payload
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import METRIC_KEYS, generate_corruption_report
from pipelines.phase1 import save_clean_artifacts
from retrieval.index import LocalEmbeddingIndex


def repair_from_raw_snapshot(settings: Settings, run_date: datetime) -> tuple[pd.DataFrame, Path]:
    """Idempotent repair: rebuild the clean layer from the immutable raw snapshot, never from corrupted data.

    Running it any number of times yields the same dataframe because it only depends on the raw files.
    """
    paths = settings.paths
    if paths.raw_records_json.exists():
        records, source = load_raw_records(paths.raw_records_json), paths.raw_records_json
    else:
        records, source = parse_crossref_payload(read_json(paths.raw_api_response)), paths.raw_api_response
    repaired_df = build_clean_dataframe(records, run_date)
    save_clean_artifacts(repaired_df, paths.repaired_clean_csv, paths.repaired_clean_json)
    return repaired_df, source


def _gate_passed(quality: dict[str, Any], freshness: dict[str, Any]) -> bool:
    return bool(quality["success"] and freshness["is_fresh"])


def _print_table(baseline: dict, corrupted: dict, repaired: dict, qualities: list[dict], freshness: list[dict]) -> None:
    header = f"{'metric':<22}{'baseline':>12}{'corrupted':>12}{'repaired':>12}"
    print("\n" + header + "\n" + "-" * len(header))
    for key in METRIC_KEYS:
        print(f"{key:<22}{baseline[key]:>12.4f}{corrupted[key]:>12.4f}{repaired[key]:>12.4f}")
    print(f"{'quality_gate':<22}" + "".join(f"{('PASS' if q['success'] else 'FAIL'):>12}" for q in qualities))
    print(f"{'freshness':<22}" + "".join(f"{('Fresh' if f['is_fresh'] else 'Stale'):>12}" for f in freshness))
    print()


def run_corruption_flow_pipeline(settings: Settings) -> dict[str, Any]:
    """Corrupt -> re-index & evaluate (silent failure) -> gate -> repair from raw -> re-evaluate -> compare."""
    paths = settings.paths
    run_date = now_utc()

    if not paths.baseline_metrics.exists() or not paths.clean_json.exists():
        raise SystemExit("Baseline artifacts missing. Run `python script/run_phase1.py` first.")
    baseline_metrics = read_json(paths.baseline_metrics)
    baseline_quality = read_json(paths.baseline_quality_report)
    baseline_freshness = read_json(paths.freshness_report)
    clean_df = pd.DataFrame(read_json(paths.clean_json))

    # --- Corrupt -------------------------------------------------------------------------------
    corrupted_df = corrupt_clean_dataframe(clean_df, paths.corruption_log, run_date)
    save_clean_artifacts(corrupted_df, paths.corrupted_clean_csv, paths.corrupted_clean_json)
    print(f"[corruption] Injected 6 scenarios: {len(clean_df)} -> {len(corrupted_df)} rows")

    corrupted_index = LocalEmbeddingIndex.build(corrupted_df, settings, paths.corrupted_embeddings_json)
    corrupted_eval = evaluate_pipeline(
        settings, corrupted_index, paths.eval_testset, paths.corrupted_metrics, paths.corrupted_answers
    )
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, "corrupted")
    corrupted_freshness = build_freshness_report(
        corrupted_df, settings, paths.quality_dir / "corrupted_freshness_report.json"
    )
    print(
        f"[corruption] Quality gate success={corrupted_quality['success']} "
        f"failed={corrupted_quality['failed_checks']} | is_fresh={corrupted_freshness['is_fresh']}"
    )

    # --- Auto-repair: triggered by the quality gate, rebuilt from the raw snapshot ---------------
    if _gate_passed(corrupted_quality, corrupted_freshness):
        print("[repair] Quality gate passed on corrupted data; repair not triggered by the gate, running anyway.")
    else:
        print("[repair] Quality gate FAILED -> triggering idempotent repair from raw snapshot.")
    repaired_df, source = repair_from_raw_snapshot(settings, run_date)

    repaired_quality = run_data_quality_checks(repaired_df, settings, "repaired")
    repaired_freshness = build_freshness_report(
        repaired_df, settings, paths.quality_dir / "repaired_freshness_report.json"
    )
    if not _gate_passed(repaired_quality, repaired_freshness):
        raise SystemExit(f"[repair] Repaired data still fails the gate: {repaired_quality['failed_checks']}")

    compare_columns = [c for c in CLEAN_COLUMNS if c != "age_days"]
    idempotent = repaired_df[compare_columns].reset_index(drop=True).astype(str).equals(
        clean_df[compare_columns].reset_index(drop=True).astype(str)
    )
    print(f"[repair] Rebuilt {len(repaired_df)} rows from {source.name}; identical to baseline clean data: {idempotent}")

    repaired_index = LocalEmbeddingIndex.build(repaired_df, settings, paths.repaired_embeddings_json)
    repaired_eval = evaluate_pipeline(
        settings, repaired_index, paths.eval_testset, paths.repaired_metrics, paths.repaired_answers
    )

    # --- Compare -------------------------------------------------------------------------------
    generate_corruption_report(
        paths.comparison_report,
        baseline_metrics,
        corrupted_eval.summary,
        repaired_eval.summary,
        corrupted_quality,
        repaired_quality,
        corrupted_freshness,
        repaired_freshness,
        baseline_quality=baseline_quality,
        baseline_freshness=baseline_freshness,
        corruption_log=read_json(paths.corruption_log),
    )
    _print_table(
        baseline_metrics,
        corrupted_eval.summary,
        repaired_eval.summary,
        [baseline_quality, corrupted_quality, repaired_quality],
        [baseline_freshness, corrupted_freshness, repaired_freshness],
    )
    print(f"[report] -> {paths.comparison_report.relative_to(paths.project_dir)}")
    return {
        "baseline": baseline_metrics,
        "corrupted": corrupted_eval.summary,
        "repaired": repaired_eval.summary,
        "idempotent_repair": idempotent,
    }


def main() -> None:
    run_corruption_flow_pipeline(load_settings())
