# 📊 BÁO CÁO THU HOẠCH NGHIỆM THU BÀI LAB 3 (BƯỚC 3 — SUBMISSION ARTIFACT)

> **Họ và Tên Học viên:** Đỗ Thanh Tùng
> **Mã Sinh Viên / Mã Học viên:** 2A202602845
> **Chủ đề Lựa chọn:** Gợi ý 1.1 — *Trợ lý Học vụ & Tra cứu Lịch thi VinUni* (Tra cứu hồ sơ học vụ + Đặt lịch hẹn tư vấn với Cố vấn học tập)
> **LLM Provider nghiệm thu:** ✅ **Google Gemini API THẬT** — `GeminiProvider` / model `gemini-flash-lite-latest`, Native Function Calling
> **MCP Server:** `vinuni-academic-mcp-server` v2026.1.0 — công bố 2 Tools qua JSON-RPC 2.0
> **Thời điểm nghiệm thu:** 13/09/2026 — 11 sự kiện trace, **0 sự kiện fallback về Mock**

---

## 1. BẢNG CHẤM ĐIỂM AGENTIC FIT SCORING MATRIX (ĐÁNH GIÁ CHỦ ĐỀ)

| Tiêu chí Đánh giá | Mức độ (1 - 5) | Giải trình chi tiết lý do chọn điểm |
| :--- | :---: | :--- |
| **1. Multi-step Reasoning** | **4** / 5 | Yêu cầu "đặt lịch với cố vấn của sinh viên X" **không thể giải trong một bước**: Agent buộc phải (1) tra cứu hồ sơ để lấy trường `advisor`, rồi (2) mới gọi được `schedule_appointment`. Đã kiểm chứng thực tế ở TC04 trên Gemini API: 2 lượt gọi Tool nối tiếp, 3 vòng lặp ReAct. Chưa đạt 5/5 vì chuỗi dừng ở 2–3 bước, chưa tới mức phân rã kế hoạch nhiều nhánh. |
| **2. Tool Interaction** | **5** / 5 | Bài toán bắt buộc truy vấn dữ liệu **thời gian thực** (GPA, trạng thái học vụ, tên cố vấn) và thực hiện **hành động ghi** (tạo booking). LLM thuần không thể sinh các dữ liệu này mà không bịa đặt. Hệ thống kết nối 2 Tools (`academic_query` tra cứu + `schedule_appointment` hành động) phục vụ độc lập qua MCP Server chuẩn JSON-RPC 2.0. Thực tế ghi nhận **6 lượt gọi Tool** qua MCP trong 5 test case. |
| **3. Dynamic Decision** | **5** / 5 | Bước kế tiếp **phụ thuộc hoàn toàn** vào Observation của bước trước. Bằng chứng đối lập rõ rệt: TC05 nhận `status: NOT_FOUND` → Agent lập tức **dừng chuỗi**, không gọi `schedule_appointment`. TC04 nhận `status: SUCCESS` → Agent trích `advisor` từ Observation và đi tiếp bước 2. Cùng một System Prompt nhưng hai nhánh hành vi khác nhau, do dữ liệu quan sát quyết định. |
| **4. Long Horizon Goal** | **3** / 5 | Agent giữ được mục tiêu "đặt lịch cho đúng cố vấn" xuyên suốt nhiều vòng lặp nhờ cơ chế `messages` history (mục tiêu gốc luôn nằm ở message đầu tiên). Tuy nhiên phạm vi bài Lab giới hạn ở hội thoại ngắn (`MAX_ITERATIONS = 5`), **chưa có Long-term Memory** lưu trạng thái xuyên phiên — đặc trưng của Cấp 4 (Autonomous Agent). |
| **TỔNG ĐIỂM AGENTIC FIT** | **17 / 20** | ✅ **17/20 > 12/20 → Bài toán RẤT PHÙ HỢP triển khai Agentic System (ReAct Agent Cấp 3).** Điểm cao đến từ Tool Interaction và Dynamic Decision — hai yếu tố mà Chatbot Cấp 2 hoàn toàn không đáp ứng được. |

