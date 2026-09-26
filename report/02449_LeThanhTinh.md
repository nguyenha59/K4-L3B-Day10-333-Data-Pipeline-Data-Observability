# BÁO CÁO CÁ NHÂN — DATA PIPELINE & DATA OBSERVABILITY

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Lê Thanh Tình |
| MSSV | 02449 |
| Khóa/Lớp | K4-L3B-DAY10 |
| Tên nhóm | 333 |
| Vai trò chính | Evaluation & Observability |
| Repository | https://github.com/nguyenha59/K4-L3B-Day10-333-Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-09-26 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Evaluation set | `src/evaluation/testset.py`: `build_test_set`, `_question_for` | DataFrame sạch gồm thông tin bài báo | `data/eval/test_set.json` gồm 10 câu hỏi thuộc 4 nhóm | Hoàn thành |
| Data quality gate | `src/observability/quality.py`: `run_data_quality_checks`, `_build_suite` | DataFrame ở từng trạng thái và cấu hình pipeline | GX suite và các báo cáo `data/quality/*_quality_report.json` | Hoàn thành |
| Freshness SLA | `src/observability/quality.py`: `evaluate_freshness_sla`, `build_freshness_report` | `published`, `age_days`, ngưỡng freshness | Trạng thái fresh/stale và các thống kê freshness | Hoàn thành |
| Báo cáo baseline | `src/observability/reporting.py`: `generate_phase1_report` | Source summary, metrics, quality và freshness | `data/reports/phase1_report.md` | Hoàn thành |
| Báo cáo ba trạng thái | `src/observability/reporting.py`: `generate_corruption_report` | Metrics và quality của baseline/corrupted/repaired | `data/reports/corruption_report.md` | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Xác minh đầu ra của pipeline baseline | `src/pipelines/phase1.py` | Báo cáo Phase 1 phản ánh đúng metrics, quality gate và freshness artifact |
| Xác minh luồng corruption/repair | `src/pipelines/corruption_flow.py` | Cùng một test set được dùng cho ba trạng thái; bảng so sánh thể hiện được suy giảm và phục hồi |
| Chuẩn bị nội dung demo | Cả nhóm | Có bảng Baseline – Corrupted – Repaired và bằng chứng về silent failure |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Xây dựng benchmark cố định | `src/evaluation/testset.py`, `data/eval/test_set.json` | 10 câu hỏi: 3 summary, 3 authors, 2 date, 2 categories | Kiểm tra số phần tử và trường `question_type`, `ground_truth`, `ground_truth_doc_ids` |
| Thiết lập GX 1.x bằng ephemeral context | `src/observability/quality.py` | 8 phép kiểm tra cho volume, completeness, uniqueness, validity và freshness | Đọc `data/quality/baseline_quality_report.json` |
| Theo dõi Freshness SLA | `evaluate_freshness_sla` | Đánh dấu stale nếu tỷ lệ bản ghi có `age_days > 180` vượt 25% | So sánh các trường `stale_ratio` và `is_fresh` |
| Sinh báo cáo baseline | `generate_phase1_report` | Báo cáo nguồn, metrics, GX và freshness | `data/reports/phase1_report.md` |
| Sinh báo cáo đối chiếu | `generate_corruption_report` | Bảng metrics, delta, recovery và chi tiết quality gate | `data/reports/corruption_report.md` |

Output tiêu biểu là báo cáo chất lượng dữ liệu corrupted: chỉ 4/8 expectation đạt, freshness chuyển sang `false`, đồng thời các metric của agent suy giảm. Sau repair, 8/8 expectation đạt lại và toàn bộ metric trở về đúng baseline.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Pipeline có thể chạy hết mà không phát sinh exception dù dữ liệu đã bị xóa, làm rỗng, cắt ngắn, làm cũ hoặc nhân bản. Phần observability cần biến các lỗi âm thầm đó thành tín hiệu có thể kiểm tra; phần evaluation phải đo được tác động của chúng lên retrieval và câu trả lời của RAG.

### Cách triển khai

Bộ test được tạo từ các bản ghi hợp lệ, loại tiêu đề chứa dấu nháy đơn và yêu cầu đủ tác giả, danh mục, tóm tắt. Các ứng viên được sắp xếp theo ngày xuất bản rồi lấy mẫu trải đều từ mới đến cũ. Mỗi câu hỏi lưu cả đáp án chuẩn và `paper_id` chuẩn để đánh giá answer quality lẫn retrieval quality.

