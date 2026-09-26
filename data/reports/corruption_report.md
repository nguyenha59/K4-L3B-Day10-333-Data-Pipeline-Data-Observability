# Corruption Report — Baseline vs Corrupted vs Repaired

_Generated at 2026-09-26T03:28:48+00:00 by `script/run_corruption_flow.py`. All three states are evaluated on the same test set (`data/eval/test_set.json`)._

## 1. Three-state comparison

| Metric / signal | Baseline | Corrupted | Repaired | Δ corruption | Recovery |
| --- | ---: | ---: | ---: | ---: | ---: |
| `retrieval_hit_rate` | 1.0000 | 0.8000 | 1.0000 | -0.2000 | 100% |
| `mean_token_f1` | 1.0000 | 0.8499 | 1.0000 | -0.1501 | 100% |
| `judge_accuracy` | 1.0000 | 0.7000 | 1.0000 | -0.3000 | 100% |
| `mean_judge_score` | 5 | 4.3000 | 5 | -0.7000 | 100% |
| Row count | 24 | 21 | 24 | — | — |
| Quality gate (GX) | PASS (8/8) | FAIL (4/8) | PASS (8/8) | — | — |
| Freshness SLA | Fresh (1/24 > 180d) | Stale (6/21 > 180d) | Fresh (1/24 > 180d) | — | — |

_Recovery = (repaired − corrupted) / (baseline − corrupted)._

## 2. Injected corruptions

Rows before: 24 → rows after: 21 (seed=20260926).

| # | Scenario | Rows affected | Details |
| ---: | --- | ---: | --- |
| 1 | `drop_latest_records` | 5 | Removed the 5 most recently published papers (20%). |
| 2 | `blank_summary` | 3 | Summary replaced with an empty string. |
| 3 | `inject_noise` | 3 | About 50% of summary words replaced with random garbage tokens. |
| 4 | `truncate_title` | 3 | Title cut to 6 characters (below the 8-character threshold). |
| 5 | `stale_date` | 6 | Published date moved back 365 days on 30% of rows. |
| 6 | `duplicate_rows` | 2 | Appended 2 exact duplicate rows (paper_id no longer unique). |

## 3. Quality gate on corrupted data

Failed checks: expect_column_values_to_be_unique(paper_id), expect_column_value_lengths_to_be_between(title), expect_column_value_lengths_to_be_between(summary), expect_column_values_to_be_between(age_days)

| Expectation | Column | Result | Observed / unexpected |
| --- | --- | :---: | --- |
| `expect_table_row_count_to_be_between` | table | PASS | 21 |
| `expect_column_values_to_not_be_null` | paper_id | PASS | 0 unexpected (0.0%) |
| `expect_column_values_to_be_unique` | paper_id | FAIL | 4 unexpected (19.0%) |
| `expect_column_values_to_not_be_null` | title | PASS | 0 unexpected (0.0%) |
| `expect_column_value_lengths_to_be_between` | title | FAIL | 3 unexpected (14.3%) |
| `expect_column_values_to_not_be_null` | text_for_embedding | PASS | 0 unexpected (0.0%) |
| `expect_column_value_lengths_to_be_between` | summary | FAIL | 3 unexpected (14.3%) |
| `expect_column_values_to_be_between` | age_days | FAIL | 6 unexpected (28.6%) |

## 4. Quality gate on repaired data

Failed checks: none

| Expectation | Column | Result | Observed / unexpected |
| --- | --- | :---: | --- |
| `expect_table_row_count_to_be_between` | table | PASS | 24 |
| `expect_column_values_to_not_be_null` | paper_id | PASS | 0 unexpected (0.0%) |
| `expect_column_values_to_be_unique` | paper_id | PASS | 0 unexpected (0.0%) |
| `expect_column_values_to_not_be_null` | title | PASS | 0 unexpected (0.0%) |
| `expect_column_value_lengths_to_be_between` | title | PASS | 0 unexpected (0.0%) |
| `expect_column_values_to_not_be_null` | text_for_embedding | PASS | 0 unexpected (0.0%) |
| `expect_column_value_lengths_to_be_between` | summary | PASS | 0 unexpected (0.0%) |
| `expect_column_values_to_be_between` | age_days | PASS | 1 unexpected (4.2%) |

## 5. Analysis

- **Silent failure:** on corrupted data the pipeline still runs end-to-end, yet `retrieval_hit_rate` changes by -0.2000 and `mean_token_f1` by -0.1501 versus baseline. Only the quality gate (4 failed checks) and the freshness SLA (stale) make the problem visible.
- **Repair:** rebuilding from the raw snapshot restores the quality gate to PASS and freshness to Fresh (1/24 > 180d); all agent metrics return exactly to baseline, confirming the repair is idempotent.