### 🔍 Đối chiếu thực nghiệm: Chatbot (Cấp 2) vs ReAct Agent (Cấp 3)

Chạy `python src/app.py --compare` cho cùng câu hỏi *"Hãy tra cứu thông tin học vụ của sinh viên SV2026001."*:

| | **Chatbot Baseline (Cấp 2)** | **ReAct Agent + MCP (Cấp 3)** |
| :--- | :--- | :--- |
| Cơ chế | Sinh văn bản 1 lượt từ System Prompt | Vòng lặp `Thought → Action → Observation → Final Answer` |
| Truy cập dữ liệu thật | ❌ Không | ✅ Qua MCP Server (JSON-RPC 2.0) |
| Kết quả | Từ chối: *"không có quyền truy cập dữ liệu thời gian thực"* | Trả đúng GPA 3.85, lớp AI-K4, cố vấn PGS.TS Nguyễn Văn A |
| Rủi ro Hallucination | Cao (nếu bị ép trả lời sẽ bịa số liệu) | Thấp — mọi con số đều truy vết được về `observation` trong trace log |

---

## 2. TRÍCH XUẤT KẾT QUẢ WATERFALL TRACE LOG (SAU KHI CHẠY TEST SUITE TRÊN API THẬT)

> ✅ **ĐÃ NGHIỆM THU TRÊN LLM API THẬT.** Toàn bộ 11 sự kiện trong `docs/trace_waterfall.json` đều mang `"llm_provider": "GeminiProvider"` và `"retry_wait_ms": 0.0` — **không có sự kiện nào rơi về Mock Offline**.

### 🎯 Trích đoạn tiêu biểu — TC04 (Multi-step Reasoning): chuỗi ReAct 2 lượt gọi Tool nối tiếp

Đây là bằng chứng cốt lõi cho vòng lặp ReAct đa bước: **Observation của Step 1 (`advisor: "TS. Lê Thị B"`) trở thành đối số đầu vào của Action ở Step 2** — điều mà Chatbot một lượt không thể làm được. Lưu ý trường `mcp_jsonrpc.id` tăng dần (4 → 5), chứng minh hai request độc lập được MCP Server xử lý tuần tự.

