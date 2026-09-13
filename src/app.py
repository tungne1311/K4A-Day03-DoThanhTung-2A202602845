"""
🚀 CORE AGENT APPLICATION (DAY 03: CHATBOT VS REACT AGENT)
Thực thi so sánh giữa Chatbot Baseline (Cấp 2) và ReAct Agent kết nối MCP Server (Cấp 3).

📌 NÂNG CẤP: run_react_agent() là vòng lặp ReAct ĐA BƯỚC thực thụ.
   Mỗi Observation từ MCP Server được nạp ngược vào lịch sử hội thoại, LLM tự quyết định
   gọi tiếp Tool hay dừng lại tổng hợp Final Answer (không hard-code câu trả lời bằng Python).
"""

import json
import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from mcp_server import MCPAcademicServer
from prompts import (
    CHATBOT_BASELINE_PROMPT,
    REACT_AGENT_SYSTEM_PROMPT,
    MAX_ITERATIONS
)
from providers import get_llm_provider

load_dotenv()


def load_test_cases():
    """Tải danh sách 5 test cases từ config/test_cases.json hoặc config/test_cases.example.json"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "test_cases.json")
    if not os.path.exists(config_path):
        example_path = os.path.join(base_dir, "config", "test_cases.example.json")
        if os.path.exists(example_path):
            print("⚠️ [CONFIG NOTICE]: Chưa thấy file 'config/test_cases.json'. Đang dùng mẫu 'config/test_cases.example.json'.")
            print("👉 Hãy chạy: copy config/test_cases.example.json config/test_cases.json và viết test cases theo đề tài của bạn!\n")
            config_path = example_path
        else:
            config_path = "test_cases.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_waterfall_trace(trace_data: list):
    """Ghi vết log Waterfall Trace Log ra file docs/trace_waterfall.json"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs_dir = os.path.join(base_dir, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    trace_path = os.path.join(docs_dir, "trace_waterfall.json")
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(trace_data, f, ensure_ascii=False, indent=2)
    print(f"📊 [OBSERVABILITY]: Đã lưu {len(trace_data)} sự kiện Waterfall Trace tại '{trace_path}'!")


def run_baseline_chatbot(user_query: str, provider) -> str:
    """Chạy Chatbot gốc (Cấp 2) không có công cụ gọi Tool"""
    print(f"\n💬 [CHATBOT BASELINE - Cấp 2] Câu hỏi: {user_query}")
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 Chatbot phản hồi:\n{response}")
    return response


