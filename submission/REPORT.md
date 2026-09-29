# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Sơn Giang
- **MSSV:** 2A202602747
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/songiangvn/K4-L3-DAY13-NguyenSonGiang-2A202602747-Monitoring-LLMOps
- **Commit SHA cuối:** `126c522ab2bcc57ebeff47d5b2310f1b56d50984` (commit chứa toàn bộ code, tests và evidence; commit ngay sau đó chỉ điền dòng SHA này vào report)
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (cohort K4, seed 1311)
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602747`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.txt` |
| Log validator (baseline → sau CP1) | `evidence/00-baseline-log-validator.txt` → `evidence/02-log-validator.txt` |
| Dashboard validator | `evidence/03-dashboard-validator.txt` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05a.png` (email), `evidence/05b.png` (phone), `evidence/05c.png` (credit card) |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png`, `evidence/09-prompt-versions.txt` |
| Prompt rollback | `evidence/10a-production-v2.png` (promote) → `evidence/10b-rollback-v1.png` (rollback) |
| Dashboard runtime | `evidence/11-dashboard-overview.png` (baseline), `evidence/11b-dashboard-practice-incidents.png` (sau practice) |
| Incident metric | `evidence/12-incident-metric.png`, `evidence/cp3-investigation.txt` (mục 1) |
| Incident log | `evidence/13-incident-log.txt`, `evidence/cp3-investigation.txt` (mục 2) |
| Incident trace | `evidence/14-incident-trace.png`, `evidence/cp3-investigation.txt` (mục 3) |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 (thiếu field, 0 correlation ID, thiếu enrichment) | 100/100 | 4/4 hạng mục đạt |
| `validate_dashboard.py` | 6/6 panel | 6/6 panel | contract không đổi |
| `pytest` | 22 passed | 30 passed | thêm test PII, generation/usage/cost, alert config, dashboard builder |
| Số traces hợp lệ | 0 (chưa có key) | ≈ 80 trace (≈ 240 observations) trong project cá nhân | mỗi trace có root + retriever + generation |
| Số PII leak | 0 (log chỉ có preview) | 0 trong log và 0 trong Langfuse | đã quét cả input/output observations lấy qua API |
| Latency P95 / TTFT P95 | – | 437 ms / 50 ms (baseline 50 request) | P95 gồm cả lần fetch prompt Langfuse lúc cold start |
| Retrieval success rate | – | 100 % baseline; 87.5 % sau practice `tool_fail` | panel Errors |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `CorrelationIdMiddleware` gọi `clear_contextvars()` đầu mỗi request (tránh rò context giữa request), nhận `x-request-id` nếu đúng format `req-<8-hex>`, ngược lại sinh `req-` + 8 ký tự hex từ `uuid4`. ID được `bind_contextvars` nên mọi log trong request đều có `correlation_id`, được truyền vào `agent.run` → trace metadata, và trả lại qua header `x-request-id` cùng `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** `ts`, `level`, `service`, `event`, `correlation_id`, `user_id_hash` (SHA-256 cắt 12 ký tự, không log user_id thô), `session_id`, `feature`, `model`, `env`; `response_sent` thêm `latency_ms`, `ttft_ms`, `tokens_in/out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success` và `trace_id`.
- **Cách bảo đảm PII được scrub trước khi ghi:** processor `scrub_event` được đăng ký trong structlog **trước** `JsonlFileProcessor` và `JSONRenderer`, và scrub đệ quy mọi field chuỗi (kể cả dict/list lồng trong `payload`), chỉ bỏ qua các ID do hệ thống sinh (`correlation_id`, `user_id_hash`, `ts`, `level`). Pattern: email, thẻ thanh toán (chạy trước để không bị CCCD/phone ăn một phần), CCCD 12 số, điện thoại VN (`0`/`+84`, có dấu cách/chấm/gạch), hộ chiếu VN.
- **Cách kiểm chứng kết quả:** `tests/test_pii.py` (email, 5 dạng số điện thoại, CCCD, 3 dạng thẻ, hộ chiếu, câu không có PII, field lồng nhau); `validate_logs.py` báo 0 leak; log thực tế cho `sample_queries` chứa `[REDACTED_EMAIL]`, `[REDACTED_PHONE_VN]`, `[REDACTED_CREDIT_CARD]` (xem `evidence/05a.png`, `05b.png`, `05c.png`).

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

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` — cohort K4, seed 1311, `affected_feature=monitoring`, `latency_threshold_ms=2000`, 5 query chạy `--challenge --concurrency 5`.
- **Khoảng thời gian điều tra:** 2026-09-29 14:03:53 → 14:04:09 UTC (incident). Để so sánh, tôi chạy cùng 5 query **trước khi inject** lúc 14:03:46 → 14:03:49 UTC (baseline cùng workload).
- **Triệu chứng từ metrics:** (`12-incident-metric.png`, dashboard lọc `feature=monitoring`)

  | Metric | Baseline (cùng workload) | Incident |
  |---|---:|---:|
  | Latency P50 / P95 / P99 (server, `latency_ms`) | 153 / 415 / 415 ms | 2653 / 2655 / 2655 ms |
  | Request vượt ngưỡng challenge 2000 ms | 0/5 | **5/5** |
  | Latency phía client (load test) | 1.3–1.7 s | 10.6–13.3 s |
  | TTFT P95 | 50 ms | 50 ms (không đổi) |
  | Error rate / retrieval success | 0 % / 100 % | 0 % / 100 % |
  | Tokens out / cost | 635 / $0.0100 | 578 / $0.0092 (không đổi) |

  Kết luận từ metrics: chỉ latency tăng, ~+2.5 s/request, áp dụng đều cho mọi request; TTFT, lỗi, token và cost không đổi → loại trừ LLM chậm, lỗi tool và cost spike. P95 2655 ms vẫn dưới SLO 3000 ms nên panel dashboard vẫn xanh, nhưng vượt ngưỡng challenge 2000 ms và kích hoạt alert `HighLatencyP95` (> 2000 ms).