```json
[
  {
    "test_case_id": "TC04",
    "step": 1,
    "timestamp": "2026-09-13T09:59:22",
    "action_type": "TOOL_EXECUTION",
    "thought": "Cần dữ liệu thời gian thực nên tôi gọi công cụ 'academic_query' với tham số: {\"student_id\": \"SV2026002\"}.",
    "tool_name": "academic_query",
    "arguments": { "student_id": "SV2026002" },
    "observation": {
      "status": "SUCCESS",
      "student_id": "SV2026002",
      "data": {
        "full_name": "Trần Thị Bình",
        "class": "AI-K4",
        "gpa": 3.6,
        "email": "binh.tt@vinuni.edu.vn",
        "status": "Đang học",
        "advisor": "TS. Lê Thị B"
      }
    },
    "mcp_jsonrpc": { "jsonrpc": "2.0", "id": 4, "server": "vinuni-academic-mcp-server", "isError": false },
    "latency_ms": 921.66,
    "mcp_latency_ms": 0.0,
    "llm_provider": "GeminiProvider",
    "llm_model": "gemini-flash-lite-latest"
  },
  {
    "test_case_id": "TC04",
    "step": 2,
    "timestamp": "2026-09-13T09:59:23",
    "action_type": "TOOL_EXECUTION",
    "thought": "Cần dữ liệu thời gian thực nên tôi gọi công cụ 'schedule_appointment' với tham số: {\"advisor_name\": \"TS. Lê Thị B\", \"datetime_str\": \"09:30 20/09/2026\", \"student_id\": \"SV2026002\"}.",
    "tool_name": "schedule_appointment",
    "arguments": {
      "advisor_name": "TS. Lê Thị B",
      "datetime_str": "09:30 20/09/2026",
      "student_id": "SV2026002"
    },
    "observation": {
      "status": "SUCCESS",
      "booking_id": "BK-SV2026002-99",
      "student_id": "SV2026002",
      "datetime": "09:30 20/09/2026",
      "advisor": "TS. Lê Thị B",
      "message": "Đặt lịch thành công cho sinh viên SV2026002 với TS. Lê Thị B vào lúc 09:30 20/09/2026."
    },
    "mcp_jsonrpc": { "jsonrpc": "2.0", "id": 5, "server": "vinuni-academic-mcp-server", "isError": false },
    "latency_ms": 999.7,
    "mcp_latency_ms": 0.0,
    "llm_provider": "GeminiProvider",
    "llm_model": "gemini-flash-lite-latest"
  },
  {
    "test_case_id": "TC04",
    "step": 3,
    "timestamp": "2026-09-13T09:59:24",
    "action_type": "FINAL_ANSWER",
    "thought": "Đã có đủ thông tin, tổng hợp câu trả lời cuối cùng (không cần gọi thêm công cụ).",
    "output": "Tôi đã tra cứu hồ sơ học tập của sinh viên Trần Thị Bình (Mã SV: SV2026002) và xác định cố vấn học tập của bạn ấy là **TS. Lê Thị B**.\n\nLịch hẹn tư vấn học vụ đã được đặt thành công:\n* **Mã sinh viên:** SV2026002 (Trần Thị Bình)\n* **Cố vấn học tập:** TS. Lê Thị B\n* **Thời gian:** 09:30 ngày 20/09/2026\n* **Mã đặt lịch:** BK-SV2026002-99",
    "latency_ms": 1332.96,
    "llm_provider": "GeminiProvider",
    "llm_model": "gemini-flash-lite-latest"
  }
]
```

📌 **Phân tích Waterfall:** tổng thời gian xử lý TC04 ≈ **3.25 giây** (921 + 999 + 1332 ms độ trễ LLM), trong khi `mcp_latency_ms ≈ 0.0 ms` ở cả hai lượt. Nút cổ chai nằm **hoàn toàn ở phía LLM inference**, không phải ở tầng Tool Execution — đây là thông tin quan trọng khi tối ưu chi phí/độ trễ hệ thống Agentic thực tế (giảm số vòng lặp có giá trị hơn nhiều so với tối ưu tốc độ Tool).

### 🛡️ Trích đoạn Anti-Hallucination — TC05 (Edge Case `NOT_FOUND`)

```json
[
  {
    "test_case_id": "TC05",
    "step": 1,
    "action_type": "TOOL_EXECUTION",
    "tool_name": "academic_query",
    "arguments": { "student_id": "SV9999999" },
    "observation": {
      "status": "NOT_FOUND",
      "message": "Không tìm thấy dữ liệu sinh viên có mã 'SV9999999'"
    },
    "mcp_jsonrpc": { "jsonrpc": "2.0", "id": 6, "server": "vinuni-academic-mcp-server", "isError": false },
    "latency_ms": 944.32
  },
  {
    "test_case_id": "TC05",
    "step": 2,
    "action_type": "FINAL_ANSWER",
    "output": "Không tìm thấy dữ liệu sinh viên có mã số **SV9999999** trong cơ sở dữ liệu của VinUni. Vui lòng kiểm tra lại mã sinh viên của bạn.",
    "latency_ms": 1027.8,
    "llm_provider": "GeminiProvider"
  }
]
```

✅ **Nhận xét:** Agent **không bịa** GPA hay tên sinh viên cho mã không tồn tại, và **không gọi tiếp** `schedule_appointment` — đúng nguyên tắc số 5 trong `REACT_AGENT_SYSTEM_PROMPT` (Anti-Hallucination).