Quality gate dùng Great Expectations 1.x với context tạm thời, pandas data source và whole-dataframe batch. Suite kiểm tra số dòng, các cột bắt buộc không null, `paper_id` duy nhất, độ dài tối thiểu của summary/title và tỷ lệ `age_days` nằm trong SLA. Kết quả GX được rút gọn thành JSON dễ đọc, đồng thời freshness được tính riêng để báo cáo rõ số bản ghi stale và tỷ lệ stale.

Module reporting không tự tính lại metric mà nhận artifact từ pipeline, định dạng thành bảng Markdown, tính mức suy giảm và tỷ lệ phục hồi. Cách này giữ một nguồn dữ liệu thống nhất giữa JSON và báo cáo.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Clean/corrupted/repaired DataFrame; `Settings`; metrics JSON; source summary |
| Output | Test-set JSON, GX suite JSON, quality/freshness JSON và báo cáo Markdown |
| Module phụ thuộc | `core.config`, `core.utils`, pandas, Great Expectations 1.x |
| Module sử dụng output | `retrieval.evaluation`, `pipelines.phase1`, `pipelines.corruption_flow` |
| Điều kiện lỗi cần xử lý | Không đủ 10 tài liệu hợp lệ; dữ liệu trùng ID; summary/title quá ngắn; tỷ lệ stale vượt SLA; trường bắt buộc null/rỗng |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** baseline pass quality gate; corrupted bị phát hiện và làm metric suy giảm; repaired trở về trạng thái baseline.
- **Kết quả thực tế:** baseline và repaired đạt 8/8 checks, corrupted chỉ đạt 4/8; các metrics sau repair khớp baseline.
- **Artifact/log:** `data/eval/test_set.json`, `data/quality/`, `data/results/*_metrics.json`, `data/reports/phase1_report.md`, `data/reports/corruption_report.md`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần so sánh công bằng chất lượng RAG giữa baseline, corrupted và repaired.
- **Các phương án đã cân nhắc:** tạo lại test set sau mỗi trạng thái, hoặc tạo một test set từ dữ liệu sạch và tái sử dụng cho cả ba trạng thái.
- **Phương án đã chọn:** cố định `data/eval/test_set.json` từ baseline và dùng lại cho mọi lần đánh giá.
- **Lý do:** nếu ground truth thay đổi cùng dữ liệu corrupted thì phép đo có thể che giấu lỗi; test set cố định giúp delta phản ánh đúng ảnh hưởng của dữ liệu.
- **Bằng chứng quyết định phù hợp:** trên cùng 10 mẫu, `retrieval_hit_rate` giảm từ 1.0 xuống 0.8 và `judge_accuracy` giảm từ 1.0 xuống 0.7 khi corrupted, sau đó đều trở lại 1.0 sau repair.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** dữ liệu corrupted vẫn đi hết pipeline nên chỉ nhìn exit code không thể kết luận dữ liệu tốt.
- **Bước tái hiện:** chạy `python script/run_corruption_flow.py` và đối chiếu corrupted metrics với quality report.
- **Nguyên nhân gốc:** retrieval/QA vẫn có thể tạo câu trả lời từ index lỗi; pipeline thiếu chốt kiểm dịch dựa trên đặc tính dữ liệu.
- **Cách xử lý:** bổ sung GX expectations cho uniqueness, độ dài title/summary và `age_days`; xuất freshness signal và danh sách failed checks vào artifact/report.
- **Cách xác minh sau khi sửa:** corrupted report báo FAIL ở 4 checks; stale ratio là 0.2857, vượt mức 0.25; sau repair quality gate PASS và freshness trở lại `true`.
- **Điều học được:** trạng thái “pipeline chạy thành công” không đồng nghĩa với “dữ liệu đạt chất lượng”; observability phải có tín hiệu định lượng và ngưỡng rõ ràng.

## 7. Hiểu biết về luồng end-to-end