- **Log line và correlation ID liên quan:** (`13-incident-log.txt`) request chậm nhất `correlation_id=req-f8236407`, `session_id=k4-l3a-challenge-s03`:
  `{"event": "response_sent", "ts": "2026-09-29T14:04:05.701996Z", "feature": "monitoring", "latency_ms": 2655, "ttft_ms": 50, "tokens_out": 96, "cost_usd": 0.001545, "tool_name": "retrieval", "tool_success": true, "trace_id": "ed9c4c45bdd9243902de693f222c2985", ...}`
  `request_received` cùng correlation ID lúc 14:04:03.043Z. Log cho biết request thành công và TTFT bình thường nhưng tổng latency cao — chưa đủ để biết bước nào chậm, nên cần trace.
- **Trace ID và span gây ảnh hưởng:** trace `ed9c4c45bdd9243902de693f222c2985` (metadata `correlation_id=req-f8236407`, prompt v1):

  | Observation | Incident trace | Baseline trace `83efdba4902b0d8bcbb0068b22b84eea` |
  |---|---:|---:|
  | `lab-agent-run` (root) | 2.655 s | 0.416 s |
  | `rag-retrieval` (retriever) | **2.501 s** | 0.000 s |
  | `llm-generation` (generation, TTFT 0.05 s) | 0.153 s | 0.158 s |

  Trên cả 5 trace incident, `rag-retrieval` 2.501–2.502 s (baseline ≤ 0.001 s) còn `llm-generation` 0.151–0.153 s (baseline 0.152–0.158 s). Span gây ảnh hưởng: **`rag-retrieval`**, chiếm ~94 % thời gian của root.
- **Root cause:** bước retrieval (vector store / `app/mock_rag.retrieve`) bị chậm thêm cố định ~2.5 s cho mọi request trong khoảng incident — feature bị ảnh hưởng là `monitoring` (sự cố `rag_slow`). Ba lớp evidence cùng chỉ về một chỗ: metric (latency tăng, TTFT/cost/lỗi không đổi) → log (`req-f8236407` 2655 ms, TTFT 50 ms) → trace (span `rag-retrieval` 2.5 s, generation bình thường). Yếu tố khuếch đại: endpoint `async def chat` gọi `agent.run` đồng bộ nên chặn event loop; 5 request đồng thời phải xếp hàng, vì vậy client chờ 10–13 s dù mỗi request server chỉ đo ~2.65 s.
- **Fix action:**
  1. Tức thời: tắt/khắc phục nguồn chậm của retrieval (`python scripts/inject_incident.py --disable` trong lab; production: failover sang replica vector store khỏe hoặc restart index). Đã kiểm chứng: sau khi disable, `/health` báo `rag_slow: false`.
  2. Đặt timeout cho retrieval (ví dụ 500 ms, gấp nhiều lần baseline ≤ 1 ms) và fallback trả lời không có context thay vì chờ 2.5 s.
  3. Không chặn event loop: đổi `chat` thành `def` (FastAPI chạy trong threadpool) hoặc dùng `await run_in_threadpool(agent.run, ...)` để request đồng thời không cộng dồn thời gian chờ.
