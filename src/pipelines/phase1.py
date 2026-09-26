from __future__ import annotations

import re
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex


def save_clean_artifacts(df: pd.DataFrame, csv_path, json_path) -> None:
    write_csv(df, csv_path)
    write_json(json_path, df.to_dict(orient="records"))


def _run_agent_demo(settings: Settings, index: LocalEmbeddingIndex, test_set: list[dict[str, Any]]) -> None:
    """Optional LLM agent demo; skipped gracefully when no provider credentials are configured."""
    questions = [item["question"] for item in test_set[:2]]
    try:
        from retrieval.agent import build_agent, run_agent_question

        agent = build_agent(settings, index)
        answers = [{"question": q, "answer": run_agent_question(agent, q)} for q in questions]
        status = "ok"
    except Exception as exc:  # the baseline metrics do not depend on the agent demo
        answers = [{"question": q, "answer": None} for q in questions]
        # Never persist provider error bodies: they can echo (partially masked) API keys.
        status = f"skipped: {type(exc).__name__}: {re.sub(r'(sk|AIza)[-_A-Za-z0-9*]{6,}', '<redacted>', str(exc))[:160]}"
    write_json(settings.paths.demo_answers, {"provider": settings.llm_provider, "status": status, "answers": answers})
    print(f"[phase1] Agent demo: {status}")


def run_phase1_pipeline(settings: Settings) -> dict[str, Any]:
    """Ingest -> Clean -> Index ChromaDB -> Test set -> Baseline evaluation -> GX quality gate + report."""
    paths = settings.paths
    run_date = now_utc()

    records = fetch_source_records(settings)
    print(f"[phase1] Raw records: {len(records)}")

    clean_df = build_clean_dataframe(records, run_date)
    save_clean_artifacts(clean_df, paths.clean_csv, paths.clean_json)
    print(f"[phase1] Clean rows: {len(clean_df)} -> {paths.clean_json.relative_to(paths.project_dir)}")

    index = LocalEmbeddingIndex.build(clean_df, settings, paths.embeddings_json)
    print(f"[phase1] Chroma collection '{index.collection_name}': {index.collection.count()} docs")

    if paths.eval_testset.exists() and not settings.refresh_test_set:
        test_set = read_json(paths.eval_testset)
        print(f"[phase1] Reusing test set ({len(test_set)} questions)")
    else:
        test_set = build_test_set(clean_df, paths.eval_testset)
        print(f"[phase1] Built test set ({len(test_set)} questions)")

    bundle = evaluate_pipeline(settings, index, paths.eval_testset, paths.baseline_metrics, paths.baseline_answers)
    quality = run_data_quality_checks(clean_df, settings, "baseline")
    freshness = build_freshness_report(clean_df, settings, paths.freshness_report)

    source_summary = {
        "source_api": settings.source_api,
        "query": settings.source_query,
        "filter": settings.source_filter,
        "mode": "live fetch" if settings.refresh_source else "local snapshot (set REFRESH_SOURCE=1 for live)",
        "raw_records": len(records),
        "clean_rows": len(clean_df),
        "embedding_model": settings.embedding_model,
        "collection": index.collection_name,
        "top_k": settings.top_k,
        "llm_provider": settings.llm_provider,
        "run_date": run_date.isoformat(timespec="seconds"),
    }
    generate_phase1_report(paths.baseline_report, source_summary, bundle.summary, quality, freshness)

    _run_agent_demo(settings, index, test_set)

    print(
        "[phase1] Baseline metrics: "
        + ", ".join(f"{k}={bundle.summary[k]:.4f}" for k in ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"))
    )
    print(f"[phase1] Quality gate success={quality['success']} | freshness is_fresh={freshness['is_fresh']}")
    print(f"[phase1] Report -> {paths.baseline_report.relative_to(paths.project_dir)}")
    return {"metrics": bundle.summary, "quality": quality, "freshness": freshness}


def main() -> None:
    run_phase1_pipeline(load_settings())
