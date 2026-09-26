# Data Quality & Observability Comparison Report

| Metric / Check | 1. Baseline | 2. Corrupted | 3. Repaired |
| :--- | :--- | :--- | :--- |
| **Quality Gate Status** | PASS | FAIL | PASS |
| **Success Rate (%)** | 100.0% | 62.5% | 100.0% |
| **Freshness (<= 180d)** | True | False | True |
| **Stale Records Count** | 0 | 1 | 0 |

### Kết luận
- **Corruption Stage:** Chốt kiểm soát phát hiện chính xác các lỗi thiếu thuộc tính, trùng khóa chính và vi phạm độ trễ dữ liệu (`age_days > 180`).
- **Repair Stage:** Pipeline khôi phục trạng thái chuẩn xác từ nguồn raw data gốc, đảm bảo tính bất biến (Idempotent).
