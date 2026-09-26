from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from core.config import Settings, load_settings
from observability.quality import build_freshness_report, run_data_quality_checks


def extract_and_clean_records(raw_path: Path, settings: Settings) -> pd.DataFrame:
    """Đọc dữ liệu Crossref và chuẩn hóa thành DataFrame sạch."""
    with open(raw_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Hỗ trợ cả định dạng list trực tiếp lẫn cấu trúc JSON envelope của Crossref
    items = data.get("message", {}).get("items", []) if isinstance(data, dict) else data

    records = []
    now = datetime.now(UTC)

    for item in items:
        # 1. Trích xuất paper_id (ưu tiên DOI)
        paper_id = item.get("DOI") or item.get("id") or item.get("paper_id")
        if not paper_id:
            continue

        # 2. Trích xuất title
        title_val = item.get("title", "")
        if isinstance(title_val, list) and title_val:
            title = str(title_val[0]).strip()
        else:
            title = str(title_val).strip()

        # 3. Trích xuất summary / abstract
        summary = item.get("abstract") or item.get("summary") or ""
        # Xóa thẻ XML/HTML thừa nếu có từ Crossref (vd: <jats:p>)
        summary = summary.replace("<jats:p>", "").replace("</jats:p>", "").strip()
        if not summary:
            summary = title  # fallback tối thiểu

        # 4. Trích xuất ngày công bố
        pub_parts = (
            item.get("published-print", {}) or item.get("published-online", {}) or item.get("issued", {})
        ).get("date-parts", [[]])
        
        pub_date = None
        if pub_parts and pub_parts[0]:
            parts = pub_parts[0]
            year = parts[0]
            month = parts[1] if len(parts) > 1 else 1
            day = parts[2] if len(parts) > 2 else 1
            try:
                pub_date = datetime(year, month, day, tzinfo=UTC)
            except Exception:
                pub_date = now
        else:
            pub_date = now

        # 5. Tính age_days
        age_days = (now - pub_date).days

        records.append({
            "paper_id": str(paper_id),
            "title": title,
            "summary": summary,
            "published": pub_date.strftime("%Y-%m-%d"),
            "age_days": max(0, age_days),
        })

    df = pd.DataFrame(records)
    # Loại bỏ bản ghi trùng paper_id và lọc bỏ bản ghi thiếu thông tin cốt lõi
    df = df.drop_duplicates(subset=["paper_id"]).dropna(subset=["paper_id", "title"])
    return df


def build_chroma_index(df: pd.DataFrame, settings: Settings, collection_name: str) -> None:
    """Build Chroma collection từ dữ liệu sạch."""
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(settings.embedding_model)
        client = chromadb.PersistentClient(path=str(settings.paths.chroma_dir))
        
        # Xóa collection cũ nếu tồn tại để đảm bảo tính Idempotent
        try:
            client.delete_collection(name=collection_name)
        except Exception:
            pass

        collection = client.create_collection(name=collection_name)

        documents = df["summary"].tolist()
        metadatas = [
            {"title": r["title"], "published": r["published"], "age_days": r["age_days"]}
            for _, r in df.iterrows()
        ]
        ids = df["paper_id"].tolist()

        embeddings = model.encode(documents, show_progress_bar=False).tolist()

        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
    except ImportError:
        print("[Notice] Chưa cài đặt chromadb/sentence-transformers. Bỏ qua bước index Chroma.")


def generate_phase1_report(df: pd.DataFrame, quality_res: dict, freshness_res: dict, output_path: Path) -> None:
    """Tạo báo cáo Markdown tổng kết Phase 1."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_content = f"""# Baseline Data Pipeline Report (Phase 1)

## Data Summary
- **Total Records Ingested:** {len(df)}
- **Unique Papers:** {df['paper_id'].nunique()}
- **Date Range:** {freshness_res.get('oldest_published')} to {freshness_res.get('latest_published')}

## Data Observability & Quality Gate (Great Expectations 1.x)
- **Status:** {'PASSED' if quality_res.get('success') else 'FAILED'}
- **Evaluated Checks:** {quality_res['statistics']['evaluated_expectations']}
- **Success Rate:** {quality_res['statistics']['success_percent']:.1f}%

## Freshness Check
- **Is Fresh (Threshold <= 180 days):** {freshness_res.get('is_fresh')}
- **Stale Records:** {freshness_res.get('stale_rows')} / {freshness_res.get('total_rows')}
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)


def main() -> None:
    settings = load_settings()
    raw_file = settings.paths.raw_api_response
    if not raw_file.exists():
        raw_file = settings.paths.raw_records_json

    # 1. Clean data
    df_clean = extract_and_clean_records(raw_file, settings)

    # 2. Save clean artifacts
    settings.paths.clean_csv.parent.mkdir(parents=True, exist_ok=True)
    df_clean.to_csv(settings.paths.clean_csv, index=False)
    df_clean.to_json(settings.paths.clean_json, orient="records", indent=2, force_ascii=False)

    # 3. Quality checks & Freshness report
    quality_res = run_data_quality_checks(df_clean, settings, report_name="baseline_quality_report")
    freshness_res = build_freshness_report(df_clean, settings, settings.paths.freshness_report)

    # 4. Build Chroma Vector Index
    build_chroma_index(df_clean, settings, settings.baseline_collection_name)

    # 5. Export Markdown report
    generate_phase1_report(df_clean, quality_res, freshness_res, settings.paths.baseline_report)
    print("✅ Hoàn thành Phase 1 Baseline Pipeline.")