def run_react_agent(user_query: str, provider, mcp_server: MCPAcademicServer, tc_id: str = None) -> list:
    """
    [REACT AGENT LOOP - MULTI-STEP] Vòng lặp Thought -> Action -> Observation với MCP Server.

    Khác biệt cốt lõi so với bản starter:
      - Giữ `messages` là lịch sử hội thoại đầy đủ (user / assistant tool_call / tool observation).
      - Sau mỗi Observation, ĐƯA NGƯỢC kết quả cho LLM để nó tự quyết định bước tiếp theo.
      - Final Answer do chính LLM tổng hợp từ Observation (chống bịa đặt, đúng tinh thần ReAct).

    Trả về danh sách trace log của phiên thực thi.
    """
    label = f"[{tc_id}] " if tc_id else ""
    print(f"\n🤖 [REACT AGENT - Cấp 3] {label}Câu hỏi: {user_query}")

    trace_logs = []
    tools_list = mcp_server.list_tools()
    messages = [{"role": "user", "content": user_query}]

    step = 0
    final_answer = None
    tool_call_count = 0

    while step < MAX_ITERATIONS:
        step += 1
        print(f"\n--- 🔄 Vòng lặp ReAct Loop (Step {step}/{MAX_ITERATIONS}) ---")

        # ============ THOUGHT: Hỏi LLM với toàn bộ lịch sử + Native Tool Calling Specs ============
        llm_start = time.time()
        llm_response = provider.generate_with_tools(
            messages, tools_list, system_prompt=REACT_AGENT_SYSTEM_PROMPT
        )
        llm_latency_ms = round((time.time() - llm_start) * 1000, 2)

        # Tách bạch: thời gian nằm chờ hạn mức Free Tier KHÔNG phải độ trễ thật của API
        retry_wait_ms = float(llm_response.get("retry_wait_ms") or 0.0)
        api_latency_ms = round(max(llm_latency_ms - retry_wait_ms, 0.0), 2)
        # Engine THỰC SỰ sinh ra phản hồi (có thể là Mock nếu API lỗi và phải fallback)
        served_by = llm_response.get("served_by") or provider.__class__.__name__

        thought = llm_response.get("thought", "Đang suy luận...")
        print(f"🧠 [Thought]: {thought}")

        # ---------- Trường hợp 1: LLM kết luận bằng văn bản -> Final Answer ----------
        if llm_response.get("type") == "text":
            final_answer = (llm_response.get("content") or "").strip()
            print(f"🏁 [Final Answer]: {final_answer}")
            trace_logs.append({
                "test_case_id": tc_id,
                "step": step,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "query": user_query,
                "action_type": "FINAL_ANSWER",
                "thought": thought,
                "output": final_answer,
                "latency_ms": api_latency_ms,
                "retry_wait_ms": retry_wait_ms,
                "llm_provider": served_by,
                "llm_model": getattr(provider, "model_name", "unknown")
            })
            break

        # ---------- Trường hợp 2: LLM đề xuất gọi Tool (Action) ----------
        elif llm_response.get("type") == "tool_call":
            tool_name = llm_response.get("tool_name")
            arguments = llm_response.get("arguments", {}) or {}
            tool_call_count += 1

            print(f"🛠️ [Action Proposed]: {tool_name}({json.dumps(arguments, ensure_ascii=False)})")

            # ============ OBSERVATION: Thực thi Tool qua MCP Server (JSON-RPC 2.0) ============
            mcp_start = time.time()
            mcp_result = mcp_server.call_tool(tool_name, arguments)
            mcp_latency_ms = round((time.time() - mcp_start) * 1000, 2)
            obs_data = mcp_result.get("result", {}) or {}

            print(f"👁️ [Observation từ MCP Server]: {json.dumps(obs_data, ensure_ascii=False)}")

            trace_logs.append({
                "test_case_id": tc_id,
                "step": step,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "query": user_query,
                "action_type": "TOOL_EXECUTION",
                "thought": thought,
                "tool_name": tool_name,
                "arguments": arguments,
                "observation": obs_data,
                "mcp_jsonrpc": {
                    "jsonrpc": mcp_result.get("jsonrpc"),
                    "id": mcp_result.get("id"),
                    "server": mcp_result.get("server"),
                    "isError": mcp_result.get("isError")
                },
                "latency_ms": api_latency_ms,
                "retry_wait_ms": retry_wait_ms,
                "mcp_latency_ms": mcp_latency_ms,
                "llm_provider": served_by,
                "llm_model": getattr(provider, "model_name", "unknown")
            })

            # ============ Nạp Observation ngược vào lịch sử cho vòng suy luận kế tiếp ============
            call_id = llm_response.get("tool_call_id") or f"call_{step}"
            messages.append({
                "role": "assistant",
                "content": llm_response.get("raw_text") or "",
                "tool_calls": [{"id": call_id, "name": tool_name, "arguments": arguments}],
                # Giữ nguyên payload gốc của Provider (Gemini cần thought_signature khi replay)
                "provider_raw": llm_response.get("provider_raw")
            })
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "name": tool_name,
                "content": json.dumps(obs_data, ensure_ascii=False)
            })
            # -> Quay lại đầu vòng lặp: LLM quyết định gọi tiếp Tool hay chốt Final Answer
            continue

        else:
            print("⚠️ [CHÚ Ý]: Phản hồi LLM không hợp lệ, dừng vòng lặp ReAct.")
            break

    # ---------- Chạm trần MAX_ITERATIONS mà chưa chốt được câu trả lời ----------
    if final_answer is None:
        final_answer = (f"Đã chạm giới hạn {MAX_ITERATIONS} vòng lặp ReAct mà chưa tổng hợp được "
                        f"câu trả lời cuối cùng. Vui lòng diễn đạt lại câu hỏi cụ thể hơn.")
        print(f"🏁 [Final Answer]: {final_answer}")
        trace_logs.append({
            "test_case_id": tc_id,
            "step": step + 1,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "query": user_query,
            "action_type": "MAX_ITERATIONS_REACHED",
            "thought": "Vượt quá số vòng lặp cho phép.",
            "output": final_answer,
            "latency_ms": 0.0
        })

    print(f"📈 [Tổng kết phiên]: {step} vòng lặp ReAct | {tool_call_count} lượt gọi Tool qua MCP Server.")
    return trace_logs


