# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Phạm Hương Giang |
| MSSV | 126061729 |
| Khóa/Lớp | K4 - L3B (Ca Sáng) |
| Tên nhóm | 333 |
| Vai trò chính | Observability Owner & Corruption Flow Integration |
| Repository | https://github.com/VinUni-AI20k/K4-L3B-Day10-333-Data-Pipeline-Data-Observability.git |
| Ngày hoàn thành | 2026-09-26 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Data Quality Gate | `src/observability/quality.py` (`run_data_quality_checks`) | `df: pd.DataFrame`, `settings: Settings`, `report_name: str` | `data/quality/{report_name}.json` | Hoàn thành |
| Freshness Monitoring | `src/observability/quality.py` (`build_freshness_report`) | `df: pd.DataFrame`, `settings: Settings`, `report_path: Path` | `data/quality/freshness_report.json` | Hoàn thành |
| Baseline & Corruption Flow | `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py` | Raw Crossref records (`crossref_response.json`) | `corruption_report.md`, clean/corrupted/repaired datasets | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Debug môi trường ảo & package | Môi trường nhóm (`.venv`, `sys.path`) | Sửa lỗi `ModuleNotFoundError: No module named 'pipelines'` bằng cấu hình `PYTHONPATH` và cài đặt gói phát triển `pip install -e .`. |
| Chuẩn hóa API Great Expectations | Tích hợp module Quality với pipeline | Cập nhật tên class Expectation phù hợp chuẩn Great Expectations 1.x (`ExpectColumnValuesToNotBeNull`). |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Xây dựng chốt kiểm soát chất lượng dữ liệu | `src/observability/quality.py` | Bộ Expectation Suite kiểm tra row count, missing title/id, duplicate id, summary length | `data/quality/baseline_quality_report.json` |
| Giám sát độ trễ tài liệu (Freshness) | `src/observability/quality.py` | Phát hiện tài liệu quá hạn dựa trên cột `age_days` (ngưỡng 180 ngày) | `data/quality/freshness_report.json` |
| Đo lường suy giảm & phục hồi | `src/pipelines/corruption_flow.py` | Báo cáo đối chiếu 3 pha Baseline - Corrupted - Repaired | `data/reports/corruption_report.md` |

**Output cụ thể tạo ra:** Bảng đối chiếu chất lượng dữ liệu tại `data/reports/corruption_report.md` chứng minh Quality Gate phát hiện thành công dữ liệu bẩn (tỷ lệ pass giảm từ 100% xuống 62.5% và phát hiện 1 bản ghi stale), sau đó phục hồi nguyên vẹn về 100% ở pha Repaired.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Dữ liệu thô thu thập từ Crossref API có thể chứa các bản ghi lỗi (thiếu tiêu đề, rỗng abstract, trùng khóa chính `paper_id`) hoặc các tài liệu quá cũ đã xuất bản nhiều năm trước. Nếu nạp trực tiếp vào Vector Database (ChromaDB), hệ thống RAG sẽ bị ô nhiễm ngữ cảnh, gây suy giảm độ chính xác và khiến LLM đưa ra câu trả lời bịa đặt.

### Cách triển khai

- Khởi tạo Great Expectations 1.x ở chế độ `ephemeral context` để tăng tốc độ kiểm thử trong pipeline mà không phụ thuộc vào cấu hình thư mục phức tạp.
- Đăng ký `Pandas Datasource`, tạo `ExpectationSuite` kiểm tra 5 điều kiện cốt lõi:
  1. `ExpectTableRowCountToBeBetween(min_value=1)`
  2. `ExpectColumnValuesToNotBeNull(column="paper_id")` và `ExpectColumnValuesToBeUnique(column="paper_id")`
  3. `ExpectColumnValuesToNotBeNull(column="title")`
  4. `ExpectColumnValuesToNotBeNull(column="summary")` và `ExpectColumnValueLengthsToBeBetween(column="summary", min_value=10)`
  5. `ExpectColumnValuesToBeBetween(column="age_days", min_value=0, max_value=180)`
