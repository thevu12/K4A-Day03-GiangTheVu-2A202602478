"""
🚀 CORE AGENT APPLICATION (DAY 03: CHATBOT VS REACT AGENT)
Thực thi so sánh giữa Chatbot Baseline (Cấp 2) và ReAct Agent kết nối MCP Server (Cấp 3).
"""

import json
import os
import sys
import time
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

load_dotenv(override=True)

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


def run_baseline_chatbot(user_query: str, provider):
    """Chạy Chatbot gốc (Cấp 2) không có công cụ gọi Tool"""
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 Chatbot phản hồi:\n{response}")


def _call_signature(tool_name: str, arguments: dict) -> str:
    return f"{tool_name}|{json.dumps(arguments or {}, sort_keys=True, ensure_ascii=False)}"


def _build_react_followup_prompt(user_query: str, react_history: list) -> str:
    """Nạp Observation các bước trước vào prompt cho lượt ReAct kế tiếp."""
    lines = [
        f"Câu hỏi gốc của sinh viên: {user_query}",
        "",
        "Lịch sử vòng lặp ReAct (Thought -> Action -> Observation) đến hiện tại:",
    ]
    for item in react_history:
        lines.append(f"[ReAct Step {item['step']}]")
        lines.append(f"Thought: {item['thought']}")
        lines.append(f"Action: {item['tool_name']}({json.dumps(item['arguments'], ensure_ascii=False)})")
        lines.append(f"Observation: {json.dumps(item['observation'], ensure_ascii=False)}")
        lines.append("")
    lines.append(
        "Hãy tiếp tục vòng lặp ReAct cho câu hỏi gốc.\n"
        "- Nếu còn thiếu dữ liệu thời gian thực, gọi đúng tool với tham số chính xác (lấy cố vấn/mã SV từ Observation nếu có).\n"
        "- Nếu đã đủ dữ liệu, trả lời cuối cùng bằng văn bản, chỉ dùng Observation, không bịa.\n"
        "- Không gọi lại cùng một tool với cùng tham số."
    )
    return "\n".join(lines)


def _fallback_final_answer(react_history: list) -> str:
    """Khi hết MAX_ITERATIONS mà LLM chưa chốt câu trả lời."""
    if not react_history:
        return "Chưa thể hoàn tất suy luận ReAct trong số bước cho phép."
    last_obs = react_history[-1].get("observation") or {}
    if last_obs.get("status") == "NOT_FOUND":
        return last_obs.get("message", "Không tìm thấy thông tin sinh viên yêu cầu.")
    if last_obs.get("status") == "SUCCESS" and last_obs.get("message"):
        return last_obs["message"]
    if last_obs.get("status") == "SUCCESS" and "data" in last_obs:
        d = last_obs["data"] or {}
        return (
            f"Kết quả tra cứu cho sinh viên {last_obs.get('student_id', '')} ({d.get('full_name', '')}): "
            f"Lớp {d.get('class', '')}, GPA: {d.get('gpa', '')}, Email: {d.get('email', '')}, "
            f"Trạng thái: {d.get('status', '')}, Cố vấn: {d.get('advisor', '')}."
        )
    return f"Đã đạt giới hạn số bước ReAct. Observation gần nhất: {json.dumps(last_obs, ensure_ascii=False)}"


