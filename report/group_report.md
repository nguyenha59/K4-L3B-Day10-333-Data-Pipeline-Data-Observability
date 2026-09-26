# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin | Nội dung |
| --- | --- |
| Khóa/Lớp | K4 — L3B |
| Tên nhóm | 333 |
| Repository | https://github.com/nguyenha59/K4-L3B-Day10-333-Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-09-26 |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- |
| 1 | Nguyễn Thị Hạ | 02536 | Corruption & Integration | `ingestion/corruption.py`, `pipelines/phase1.py`, `pipelines/corruption_flow.py`, `tests/`; metrics 3 trạng thái, `corruption_log.json` |
| 2 | Phạm Hương Giang | 02359 | Data Ingestion & Cleaning | `ingestion/crossref.py`, `ingestion/cleaning.py`; `data/raw/*`, `data/clean/papers_clean.*` |
| 3 | Lê Thanh Tình | 02449 | Evaluation & Observability | `evaluation/testset.py`, `observability/quality.py`, `observability/reporting.py`; `test_set.json`, `data/quality/*`, `data/reports/*` |

## 2. Tóm tắt kết quả

**Tóm tắt của nhóm:**

Nhóm hoàn thành đủ 6 checkpoint bắt buộc. Pipeline thu thập 24 bài báo từ Crossref (dùng snapshot local, có retry 429/5xx và fallback offline), làm sạch thành dataset 24 dòng với `age_days` và `text_for_embedding` 5 phần, index vào ChromaDB (`papers-baseline`, embedding `all-MiniLM-L6-v2`), sinh bộ 10 câu hỏi qua 4 nhóm nghiệp vụ và đánh giá bằng Hit Rate, Token F1 và LLM judge (`gpt-4o-mini`). Quality gate dùng Great Expectations 1.x (ephemeral context, 8 expectations) kèm Freshness SLA.

Baseline đạt `retrieval_hit_rate` = 1.0 và `judge_accuracy` = 1.0, quality gate PASS 8/8, freshness Fresh (1/24 bài quá 180 ngày). Sau khi tiêm 6 loại lỗi, pipeline vẫn chạy bình thường nhưng `retrieval_hit_rate` giảm còn 0.8 và `judge_accuracy` giảm còn 0.7 — đây là Silent Failure; chỉ quality gate (FAIL 4/8) và freshness (Stale, 28.6%) phát hiện sự cố. Hai lỗi tác động mạnh nhất tới agent là **drop_latest_records** (2 câu mất tài liệu đích) và **stale_date** (trả lời sai năm xuất bản). Quality gate tự động kích hoạt repair từ raw snapshot; dữ liệu repaired trùng khớp hoàn toàn bản clean ban đầu và mọi chỉ số phục hồi 100%.

Giới hạn còn lại: quality gate chưa bắt trực tiếp được `inject_noise` và `drop_latest_records` (ngưỡng row count 5–5000 quá rộng); baseline đạt điểm tối đa do câu hỏi chứa nguyên tiêu đề bài báo.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref API (hoặc snapshot data/raw/crossref_response.json)
    -> raw response + raw records (data/raw/)
    -> cleaning & data modeling (data/clean/papers_clean.*)
    -> MiniLM embedding + ChromaDB index (papers-baseline)
    -> test set 10 câu (data/eval/test_set.json)
    -> evaluation baseline (data/results/baseline_metrics.json)
    -> GX 1.x quality gate + freshness SLA (data/quality/)
    -> corruption 6 kịch bản (papers_clean_corrupted.*, corruption_log.json)
    -> re-index (papers-corrupted) + re-evaluate + quality gate -> FAIL
    -> auto-repair từ raw snapshot (papers_clean_repaired.*)
    -> re-index (papers-repaired) + re-evaluate + quality gate -> PASS
    -> comparison report (data/reports/corruption_report.md)
