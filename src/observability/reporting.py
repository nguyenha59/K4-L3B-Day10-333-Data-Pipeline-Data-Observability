from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core.utils import write_text

METRIC_KEYS = ["retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"]


def _fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _quality_label(quality: dict[str, Any]) -> str:
    stats = quality.get("statistics", {})
    return f"{_fmt(quality.get('success'))} ({stats.get('successful_expectations', '?')}/{stats.get('evaluated_expectations', '?')})"


def _freshness_label(freshness: dict[str, Any]) -> str:
    status = "Fresh" if freshness.get("is_fresh") else "Stale"
    return f"{status} ({freshness.get('stale_rows')}/{freshness.get('total_rows')} > {freshness.get('threshold_days')}d)"


def _checks_table(quality: dict[str, Any]) -> list[str]:
    lines = ["| Expectation | Column | Result | Observed / unexpected |", "| --- | --- | :---: | --- |"]
    for check in quality.get("checks", []):
        observed = check.get("observed_value")
        if observed is None and check.get("unexpected_count") is not None:
            observed = f"{check['unexpected_count']} unexpected ({check.get('unexpected_percent') or 0:.1f}%)"
        lines.append(f"| `{check['expectation']}` | {check.get('column') or 'table'} | {_fmt(check['success'])} | {_fmt(observed)} |")
    return lines


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    lines = [
        "# Phase 1 Report — Baseline Data Pipeline",
        "",
        f"_Generated at {datetime.now(UTC).isoformat(timespec='seconds')} by `script/run_phase1.py`._",
        "",
        "## 1. Source & lineage",
        "",
        "| Field | Value |",
        "| --- | --- |",
        *[f"| {key} | {_fmt(value)} |" for key, value in source_summary.items()],
        "",
        "## 2. Baseline evaluation metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        *[f"| `{key}` | {_fmt(metrics.get(key))} |" for key in ["samples", *METRIC_KEYS]],
        "",
        f"Ragas: `{metrics.get('ragas')}`",
        "",
        "## 3. Data quality gate (Great Expectations 1.x)",
        "",
        f"- Engine: `{quality.get('engine')}`",
        f"- Overall: **{_quality_label(quality)}**",
        f"- Failed checks: {', '.join(quality.get('failed_checks') or []) or 'none'}",
        "",
        *_checks_table(quality),
        "",
        "## 4. Freshness SLA",
        "",
        "| Field | Value |",
        "| --- | --- |",
        *[f"| {key} | {_fmt(value)} |" for key, value in freshness.items() if key != "generated_at"],
        "",
        f"**Status: {_freshness_label(freshness)}** — SLA: stale ratio (`age_days > {freshness.get('threshold_days')}`) "
        f"must be <= {freshness.get('max_stale_ratio')}.",
        "",
    ]
    write_text(report_path, "\n".join(lines))


def _delta(a: Any, b: Any) -> str:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return f"{b - a:+.4f}"
    return "—"


