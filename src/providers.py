"""
🔌 MULTI-PROVIDER LLM ADAPTER (Google Gemini, OpenAI & Offline Mock)
Hỗ trợ Native Tool Calling MULTI-TURN và chuyển đổi linh hoạt qua biến môi trường LLM_PROVIDER.

📌 NÂNG CẤP (Day 03 Lab - ReAct Multi-step):
    Hàm generate_with_tools() nhận vào CẢ HAI kiểu đầu vào:
      - str                : 1 câu hỏi đơn lẻ (tương thích ngược với code starter).
      - List[Dict]         : Toàn bộ lịch sử hội thoại ReAct để LLM "nhớ" Observation
                             của các bước trước -> cho phép suy luận đa bước thực sự.

    Định dạng message trung gian (provider-neutral) dùng chung cho mọi Provider:
      {"role": "user",      "content": "..."}
      {"role": "assistant", "content": "...", "tool_calls": [{"id","name","arguments"}]}
      {"role": "tool",      "tool_call_id": "...", "name": "...", "content": "<chuỗi JSON observation>"}
"""

import os
import re
import sys
import json
import time
from typing import Dict, Any, List, Union, Callable

from dotenv import load_dotenv

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()

# Kiểu dữ liệu đầu vào: 1 chuỗi prompt hoặc danh sách message lịch sử hội thoại
PromptInput = Union[str, List[Dict[str, Any]]]


def normalize_messages(prompt: PromptInput) -> List[Dict[str, Any]]:
    """Chuẩn hóa đầu vào về danh sách message thống nhất cho mọi Provider."""
    if isinstance(prompt, str):
        return [{"role": "user", "content": prompt}]
    return list(prompt or [])


# Số lần thử lại tối đa khi bị giới hạn tốc độ (Rate Limit) của gói Free Tier
MAX_API_RETRIES = int(os.getenv("MAX_API_RETRIES", "4"))


def _is_rate_limit_error(err: str) -> bool:
    return "429" in err or "RESOURCE_EXHAUSTED" in err or "rate_limit" in err.lower()


def _parse_retry_delay(err: str, default: float = 15.0) -> float:
    """Đọc thời gian chờ do API gợi ý (retryDelay / 'Please retry in Xs')."""
    for pattern in (r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)\s*s",
                    r"[Pp]lease retry in (\d+(?:\.\d+)?)\s*s"):
        match = re.search(pattern, err)
        if match:
            return float(match.group(1)) + 1.0
    return default


def call_with_retry(api_call: Callable[[], Any], provider_label: str = "LLM"):
    """
    Gọi API kèm cơ chế tự động thử lại khi gặp lỗi 429 (Free Tier giới hạn request/phút).
    Nhờ vậy toàn bộ Test Suite vẫn chạy trọn vẹn trên LLM API THẬT thay vì rơi về Mock.

    Trả về tuple (kết_quả, tổng_thời_gian_chờ_ms) để Waterfall Trace tách bạch được
    'độ trễ thực của API' với 'thời gian nằm chờ hạn mức' — tránh làm méo số liệu latency.
    """
    last_error = None
    waited_ms = 0.0
    for attempt in range(1, MAX_API_RETRIES + 1):
        try:
            return api_call(), round(waited_ms, 2)
        except Exception as exc:
            last_error = exc
            err = str(exc)
            if _is_rate_limit_error(err) and attempt < MAX_API_RETRIES:
                delay = _parse_retry_delay(err)
                print(f"⏳ [{provider_label} Rate Limit]: Chạm hạn mức Free Tier. "
                      f"Chờ {delay:.0f}s rồi thử lại (lần {attempt}/{MAX_API_RETRIES - 1})...")
                time.sleep(delay)
                waited_ms += delay * 1000
                continue
            raise
    raise last_error


