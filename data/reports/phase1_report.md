# Phase 1 Report — Baseline Data Pipeline

_Generated at 2026-09-26T03:27:50+00:00 by `script/run_phase1.py`._

## 1. Source & lineage

| Field | Value |
| --- | --- |
| source_api | Crossref REST API |
| query | agentic retrieval augmented generation large language model |
| filter | from-pub-date:2026-03-30,has-abstract:true |
| mode | local snapshot (set REFRESH_SOURCE=1 for live) |
| raw_records | 24 |
| clean_rows | 24 |
| embedding_model | sentence-transformers/all-MiniLM-L6-v2 |
| collection | papers-baseline |
| top_k | 4 |
| llm_provider | openai |
| run_date | 2026-09-26T03:27:30+00:00 |

## 2. Baseline evaluation metrics

| Metric | Value |
| --- | ---: |
| `samples` | 10 |
| `retrieval_hit_rate` | 1.0000 |
| `mean_token_f1` | 1.0000 |
| `judge_accuracy` | 1.0000 |
| `mean_judge_score` | 5 |

Ragas: `{'skipped': 'Set RUN_RAGAS=1 to enable the slower Ragas pass.'}`

## 3. Data quality gate (Great Expectations 1.x)

- Engine: `great_expectations 1.23.2`
- Overall: **PASS (8/8)**
- Failed checks: none

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

## 4. Freshness SLA

| Field | Value |
| --- | --- |
| latest_published | 2026-07-22 |
| oldest_published | 2026-03-28 |
| median_age_days | 111.5000 |
| max_age_days | 182 |
| threshold_days | 180 |
| max_stale_ratio | 0.2500 |
| stale_rows | 1 |
| total_rows | 24 |
| stale_ratio | 0.0417 |
| is_fresh | PASS |

**Status: Fresh (1/24 > 180d)** — SLA: stale ratio (`age_days > 180`) must be <= 0.25.
