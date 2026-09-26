# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Nguyễn Thị Hạ |
| MSSV | 02536 |
| Khóa/Lớp | K4 — L3B |
| Tên nhóm | 333 |
| Vai trò chính | Corruption & Integration |
| Repository | https://github.com/nguyenha59/K4-L3B-Day10-333-Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-09-26 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Corruption suite | `src/ingestion/corruption.py` — `corrupt_clean_dataframe` | Clean dataframe 24 dòng | Dataframe bẩn 21 dòng, `data/results/corruption_log.json` | Hoàn thành |
| Baseline orchestration | `src/pipelines/phase1.py` — `run_phase1_pipeline` | Settings, raw snapshot | `papers_clean.*`, `papers-baseline`, `baseline_metrics.json`, `phase1_report.md` | Hoàn thành |
| Corruption → repair → compare | `src/pipelines/corruption_flow.py` — `run_corruption_flow_pipeline`, `repair_from_raw_snapshot` | Baseline artifacts, raw records | `corrupted_metrics.json`, `repaired_metrics.json`, `corruption_report.md` | Hoàn thành |
| Test suite | `tests/`, `script/run_tests.py`, `.github/workflows/tests.yml` | Toàn bộ `src/` | 50 test, coverage 97.19% | Hoàn thành |

Phần việc của tôi nhận raw/clean data từ Giang (`crossref.py`, `cleaning.py`) và dùng test set, quality gate, report của Tình (`testset.py`, `quality.py`, `reporting.py`) để ghép thành hai flow end-to-end.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Sửa `persist_path` tuyệt đối trong manifest embedding | `retrieval/index.py` | Manifest ghi `data/chroma`, repo chạy được trên máy khác |
| Dọn thư mục segment thừa của ChromaDB, thêm `.gitattributes` | `data/chroma/` | Còn đúng 3 collection (1.4 MB), file binary không bị đổi CRLF |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Tiêm 6 loại lỗi có seed, log từng dòng | `corruption.py`, `corruption_log.json` | 24 → 21 dòng; 5 / 3 / 3 / 3 / 6 / 2 dòng bị tác động | `python -c "... corrupt_clean_dataframe ..."` in `Corrupted 21 dòng` |
| Pipeline baseline | `phase1.py` | Hit rate 1.0, judge accuracy 1.0, gate PASS | `python script/run_phase1.py` exit 0 |
| Pipeline corruption + auto-repair | `corruption_flow.py` | Gate FAIL 4/8 → repair → PASS 8/8; chỉ số phục hồi 100% | `python script/run_corruption_flow.py` exit 0, in bảng 3 cột |
| Bộ test tự động | `tests/` | 50 passed, coverage 97.19% | `pytest` |

Output cụ thể: bảng so sánh trong `data/reports/corruption_report.md`, được sinh từ `run_corruption_flow_pipeline`:

| Metric | Baseline | Corrupted | Repaired |
| --- | --: | --: | --: |
| `retrieval_hit_rate` | 1.0000 | 0.8000 | 1.0000 |
| `judge_accuracy` | 1.0000 | 0.7000 | 1.0000 |
| Quality gate | PASS 8/8 | FAIL 4/8 | PASS 8/8 |

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Chứng minh rằng dữ liệu bẩn làm RAG agent trả lời sai một cách âm thầm (pipeline không báo lỗi), rằng quality gate phát hiện được sự cố, và rằng hệ thống tự phục hồi về đúng trạng thái baseline.

### Cách triển khai

