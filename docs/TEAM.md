# Danh Sách Thành Viên & Báo Cáo Phân Công Nhóm

- **Tên Nhóm:** `333`
- **Mã Nhóm / Lớp:** `K4-L3B-DAY10`
- **Tên Repository Nộp Bài:** `K4-L3B-Day10-333-Data-Pipeline-Data-Observability`
- **Repository:** https://github.com/nguyenha59/K4-L3B-Day10-333-Data-Pipeline-Data-Observability

---

## # Thành viên

| STT | Họ và tên | MSSV | Email | Vai trò & Phân công công việc | Báo cáo cá nhân |
|---:|---|---|---|---|---|
| 1 | Nguyễn Thị Hạ | 02536 | | Corruption & Integration (`corruption.py`, `phase1.py`, `corruption_flow.py`, `tests/`) | `report/02536_NguyenThiHa.md` |
| 2 | Phạm Hương Giang | 02359 | | Data Ingestion & Cleaning (`crossref.py`, `cleaning.py`, raw data) | `report/02359_PhamHuongGiang.md` |
| 3 | Lê Thanh Tình | | | Evaluation & Observability (`testset.py`, `quality.py` GX 1.x, `reporting.py`) | `report/<MSSV>_LeThanhTinh.md` |

Nhóm 3 thành viên, chia theo mô hình 3 người trong `report/README.md`. Các thành viên phụ trách ngang nhau, không có vai trò trưởng nhóm.

| Checkpoint | Nguyễn Thị Hạ | Phạm Hương Giang | Lê Thanh Tình |
|---|:---:|:---:|:---:|
| CP0 — Môi trường & ingestion | | ● | |
| CP1 — Cleaning & GX 1.x + Freshness | | ● (cleaning) | ● (GX, freshness) |
| CP2 — Test set & ChromaDB index | | | ● |
| CP3 — Baseline pipeline & Phase 1 report | ● | | ● (report) |
| CP4 — Corruption suite | ● | | |
| CP5 — Repair & báo cáo 3 trạng thái | ● | ● (dữ liệu repair) | ● (report) |
| CP6 — Live demo | ● | ● | ● |

---

## # Cá nhân

### ## NguyenThiHa-02536
- **Vai trò:** Corruption & Integration.
- **Công việc chi tiết đã hoàn thành:**
  - Xây dựng bộ 6 kịch bản làm bẩn dữ liệu có seed cố định trong `src/ingestion/corruption.py` (drop latest 20%, blank summary, inject noise, truncate title, stale date −365 ngày, duplicate rows), ghi log từng dòng bị sửa (`before`/`after`) vào `data/results/corruption_log.json`.
  - Kết nối luồng baseline end-to-end trong `src/pipelines/phase1.py` (`run_phase1_pipeline`): ingest → clean → index ChromaDB → test set → evaluate → GX quality gate → `phase1_report.md`.
  - Xây dựng `src/pipelines/corruption_flow.py` (`run_corruption_flow_pipeline`): đánh giá trên dữ liệu bẩn, tự kích hoạt `repair_from_raw_snapshot()` khi quality gate FAIL, đánh giá lại và xuất bảng Baseline vs Corrupted vs Repaired.
  - Viết bộ kiểm thử `tests/` (50 test, coverage 97%) và workflow `.github/workflows/tests.yml`.
- **Điều học được / Đóng góp chính:**
  - Silent Failure: pipeline vẫn chạy thành công trên dữ liệu bẩn trong khi `judge_accuracy` giảm từ 1.0 xuống 0.7; chỉ quality gate và freshness SLA làm lộ sự cố.
  - Repair phải đi từ nguồn raw bất biến mới đảm bảo idempotent — dữ liệu sau repair trùng khớp 100% bản clean ban đầu.

### ## PhamHuongGiang-02359
- **Vai trò:** Data Ingestion & Cleaning.
- **Công việc chi tiết đã hoàn thành:**
  - Xây dựng module thu thập Crossref trong `src/ingestion/crossref.py`: `parse_crossref_payload` (bóc tách DOI, title, abstract bỏ thẻ JATS, authors, subject, ngày xuất bản), `fetch_source_records` có retry 429/5xx và fallback snapshot offline, `load_raw_records`.
  - Lưu 2 raw artifact phục vụ lineage: `data/raw/crossref_response.json`, `data/raw/crossref_records.json`.
  - Chuẩn hóa schema trong `src/ingestion/cleaning.py`: làm sạch văn bản, tính `age_days`, khử trùng lặp theo `paper_id`, sinh `text_for_embedding` 5 phần.
- **Điều học được / Đóng góp chính:**
  - _(Giang tự điền)_

### ## LeThanhTinh-<MSSV>
- **Vai trò:** Evaluation & Observability.
- **Công việc chi tiết đã hoàn thành:**
  - Thiết lập Quality Gate theo chuẩn **Great Expectations 1.x** (ephemeral context) và Freshness SLA trong `src/observability/quality.py`.
  - Xây dựng bộ 10 câu hỏi đánh giá qua 4 nhóm `summary/authors/date/categories` trong `src/evaluation/testset.py`.
  - Sinh báo cáo `phase1_report.md` và bảng đối chiếu 3 trạng thái `corruption_report.md` trong `src/observability/reporting.py`.
- **Điều học được / Đóng góp chính:**
  - _(Tình tự điền)_