def _recovery(baseline: Any, corrupted: Any, repaired: Any) -> str:
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (baseline, corrupted, repaired)):
        return "—"
    drop = baseline - corrupted
    if abs(drop) < 1e-9:
        return "no drop"
    return f"{(repaired - corrupted) / drop:.0%}"


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
    baseline_quality: dict[str, Any] | None = None,
    baseline_freshness: dict[str, Any] | None = None,
    corruption_log: dict[str, Any] | None = None,
) -> None:
    baseline_quality = baseline_quality or {}
    baseline_freshness = baseline_freshness or {}

    table = [
        "| Metric / signal | Baseline | Corrupted | Repaired | Δ corruption | Recovery |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key in METRIC_KEYS:
        b, c, r = baseline_metrics.get(key), corrupted_metrics.get(key), repaired_metrics.get(key)
        table.append(f"| `{key}` | {_fmt(b)} | {_fmt(c)} | {_fmt(r)} | {_delta(b, c)} | {_recovery(b, c, r)} |")
    table.append(
        f"| Row count | {_fmt(baseline_quality.get('row_count'))} | {_fmt(corrupted_quality.get('row_count'))} "
        f"| {_fmt(repaired_quality.get('row_count'))} | — | — |"
    )
    table.append(
        f"| Quality gate (GX) | {_quality_label(baseline_quality) if baseline_quality else 'N/A'} "
        f"| {_quality_label(corrupted_quality)} | {_quality_label(repaired_quality)} | — | — |"
    )
    table.append(
        f"| Freshness SLA | {_freshness_label(baseline_freshness) if baseline_freshness else 'N/A'} "
        f"| {_freshness_label(corrupted_freshness)} | {_freshness_label(repaired_freshness)} | — | — |"
    )

    lines = [
        "# Corruption Report — Baseline vs Corrupted vs Repaired",
        "",
        f"_Generated at {datetime.now(UTC).isoformat(timespec='seconds')} by `script/run_corruption_flow.py`. "
        "All three states are evaluated on the same test set (`data/eval/test_set.json`)._",
        "",
        "## 1. Three-state comparison",
        "",
        *table,
        "",
        "_Recovery = (repaired − corrupted) / (baseline − corrupted)._",
        "",
    ]

    if corruption_log:
        lines += [
            "## 2. Injected corruptions",
            "",
            f"Rows before: {corruption_log.get('rows_before')} → rows after: {corruption_log.get('rows_after')} "
            f"(seed={corruption_log.get('seed')}).",
            "",
            "| # | Scenario | Rows affected | Details |",
            "| ---: | --- | ---: | --- |",
        ]
        for number, step in enumerate(corruption_log.get("scenarios", []), start=1):
            lines.append(
                f"| {number} | `{step['scenario']}` | {step['rows_affected']} | {step['description']} |"
            )
        lines.append("")

    lines += [
        "## 3. Quality gate on corrupted data",
        "",
        f"Failed checks: {', '.join(corrupted_quality.get('failed_checks') or []) or 'none'}",
        "",
        *_checks_table(corrupted_quality),
        "",
        "## 4. Quality gate on repaired data",
        "",
        f"Failed checks: {', '.join(repaired_quality.get('failed_checks') or []) or 'none'}",
        "",
        *_checks_table(repaired_quality),
        "",
        "## 5. Analysis",
        "",
    ]

    hit_drop = (baseline_metrics.get("retrieval_hit_rate") or 0) - (corrupted_metrics.get("retrieval_hit_rate") or 0)
    f1_drop = (baseline_metrics.get("mean_token_f1") or 0) - (corrupted_metrics.get("mean_token_f1") or 0)
    lines.append(
        f"- **Silent failure:** on corrupted data the pipeline still runs end-to-end, yet `retrieval_hit_rate` changes by "
        f"{-hit_drop:+.4f} and `mean_token_f1` by {-f1_drop:+.4f} versus baseline. Only the quality gate "
        f"({len(corrupted_quality.get('failed_checks') or [])} failed checks) and the freshness SLA "
        f"({'stale' if not corrupted_freshness.get('is_fresh') else 'still fresh'}) make the problem visible."
    )
    repaired_matches = all(
        abs((repaired_metrics.get(k) or 0) - (baseline_metrics.get(k) or 0)) < 1e-9 for k in METRIC_KEYS
    )
    lines.append(
        f"- **Repair:** rebuilding from the raw snapshot restores the quality gate to "
        f"{_fmt(repaired_quality.get('success'))} and freshness to {_freshness_label(repaired_freshness)}; "
        + (
            "all agent metrics return exactly to baseline, confirming the repair is idempotent."
            if repaired_matches
            else "agent metrics do not fully match baseline — investigate the differing metrics above."
        )
    )
    lines.append("")
    write_text(report_path, "\n".join(lines))
