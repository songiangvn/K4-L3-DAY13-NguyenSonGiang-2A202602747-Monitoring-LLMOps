# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Sơn Giang
- **MSSV:** 2A202602747
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/songiangvn/K4-L3-DAY13-NguyenSonGiang-2A202602747-Monitoring-LLMOps
- **Commit SHA cuối:** _(điền sau commit cuối)_
- **Challenge ID:** _(điền ở CP3)_
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602747`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.txt` |
| Log validator (baseline → sau CP1) | `evidence/00-baseline-log-validator.txt` → `evidence/02-log-validator.txt` |
| Dashboard validator | `evidence/03-dashboard-validator.txt` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05-pii-redaction.png` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png`, `evidence/09-prompt-versions.txt` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` (baseline), `evidence/11b-dashboard-practice-incidents.png` (sau practice) |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 (thiếu field, 0 correlation ID, thiếu enrichment) | 100/100 | 4/4 hạng mục đạt |
| `validate_dashboard.py` | 6/6 panel | 6/6 panel | contract không đổi |
| `pytest` | 22 passed | 30 passed | thêm test PII, generation/usage/cost, alert config, dashboard builder |
| Số traces hợp lệ | 0 (chưa có key) | 50+ trong project cá nhân | mỗi trace có root + retriever + generation |
| Số PII leak | 0 (log chỉ có preview) | 0 trong log và 0 trong Langfuse | đã quét cả input/output observations lấy qua API |
| Latency P95 / TTFT P95 | – | 437 ms / 50 ms (baseline 50 request) | P95 gồm cả lần fetch prompt Langfuse lúc cold start |
| Retrieval success rate | – | 100 % baseline; 87.5 % sau practice `tool_fail` | panel Errors |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `CorrelationIdMiddleware` gọi `clear_contextvars()` đầu mỗi request (tránh rò context giữa request), nhận `x-request-id` nếu đúng format `req-<8-hex>`, ngược lại sinh `req-` + 8 ký tự hex từ `uuid4`. ID được `bind_contextvars` nên mọi log trong request đều có `correlation_id`, được truyền vào `agent.run` → trace metadata, và trả lại qua header `x-request-id` cùng `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** `ts`, `level`, `service`, `event`, `correlation_id`, `user_id_hash` (SHA-256 cắt 12 ký tự, không log user_id thô), `session_id`, `feature`, `model`, `env`; `response_sent` thêm `latency_ms`, `ttft_ms`, `tokens_in/out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success` và `trace_id`.
- **Cách bảo đảm PII được scrub trước khi ghi:** processor `scrub_event` được đăng ký trong structlog **trước** `JsonlFileProcessor` và `JSONRenderer`, và scrub đệ quy mọi field chuỗi (kể cả dict/list lồng trong `payload`), chỉ bỏ qua các ID do hệ thống sinh (`correlation_id`, `user_id_hash`, `ts`, `level`). Pattern: email, thẻ thanh toán (chạy trước để không bị CCCD/phone ăn một phần), CCCD 12 số, điện thoại VN (`0`/`+84`, có dấu cách/chấm/gạch), hộ chiếu VN.
- **Cách kiểm chứng kết quả:** `tests/test_pii.py` (email, 5 dạng số điện thoại, CCCD, 3 dạng thẻ, hộ chiếu, câu không có PII, field lồng nhau); `validate_logs.py` báo 0 leak; log thực tế cho `sample_queries` chứa `[REDACTED_EMAIL]`, `[REDACTED_PHONE_VN]`, `[REDACTED_CREDIT_CARD]` (xem `evidence/05-pii-redaction.png`).

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** key trong `.env` thuộc project `day13-k4-l3a-2A202602747`; trace ID ghi trong `data/logs.jsonl` (`response_sent.trace_id`) được tra lại bằng Langfuse API `GET /api/public/v2/observations` và khớp với trace trong project.
- **Cấu trúc root/retrieval/generation observations:** `lab-agent-run` (type `agent`, root, metadata prompt name/label/version/source) → con `rag-retrieval` (type `retriever`, input = query preview đã scrub, output = số doc) và con `llm-generation` (type `generation`, có `model=claude-sonnet-4-5`, `usage_details` input/output/total, `cost_details` input/output/total, `completion_start_time` = TTFT, liên kết prompt Langfuse). Không capture raw input/output (`capture_input=False`), chỉ gửi preview đã scrub.
- **Cách nối trace với log:** `correlation_id` được propagate vào metadata của mọi observation trong trace; ngược lại log `response_sent` ghi `trace_id`. Từ log → mở thẳng trace; từ trace → lọc log theo `correlation_id`.
- **Prompt name:** `day13-chat`
- **Version/label baseline:** v1 — labels `baseline`, `production` (ban đầu)
- **Version/label candidate:** v2 — label `candidate` (thêm dòng "Answer in no more than three concise bullet points.")
- **Trace ID của mỗi version:**

  | Bước | Label app dùng | Prompt version trên trace | Trace ID | Correlation ID |
  |---|---|---|---|---|
  | Baseline | `baseline` | 1 | `8bd3b80d9e7f02d45e0575f3783f2c01` | `req-b0ba91a1` |
  | Candidate | `candidate` | 2 | `d7404705707574946552cd645fec2c32` | `req-03346e14` |
  | Promote | `production` → v2 | 2 | `6d2b4d26f98d45e6ecc7af41d52da051` | `req-f3462acb` |
  | Rollback | `production` → v1 | 1 | `7f3c97bea8f039c808328d1662432964` | `req-e857e019` |