- **Preventive measure:**
  1. Giữ alert `HighLatencyP95` (P95 > 2000 ms trong 5m) và thêm alert riêng cho span: P95 latency của `rag-retrieval` > 500 ms, để báo trước khi người dùng cảm nhận.
  2. Log thêm `retrieval_ms` và thời gian end-to-end ở middleware (`x-response-time-ms`) vào `response_sent`, để dashboard thấy được cả thời gian xếp hàng mà `latency_ms` hiện bỏ sót.
  3. Cache kết quả retrieval cho query lặp lại và đưa load test `--concurrency 5` vào CI để phát hiện regression latency trước khi deploy.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** tách retrieval và LLM thành hai child observation riêng (`retriever` và `generation`) thay vì chỉ ghi metadata trên root, đồng thời ghi `trace_id` vào log `response_sent`. Nếu chỉ có root, trace của CP3 chỉ cho biết request mất 2.65 s mà không chỉ ra bước nào chậm; khi có child span, waterfall cho thấy ngay `rag-retrieval` 2.50 s so với `llm-generation` 0.15 s. Việc ghi `trace_id` vào log giúp đi từ log sang trace bằng một lần tra, không cần tìm theo thời gian. Quyết định thứ hai là scrub PII **đệ quy trên toàn bộ event** thay vì chỉ `payload` và `event`, vì các field lỗi như `payload.detail` hoặc list lồng nhau cũng có thể chứa dữ liệu người dùng; riêng các ID hệ thống (`correlation_id`, `user_id_hash`) được bỏ qua để không phá mối nối log ↔ trace.
- **Một lỗi/blocker đã gặp:** khi kiểm chứng trace bằng Langfuse SDK (`client.api.trace.get`), API trả `410 LEGACY_API_UNAVAILABLE_FOR_NEW_ORGANIZATION`: organization tạo sau 16/09/2026 không còn dùng được endpoint `/api/public/traces`. Ngoài ra ảnh chụp metadata trên Langfuse có dòng `scope.attributes.public_key` do SDK tự thêm.
- **Cách tìm nguyên nhân và xử lý:** đọc body lỗi, trong đó có nêu endpoint thay thế, rồi chuyển sang `GET /api/public/v2/observations` với tham số `fields=core,basic,time,io,metadata,model,usage,prompt`. Mặc định endpoint chỉ trả field tối thiểu nên lần đầu thấy `metadata`/`usage` rỗng; thêm `fields` thì mới lấy được đầy đủ. Nhờ đó tôi xác nhận cho 4 trace baseline/candidate/promote/rollback: đúng cây cha-con, đúng `promptVersion`, có usage/cost, metadata có `correlation_id`, và quét toàn bộ input/output không thấy PII mẫu. Với public key trong ảnh, tôi che dòng đó trước khi commit evidence.
- **Cách hiểu luồng Metrics → Logs → Traces:** metrics trả lời *có vấn đề gì và từ khi nào*: ở CP3, P95 tăng từ 415 lên 2655 ms, 5/5 request vượt 2000 ms, trong khi TTFT, lỗi và cost không đổi, nên loại được LLM, tool lỗi và cost spike. Logs trả lời *request nào bị ảnh hưởng*: lọc `response_sent` trong khoảng 14:03:53–14:04:09 ra `req-f8236407`, 2655 ms, TTFT 50 ms, kèm `trace_id`. Traces trả lời *bước nào là nguyên nhân*: span `rag-retrieval` 2.50 s. Chỉ kết luận root cause khi cả ba lớp cùng chỉ về một chỗ; so với baseline chạy cùng workload để chắc thay đổi là do incident chứ không phải do input.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** prompt là "code" của LLM nhưng thay đổi được mà không cần deploy, nên mỗi trace phải ghi prompt name/label/version để biết câu trả lời xấu đến từ version nào. Label `production` là con trỏ, nên promote và rollback chỉ là chuyển label, không sửa code và có hiệu lực sau khi hết cache. Token và cost là chỉ số riêng của LLM: một prompt dài dòng hơn có thể không làm tăng latency nhưng làm tăng hóa đơn (practice `cost_spike`: token output tăng khoảng 4x), vì vậy có alert `CostPerRequestSpike`. SLO và error budget biến "hệ thống có ổn không" thành con số để ra quyết định: còn budget thì được promote prompt mới, sắp hết thì dừng lại và rollback.
- **Điều quan trọng nhất đã học:** metric ở phía server có thể che mất trải nghiệm thật của người dùng. Ở CP3, `latency_ms` chỉ 2.65 s (dưới SLO 3 s, dashboard vẫn xanh) nhưng client chờ 10–13 s, vì `async def chat` gọi code đồng bộ làm chặn event loop và các request phải xếp hàng. Vì vậy cần đặt ngưỡng alert sớm hơn SLO, và đo cả latency end-to-end ở middleware chứ không chỉ trong agent.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** dashboard là trang HTML tĩnh sinh từ `data/logs.jsonl` (tự refresh 30 s nhưng phải chạy lại script để có dữ liệu mới), chưa phải Grafana/Langfuse dashboard trực tiếp. Alert mới được định nghĩa trong YAML và runbook, chưa nối với Slack thật. Các fix nêu ở mục 7 (timeout retrieval, không chặn event loop, log `retrieval_ms`) mới là đề xuất; tôi chưa sửa code app để không làm thay đổi hành vi của challenge chính thức. `quality_score` chỉ là heuristic, không phải đánh giá chất lượng thật.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