def run_react_agent(user_query: str, provider, mcp_server: MCPAcademicServer) -> list:
    """
    [TASK 2.2] ReAct Loop: Thought -> Action -> Observation -> (lặp lại) -> Final Answer.
    Observation từ MCP được nạp vào lượt LLM kế tiếp, không chốt câu trả lời ngay sau 1 tool.
    """
    print(f"\n🤖 [REACT AGENT] Câu hỏi: {user_query}")

    step = 0
    trace_logs = []
    react_history = []
    executed_calls = set()
    tools_list = mcp_server.list_tools()

    while step < MAX_ITERATIONS:
        step += 1
        step_start_time = time.time()
        print(f"\n--- 🔄 Vòng lặp ReAct Loop (Step {step}/{MAX_ITERATIONS}) ---")

        prompt = (
            _build_react_followup_prompt(user_query, react_history)
            if react_history
            else user_query
        )
        llm_response = provider.generate_with_tools(
            prompt, tools_list, system_prompt=REACT_AGENT_SYSTEM_PROMPT
        )
        latency_ms = round((time.time() - step_start_time) * 1000, 2)

        thought = llm_response.get("thought", "Đang suy luận...")
        print(f"🧠 [Thought]: {thought}")

        # Trường hợp 1: LLM trả lời bằng văn bản — kết thúc vòng lặp
        if llm_response.get("type") == "text":
            final_content = llm_response.get("content", "")
            print(f"🏁 [Final Answer]: {final_content}")
            trace_logs.append({
                "step": step,
                "query": user_query,
                "action_type": "FINAL_ANSWER",
                "thought": thought,
                "output": final_content,
                "latency_ms": latency_ms
            })
            break

        # Trường hợp 2: LLM đề xuất gọi Tool — thực thi MCP rồi nạp Observation cho lượt sau
        if llm_response.get("type") == "tool_call":
            tool_name = llm_response.get("tool_name") or ""
            arguments = llm_response.get("arguments") or {}
            print(f"🛠️ [Action Proposed]: {tool_name}({arguments})")

            signature = _call_signature(tool_name, arguments)
            if signature in executed_calls:
                print("⚠️ [ReAct]: Tool đã gọi với cùng tham số — dừng lặp để tránh vòng vô hạn.")
                react_history.append({
                    "step": step,
                    "thought": thought,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "observation": {
                        "status": "DUPLICATE_CALL",
                        "error": "Tool đã được gọi với cùng tham số trong phiên này."
                    },
                })
                final_content = _fallback_final_answer(react_history)
                print(f"🏁 [Final Answer]: {final_content}")
                trace_logs.append({
                    "step": step,
                    "query": user_query,
                    "action_type": "FINAL_ANSWER",
                    "thought": "Phát hiện tool call trùng, tổng hợp từ Observation đã có.",
                    "output": final_content,
                    "latency_ms": latency_ms
                })
                break

            executed_calls.add(signature)
            mcp_result = mcp_server.call_tool(tool_name, arguments)
            obs_data = mcp_result.get("result") or {}

            if not obs_data:
                print("👁️ [Observation từ MCP Server]: {}")
                print("⚠️ [CHÚ Ý]: MCP Server trả về kết quả rỗng! Kiểm tra TODO 2.1 trong 'src/mcp_server.py'.")
                obs_data = {
                    "status": "EMPTY_MCP_RESULT",
                    "error": "MCP Server trả về result rỗng."
                }
            else:
                print(f"👁️ [Observation từ MCP Server]: {json.dumps(obs_data, ensure_ascii=False)}")

            react_history.append({
                "step": step,
                "thought": thought,
                "tool_name": tool_name,
                "arguments": arguments,
                "observation": obs_data,
            })
            trace_logs.append({
                "step": step,
                "query": user_query,
                "action_type": "TOOL_EXECUTION",
                "thought": thought,
                "tool_name": tool_name,
                "arguments": arguments,
                "observation": obs_data,
                "latency_ms": latency_ms
            })
            continue

        print(f"⚠️ [ReAct]: Phản hồi LLM không hợp lệ: {llm_response}")
        break

    has_final = any(item.get("action_type") == "FINAL_ANSWER" for item in trace_logs)
    if not has_final:
        final_content = _fallback_final_answer(react_history)
        print(f"🏁 [Final Answer]: {final_content}")
        trace_logs.append({
            "step": step + 1,
            "query": user_query,
            "action_type": "FINAL_ANSWER",
            "thought": "Hết số bước ReAct cho phép, tổng hợp từ Observation đã thu thập.",
            "output": final_content,
            "latency_ms": 10.0
        })

    return trace_logs


if __name__ == "__main__":
    print("==========================================================")
    print("🏫 VINUNI AI COURSE - DAY 03 LAB: CHATBOT VS REACT AGENT")
    print("==========================================================")
    
    provider = get_llm_provider()
    mcp_server = MCPAcademicServer()
    
    print(f"🔌 LLM Provider: {provider.__class__.__name__}")
    print(f"🌐 MCP Server: {mcp_server.server_name}\n")
    
    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases thử nghiệm.\n")
    
    if "--interactive" in sys.argv:
        print("🎮 [INTERACTIVE MODE] Trò chuyện trực tiếp với ReAct Agent:")
        print("💡 Gợi ý câu hỏi thử nghiệm:")
        print("   - Câu hỏi chung: 'Quy chế học vụ VinUni yêu cầu bao nhiêu tín chỉ?'")
        print("   - Tra cứu học vụ: 'Hãy tra cứu thông tin học vụ của sinh viên SV2026001'")
        print("   - Đặt lịch hẹn: 'Đặt lịch hẹn tư vấn cho SV2026001 vào 14:00 ngày 15/09/2026'")
        print("   - Gõ 'exit' hoặc 'quit' để kết thúc phiên trò chuyện.\n")
        while True:
            try:
                user_input = input("👤 Sinh viên hỏi: ").strip()
                if not user_input or user_input.lower() in ["exit", "quit"]:
                    print("👋 Tạm biệt! Kết thúc phiên trò chuyện.")
                    break
                logs = run_react_agent(user_input, provider, mcp_server)
                save_waterfall_trace(logs)
            except (KeyboardInterrupt, EOFError):
                print("\n👋 Đã thoát phiên tương tác.")
                break
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
                logs = run_react_agent(tc["question"], provider, mcp_server)
                all_traces.extend(logs)
                completed_count += 1
                
        print(f"\n==================================================")
        print(f"📊 [KẾT QUẢ TEST SUITE]: Đã thực thi {completed_count}/{len(tests)} Test Cases | {todo_count} Test Cases đang chờ điền câu hỏi (TODO)")
        if all_traces:
            save_waterfall_trace(all_traces)
        print(f"💡 Để trò chuyện trực tiếp từng câu: Chạy 'python src/app.py --interactive'")
    else:
        # Chế độ mặc định khi chỉ gõ 'python src/app.py'
        print("ℹ️ HƯỚNG DẪN SỬ DỤNG CHƯƠNG TRÌNH:")
        print("  1. Chat trực tiếp liên tục:   python src/app.py --interactive")
        print("  2. Chạy toàn bộ Test Cases:    python src/app.py --all\n")
        
        sample_query = tests[1]["question"]
        print(f"--- 🏁 DEMO CHẠY THỬ 1 TEST CASE MẪU (TC02: Tra cứu học vụ) ---")
        logs = run_react_agent(sample_query, provider, mcp_server)
        save_waterfall_trace(logs)
        print("\n💡 Hãy thử ngay lệnh: python src/app.py --interactive để chat trực tiếp!")