- **Cách promote và rollback `production`:** không sửa source code. `scripts/prompt_versions.py promote` chuyển label `production` sang v2 (Langfuse tự gỡ label khỏi v1 vì label là duy nhất trong một prompt), restart API để xóa cache prompt trong tiến trình, chạy load test → trace ghi `prompt_label=production`, `prompt_version=2`. `scripts/prompt_versions.py rollback` đưa `production` về v1, restart, chạy lại → trace ghi version 1. Có thể làm tương đương trên UI Prompt Management.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** `scripts/build_dashboard.py` đọc chính `config/dashboard.yaml` và `data/logs.jsonl`, sinh `reports/dashboard.html` (time range 60 phút, auto-refresh 30 s) gồm đúng 6 panel: Latency P50/P95/P99 + TTFT P95; Traffic (count, request/phút); Error rate + breakdown `error_type` + retrieval success; Cost theo phút và tổng; Tokens input/output; Quality mean. Mỗi panel hiển thị đơn vị, threshold (đường đỏ nét đứt khi so được theo phút) và trạng thái ✓/✕. Kiểm chứng runtime: sau practice `rag_slow` P95 tăng 437 → 2654 ms; `tool_fail` làm error rate 12.5 % (✕ Breached) và retrieval success 87.5 %; `cost_spike` làm tokens_out/cost tăng ~4x.
- **SLO và lý do chọn:** `fast_successful_requests` — 99.5 % request (tính trên `request_received`) phải thành công và `latency_ms ≤ 3000` trong 28 ngày. Giữ 3000 ms bằng đúng threshold của panel latency để SLO line và dashboard là một con số; baseline P95 437 ms nên còn dư ~7x headroom cho LLM thật.
- **Cách tính error budget:** budget = 0.5 % tổng request trong 28 ngày, ví dụ 10 000 request → 50 request được phép chậm > 3 s hoặc lỗi. Burn rate = (bad/total trong cửa sổ) / 0.005; practice `tool_fail` (100 % lỗi) tương ứng burn rate 200x → alert P1. Khi còn < 25 % budget thì đóng băng promote prompt/model.
- **Ba alert và runbook tương ứng:** (chi tiết trong `config/alert_rules.yaml` và `docs/alerts.md`, Slack `#day13-l3a-alerts`/`#day13-l3a-cost`)
  1. `HighLatencyP95` — P2, P95 > 2000 ms trong 5m. Ngưỡng thấp hơn SLO vì practice `rag_slow` cho P95 2654 ms mà vẫn chưa vượt 3000 ms → cần cảnh báo sớm.
  2. `HighErrorRateOrRetrievalFailure` — P1, error rate > 2 % hoặc retrieval success < 90 % trong 3m.
  3. `CostPerRequestSpike` — P3, cost trung bình > 0.005 USD/request (~2.5x baseline) trong 15m hoặc dự phóng ngày > 2.5 USD.

## 7. Điều tra challenge

- **Challenge ID:**
- **Khoảng thời gian điều tra:**
- **Triệu chứng từ metrics:**
- **Log line và correlation ID liên quan:**
- **Trace ID và span gây ảnh hưởng:**
- **Root cause:**
- **Fix action:**
- **Preventive measure:**

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
- **Một lỗi/blocker đã gặp:**
- **Cách tìm nguyên nhân và xử lý:**
- **Cách hiểu luồng Metrics → Logs → Traces:**
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
- **Điều quan trọng nhất đã học:**
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
