from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from core.config import load_settings
from observability.quality import build_freshness_report, run_data_quality_checks
from pipelines.phase1 import build_chroma_index, extract_and_clean_records


def inject_corruption(df: pd.DataFrame) -> pd.DataFrame:
    """Tiêm lỗi có chủ đích vào dữ liệu để kiểm tra Quality Gate."""
    df_bad = df.copy()

    if len(df_bad) >= 3:
        # Lỗi 1: Gán NULL vào trường title bắt buộc
        df_bad.loc[0, "title"] = None

        # Lỗi 2: Tạo trùng lặp paper_id
        df_bad.loc[1, "paper_id"] = df_bad.loc[2, "paper_id"]

        # Lỗi 3: Làm cũ dữ liệu vượt ngưỡng freshness (> 180 ngày)
        df_bad.loc[2, "age_days"] = 999
        df_bad.loc[2, "published"] = "2020-01-01"

    return df_bad


def generate_comparison_report(
    baseline_stats: dict, corrupted_stats: dict, repaired_stats: dict, output_path: Path
) -> None:
    """Tạo bảng đối chiếu 3 trạng thái: Baseline vs. Corrupted vs. Repaired."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_md = f"""# Data Quality & Observability Comparison Report

| Metric / Check | 1. Baseline | 2. Corrupted | 3. Repaired |
| :--- | :--- | :--- | :--- |
| **Quality Gate Status** | {'PASS' if baseline_stats.get('success') else 'FAIL'} | {'PASS' if corrupted_stats.get('success') else 'FAIL'} | {'PASS' if repaired_stats.get('success') else 'FAIL'} |
| **Success Rate (%)** | {baseline_stats['statistics']['success_percent']:.1f}% | {corrupted_stats['statistics']['success_percent']:.1f}% | {repaired_stats['statistics']['success_percent']:.1f}% |
| **Freshness (<= 180d)** | {baseline_stats.get('freshness', {}).get('is_fresh')} | {corrupted_stats.get('freshness', {}).get('is_fresh')} | {repaired_stats.get('freshness', {}).get('is_fresh')} |
| **Stale Records Count** | {baseline_stats.get('freshness', {}).get('stale_rows', 0)} | {corrupted_stats.get('freshness', {}).get('stale_rows', 0)} | {repaired_stats.get('freshness', {}).get('stale_rows', 0)} |

### Kết luận
- **Corruption Stage:** Chốt kiểm soát phát hiện chính xác các lỗi thiếu thuộc tính, trùng khóa chính và vi phạm độ trễ dữ liệu (`age_days > 180`).
- **Repair Stage:** Pipeline khôi phục trạng thái chuẩn xác từ nguồn raw data gốc, đảm bảo tính bất biến (Idempotent).
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_md)


def main() -> None:
    settings = load_settings()

    # 1. Đọc Baseline Clean Data
    if settings.paths.clean_csv.exists():
        df_clean = pd.read_csv(settings.paths.clean_csv)
    else:
        df_clean = extract_and_clean_records(settings.paths.raw_api_response, settings)

    baseline_quality = run_data_quality_checks(df_clean, settings, "baseline_check")
    baseline_fresh = build_freshness_report(df_clean, settings, settings.paths.freshness_report)
    baseline_quality["freshness"] = baseline_fresh

    # 2. Tạo & Lưu Corrupted Data
    df_corrupted = inject_corruption(df_clean)
    settings.paths.corrupted_clean_csv.parent.mkdir(parents=True, exist_ok=True)
    df_corrupted.to_csv(settings.paths.corrupted_clean_csv, index=False)

    # 3. Đánh giá trên Corrupted Data (Kỳ vọng FAIL tại Gate)
    corrupted_quality = run_data_quality_checks(df_corrupted, settings, "corrupted_quality_report")
    corrupted_fresh = build_freshness_report(df_corrupted, settings, settings.paths.quality_dir / "corrupted_freshness.json")
    corrupted_quality["freshness"] = corrupted_fresh

    # 4. Phục hồi dữ liệu (Idempotent Repair từ Raw gốc)
    raw_source = settings.paths.raw_api_response if settings.paths.raw_api_response.exists() else settings.paths.raw_records_json
    df_repaired = extract_and_clean_records(raw_source, settings)
    df_repaired.to_csv(settings.paths.repaired_clean_csv, index=False)

    repaired_quality = run_data_quality_checks(df_repaired, settings, "repaired_quality_report")
    repaired_fresh = build_freshness_report(df_repaired, settings, settings.paths.quality_dir / "repaired_freshness.json")
    repaired_quality["freshness"] = repaired_fresh

    # 5. Xuất báo cáo đối chiếu
    generate_comparison_report(baseline_quality, corrupted_quality, repaired_quality, settings.paths.comparison_report)
    print("✅ Hoàn thành quy trình: Baseline -> Corruption -> Repair -> Comparison Report.")