if __name__ == "__main__":
    print("==========================================================")
    print("🏫 VINUNI AI COURSE - DAY 03 LAB: CHATBOT VS REACT AGENT")
    print("==========================================================")

    provider = get_llm_provider()
    mcp_server = MCPAcademicServer()

    print(f"🔌 LLM Provider: {provider.__class__.__name__} (model: {getattr(provider, 'model_name', 'n/a')})")
    print(f"🌐 MCP Server: {mcp_server.server_name} (v{mcp_server.version}) | Tools: {len(mcp_server.list_tools())}")
    if provider.__class__.__name__ == "MockOfflineProvider":
        print("⚠️ [CẢNH BÁO NGHIỆM THU]: Đang chạy MOCK OFFLINE. Hãy điền GEMINI_API_KEY vào '.env' trước khi nộp bài!\n")
    else:
        print("✅ [LIVE API MODE]: Agent đang kết nối LLM API thật.\n")

    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases thử nghiệm.\n")

    if "--interactive" in sys.argv:
        print("🎮 [INTERACTIVE MODE] Trò chuyện trực tiếp với ReAct Agent:")
        print("💡 Gợi ý câu hỏi thử nghiệm:")
        print("   - Câu hỏi chung: 'Quy chế học vụ VinUni yêu cầu bao nhiêu tín chỉ?'")
        print("   - Tra cứu học vụ: 'Hãy tra cứu thông tin học vụ của sinh viên SV2026001'")
        print("   - Đặt lịch hẹn: 'Đặt lịch hẹn tư vấn cho SV2026001 vào 14:00 ngày 15/09/2026'")
        print("   - Đa bước: 'Cố vấn của SV2026002 là ai? Đặt lịch với thầy/cô đó lúc 09:00 20/09/2026'")
        print("   - Gõ 'exit' hoặc 'quit' để kết thúc phiên trò chuyện.\n")
        session_traces = []
        while True:
            try:
                user_input = input("👤 Sinh viên hỏi: ").strip()
                if not user_input or user_input.lower() in ["exit", "quit"]:
                    print("👋 Tạm biệt! Kết thúc phiên trò chuyện.")
                    break
                session_traces.extend(run_react_agent(user_input, provider, mcp_server))
                save_waterfall_trace(session_traces)
            except (KeyboardInterrupt, EOFError):
                print("\n👋 Đã thoát phiên tương tác.")
                break

    elif "--compare" in sys.argv:
        # 🎁 Chế độ bổ sung: đối chiếu trực tiếp Chatbot (Cấp 2) vs ReAct Agent (Cấp 3)
        print("⚖️ [COMPARE MODE] Đối chiếu Chatbot Baseline (Cấp 2) vs ReAct Agent (Cấp 3)")
        compare_query = "Hãy tra cứu thông tin học vụ của sinh viên SV2026001."
        for arg in sys.argv[1:]:
            if not arg.startswith("--"):
                compare_query = arg
        run_baseline_chatbot(compare_query, provider)
        print("\n" + "-" * 58)
        run_react_agent(compare_query, provider, mcp_server, tc_id="COMPARE")
        print("\n💡 Nhận xét: Chatbot Cấp 2 không truy cập được dữ liệu thời gian thực, "
              "trong khi ReAct Agent Cấp 3 gọi Tool qua MCP Server để lấy dữ liệu thật.")

    elif "--all" in sys.argv:
        print("🚀 [TEST SUITE MODE] Kiểm tra 5 Test Cases:")
        completed_count = 0
        todo_count = 0
        all_traces = []

        for tc in tests:
            print(f"\n==================================================")
            print(f"🧪 [{tc['id']}] Loại test: {tc['type']} (Độ phức tạp: {tc['complexity']})")
            print(f"📌 Kỳ vọng: {tc['expected_behavior']}")

            if tc["question"].strip().startswith("TODO"):
                print(f"⏸️ [CHƯA KÍCH HOẠT - ĐANG LÀ TODO]:")
                print(f"   {tc['question']}")
                print(f"   👉 Hãy mở file 'config/test_cases.json' để viết câu hỏi thực tế cho Test Case này!")
                todo_count += 1
            else:
                logs = run_react_agent(tc["question"], provider, mcp_server, tc_id=tc["id"])
                all_traces.extend(logs)
                completed_count += 1

        tool_calls = sum(1 for t in all_traces if t.get("action_type") == "TOOL_EXECUTION")
        print(f"\n==================================================")
        print(f"📊 [KẾT QUẢ TEST SUITE]: Đã thực thi {completed_count}/{len(tests)} Test Cases "
              f"| {todo_count} Test Cases đang chờ điền câu hỏi (TODO)")
        print(f"🛠️ [MCP TOOL CALLS]: Tổng {tool_calls} lượt gọi Tool qua MCP Server.")
        if all_traces:
            save_waterfall_trace(all_traces)
        print(f"💡 Để trò chuyện trực tiếp từng câu: Chạy 'python src/app.py --interactive'")

    else:
        # Chế độ mặc định khi chỉ gõ 'python src/app.py'
        print("ℹ️ HƯỚNG DẪN SỬ DỤNG CHƯƠNG TRÌNH:")
        print("  1. Chat trực tiếp liên tục:   python src/app.py --interactive")
        print("  2. Chạy toàn bộ Test Cases:    python src/app.py --all")
        print("  3. So sánh Chatbot vs Agent:   python src/app.py --compare\n")

        sample_query = tests[1]["question"]
        print(f"--- 🏁 DEMO CHẠY THỬ 1 TEST CASE MẪU (TC02: Tra cứu học vụ) ---")
        logs = run_react_agent(sample_query, provider, mcp_server, tc_id=tests[1]["id"])
        save_waterfall_trace(logs)
        print("\n💡 Hãy thử ngay lệnh: python src/app.py --interactive để chat trực tiếp!")