---

## 3. TỔNG KẾT KẾT QUẢ NGHIỆM THU & NỘP BÀI

### 3.1. Bảng kết quả 5 Test Cases (chạy thật trên Gemini API — 13/09/2026)

| ID | Loại test | Độ phức tạp | Vòng ReAct | Tool Calls | Kết quả |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **TC01** | `direct_query` | Low | 1 | 0 | ✅ PASS — trả lời trực tiếp từ System Prompt, **không gọi Tool** (đúng kỳ vọng) |
| **TC02** | `single_tool_query` | Medium | 2 | 1 — `academic_query` | ✅ PASS |
| **TC03** | `appointment_booking` | Medium | 3 | 2 — `academic_query` → `schedule_appointment` | ✅ PASS (kèm ghi chú ⚠️ bên dưới) |
| **TC04** | `multi_step_reasoning` | **High** | **3** | **2** — `academic_query` → `schedule_appointment` | ✅ PASS — chuỗi ReAct đa bước đúng như thiết kế |
| **TC05** | `edge_case_handling` | Medium | 2 | 1 — `academic_query` → `NOT_FOUND` | ✅ PASS — không hallucinate |

> ⚠️ **Ghi chú trung thực về TC03:** kỳ vọng ban đầu là Agent gọi thẳng `schedule_appointment` (1 Tool) vì câu hỏi đã cho sẵn tên cố vấn. Thực tế Gemini **chủ động gọi `academic_query` trước để xác minh** rồi mới đặt lịch. Nguyên nhân: phần `description` của Tool `schedule_appointment` nhấn mạnh *"BẮT BUỘC phải biết ĐÚNG tên Cố vấn học tập của sinh viên"*, khiến mô hình chọn phương án thận trọng là kiểm chứng lại dữ liệu người dùng cung cấp. Đây là **hành vi an toàn hơn kỳ vọng** (chống việc người dùng nhập sai tên cố vấn), vẫn gọi đúng `schedule_appointment` với đủ 3 tham số bắt buộc, nên được tính PASS. Bài học rút ra: **câu chữ trong Tool description tác động trực tiếp tới hành vi lập kế hoạch của Agent** — đây là một dạng prompt engineering ở tầng công cụ.

### 3.2. Checklist nghiệm thu

- [x] Đã điền API Key thật trong `.env` và xác nhận Agent chạy mượt trên **LLM API thật** (Google Gemini, `gemini-flash-lite-latest`).
- [x] Đã hoàn thành **TODO 1.2** — Tool Schema `schedule_appointment` chuẩn JSON Schema với 3 tham số bắt buộc (`src/tools.py`).
- [x] Đã hoàn thành **TODO 2.1** — hàm `call_tool()` đóng gói phản hồi chuẩn **JSON-RPC 2.0** kèm xử lý lỗi `-32601 Method not found` (`src/mcp_server.py`).
- [x] Đã hoàn thiện đủ 5 Test Cases trong `config/test_cases.json` (không còn dòng `TODO`).
- [x] Đã nâng cấp `run_react_agent()` thành vòng lặp ReAct **đa bước thực thụ**: Observation nạp ngược vào lịch sử hội thoại, Final Answer do chính LLM tổng hợp.
- [x] Đã thử nghiệm thành công chế độ đàm thoại trực tiếp `python src/app.py --interactive`.
- [x] File `docs/trace_waterfall.json` sinh ra với **11 sự kiện, 100% từ LLM API thật**.
- **Tổng số Test Cases đã chạy thành công:** **5** / 5 test cases.
- **Số lượt gọi Tool qua MCP Server chính xác:** **6** lượt (TC02: 1, TC03: 2, TC04: 2, TC05: 1).
- **Kết quả đẩy Repo nộp bài:** [ ] Đã Commit và Push mã nguồn thành công lên GitHub cá nhân.