- **Corruption:** Kịch bản 1 xóa 20% bài có `published` mới nhất. Kịch bản 2–5 lấy các nhóm dòng **không giao nhau** từ một danh sách xáo trộn theo `random.Random(20260926)`, để mỗi hậu quả quy được về đúng một loại lỗi. Kịch bản 6 nhân đôi 2 dòng. Sau cùng tính lại `age_days` và `text_for_embedding` bằng `add_derived_columns` của cleaning, để embedding phản ánh dữ liệu bẩn thay vì văn bản cũ. Mỗi thay đổi được log `paper_id`, `field`, `before`, `after`.
- **Orchestration phase 1:** ingest → clean → lưu CSV/JSON → build collection `papers-baseline` → dùng lại test set nếu đã có (chỉ sinh lại khi `REFRESH_TEST_SET=1`) → evaluate → quality gate + freshness → `phase1_report.md` → agent demo (tùy chọn, lỗi provider không làm hỏng pipeline).
- **Corruption flow:** dữ liệu bẩn được index vào collection riêng `papers-corrupted` để không ảnh hưởng baseline; đánh giá trên cùng test set; chạy quality gate. Nếu gate hoặc freshness FAIL thì gọi `repair_from_raw_snapshot()`, dữ liệu repaired phải PASS gate lần nữa (nếu không pipeline dừng với lỗi), rồi mới index `papers-repaired` và đánh giá lại.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Clean dataframe theo `CLEAN_COLUMNS` (16 cột), `data/raw/crossref_records.json`, `data/eval/test_set.json` |
| Output | `papers_clean_corrupted.*`, `papers_clean_repaired.*`, `corruption_log.json`, `*_metrics.json`, `*_answers.json`, `corruption_report.md` |
| Module phụ thuộc | `ingestion.crossref`, `ingestion.cleaning`, `observability.quality`, `evaluation.metrics`, `retrieval.index` |
| Module sử dụng output | `observability.reporting`, `tests/` |
| Điều kiện lỗi cần xử lý | Chưa chạy phase 1 (thiếu baseline) → dừng với hướng dẫn; dữ liệu repaired vẫn FAIL gate → dừng; LLM provider lỗi → bỏ qua agent demo, judge dùng heuristic |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
python -c "from core.config import load_settings; from ingestion.corruption import corrupt_clean_dataframe; import pandas as pd; s=load_settings(); df=pd.read_json(s.paths.clean_json); c=corrupt_clean_dataframe(df, s.paths.corruption_log); print(f'Tín hiệu hoàn thành: Corrupted {len(c)} dòng')"
pytest
```

- **Kết quả mong đợi:** Hai script exit 0; corrupted có chỉ số thấp hơn baseline và gate FAIL; repaired bằng baseline; log đủ 6 kịch bản.
- **Kết quả thực tế:** Đúng như mong đợi. Console in `[repair] Rebuilt 24 rows from crossref_records.json; identical to baseline clean data: True` và bảng 3 cột; `Corrupted 21 dòng`; `50 passed`, coverage 97.19%.
- **Artifact/log:** `data/results/corruption_log.json`, `data/results/*_metrics.json`, `data/reports/corruption_report.md`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Chọn cách repair dữ liệu sau khi bị làm bẩn.
- **Các phương án đã cân nhắc:** (1) Sửa trực tiếp trên dữ liệu bẩn: drop duplicate, lọc summary rỗng, bỏ dòng title ngắn. (2) Dựng lại toàn bộ clean layer từ raw snapshot bất biến.
- **Phương án đã chọn:** (2) — `repair_from_raw_snapshot()` đọc `crossref_records.json` (hoặc parse lại `crossref_response.json` nếu thiếu) và chạy lại `build_clean_dataframe`.
- **Lý do:** Phương án (1) chỉ che triệu chứng: không lấy lại được 5 bài đã bị xóa, không biết ngày xuất bản đúng của bài bị lùi ngày, không khôi phục được tiêu đề đầy đủ. Phương án (2) chỉ phụ thuộc vào raw nên chạy bao nhiêu lần cũng ra cùng kết quả (idempotent), không cần gọi lại API nên tránh rate limit.
- **Bằng chứng quyết định phù hợp:** Pipeline so sánh dữ liệu repaired với bản clean ban đầu và in `identical to baseline clean data: True`; bốn chỉ số repaired trùng baseline; test `test_corruption_degrades_and_repair_restores` PASS.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Khi chạy `run_phase1.py` với OpenAI key sai, agent demo báo `OpenAIAuthenticationError: Error code: 401 - {'error': {'message': 'Incorrect API key provided: sk-proj-****…****. …'}}` và toàn bộ thông báo lỗi được ghi vào `data/results/agent_demo_answers.json`.
- **Lệnh hoặc bước tái hiện:** Đặt `OPENAI_API_KEY` không hợp lệ trong `.env`, chạy `python script/run_phase1.py`.
- **Nguyên nhân gốc:** `_run_agent_demo` lưu nguyên `str(exc)`; nội dung lỗi từ provider có lặp lại một phần API key (đã che nhưng vẫn lộ vài ký tự cuối) → key có thể lọt vào artifact được commit.
- **Cách xử lý:** Trước khi ghi trạng thái, thay mọi chuỗi dạng key (`sk…`, `AIza…`) bằng `<redacted>` và cắt thông báo còn tối đa 160 ký tự; quét lại `data/` để chắc không còn chuỗi `sk-`.
- **Cách xác minh sau khi sửa:** Chạy lại demo với key sai → trạng thái ghi `Incorrect API key provided: <redacted>`; quét nội dung trước khi commit không có key; sau khi thay key hợp lệ, `agent_demo_answers.json` có `"status": "ok"`.
- **Điều học được:** Artifact của pipeline cũng là một kênh rò rỉ secret, không chỉ file `.env`; thông báo lỗi từ dịch vụ bên ngoài cần được làm sạch trước khi lưu.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. `fetch_source_records` lấy payload Crossref (snapshot hoặc API có retry), lưu nguyên bản `crossref_response.json` và bản đã parse `crossref_records.json`. `build_clean_dataframe` làm sạch, dedup, tính `age_days` và ghép `text_for_embedding`. `LocalEmbeddingIndex.build` encode văn bản bằng MiniLM (384 chiều, chuẩn hóa) và nạp vào collection ChromaDB với metadata (tác giả, ngày, lĩnh vực, summary).
2. Mỗi câu hỏi có `ground_truth` (giá trị đúng) và `ground_truth_doc_ids` (DOI bài chứa đáp án). Retrieval tính hit khi một DOI trong top-4 trùng ground truth; câu trả lời được so với `ground_truth` bằng Token F1 và LLM judge.
3. Quality checks kiểm tra cấu trúc và nội dung từng dòng (null, unique, độ dài, số dòng). Freshness đo độ cũ của cả tập dữ liệu (tỷ lệ bài có `age_days > 180` không vượt 25%). Dữ liệu có thể hợp lệ về cấu trúc nhưng vẫn quá cũ.
4. Nếu đổi test set thì không tách được thay đổi do dữ liệu khỏi thay đổi do đề. Ví dụ nếu sinh lại đề từ dữ liệu bẩn, 5 bài bị xóa sẽ không còn câu hỏi và sự sụt giảm bị che mất.
5. Repair thành công khi: quality gate PASS 8/8 và freshness Fresh trên `data/quality/repaired_*`; dữ liệu repaired trùng bản clean ban đầu; `repaired_metrics.json` bằng `baseline_metrics.json`.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | --: | --: | --: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.8000 | 1.0000 | Chỉ giảm do bài đích bị xóa (`eval_001`, `eval_002`) |
| `mean_token_f1` | 1.0000 | 0.8499 | 1.0000 | `eval_007` về 0 vì sai năm |
| `judge_accuracy` | 1.0000 | 0.7000 | 1.0000 | Giảm mạnh hơn hit rate: có câu tìm đúng bài vẫn trả lời sai |
| `mean_judge_score` | 5.0 | 4.3 | 5.0 | |
| Quality checks | PASS 8/8 | FAIL 4/8 | PASS 8/8 | Fail: unique, title, summary, age_days |
| Freshness status | Fresh | Stale | Fresh | 1/24 → 6/21 → 1/24 bài quá hạn |

### Kết luận từ số liệu

1. `stale_date` (6 dòng) → `age_days` FAIL, freshness Stale 28.6% → `eval_007` trả lời `2025-06-03`, judge chấm sai.
2. Repair từ raw snapshot → gate PASS 8/8, freshness Fresh → cả 4 chỉ số trở về đúng baseline.

Corruption ảnh hưởng rõ nhất là `drop_latest_records`: làm 2/10 câu mất tài liệu đích, và là lỗi mà quality gate hiện tại **không** bắt được (row count 21 vẫn trong ngưỡng 5–5000). Chỉ có hit rate và `latest_published` (2026-07-22 → 2026-06-12) phản ánh sự cố.

Kết quả khác kỳ vọng: `eval_002` bị MISS nhưng vẫn được judge chấm đúng. Kiểm tra `corrupted_answers.json` cho thấy top-1 là một bài khác có cùng tác giả (Kien Duong, Vy Ly), nên câu trả lời trùng hợp đúng. Như vậy nếu chỉ theo dõi judge accuracy thì sẽ bỏ sót lỗi retrieval này. Ngoài ra `eval_009` tìm thấy bài đích trong top-4 nhưng vẫn sai, vì tiêu đề bị cắt khiến tra cứu chính xác theo tiêu đề thất bại và câu trả lời lấy từ top-1 là bài khác.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Data pipeline cần giữ raw snapshot bất biến làm điểm tựa lineage; repair từ raw mới idempotent và khôi phục được cả dữ liệu đã mất.
2. Quality gate phải được thiết kế theo từng kiểu lỗi cụ thể: gate hiện tại bắt được 4/6 kịch bản, bỏ lọt `drop_latest_records` và `inject_noise`.
3. Dữ liệu bẩn làm RAG agent trả lời sai mà không báo lỗi; cần theo dõi đồng thời chỉ số retrieval, chỉ số câu trả lời và tín hiệu chất lượng dữ liệu.

### Nếu có thêm thời gian

Thêm expectation so sánh số dòng với lần chạy trước (không giảm quá 10%) để bắt `drop_latest_records`. Đo cải thiện bằng cách chạy lại corruption flow và kiểm tra check này FAIL trên dữ liệu corrupted nhưng PASS trên baseline và repaired.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Thị Hạ
**Ngày xác nhận:** 2026-09-26