1. Crossref trả về payload thô; ingestion chuẩn hóa thành raw records và lưu snapshot. Cleaning khử trùng, chuẩn hóa trường, tính `age_days`, ghép `text_for_embedding`. Dữ liệu sạch sau đó được embedding bằng `all-MiniLM-L6-v2` và nạp vào ChromaDB.
2. Evaluation set lưu câu hỏi, đáp án chuẩn và `ground_truth_doc_ids`. Document ID dùng để tính retrieval hit; đáp án chuẩn dùng để tính token F1 và các chỉ số judge.
3. Quality checks kiểm tra cấu trúc và nội dung như số dòng, null, uniqueness, độ dài. Freshness monitoring tập trung vào độ tuổi dữ liệu và tỷ lệ bản ghi vượt ngưỡng 180 ngày. Freshness là một tín hiệu nghiệp vụ cụ thể, còn quality gate bao quát nhiều chiều chất lượng.
4. Cùng một test set giữ nguyên thước đo. Nếu thay câu hỏi/ground truth giữa các trạng thái thì chênh lệch metric có thể do benchmark thay đổi chứ không phải corruption hoặc repair.
5. Repair thành công khi dữ liệu được dựng lại từ raw snapshot bất biến, GX và freshness phục hồi, đồng thời repaired metrics khớp baseline. Trong kết quả hiện tại, 8/8 quality checks pass và bốn metric chính đều trở về baseline.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.8000 | 1.0000 | Corruption làm mất hit ở 20% câu hỏi; repair phục hồi hoàn toàn |
| `mean_token_f1` | 1.0000 | 0.8499 | 1.0000 | Nội dung lỗi làm đáp án kém khớp ground truth |
| `judge_accuracy` | 1.0000 | 0.7000 | 1.0000 | Đây là mức giảm mạnh nhất, 30 điểm phần trăm |
| `mean_judge_score` | 5.0000 | 4.3000 | 5.0000 | Chất lượng trung bình giảm dù pipeline vẫn hoàn tất |
| Quality checks | PASS (8/8) | FAIL (4/8) | PASS (8/8) | Corrupted bị phát hiện bởi uniqueness, title, summary và age |
| Freshness status | Fresh (1/24 stale) | Stale (6/21 stale) | Fresh (1/24 stale) | Tỷ lệ stale: 0.0417 → 0.2857 → 0.0417 |

### Kết luận từ số liệu

1. Sáu dạng corruption làm dữ liệu còn 21 dòng, xuất hiện ID trùng, title/summary ngắn và 6 bản ghi quá hạn → quality gate FAIL, freshness chuyển sang stale → hit rate giảm 0.2, token F1 giảm khoảng 0.1501 và judge accuracy giảm 0.3.
2. Repair dựng lại dữ liệu từ raw snapshot → số dòng về 24, GX đạt 8/8 và freshness về 0.0417 → toàn bộ agent metrics trở lại đúng baseline.

Nhóm lỗi ảnh hưởng rõ nhất tới kết quả tổng thể là drop records kết hợp với blank/noisy summary: chúng làm tài liệu chuẩn không được retrieve hoặc làm nội dung trả lời không còn khớp ground truth. Riêng stale date có thể không trực tiếp làm hỏng mọi câu trả lời, nhưng được freshness SLA phát hiện sớm trước khi dữ liệu cũ gây suy giảm dài hạn.

Điểm khác kỳ vọng là pipeline corrupted vẫn chạy thành công về mặt kỹ thuật. Việc đối chiếu metrics và artifact quality cho thấy đây chính là silent failure, không phải bằng chứng dữ liệu hợp lệ.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Evaluation chỉ có ý nghĩa khi test set, ground truth và cấu hình được giữ cố định giữa các lần chạy.
2. Data observability cần kết hợp nhiều chiều: schema/completeness/uniqueness/validity và freshness; một tín hiệu đơn lẻ không bao phủ hết lỗi.
3. Chất lượng dữ liệu tác động trực tiếp đến retrieval và đáp án RAG, kể cả khi chương trình không báo exception.

### Nếu có thêm thời gian

Tôi sẽ bổ sung lịch sử metric theo lần chạy và cảnh báo theo mức độ nghiêm trọng. Cải thiện được đo bằng thời gian phát hiện sự cố, tỷ lệ corruption scenario được cảnh báo đúng và số cảnh báo giả trên dữ liệu baseline.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Lê Thanh Tình  
**Ngày xác nhận:** 2026-09-26