### 3.3. Hai sự cố kỹ thuật thực tế đã gặp & cách khắc phục

Phần này ghi lại hai lỗi **chỉ xuất hiện khi chạy trên API thật** (không thể phát hiện ở chế độ Mock):

**Sự cố 1 — `400 INVALID_ARGUMENT: Function call is missing a thought_signature`**

Khi nạp Observation ngược vào lịch sử ở vòng lặp thứ 2, code ban đầu **dựng lại** `Part.from_function_call(name, args)` từ tên và tham số. Nhưng Gemini 3.x gắn kèm mỗi `functionCall` một trường `thought_signature` (chữ ký chuỗi suy luận); dựng lại thủ công làm mất chữ ký này và API từ chối request.

→ **Khắc phục:** giữ nguyên vẹn đối tượng `Content` gốc do model sinh ra (`response.candidates[0].content`) và gửi lại đúng object đó ở vòng sau, thay vì tái tạo. Xem `provider_raw` trong `src/providers.py`.

**Sự cố 2 — `429 RESOURCE_EXHAUSTED` (Free Tier giới hạn 5 request/phút)**

Test Suite cần ~11 request LLM nên chạm trần hạn mức, khiến các bước sau **âm thầm rơi về Mock Offline** — làm hỏng giá trị nghiệm thu của trace log.

→ **Khắc phục kép:**
1. Thêm hàm `call_with_retry()` tự đọc `retryDelay` do API gợi ý và thử lại (tối đa 4 lần), đồng thời **tách `retry_wait_ms` ra khỏi `latency_ms`** để thời gian nằm chờ hạn mức không làm méo số liệu độ trễ trong Waterfall Log.
2. Thêm trường `served_by` để mỗi bước **khai báo trung thực engine đã thực sự sinh ra phản hồi**. Nếu một bước phải fallback, trace sẽ ghi rõ `"MockOfflineProvider (FALLBACK)"` thay vì khai khống là API thật. Trong lần nghiệm thu cuối, số bước fallback = **0**.

### 3.4. Điểm nâng cấp so với mã nguồn Starter

| # | Hạng mục | Bản Starter | Bản nộp bài |
| :---: | :--- | :--- | :--- |
| 1 | Vòng lặp ReAct | `break` ngay sau **1** lượt gọi Tool | Lặp tới `MAX_ITERATIONS`, chain được **nhiều** Tool nối tiếp |
| 2 | Final Answer | Hard-code bằng f-string Python | Do **chính LLM** tổng hợp từ Observation |
| 3 | Ngữ cảnh hội thoại | Chỉ gửi lại `user_query` mỗi vòng | Gửi đầy đủ `messages` history (user / assistant tool_call / tool response) |
| 4 | MCP Response | `return {}` | JSON-RPC 2.0 đầy đủ: `jsonrpc`, `id`, `server`, `tool`, `arguments`, `isError`, `result` |
| 5 | Xử lý lỗi Tool | Không có | Trả mã lỗi chuẩn `-32601 Method not found` cho Tool không tồn tại |
| 6 | Độ bền API | Lỗi là fallback ngay về Mock | Tự retry theo `retryDelay`, chỉ fallback khi đã cạn lượt thử |
| 7 | Trace Log | 6 trường | Thêm `test_case_id`, `timestamp`, `mcp_jsonrpc`, `mcp_latency_ms`, `retry_wait_ms`, `llm_provider` (trung thực), `llm_model` |
| 8 | Chế độ chạy | `--all`, `--interactive` | Thêm `--compare` đối chiếu trực tiếp Chatbot Cấp 2 vs ReAct Agent Cấp 3 |

---

> ✅ **HOÀN TẤT NỘP BÀI:** Sao chép đường link GitHub Repository cá nhân của bạn và dán vào ô nộp bài trên hệ thống LMS VLearn để hoàn tất Bài Lab 3!
