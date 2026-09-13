"""
🔌 MODEL CONTEXT PROTOCOL (MCP) SERVER MODULE
Mô phỏng kiến trúc MCP Server (Client-Server Architecture) cung cấp công cụ chuẩn hóa.
"""

import json
import sys
from typing import Dict, Any, List
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
        self._request_id = 0   # Bộ đếm id request theo chuẩn JSON-RPC 2.0

    def list_tools(self) -> List[Dict[str, Any]]:
        """Trả về danh sách các Tools chuẩn giao thức MCP"""
        return TOOLS_SCHEMA
        
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        [TASK 2.1] HỌC VIÊN HOÀN THIỆN HÀM THỰC THI TOOL TRÊN MCP SERVER
        Thực thi request gọi Tool theo chuẩn MCP JSON-RPC
        """
        # [ĐÃ HOÀN THÀNH TODO 2.1]
        # Luồng xử lý: Request -> dispatch_tool_call() -> json.loads() -> đóng gói JSON-RPC 2.0
        self._request_id += 1
        arguments = arguments or {}

        # Bước 0: Kiểm tra Tool có được công bố qua MCP hay không (JSON-RPC error -32601)
        known_tools = {t.get("name") for t in self.list_tools()}
        if tool_name not in known_tools:
            return {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "server": self.server_name,
                "tool": tool_name,
                "isError": True,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: Tool '{tool_name}' không được MCP Server công bố."
                },
                "result": {
                    "status": "UNKNOWN_TOOL",
                    "message": f"Tool '{tool_name}' không tồn tại trên {self.server_name}."
                }
            }

        # Bước 1: Ủy quyền thực thi xuống Tool Router (Execution Layer trong src/tools.py)
        raw_result = dispatch_tool_call(tool_name, arguments)

        # Bước 2: Chuyển chuỗi JSON kết quả thành Python Dictionary
        try:
            content = json.loads(raw_result)
        except (json.JSONDecodeError, TypeError):
            # Tool trả về text thuần -> vẫn bọc lại thành object để Agent đọc được
            content = {"status": "RAW_TEXT", "message": str(raw_result)}

        # Bước 3: Đóng gói phản hồi chuẩn giao thức MCP JSON-RPC 2.0
        return {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "server": self.server_name,
            "tool": tool_name,
            "arguments": arguments,
            "isError": content.get("status") in ("EXECUTION_ERROR", "UNKNOWN_TOOL"),
            "result": content
        }


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
