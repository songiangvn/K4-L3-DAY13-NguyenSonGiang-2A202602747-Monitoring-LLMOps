# Alert và Runbook

Mỗi alert dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ. Ngưỡng lấy từ baseline đo thật trên repo (P95 437 ms, error 0 %, cost trung bình ~0.002 USD/request) và từ ba kịch bản practice (`rag_slow`, `tool_fail`, `cost_spike`).

Cả ba runbook dùng chung luồng điều tra **Metrics → Logs → Traces**:

1. Dashboard (`python scripts/build_dashboard.py`) → xác định panel xấu và phút bắt đầu.
2. `data/logs.jsonl` → lọc event trong khoảng đó, lấy `correlation_id` và `trace_id` của request bất thường.
3. Langfuse → mở trace có cùng `trace_id` (metadata chứa cùng `correlation_id`) → so sánh `rag-retrieval` và `llm-generation`.

## Alert 1

- Tên: `HighLatencyP95`
- Severity: P2-warning
- Duration: 5m
- Kênh thông báo: Slack `#day13-l3a-alerts`
- SLI/SLO liên quan: `fast_successful_requests` (99.5 % request thành công và ≤ 3000 ms trong 28 ngày)
- Điều kiện và thời gian duy trì: `p95(response_sent.latency_ms) > 2000` trên cửa sổ trượt 5 phút, duy trì liên tục 5 phút. Ngưỡng 2000 ms thấp hơn SLO 3000 ms để cảnh báo sớm: practice `rag_slow` đẩy P95 lên 2654 ms nhưng vẫn chưa vượt SLO.
- Ảnh hưởng tới người dùng: câu trả lời chậm rõ rệt; nếu kéo dài sẽ vượt 3000 ms và đốt error budget.
- Ba bước kiểm tra đầu tiên:
  1. Panel Latency: P95/P99 tăng nhưng TTFT P95 giữ nguyên (~50 ms) → chậm nằm ngoài LLM, nghi retrieval; nếu TTFT cũng tăng → nghi LLM/provider.
  2. Lọc log: `response_sent` có `latency_ms > 2000`, lấy `correlation_id` và `trace_id`.
  3. Mở trace trên Langfuse: so sánh latency của `rag-retrieval` với `llm-generation` để khoanh vùng span chậm.
- Mitigation tạm thời: nếu retrieval chậm → giảm top-k/timeout vector store, bật cache kết quả retrieval, hoặc trả fallback "no document"; nếu LLM chậm → chuyển model nhỏ hơn hoặc giới hạn `max_tokens`; rollback prompt/label `production` nếu vừa promote.
- Owner: nguyen-son-giang (on-call)

## Alert 2

- Tên: `HighErrorRateOrRetrievalFailure`
- Severity: P1-critical
- Duration: 3m
- Kênh thông báo: Slack `#day13-l3a-alerts`
- SLI/SLO liên quan: `fast_successful_requests` (request lỗi luôn là bad event) và guardrail `retrieval_success_rate_pct_min: 90`
- Điều kiện và thời gian duy trì: `request_failed / request_received * 100 > 2` **hoặc** retrieval success < 90 % trên cửa sổ 5 phút, duy trì 3 phút. Duration ngắn hơn alert latency vì người dùng nhận HTTP 500 ngay lập tức.
- Ảnh hưởng tới người dùng: request trả HTTP 500, không có câu trả lời; burn rate có thể > 100x (practice `tool_fail` cho error rate 100 %).
- Ba bước kiểm tra đầu tiên:
  1. Panel Errors: xem `count_by_value` của `error_type` và retrieval success cùng lúc — nếu cả hai xấu → lỗi ở bước retrieval.
  2. Lọc log `request_failed`: đọc `error_type`, `tool_name`, `payload.detail` (đã scrub PII), lấy `correlation_id`.
  3. Trên Langfuse, lọc trace theo metadata `correlation_id`, kiểm tra observation nào có level `ERROR` và status message.
- Mitigation tạm thời: bật fallback trả lời không cần retrieval (degraded mode) thay vì 500; tăng timeout/retry có backoff cho vector store; nếu lỗi xuất hiện sau khi deploy/promote → rollback.
- Owner: nguyen-son-giang (on-call)

## Alert 3

- Tên: `CostPerRequestSpike`
- Severity: P3-info
- Duration: 15m
- Kênh thông báo: Slack `#day13-l3a-cost`
- SLI/SLO liên quan: guardrail `daily_cost_usd_max: 2.5`
- Điều kiện và thời gian duy trì: `avg(response_sent.cost_usd) > 0.005` mỗi request (≈ 2.5x baseline 0.002) trên cửa sổ 15 phút, **hoặc** chi phí dự phóng 24h > 2.5 USD. Duration dài vì cost không làm hỏng trải nghiệm ngay, tránh báo động theo từng burst ngắn.
- Ảnh hưởng tới người dùng: không thấy ngay; ảnh hưởng ngân sách, câu trả lời dài bất thường có thể làm giảm chất lượng/độ ngắn gọn.
- Ba bước kiểm tra đầu tiên:
  1. Panel Tokens và Cost: token output tăng mà token input giữ nguyên → model sinh dài bất thường; input tăng → prompt/context phình.
  2. Lọc log `response_sent` có `cost_usd` cao nhất, lấy `trace_id`.
  3. Trên Langfuse, mở generation `llm-generation`: kiểm tra `usage_details`, `cost_details` và prompt version đang dùng (có vừa promote version mới không).
- Mitigation tạm thời: đặt `max_tokens` cho output, rollback label `production` về prompt version trước, hoặc chuyển feature ít quan trọng sang model rẻ hơn.
- Owner: nguyen-son-giang (on-call)
