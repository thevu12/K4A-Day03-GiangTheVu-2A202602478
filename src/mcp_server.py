"""
🔌 MODEL CONTEXT PROTOCOL (MCP) SERVER MODULE
Mô phỏng kiến trúc MCP Server (Client-Server Architecture) cung cấp công cụ chuẩn hóa.
"""

import json
import sys
from typing import Any, Dict, List, Optional, Tuple
from tools import TOOLS_SCHEMA, dispatch_tool_call

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

class MCPAcademicServer:
    """
    Giả lập MCP Server tuân thủ chuẩn giao thức Model Context Protocol
    """
    def __init__(self, server_name: str = "vinuni-academic-mcp-server"):
        self.server_name = server_name
        self.version = "2026.1.0"
        
    def list_tools(self) -> List[Dict[str, Any]]:
        """Trả về danh sách các Tools chuẩn giao thức MCP"""
        return TOOLS_SCHEMA
        
    def _build_rpc_response(self, tool_name: str, result: Dict[str, Any], request_id: int = 1) -> Dict[str, Any]:
        """Đóng gói envelope JSON-RPC 2.0. Luôn có result (dict) để Agent đọc Observation."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "server": self.server_name,
            "tool": tool_name,
            "result": result,
        }

    def _schema_for(self, tool_name: str) -> Optional[Dict[str, Any]]:
        return next((tool for tool in TOOLS_SCHEMA if tool.get("name") == tool_name), None)

    def _normalize_arguments(self, arguments: Any) -> Dict[str, Any]:
        """LLM đôi khi gửi arguments là None, JSON string, hoặc kiểu lạ — chuẩn hóa về dict."""
        if arguments is None:
            return {}
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _prepare_arguments(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Lọc đúng property trong schema, kiểm tra required. Trả (args, error_result)."""
        schema = self._schema_for(tool_name)
        if not schema:
            return arguments, None

        parameters = schema.get("parameters") or {}
        properties = parameters.get("properties") or {}
        required = parameters.get("required") or []

        clean_args = (
            {key: value for key, value in arguments.items() if key in properties}
            if properties
            else dict(arguments)
        )

        missing = [
            field
            for field in required
            if field not in clean_args or clean_args[field] in (None, "")
        ]
        if missing:
            return None, {
                "status": "INVALID_PARAMS",
                "error": f"Thiếu tham số bắt buộc: {', '.join(missing)}",
                "missing": missing,
            }
        return clean_args, None

    def _parse_tool_payload(self, raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            return {"status": "SUCCESS", "data": raw}

        try:
            content = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {
                "status": "PARSE_ERROR",
                "error": f"Không parse được JSON từ Tool Router: {exc}",
                "raw": raw,
            }

        if isinstance(content, dict):
            return content
        return {"status": "SUCCESS", "data": content}

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        [TASK 2.1] Thực thi tool trên MCP Server theo JSON-RPC 2.0.
        1. Gọi dispatch_tool_call(tool_name, arguments) lấy chuỗi JSON từ Tool Router.
        2. json.loads chuỗi kết quả thành dict.
        3. Trả envelope: jsonrpc, server, tool, result.
        """
        name = (tool_name or "").strip() if isinstance(tool_name, str) else ""
        if not name:
            return self._build_rpc_response(
                "",
                {"status": "INVALID_REQUEST", "error": "Thiếu tên tool (tool_name)."},
            )

        args = self._normalize_arguments(arguments)
        clean_args, param_error = self._prepare_arguments(name, args)
        if param_error:
            return self._build_rpc_response(name, param_error)

        try:
            raw_result = dispatch_tool_call(name, clean_args)
        except Exception as exc:
            return self._build_rpc_response(
                name,
                {"status": "INTERNAL_ERROR", "error": str(exc)},
            )

        content = self._parse_tool_payload(raw_result)
        return self._build_rpc_response(name, content)


if __name__ == "__main__":
    print("==========================================================")
    print("🔌 KIỂM THỬ ĐỘC LẬP MCP SERVER (vinuni-academic-mcp-server)")
    print("==========================================================")
    
    server = MCPAcademicServer()
    tools = server.list_tools()
    print(f"✅ Khởi tạo thành công MCP Server: {server.server_name} (Version: {server.version})")
    print(f"📦 Số lượng Tools công bố: {len(tools)}")
    
    # Kiểm tra trạng thái TODO 1.2 (Tool Schema)
    sched_tool = next((t for t in tools if t.get("name") == "schedule_appointment"), None)
    if sched_tool and not sched_tool.get("parameters", {}).get("properties"):
        print("⏳ [TODO 1.2]: Tool 'schedule_appointment' chưa được định nghĩa properties trong 'src/tools.py'.")
    else:
        print("✅ [TODO 1.2]: Tool 'schedule_appointment' đã có schema đầy đủ.")

    # Kiểm tra trạng thái TODO 2.1 (call_tool)
    test_result = server.call_tool("academic_query", {"student_id": "SV2026001"})
    if not test_result:
        print("⏳ [TODO 2.1]: Hàm call_tool() đang trả về rỗng. Học viên hãy hoàn thiện TODO 2.1 trong 'src/mcp_server.py'!")
    else:
        print(f"✅ [TODO 2.1]: Test dispatch tool 'academic_query' thành công:")
        print(f"   Phản hồi JSON-RPC: {json.dumps(test_result, ensure_ascii=False)}")

        booking = server.call_tool(
            "schedule_appointment",
            {
                "student_id": "SV2026001",
                "datetime_str": "14:00 15/09/2026",
                "advisor_name": "PGS.TS Nguyễn Văn A",
                "extra_field_from_llm": "should_be_ignored",
            },
        )
        missing = server.call_tool("schedule_appointment", {"student_id": "SV2026001"})
        not_found = server.call_tool("academic_query", {"student_id": "SV9999999"})
        unknown = server.call_tool("delete_student", {"student_id": "SV2026001"})
        print(f"   Booking status: {booking.get('result', {}).get('status')}")
        print(f"   Missing params status: {missing.get('result', {}).get('status')}")
        print(f"   NOT_FOUND status: {not_found.get('result', {}).get('status')}")
        print(f"   Unknown tool status: {unknown.get('result', {}).get('status')}")