```

### Trách nhiệm của từng khối

| Khối | Input | Xử lý chính | Output/artifact | Owner |
| --- | --- | --- | --- | --- |
| Ingestion | Crossref REST API / snapshot | Fetch có retry 429/5xx, fallback offline, parse DOI/title/abstract/authors/subject/dates, bỏ thẻ JATS | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | Phạm Hương Giang |
| Cleaning | `crossref_records.json` | Chuẩn hóa text, parse ngày, lọc dòng thiếu dữ liệu, dedup `paper_id`, `age_days`, `text_for_embedding` | `data/clean/papers_clean.csv/.json` | Phạm Hương Giang |
| Embedding/index | Clean dataframe | `all-MiniLM-L6-v2` (384 chiều, normalize), ChromaDB cosine, 1 collection mỗi trạng thái | `data/chroma/`, `data/embeddings/*.json` | Lê Thanh Tình |
| Evaluation | Clean dataframe, index | Test set 10 câu / 4 loại; Hit Rate, Token F1, LLM judge | `data/eval/test_set.json`, `data/results/*_metrics.json` | Lê Thanh Tình |
| Observability | Dataframe mỗi trạng thái | GX 1.x 8 expectations + Freshness SLA | `data/quality/*_quality_report.json`, `*freshness_report.json`, `data/quality/gx/` | Lê Thanh Tình |
| Corruption/repair | Clean dataset, raw snapshot | 6 kịch bản lỗi có seed; repair tự động khi gate FAIL | `corruption_log.json`, `papers_clean_corrupted.*`, `papers_clean_repaired.*` | Nguyễn Thị Hạ |
| Orchestration | Settings | `run_phase1_pipeline`, `run_corruption_flow_pipeline` | `phase1_report.md`, `corruption_report.md` | Nguyễn Thị Hạ |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình | Giá trị sử dụng |
| --- | --- |
| `LLM_PROVIDER` | `openai` |
| `LLM_MODEL` | `gpt-4o-mini` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Số lượng Crossref records | 24 |
| Retrieval `top_k` | 4 |
| Freshness threshold | 180 ngày, tối đa 25% bài quá hạn |
| Random seed | 20260926 (corruption) |

### Lệnh cài đặt

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
copy .env.example .env   # điền OPENAI_API_KEY
```

### Lệnh chạy

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
pytest                      # 50 test, coverage 97%
```

### Kết quả tái hiện

| Lệnh | Trạng thái | Thời điểm chạy gần nhất | Bằng chứng |
| --- | --- | --- | --- |
| Baseline pipeline | Thành công (exit 0) | 2026-09-26 10:27 (GMT+7) | `data/results/baseline_metrics.json`, `data/reports/phase1_report.md` |
| Corruption flow | Thành công (exit 0) | 2026-09-26 10:28 (GMT+7) | `data/results/corruption_log.json`, `data/reports/corruption_report.md` |
| Pytest | 50 passed, coverage 97.19% | 2026-09-26 | `pytest` output |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính | Giá trị |
| --- | --- |
| Source | Crossref REST API `https://api.crossref.org/works` (snapshot `data/raw/crossref_response.json`) |
| Query/filter | `agentic retrieval augmented generation large language model`; `from-pub-date:<run_date − 180 ngày>,has-abstract:true`; `rows=24` |
| Thời điểm lấy dữ liệu | Snapshot offline đi kèm repo (`total-results: 24`); gọi API live khi đặt `REFRESH_SOURCE=1` |
| Số record nhận được | 24 item → 24 `PaperRecord` hợp lệ |
| Cơ chế retry/backoff | Tối đa 4 lần cho 429/500/502/503/504 và lỗi mạng; chờ theo header `Retry-After` hoặc backoff 1–2–4–8 giây; thất bại thì fallback snapshot local, không ghi đè snapshot |

### Raw và clean schema

| Trường | Kiểu dữ liệu | Bắt buộc? | Ý nghĩa | Xử lý khi thiếu/sai |
| --- | --- | --- | --- | --- |
| `paper_id` | str | Có | DOI viết thường, khóa định danh tài liệu | Thiếu → bỏ record; trùng → giữ bản `updated` mới nhất |
| `title` | str | Có | Tiêu đề (phần tử đầu của `title[]`) | Thiếu → bỏ record |
| `summary` | str | Có | Abstract đã bỏ thẻ JATS/HTML, gộp khoảng trắng | Thiếu/rỗng → bỏ record |
| `authors` | list[str] | Không | `given family` hoặc `name` | Rỗng → giữ record, `authors_joined = ""` |
| `categories` | list[str] | Không | `subject[]` | Rỗng → `primary_category = "Uncategorized"` |
| `published` | str `YYYY-MM-DD` | Có | Lấy từ `published` → `published-online` → `published-print` → `issued` | Không parse được → bỏ record |
| `updated` | str `YYYY-MM-DD` | Không | `created.date-time` | Thiếu → dùng `published` |
| `age_days` | int | Có | `(run_date − published).days` | Tính lại mỗi lần chạy |
| `text_for_embedding` | str | Có | Title / Authors / Published / Categories / Summary | Luôn sinh lại từ các cột gốc |

### Quy tắc cleaning

| Quy tắc | Quality dimension liên quan | Số record bị tác động | Cách xác minh |
| --- | --- | --: | --- |
| Bỏ thẻ JATS/HTML trong abstract, unescape HTML | Validity | 24 (mọi abstract trong snapshot đều bọc `<jats:p>`) | `crossref_records.json` không còn ký tự `<`; test `test_parse_payload_normalizes_fields` |
| Loại record thiếu DOI/title/abstract/ngày | Completeness | 0 | Clean 24/24 dòng |
| Khử trùng lặp theo `paper_id` | Uniqueness | 0 | GX `expect_column_values_to_be_unique(paper_id)` PASS |
| Chuẩn hóa ngày về `YYYY-MM-DD` | Consistency | 24 | Cột `published` dạng chuỗi ISO |

`text_for_embedding` ghép 5 dòng `Title: …`, `Authors: …`, `Published: …`, `Categories: …`, `Summary: …` để embedding chứa cả metadata lẫn nội dung. Document ID là DOI viết thường (ổn định qua các lần chạy); trong ChromaDB mỗi bản ghi có `record_id = <paper_id>::<vị trí>` để vẫn index được khi dữ liệu bẩn có dòng trùng. `age_days` tính theo ngày chạy pipeline (UTC); ngày 2026-09-26 bài cũ nhất (2026-03-28) có `age_days = 182`.

## 6. Evaluation setup

| Thành phần | Cấu hình thực tế |
| --- | --- |
| Số câu hỏi | 10 |
| Các `question_type` | `summary` (3), `authors` (3), `date` (2), `categories` (2) |
| Ground-truth document ID | DOI của bài báo được dùng để sinh câu hỏi; 10 câu trỏ tới 10 bài khác nhau, chọn đều từ mới nhất đến cũ nhất |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector store/collection | ChromaDB `data/chroma`, cosine; `papers-baseline`, `papers-corrupted`, `papers-repaired` |
| Retrieval `top_k` | 4 |
| LLM provider/model | OpenAI `gpt-4o-mini` (judge + agent demo) |
| Test set dùng chung cho ba trạng thái | `data/eval/test_set.json` (`eval_001` … `eval_010`) |

Test set được sinh một lần từ dữ liệu sạch và giữ nguyên cho cả baseline, corrupted và repaired, để mọi chênh lệch chỉ số phản ánh thay đổi của dữ liệu chứ không phải thay đổi của câu hỏi. Nếu sinh lại test set từ dữ liệu bẩn, các bài đã bị xóa sẽ biến mất khỏi đề và sự sụt giảm bị che đi.

## 7. Kết quả baseline

### Artifact checklist

| Artifact | Đường dẫn thực tế | Trạng thái | Ghi chú |
| --- | --- | --- | --- |
| Raw response/records | `data/raw/` | Có | 24 item / 24 records |
| Cleaned dataset | `data/clean/papers_clean.csv`, `.json` | Có | 24 dòng, 16 cột |
| Embedding manifest/index | `data/embeddings/`, `data/chroma/` | Có | 3 collection, `persist_path` tương đối |
| Evaluation set | `data/eval/test_set.json` | Có | 10 câu |
| Baseline metrics | `data/results/baseline_metrics.json` | Có | |
| Quality/freshness | `data/quality/` | Có | GX report, suite, freshness |
| Baseline report | `data/reports/phase1_report.md` | Có | |

### Baseline metrics

| Metric | Giá trị | Diễn giải |
| --- | --: | --- |
| `retrieval_hit_rate` | 1.0 | 10/10 câu có tài liệu đích trong top-4 |
| `mean_token_f1` | 1.0 | Câu trả lời trích đúng trường metadata trùng với ground truth |
| `judge_accuracy` | 1.0 | `gpt-4o-mini` chấm đúng cả 10 câu |
| `mean_judge_score` | 5.0 | Điểm tối đa ở mọi câu |
| Ragas | N/A | Không bật (`RUN_RAGAS` chưa đặt) để tiết kiệm thời gian và chi phí |

Baseline đạt điểm tối đa vì câu hỏi chứa nguyên tiêu đề bài báo (QA tra cứu chính xác theo tiêu đề) và câu trả lời trích nguyên văn metadata. Baseline đóng vai trò mốc tham chiếu để đo mức sụt giảm và phục hồi.

## 8. Data quality và freshness

### Quality checks

| Check | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline | Bằng chứng |
| --- | --- | --- | --- | --- |
| `ExpectTableRowCountToBeBetween` | Volume | 5 – 5000 dòng | PASS (24) | `data/quality/baseline_quality_report.json` |
| `ExpectColumnValuesToNotBeNull` × 3 | Completeness | `paper_id`, `title`, `text_for_embedding` không rỗng | PASS (0 null) | như trên |
| `ExpectColumnValuesToBeUnique` | Uniqueness | `paper_id` duy nhất | PASS (0 trùng) | như trên |
| `ExpectColumnValueLengthsToBeBetween` | Validity | `summary` ≥ 30 ký tự | PASS (ngắn nhất 193) | như trên |
| `ExpectColumnValueLengthsToBeBetween` | Validity | `title` ≥ 8 ký tự | PASS (ngắn nhất 55) | như trên |
| `ExpectColumnValuesToBeBetween` | Timeliness | `age_days` ∈ [0, 180], mostly = 0.75 | PASS (1 ngoài ngưỡng) | như trên |

### Freshness

| Thuộc tính | Giá trị |
| --- | --- |
| Freshness được đo tại | Clean dataset (cột `published` / `age_days`) |
| Timestamp mới nhất | `latest_published` = 2026-07-22 (cũ nhất 2026-03-28) |
| Ngưỡng freshness | `age_days > 180` bị coi là stale; tối đa 25% số bài |
| Trạng thái baseline | Fresh |
| Lý do | 1/24 bài quá hạn (4.17%), median `age_days` = 111.5 |

## 9. Corruption scenarios và repair

| Corruption | Cách tạo | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế | Cách repair |
| --- | --- | --: | --- | --- | --- |
| `drop_latest_records` | Xóa 20% bài có `published` mới nhất | 5 | Row count, freshness | Row count vẫn PASS (21 nằm trong 5–5000); `latest_published` lùi về 2026-06-12. `eval_001`, `eval_002` mất tài liệu đích (MISS) | Rebuild từ raw snapshot |
| `blank_summary` | Summary = `""` | 3 | `summary` length | FAIL 3 dòng. Câu test trỏ tới bài này (`eval_004`, loại categories) không bị ảnh hưởng | như trên |
| `inject_noise` | ~50% từ trong summary thay bằng token rác | 3 | (chưa có check) | Không expectation nào bắt được; không câu test nào trỏ tới 3 bài này | như trên |
| `truncate_title` | Title cắt còn 6 ký tự | 3 | `title` length | FAIL 3 dòng. `eval_009` trả lời sai (exact lookup theo tiêu đề thất bại, top-1 là bài khác) | như trên |
| `stale_date` | Lùi `published` 365 ngày | 6 | `age_days`, freshness | FAIL 6 dòng (28.6% > 25%), freshness Stale. `eval_007` trả lời `2025-06-03` thay vì `2026-06-03` | như trên |
| `duplicate_rows` | Nhân đôi dòng | 2 | `paper_id` unique | FAIL (4 giá trị trùng). Không làm sai câu trả lời nào | như trên |

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: Có
- Nhận xét: Log ghi seed (20260926), số dòng trước/sau (24 → 21) và với mỗi kịch bản: số dòng bị tác động, mô tả, danh sách `paper_id` kèm giá trị `before`/`after` của trường bị sửa.

Repair không sửa trên dữ liệu bẩn mà dựng lại toàn bộ clean layer từ `data/raw/crossref_records.json` — bản raw bất biến được lưu ở bước ingestion. Vì chỉ phụ thuộc vào raw, repair chạy bao nhiêu lần cũng cho cùng kết quả (idempotent); pipeline so sánh dữ liệu repaired với bản clean ban đầu và xác nhận trùng khớp trên mọi cột (trừ `age_days` phụ thuộc ngày chạy). Repair được kích hoạt tự động khi quality gate hoặc freshness trên dữ liệu bẩn FAIL, và dữ liệu repaired phải PASS lại gate trước khi được index.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét |
| --- | --: | --: | --: | --: | --: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.8000 | 1.0000 | −0.2000 | 100% | 2 câu mất tài liệu đích do drop latest |
| `mean_token_f1` | 1.0000 | 0.8499 | 1.0000 | −0.1501 | 100% | Giảm ở `eval_001`, `eval_007`, `eval_009` |
| `judge_accuracy` | 1.0000 | 0.7000 | 1.0000 | −0.3000 | 100% | 3 câu sai: `eval_001`, `eval_007`, `eval_009` |
| `mean_judge_score` | 5.0 | 4.3 | 5.0 | −0.7 | 100% | |
| Quality checks pass/fail | PASS 8/8 | FAIL 4/8 | PASS 8/8 | −4 checks | 100% | Fail: unique, title length, summary length, age_days |
| Freshness status | Fresh (1/24) | Stale (6/21) | Fresh (1/24) | 4.17% → 28.57% | 100% | |

Kết luận nhân quả:

1. `stale_date` lùi ngày xuất bản 6 bài → `expect_column_values_to_be_between(age_days)` FAIL và freshness chuyển Stale (28.6% > 25%) → câu `eval_007` trả lời `2025-06-03`, Token F1 = 0, judge chấm sai.
2. `drop_latest_records` xóa 5 bài mới nhất → `latest_published` lùi từ 2026-07-22 về 2026-06-12 → `eval_001` và `eval_002` không còn tài liệu đích, `retrieval_hit_rate` giảm 0.2. Riêng `eval_002` vẫn được judge chấm đúng vì một bài khác có cùng tác giả — ví dụ Silent Failure mà judge không phát hiện, chỉ hit rate mới lộ ra.
3. Repair dựng lại từ raw snapshot → quality gate PASS 8/8, freshness Fresh → cả 4 chỉ số agent trở về đúng giá trị baseline.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Manifest `data/embeddings/*.json` ghi `persist_path` dạng tuyệt đối (`C:\Users\...\data\chroma`); thư mục `data/chroma/` phình lên 15 thư mục segment dù chỉ có 3 collection.
- **Nguyên nhân:** `LocalEmbeddingIndex.build` lưu `str(persist_path)` tuyệt đối; mỗi lần build lại, ChromaDB xóa collection nhưng không dọn thư mục segment cũ.
- **Cách xử lý:** Lưu `persist_path` tương đối so với thư mục project và ghép lại khi `load`; xóa sạch `data/chroma/` rồi chạy lại hai pipeline; thêm `.gitattributes` đánh dấu file ChromaDB là binary để git trên Windows không đổi CRLF làm hỏng file `.bin`.
- **Cách xác minh:** Manifest ghi `"persist_path": "data/chroma"`; `data/chroma/` còn đúng 3 thư mục collection + `chroma.sqlite3` (1.4 MB); test `test_load_from_manifest_and_collection_names` PASS.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng | Hướng cải thiện có thể kiểm chứng |
| --- | --- | --- |
| Row count 5–5000 không bắt được việc mất 20% bản ghi | `drop_latest_records` lọt qua gate | So sánh row count với lần chạy trước (ví dụ không giảm quá 10%); kiểm chứng bằng việc check FAIL trên dữ liệu corrupted |
| Không expectation nào bắt `inject_noise` | Tóm tắt chứa rác vẫn được index | Thêm check tỷ lệ token không phải từ điển / ký tự đặc biệt trong `summary` |
| Câu hỏi chứa nguyên tiêu đề nên baseline = 1.0 | Baseline không phản ánh chất lượng semantic search | Thêm câu hỏi diễn đạt lại không chứa tiêu đề; đo lại hit rate |
| LLM judge không hoàn toàn tất định | `mean_judge_score` corrupted dao động 4.3–4.4 giữa các lần chạy | Chạy nhiều lần lấy trung bình hoặc cố định seed |

## 13. Checklist trước khi nộp

- [x] Thông tin nhóm và repository chính xác.
- [x] Phân công khớp với module, artifact và kết quả thực tế.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set.
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Quality/freshness conclusions khớp với `data/quality/`.
- [x] Các đường dẫn báo cáo và artifact truy cập được.
- [x] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng.
- [x] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.