def _tag_fallback(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Đánh dấu TRUNG THỰC những bước bị rơi về Mock Offline (do lỗi API / hết hạn mức).
    Waterfall Trace nhờ đó phản ánh đúng engine đã thực sự sinh ra phản hồi,
    tránh việc log khai khống là đã chạy trên LLM API thật.
    """
    result["served_by"] = "MockOfflineProvider (FALLBACK)"
    return result


def _safe_json_loads(raw: Any) -> Dict[str, Any]:
    """Ép chuỗi JSON kết quả Tool về dict (Gemini bắt buộc response phải là object)."""
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"result": parsed}
    except (json.JSONDecodeError, TypeError):
        return {"result": str(raw)}


class BaseLLMProvider:
    """Interface cơ sở cho các LLM Provider hỗ trợ Native Tool Calling"""

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        raise NotImplementedError

    def generate_with_tools(self, prompt: PromptInput, tools_schema: List[Dict[str, Any]],
                            system_prompt: str = "") -> Dict[str, Any]:
        raise NotImplementedError


class MockOfflineProvider(BaseLLMProvider):
    """
    Offline Mock Provider dùng để chạy thử mà không tốn API Key.
    Đã nâng cấp mô phỏng được suy luận ReAct ĐA BƯỚC (tra cứu -> đặt lịch).
    """

    def __init__(self):
        self.model_name = "Offline-Mock-Model-2026"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return (f"[Mock Chatbot Response]: Xin chào! Tôi đã nhận được câu hỏi '{prompt}'. "
                f"(Chế độ Chatbot không có Tool tra cứu dữ liệu thời gian thực).")

    # ----- Các hàm phụ trợ mô phỏng trạng thái hội thoại -----
    @staticmethod
    def _collect_state(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Rút trích: câu hỏi gốc, các tool đã gọi và Observation thu được."""
        user_query = ""
        called_tools, observations = [], []
        for msg in messages:
            if msg.get("role") == "user" and not user_query:
                user_query = msg.get("content", "") or ""
            if msg.get("role") == "assistant":
                for call in msg.get("tool_calls") or []:
                    called_tools.append(call.get("name"))
            if msg.get("role") == "tool":
                observations.append({
                    "name": msg.get("name"),
                    "data": _safe_json_loads(msg.get("content"))
                })
        return {"query": user_query, "called_tools": called_tools, "observations": observations}

    @staticmethod
    def _extract_student_id(text: str) -> str:
        import re
        match = re.search(r"SV\d{6,}", text or "", re.IGNORECASE)
        return match.group(0).upper() if match else "SV2026001"

    @staticmethod
    def _extract_datetime(text: str) -> str:
        import re
        match = re.search(r"(\d{1,2}[:h]\d{2})\D{0,20}?(\d{1,2}/\d{1,2}/\d{4})", text or "")
        if match:
            return f"{match.group(1).replace('h', ':')} {match.group(2)}"
        return "14:00 15/09/2026"

    def generate_with_tools(self, prompt: PromptInput, tools_schema: List[Dict[str, Any]],
                            system_prompt: str = "") -> Dict[str, Any]:
        messages = normalize_messages(prompt)
        state = self._collect_state(messages)
        query = state["query"]
        query_lower = query.lower()
        called = state["called_tools"]
        observations = state["observations"]

        wants_booking = any(kw in query_lower for kw in ["đặt lịch", "dat lich", "hẹn", "hen", "tư vấn", "booking"])
        student_id = self._extract_student_id(query)

        # --- Bước cuối: đã đặt lịch xong -> tổng hợp Final Answer ---
        if "schedule_appointment" in called:
            booking = next((o["data"] for o in observations if o["name"] == "schedule_appointment"), {})
            return {
                "type": "text",
                "content": booking.get("message", "Đã hoàn tất đặt lịch hẹn tư vấn học vụ."),
                "thought": "Đã nhận Observation đặt lịch thành công từ MCP Server. Tổng hợp câu trả lời cuối cùng."
            }

        # --- Đã tra cứu xong, người dùng muốn đặt lịch -> bước 2: gọi schedule_appointment ---
        if "academic_query" in called:
            academic = next((o["data"] for o in observations if o["name"] == "academic_query"), {})
            if academic.get("status") == "NOT_FOUND":
                return {
                    "type": "text",
                    "content": academic.get("message", "Rất tiếc, tôi không tìm thấy hồ sơ sinh viên này trong hệ thống."),
                    "thought": "Observation trả về NOT_FOUND. Trả lời trung thực, không bịa đặt dữ liệu (Anti-Hallucination)."
                }
            if wants_booking:
                advisor = (academic.get("data") or {}).get("advisor", "PGS.TS Nguyễn Văn A")
                return {
                    "type": "tool_call",
                    "tool_name": "schedule_appointment",
                    "arguments": {
                        "student_id": academic.get("student_id", student_id),
                        "datetime_str": self._extract_datetime(query),
                        "advisor_name": advisor
                    },
                    "thought": (f"Đã tra cứu được Cố vấn học tập là '{advisor}'. "
                                f"Bây giờ tôi gọi tiếp tool schedule_appointment để đặt lịch hẹn.")
                }
            data = academic.get("data") or {}
            return {
                "type": "text",
                "content": (f"Sinh viên {academic.get('student_id', student_id)} - {data.get('full_name', '')}, "
                            f"lớp {data.get('class', '')}, GPA {data.get('gpa', '')}, "
                            f"trạng thái {data.get('status', '')}, cố vấn {data.get('advisor', '')}."),
                "thought": "Đã có đủ dữ liệu học vụ từ Observation. Tổng hợp câu trả lời cho sinh viên."
            }

        # --- Bước 1: chưa gọi tool nào ---
        if wants_booking:
            # Nếu người dùng đã cung cấp sẵn tên cố vấn -> gọi thẳng schedule_appointment (1 bước)
            import re
            advisor_match = re.search(r"((?:PGS\.?\s*)?TS\.?\s*[^\d,\.]{2,40}?)(?=\s+vào|\s+lúc|,|\.|$)", query)
            if advisor_match:
                return {
                    "type": "tool_call",
                    "tool_name": "schedule_appointment",
                    "arguments": {
                        "student_id": student_id,
                        "datetime_str": self._extract_datetime(query),
                        "advisor_name": advisor_match.group(1).strip()
                    },
                    "thought": ("Người dùng đã cung cấp đủ mã sinh viên, thời gian và tên cố vấn. "
                                "Tôi gọi thẳng tool schedule_appointment mà không cần tra cứu thêm.")
                }
            return {
                "type": "tool_call",
                "tool_name": "academic_query",
                "arguments": {"student_id": student_id},
                "thought": (f"Người dùng muốn đặt lịch hẹn nhưng tôi chưa biết Cố vấn học tập của {student_id}. "
                            f"Theo mô tả tool, tôi phải gọi academic_query trước để lấy trường 'advisor'.")
            }
        if "sv" in query_lower and any(ch.isdigit() for ch in query) or "tra cứu" in query_lower:
            return {
                "type": "tool_call",
                "tool_name": "academic_query",
                "arguments": {"student_id": student_id},
                "thought": f"Người dùng muốn tra cứu hồ sơ học vụ của {student_id}. Tôi sẽ gọi tool academic_query."
            }
        return {
            "type": "text",
            "content": ("[Mock Agent Response]: Xin chào! Quy chế học vụ VinUni yêu cầu sinh viên tích lũy "
                        "tối thiểu 120 tín chỉ và duy trì GPA trên 2.0 để tốt nghiệp."),
            "thought": "Câu hỏi chung về quy chế học vụ, trả lời trực tiếp không cần gọi Tool."
        }


class GeminiProvider(BaseLLMProvider):
    """Google Gemini Provider (Native Tool Calling MULTI-TURN với Google GenAI SDK)"""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-2.5-flash"

    def _has_key(self) -> bool:
        return bool(self.api_key) and self.api_key != "your_gemini_api_key_here"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self._has_key():
            return "[Gemini Error]: Chưa cấu hình GEMINI_API_KEY trong file .env! Đang sử dụng chế độ Mock."
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            response = client.models.generate_content(model=self.model_name, contents=contents)
            return response.text
        except Exception as e:
            return f"[Gemini Exception]: {str(e)}"

    @staticmethod
    def _extract_text(response) -> str:
        """Gom các text part trong phản hồi Gemini (bỏ qua function_call part)."""
        chunks = []
        try:
            for candidate in response.candidates or []:
                content = getattr(candidate, "content", None)
                for part in (getattr(content, "parts", None) or []):
                    text = getattr(part, "text", None)
                    # Bỏ qua phần "thinking" nội bộ của model nếu SDK có đánh dấu
                    if text and not getattr(part, "thought", False):
                        chunks.append(text)
        except Exception:
            return ""
        return "".join(chunks).strip()

    @staticmethod
    def _to_gemini_contents(messages: List[Dict[str, Any]], types) -> List[Any]:
        """Chuyển message trung gian -> danh sách types.Content của Gemini SDK."""
        contents = []
        for msg in messages:
            role = msg.get("role")
            if role == "user":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=msg.get("content", ""))]
                ))
            elif role == "assistant":
                # ⚠️ QUAN TRỌNG (Gemini 3.x): phải gửi lại NGUYÊN VẸN đối tượng Content mà model
                # đã sinh ra, vì mỗi function_call part mang kèm 'thought_signature'. Nếu tự dựng
                # lại Part từ name/args, chữ ký này mất -> API trả lỗi 400 INVALID_ARGUMENT
                # ("Function call is missing a thought_signature in functionCall parts").
                raw_content = msg.get("provider_raw")
                if raw_content is not None:
                    contents.append(raw_content)
                    continue

                # Fallback: chỉ dùng khi không có Content gốc (ví dụ lịch sử nạp từ file)
                parts = []
                if msg.get("content"):
                    parts.append(types.Part.from_text(text=msg["content"]))
                for call in msg.get("tool_calls") or []:
                    parts.append(types.Part.from_function_call(
                        name=call.get("name", ""),
                        args=call.get("arguments") or {}
                    ))
                if parts:
                    contents.append(types.Content(role="model", parts=parts))
            elif role == "tool":
                # Observation trả ngược về cho model dưới dạng function_response
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_function_response(
                        name=msg.get("name", ""),
                        response=_safe_json_loads(msg.get("content"))
                    )]
                ))
        return contents

    def generate_with_tools(self, prompt: PromptInput, tools_schema: List[Dict[str, Any]],
                            system_prompt: str = "") -> Dict[str, Any]:
        messages = normalize_messages(prompt)

        if not self._has_key():
            print("ℹ️ [Gemini Provider]: Chưa tìm thấy GEMINI_API_KEY hợp lệ. Tự động chuyển sang Mock Offline.")
            return _tag_fallback(MockOfflineProvider().generate_with_tools(messages, tools_schema, system_prompt))

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)

            # Chuẩn hóa function declarations cho Gemini SDK
            function_declarations = []
            for tool in tools_schema:
                # Bỏ qua các tool schema chưa được định nghĩa hoàn chỉnh
                if not tool.get("name") or not tool.get("parameters"):
                    continue
                function_declarations.append({
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {})
                })

            config = types.GenerateContentConfig(
                system_instruction=system_prompt if system_prompt else None,
                tools=[{"function_declarations": function_declarations}] if function_declarations else None,
                temperature=0.2
            )

            gemini_contents = self._to_gemini_contents(messages, types)
            response, retry_wait_ms = call_with_retry(
                lambda: client.models.generate_content(
                    model=self.model_name,
                    contents=gemini_contents,
                    config=config
                ),
                provider_label="Gemini"
            )

            # Lấy phần văn bản suy luận (Thought) nếu model có sinh kèm.
            # Đọc trực tiếp từ candidates[].content.parts để tránh cảnh báo của SDK
            # khi response chứa đồng thời cả text part lẫn function_call part.
            reasoning_text = self._extract_text(response)

            # Kiểm tra xem Gemini có trả về Tool Call không
            if response.function_calls:
                call = response.function_calls[0]
                args = dict(call.args) if getattr(call, "args", None) else {}
                thought = reasoning_text or (
                    f"Cần dữ liệu thời gian thực nên tôi gọi công cụ '{call.name}' "
                    f"với tham số: {json.dumps(args, ensure_ascii=False)}."
                )
                return {
                    "type": "tool_call",
                    "tool_name": call.name,
                    "arguments": args,
                    "thought": thought,
                    "raw_text": reasoning_text,
                    # Giữ lại Content gốc (kèm thought_signature) để nạp ngược vào vòng lặp sau
                    "provider_raw": response.candidates[0].content if response.candidates else None,
                    "served_by": "GeminiProvider",
                    "retry_wait_ms": retry_wait_ms
                }

            return {
                "type": "text",
                "content": reasoning_text,
                "thought": "Đã có đủ thông tin, tổng hợp câu trả lời cuối cùng (không cần gọi thêm công cụ).",
                "served_by": "GeminiProvider",
                "retry_wait_ms": retry_wait_ms
            }

        except Exception as e:
            print(f"⚠️ [Gemini API Warning]: Không thể kết nối live API sau {MAX_API_RETRIES} lần thử "
                  f"({str(e).splitlines()[0][:160]}). Tự động fallback về Mock.")
            return _tag_fallback(MockOfflineProvider().generate_with_tools(messages, tools_schema, system_prompt))


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Provider (Native Tool Calling MULTI-TURN với OpenAI SDK)"""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"

    def _has_key(self) -> bool:
        return bool(self.api_key) and self.api_key != "your_openai_api_key_here"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self._has_key():
            return "[OpenAI Error]: Chưa cấu hình OPENAI_API_KEY trong file .env! Đang sử dụng chế độ Mock."
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = client.chat.completions.create(model=self.model_name, messages=messages)
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"[OpenAI Exception]: {str(e)}"

    @staticmethod
    def _to_openai_messages(messages: List[Dict[str, Any]], system_prompt: str) -> List[Dict[str, Any]]:
        """Chuyển message trung gian -> định dạng messages của OpenAI Chat Completions."""
        out = []
        if system_prompt:
            out.append({"role": "system", "content": system_prompt})
        for msg in messages:
            role = msg.get("role")
            if role == "user":
                out.append({"role": "user", "content": msg.get("content", "")})
            elif role == "assistant":
                entry = {"role": "assistant", "content": msg.get("content") or None}
                if msg.get("tool_calls"):
                    entry["tool_calls"] = [{
                        "id": call.get("id", f"call_{idx}"),
                        "type": "function",
                        "function": {
                            "name": call.get("name", ""),
                            "arguments": json.dumps(call.get("arguments") or {}, ensure_ascii=False)
                        }
                    } for idx, call in enumerate(msg["tool_calls"])]
                out.append(entry)
            elif role == "tool":
                out.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id", "call_0"),
                    "content": msg.get("content", "")
                })
        return out

    def generate_with_tools(self, prompt: PromptInput, tools_schema: List[Dict[str, Any]],
                            system_prompt: str = "") -> Dict[str, Any]:
        messages = normalize_messages(prompt)

        if not self._has_key():
            print("ℹ️ [OpenAI Provider]: Chưa tìm thấy OPENAI_API_KEY hợp lệ. Tự động chuyển sang Mock Offline.")
            return _tag_fallback(MockOfflineProvider().generate_with_tools(messages, tools_schema, system_prompt))

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)

            tools = []
            for tool in tools_schema:
                if not tool.get("name"):
                    continue
                tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {})
                    }
                })

            openai_messages = self._to_openai_messages(messages, system_prompt)
            response, retry_wait_ms = call_with_retry(
                lambda: client.chat.completions.create(
                    model=self.model_name,
                    messages=openai_messages,
                    tools=tools if tools else None,
                    tool_choice="auto" if tools else None
                ),
                provider_label="OpenAI"
            )

            msg = response.choices[0].message
            reasoning_text = (msg.content or "").strip()

            if msg.tool_calls:
                call = msg.tool_calls[0]
                args = json.loads(call.function.arguments) if call.function.arguments else {}
                thought = reasoning_text or (
                    f"Cần dữ liệu thời gian thực nên tôi gọi công cụ '{call.function.name}' "
                    f"với tham số: {json.dumps(args, ensure_ascii=False)}."
                )
                return {
                    "type": "tool_call",
                    "tool_name": call.function.name,
                    "arguments": args,
                    "thought": thought,
                    "tool_call_id": call.id,
                    "raw_text": reasoning_text,
                    "served_by": "OpenAIProvider",
                    "retry_wait_ms": retry_wait_ms
                }

            return {
                "type": "text",
                "content": reasoning_text,
                "thought": "Đã có đủ thông tin, tổng hợp câu trả lời cuối cùng (không cần gọi thêm công cụ).",
                "served_by": "OpenAIProvider",
                "retry_wait_ms": retry_wait_ms
            }
        except Exception as e:
            print(f"⚠️ [OpenAI API Warning]: Không thể kết nối live API sau {MAX_API_RETRIES} lần thử "
                  f"({str(e).splitlines()[0][:160]}). Tự động fallback về Mock.")
            return _tag_fallback(MockOfflineProvider().generate_with_tools(messages, tools_schema, system_prompt))


def get_llm_provider() -> BaseLLMProvider:
    """Factory function khởi tạo Provider theo LLM_PROVIDER env variable"""
    provider_type = os.getenv("LLM_PROVIDER", "gemini").lower()

    if provider_type == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if key and key != "your_gemini_api_key_here":
            return GeminiProvider()
        return MockOfflineProvider()
    elif provider_type == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if key and key != "your_openai_api_key_here":
            return OpenAIProvider()
        return MockOfflineProvider()
    elif provider_type == "mock":
        return MockOfflineProvider()
    return MockOfflineProvider()
