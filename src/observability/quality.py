from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import great_expectations as gx
import great_expectations.expectations as gxe
import pandas as pd
from great_expectations.core.expectation_suite import ExpectationSuite

from core.config import Settings


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Tạo bộ data quality checks với Great Expectations 1.x:
    1. Check row count >= 1
    2. Check `paper_id` not null & unique
    3. Check `title` not null
    4. Check độ dài `summary`
    5. Check freshness bằng `age_days`
    6. Ghi kết quả vào `data/quality/`
    """
    context = gx.get_context(mode="ephemeral")

    # Tạo data source và data asset từ pandas DataFrame
    data_source = context.data_sources.add_pandas("pandas_pipeline_source")
    data_asset = data_source.add_dataframe_asset(name="paper_records_asset")
    batch_definition = data_asset.add_batch_definition_whole_dataframe("whole_dataframe_batch")

    # Tạo Expectation Suite
    suite_name = f"quality_suite_{report_name}"
    suite = ExpectationSuite(name=suite_name)

    # 1. Row count: Tối thiểu 1 dòng
    suite.add_expectation(
        gxe.ExpectTableRowCountToBeBetween(min_value=1)
    )

    # 2. `paper_id`: Not null và Unique
    suite.add_expectation(
        gxe.ExpectColumnValuesToNotBeNull(column="paper_id")
    )
    suite.add_expectation(
        gxe.ExpectColumnValuesToBeUnique(column="paper_id")
    )

    # 3. `title`: Not null
    suite.add_expectation(
        gxe.ExpectColumnValuesToNotBeNull(column="title")
    )

    # 4. Độ dài `summary`: tối thiểu 10 ký tự nếu cột tồn tại
    if "summary" in df.columns:
        suite.add_expectation(
            gxe.ExpectColumnValuesToNotBeNull(column="summary")
        )
        suite.add_expectation(
            gxe.ExpectColumnValueLengthsToBeBetween(column="summary", min_value=10)
        )

    # 5. Freshness check: `age_days` >= 0 và không vượt quá ngưỡng freshness
    if "age_days" in df.columns:
        max_age = getattr(settings, "freshness_threshold_days", 180)
        suite.add_expectation(
            gxe.ExpectColumnValuesToNotBeNull(column="age_days")
        )
        suite.add_expectation(
            gxe.ExpectColumnValuesToBeBetween(column="age_days", min_value=0, max_value=max_age)
        )

    suite = context.suites.add(suite)

    # Đăng ký Validation Definition
    validation_definition = context.validation_definitions.add(
        gx.ValidationDefinition(
            name=f"validation_{report_name}",
            data=batch_definition,
            suite=suite,
        )
    )

    # Chạy validation
    batch_parameters = {"dataframe": df}
    validation_results = validation_definition.run(batch_parameters=batch_parameters)

    # Tổng hợp payload kết quả
    success = bool(validation_results.success)
    evaluated_expectations = len(validation_results.results)
    successful_expectations = sum(1 for r in validation_results.results if r.success)

    detailed_results = []
    for res in validation_results.results:
        detailed_results.append({
            "expectation_type": res.expectation_config.type,
            "column": res.expectation_config.kwargs.get("column", "table-level"),
            "success": bool(res.success),
            "result": res.result,
        })

    report_payload = {
        "report_name": report_name,
        "success": success,
        "statistics": {
            "evaluated_expectations": evaluated_expectations,
            "successful_expectations": successful_expectations,
            "unsuccessful_expectations": evaluated_expectations - successful_expectations,
            "success_percent": (successful_expectations / evaluated_expectations * 100) if evaluated_expectations > 0 else 0,
        },
        "details": detailed_results,
    }

    # 6. Ghi kết quả vào data/quality/{report_name}.json
    output_dir = Path("data/quality")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_file = output_dir / f"{report_name}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2, ensure_ascii=False)

    return report_payload


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path: str | Path) -> dict[str, Any]:
    """Tổng hợp freshness report."""
    total_rows = len(df)
    max_age_days = getattr(settings, "freshness_threshold_days", 180)

    date_col = next((c for c in ["published", "published_date", "created"] if c in df.columns), None)

    latest_published = str(df[date_col].max()) if date_col and not df.empty else None
    oldest_published = str(df[date_col].min()) if date_col and not df.empty else None

    if "age_days" in df.columns:
        stale_rows = int((df["age_days"] > max_age_days).sum() + df["age_days"].isna().sum())
    else:
        stale_rows = 0

    is_fresh = stale_rows == 0 and total_rows > 0

    payload = {
        "latest_published": latest_published,
        "oldest_published": oldest_published,
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "is_fresh": is_fresh,
    }

    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return payload