- Viết hàm `build_freshness_report` tính toán số dòng `stale_rows` dựa trên `age_days > max_age_days` và cờ trạng thái `is_fresh`.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `pd.DataFrame` chứa các cột chuẩn: `paper_id`, `title`, `summary`, `published`, `age_days` |
| Output | Dict JSON chứa thống kê validation: `success`, `evaluated_expectations`, `success_percent`, `details` |
| Module phụ thuộc | `src/core/config.py` (đọc đường dẫn file và cấu hình `freshness_threshold_days`) |
| Module sử dụng output | `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py` |
| Điều kiện lỗi cần xử lý | Cột `summary` rỗng hoặc thiếu; ngày tháng không đúng định dạng ISO; `age_days` âm hoặc bị null |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** Pha Baseline đạt PASS (100%), Pha Corrupted báo FAIL (<100%, `stale_rows > 0`), Pha Repaired đạt PASS (100%).
- **Kết quả thực tế:** Terminal in `Hoàn thành quy trình: Baseline -> Corruption -> Repair -> Comparison Report.` với tiến trình tính metric 39/39 đạt 100%.
- **Artifact/log:** `data/reports/corruption_report.md`, `data/quality/baseline_quality_report.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Lựa chọn giữa việc dùng File-based GX Store (khởi tạo thư mục `gx/` trên disk) và chế độ bộ nhớ tạm thời (`gx.get_context(mode="ephemeral")`).
- **Các phương án đã cân nhắc:**
  1. Lưu trữ cấu hình trên disk (`gx init` / project context).
  2. Ephemeral In-Memory Context kết hợp xuất file JSON kết quả trực tiếp ra `data/quality/`.
- **Phương án đã chọn:** Phương án 2 (Ephemeral In-Memory Context).
- **Lý do:** Giảm thiểu xung đột metadata khi chạy trong môi trường nhóm qua Git, đảm bảo tính bất biến (Idempotent), chạy độc lập và nhẹ hơn rất nhiều khi tích hợp vào CI/CD pipeline hoặc script automation.
- **Bằng chứng quyết định phù hợp:** Pipeline chạy trơn tru, không gặp lỗi lock file cơ sở dữ liệu metadata GX, xuất đúng định dạng file JSON báo cáo theo yêu cầu của dự án.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `AttributeError: module 'great_expectations.expectations' has no attribute 'ExpectColumnValuesToBeNotNull'. Did you mean: 'ExpectColumnValuesToBeNull'?`
- **Lệnh hoặc bước tái hiện:** Chạy lệnh `python script/run_phase1.py`.
- **Nguyên nhân gốc:** Sự thay đổi quy ước đặt tên (naming convention) trong Great Expectations 1.x; cụm `Not` được đưa lên trước `Be` (`ToNotBeNull` thay vì `ToBeNotNull`).
- **Cách xử lý:** Đổi tên class thành `gxe.ExpectColumnValuesToNotBeNull` trong file `src/observability/quality.py`.
- **Cách xác minh sau khi sửa:** Chạy lại `python script/run_phase1.py`, pipeline vượt qua bước kiểm tra chất lượng và hoàn thành Phase 1 thành công.
- **Điều học được:** Khi làm việc với các thư viện vừa nâng cấp phiên bản lớn (Major Release như GX 1.x), cần kiểm tra kỹ namespace và tên class từ tài liệu chính thức thay vì áp dụng trực tiếp quy ước từ phiên bản cũ (GX 0.18.x).

## 7. Hiểu biết về luồng end-to-end

1. **Dữ liệu đi từ Crossref đến vector index như thế nào?**  
   Dữ liệu thô JSON từ Crossref API được trích xuất thông tin định danh (DOI), tiêu đề, tóm tắt khoa học và ngày xuất bản; sau đó được làm sạch, tính toán `age_days`, kiểm duyệt qua Data Quality Gate, rồi mã hóa thành vector embeddings bằng model `sentence-transformers/all-MiniLM-L6-v2` và nạp vào ChromaDB collection.

2. **Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?**  
   Dùng để đo lường định lượng khả năng truy xuất (`retrieval_hit_rate` xem văn bản liên quan có lọt vào top-k không) và chất lượng sinh câu trả lời của mô hình (`mean_token_f1`, `judge_accuracy` dựa trên LLM-as-a-judge so sánh với ground truth).

3. **Quality checks khác freshness monitoring ở điểm nào trong bài lab?**  
   Quality checks tập trung vào tính toàn vẹn và cấu trúc của dữ liệu (schema, độ dài, null, unique); còn Freshness monitoring tập trung vào tính thời điểm (temporal validity) để phát hiện tài liệu đã quá hạn (`age_days > 180`) dù cấu trúc của nó hoàn toàn hợp lệ.

4. **Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?**  
   Để đảm bảo tính khách quan và khoa học của phép đo. Giữ cố định tập câu hỏi đánh giá là cách duy nhất để cô lập biến số, chứng minh sự suy giảm hiệu năng hoàn toàn bắt nguồn từ sự xuống cấp của dữ liệu (data corruption) chứ không phải do độ khó của câu hỏi thay đổi.

5. **Repair được xem là thành công dựa trên artifact và metric nào?**  
   Repair thành công khi Quality Gate chuyển từ FAIL về lại PASS (tỷ lệ 100%), `stale_rows = 0`, và các chỉ số RAG (`retrieval_hit_rate`, `mean_token_f1`) khôi phục tương đương hoặc bằng trạng thái baseline ban đầu.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.00 | 0.67 | 1.00 | Suy giảm rõ rệt khi tài liệu bị mất tiêu đề hoặc trùng ID. |
| `mean_token_f1` | 0.82 | 0.45 | 0.82 | Câu trả lời của agent bị giảm chất lượng do ngữ cảnh bẩn. |
| `judge_accuracy` | 1.00 | 0.50 | 1.00 | Mô hình judge phát hiện câu trả lời hallucinate ở pha lỗi. |
| `mean_judge_score` | 4.80 | 2.30 | 4.80 | Điểm đánh giá giảm mạnh ở pha Corrupted và hồi phục ở pha Repair. |
| Quality checks | PASS | FAIL | PASS | Gate bắt được chính xác các vi phạm missing và uniqueness. |
| Freshness status | True | False | True | Bắt đúng 1 bản ghi bị cố tình gán `age_days = 999`. |

### Kết luận từ số liệu

1. **Chuỗi lỗi:** Inject missing title, duplicate `paper_id`, `age_days = 999` → Quality Gate giảm tỷ lệ pass từ 100% xuống 62.5%, Freshness báo False → Retrieval Hit Rate tụt từ 1.00 xuống 0.67 và Token F1 giảm xuống 0.45.
2. **Chuỗi phục hồi:** Idempotent re-ingestion từ raw source gốc → Quality Gate đạt lại 100% PASS, Freshness báo True → Agent metrics phục hồi hoàn toàn về trạng thái Baseline (Hit Rate 1.00, F1 0.82).

**Corruption ảnh hưởng rõ nhất và vì sao?**  
Lỗi mất title và trùng lặp `paper_id` ảnh hưởng nghiêm trọng nhất vì làm sai lệch định danh trong Vector Store, khiến bước truy xuất trả về sai ngữ cảnh hoặc bị ghi đè dữ liệu.

**Kết quả nào khác với kỳ vọng ban đầu?**  
Ban đầu kỳ vọng khi tiêm lỗi freshness thì model vẫn truy xuất được văn bản cũ; tuy nhiên chất lượng judge score vẫn bị phạt nặng do thông tin bị coi là lỗi thời.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Kiến trúc Pipeline:** Kiểm soát chất lượng dữ liệu ở thượng nguồn (Upstream Quality Gate) tiết kiệm chi phí và rủi ro hơn rất nhiều so với việc cố gắng xử lý lỗi ở hạ nguồn AI.
2. **Data Observability:** Độ tươi (Freshness) là một chiều kích chất lượng quan trọng không kém gì tính đúng đắn của Schema trong các bài toán tri thức động.
3. **Tính Bất biến (Idempotency):** Đường ống dữ liệu tốt phải đảm bảo chạy lại nhiều lần từ dữ liệu nguồn gốc mà không làm sai lệch hay nhân bản trạng thái hệ thống.

### Nếu có thêm thời gian

Tích hợp thêm Drift Detection (kiểm soát độ trôi dạt ngữ nghĩa của embeddings): sử dụng khoảng cách phân phối (như MMD hoặc Cosine Similarity drift) để phát hiện khi văn bản bài báo thay đổi chủ đề quá xa so với domain huấn luyện ban đầu của hệ thống RAG.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Phạm Hương Giang  
**Ngày xác nhận:** 2026-09-26
