"""
🔌 MULTI-PROVIDER LLM ADAPTER (Google Gemini, OpenAI & Offline Mock)
Hỗ trợ Native Tool Calling và chuyển đổi linh hoạt qua biến môi trường LLM_PROVIDER.
"""

import os
import sys
import json
import re
import time
from typing import Dict, Any, List
from dotenv import load_dotenv

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv(override=True)

class BaseLLMProvider:
    """Interface cơ sở cho các LLM Provider hỗ trợ Native Tool Calling"""
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        raise NotImplementedError

    def generate_with_tools(self, prompt: str, tools_schema: List[Dict[str, Any]], system_prompt: str = "") -> Dict[str, Any]:
        raise NotImplementedError


class MockOfflineProvider(BaseLLMProvider):
    """Offline Mock Provider dùng để chạy thử mà không tốn API Key"""
    def __init__(self):
        self.model_name = "Offline-Mock-Model-2026"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return f"[Mock Chatbot Response]: Xin chào! Tôi đã nhận được câu hỏi '{prompt}'. (Chế độ Chatbot không có Tool tra cứu dữ liệu thời gian thực)."

    def _extract_student_id(self, prompt: str) -> str:
        match = re.search(r"\bSV\d+\b", prompt, flags=re.IGNORECASE)
        return match.group(0).upper() if match else "SV2026001"

    def _extract_datetime(self, prompt: str) -> str:
        match = re.search(r"(\d{1,2}:\d{2})\s*(?:ngày\s*)?(\d{1,2}/\d{1,2}/\d{4})", prompt)
        if match:
            return f"{match.group(1)} {match.group(2)}"
        return "14:00 15/09/2026"

    def _parse_observations(self, prompt: str) -> List[Dict[str, Any]]:
        observations = []
        for chunk in prompt.split("Observation:")[1:]:
            raw = chunk.strip().split("\n\n")[0].strip()
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                observations.append(parsed)
        return observations

    def _summarize_observations(self, observations: List[Dict[str, Any]]) -> str:
        parts = []
        for obs in observations:
            if obs.get("status") == "NOT_FOUND":
                parts.append(obs.get("message", "Không tìm thấy dữ liệu sinh viên."))
            elif obs.get("status") == "SUCCESS" and "data" in obs:
                data = obs.get("data") or {}
                parts.append(
                    f"Sinh viên {obs.get('student_id', '')} ({data.get('full_name', '')}): "
                    f"Lớp {data.get('class', '')}, GPA {data.get('gpa', '')}, "
                    f"Email {data.get('email', '')}, trạng thái {data.get('status', '')}, "
                    f"cố vấn {data.get('advisor', '')}."
                )
            elif obs.get("status") == "SUCCESS" and obs.get("message"):
                parts.append(obs["message"])
        if not parts:
            return "Tôi đã nhận Observation từ công cụ nhưng không đủ dữ liệu để trả lời chi tiết."
        return " ".join(parts)

    def generate_with_tools(self, prompt: str, tools_schema: List[Dict[str, Any]], system_prompt: str = "") -> Dict[str, Any]:
        prompt_lower = prompt.lower()
        student_id = self._extract_student_id(prompt)
        datetime_str = self._extract_datetime(prompt)
        observations = self._parse_observations(prompt)
        wants_booking = "đặt lịch" in prompt_lower
        wants_lookup = "tra cứu" in prompt_lower
        already_booked = any(obs.get("booking_id") for obs in observations)
        last_status = observations[-1].get("status") if observations else ""

        # Đã có Observation: quyết định bước tiếp theo (multi-step ReAct)
        if observations:
            if last_status == "NOT_FOUND":
                message = observations[-1].get(
                    "message",
                    f"Không tìm thấy dữ liệu sinh viên có mã '{student_id}'.",
                )
                return {
                    "type": "text",
                    "content": (
                        f"Tôi đã tra cứu qua hệ thống học vụ nhưng không tìm thấy hồ sơ cho mã {student_id}. "
                        f"{message.rstrip('.')}. Tôi không bịa GPA hay thông tin cá nhân khi dữ liệu không tồn tại."
                    ),
                    "thought": "Observation trả về NOT_FOUND. Dừng lại và thông báo trung thực, không gọi tool tiếp.",
                }

            if wants_booking and not already_booked:
                advisor_name = "PGS.TS Nguyễn Văn A"
                for obs in reversed(observations):
                    data = obs.get("data") or {}
                    if data.get("advisor"):
                        advisor_name = data["advisor"]
                        break
                    if obs.get("advisor"):
                        advisor_name = obs["advisor"]
                        break
                return {
                    "type": "tool_call",
                    "tool_name": "schedule_appointment",
                    "arguments": {
                        "student_id": student_id,
                        "datetime_str": datetime_str,
                        "advisor_name": advisor_name,
                    },
                    "thought": (
                        f"Đã có hồ sơ sinh viên {student_id}. Bước tiếp theo là đặt lịch với cố vấn "
                        f"{advisor_name} vào {datetime_str}."
                    ),
                }

            return {
                "type": "text",
                "content": self._summarize_observations(observations),
                "thought": "Đã đủ Observation để trả lời câu hỏi gốc. Không cần gọi thêm Tool.",
            }

        # Lượt đầu: ưu tiên tra cứu trước nếu câu hỏi yêu cầu cả tra cứu lẫn đặt lịch
        if wants_booking and wants_lookup:
            return {
                "type": "tool_call",
                "tool_name": "academic_query",
                "arguments": {"student_id": student_id},
                "thought": (
                    f"Cần tra cứu hồ sơ {student_id} trước để lấy đúng cố vấn, sau đó mới đặt lịch."
                ),
            }
        if wants_booking:
            return {
                "type": "tool_call",
                "tool_name": "schedule_appointment",
                "arguments": {
                    "student_id": student_id,
                    "datetime_str": datetime_str,
                    "advisor_name": "PGS.TS Nguyễn Văn A",
                },
                "thought": f"Người dùng yêu cầu đặt lịch hẹn cho {student_id}. Gọi tool schedule_appointment.",
            }
        if wants_lookup or re.search(r"\bSV\d+\b", prompt, flags=re.IGNORECASE):
            return {
                "type": "tool_call",
                "tool_name": "academic_query",
                "arguments": {"student_id": student_id},
                "thought": f"Người dùng muốn tra cứu thông tin học vụ của {student_id}. Gọi tool academic_query.",
            }
        return {
            "type": "text",
            "content": (
                "[Mock Agent Response]: Xin chào! Quy chế học vụ VinUni yêu cầu sinh viên tích lũy "
                "tối thiểu 120 tín chỉ và duy trì GPA trên 2.0 để tốt nghiệp."
            ),
            "thought": "Câu hỏi chung về quy chế học vụ, trả lời trực tiếp không cần gọi Tool.",
        }


class GeminiProvider(BaseLLMProvider):
    """Google Gemini Provider (Native Tool Calling với Google GenAI SDK)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-3.6-flash"
        self._last_call_at = 0.0
        self._min_interval_s = 13.0

    def _throttle(self):
        """Free-tier Gemini ~5 request/phút — giãn cách để tránh 429."""
        elapsed = time.time() - self._last_call_at
        if elapsed < self._min_interval_s:
            wait_s = self._min_interval_s - elapsed
            print(f"⏳ [Gemini]: Giãn cách {wait_s:.1f}s để tránh hết quota free-tier...")
            time.sleep(wait_s)
        self._last_call_at = time.time()

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return "[Gemini Error]: Chưa cấu hình GEMINI_API_KEY trong file .env! Đang sử dụng chế độ Mock."
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            response = client.models.generate_content(model=self.model_name, contents=contents)
            return response.text
        except Exception as e:
            return f"[Gemini Exception]: {str(e)}"

    def generate_with_tools(self, prompt: str, tools_schema: List[Dict[str, Any]], system_prompt: str = "") -> Dict[str, Any]:
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            print("ℹ️ [Gemini Provider]: Chưa tìm thấy GEMINI_API_KEY hợp lệ. Tự động chuyển sang Mock Offline.")
            return MockOfflineProvider().generate_with_tools(prompt, tools_schema, system_prompt)

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)

        function_declarations = []
        for tool in tools_schema:
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

        last_error = None
        for attempt in range(1, 6):
            try:
                self._throttle()
                response = client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config
                )
                if response.function_calls:
                    call = response.function_calls[0]
                    args = dict(call.args) if hasattr(call, "args") and call.args else {}
                    return {
                        "type": "tool_call",
                        "tool_name": call.name,
                        "arguments": args,
                        "thought": f"Gemini quyết định gọi công cụ '{call.name}' với tham số: {json.dumps(args, ensure_ascii=False)}"
                    }
                return {
                    "type": "text",
                    "content": response.text or "",
                    "thought": "Gemini phản hồi trực tiếp bằng văn bản (không cần gọi công cụ)."
                }
            except Exception as e:
                last_error = e
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    wait_s = 12 * attempt
                    print(f"⚠️ [Gemini]: Hết quota tạm thời (429). Chờ {wait_s}s rồi thử lại ({attempt}/5)...")
                    time.sleep(wait_s)
                    continue
                print(f"⚠️ [Gemini API Warning]: Không thể kết nối live API ({err}). Tự động fallback về Mock.")
                return MockOfflineProvider().generate_with_tools(prompt, tools_schema, system_prompt)

        print(f"⚠️ [Gemini API Warning]: Vẫn lỗi sau 5 lần thử ({last_error}). Tự động fallback về Mock.")
        return MockOfflineProvider().generate_with_tools(prompt, tools_schema, system_prompt)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Provider (Native Tool Calling với OpenAI SDK)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_openai_api_key_here":
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

    def generate_with_tools(self, prompt: str, tools_schema: List[Dict[str, Any]], system_prompt: str = "") -> Dict[str, Any]:
        if not self.api_key or self.api_key == "your_openai_api_key_here":
            print("ℹ️ [OpenAI Provider]: Chưa tìm thấy OPENAI_API_KEY hợp lệ. Tự động chuyển sang Mock Offline.")
            return MockOfflineProvider().generate_with_tools(prompt, tools_schema, system_prompt)

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

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None
            )

            msg = response.choices[0].message
            if msg.tool_calls:
                call = msg.tool_calls[0]
                args = json.loads(call.function.arguments) if call.function.arguments else {}
                return {
                    "type": "tool_call",
                    "tool_name": call.function.name,
                    "arguments": args,
                    "thought": f"OpenAI quyết định gọi công cụ '{call.function.name}' với tham số: {json.dumps(args, ensure_ascii=False)}"
                }
            else:
                return {
                    "type": "text",
                    "content": msg.content or "",
                    "thought": "OpenAI phản hồi trực tiếp bằng văn bản (không cần gọi công cụ)."
                }
        except Exception as e:
            print(f"⚠️ [OpenAI API Warning]: Không thể kết nối live API ({str(e)}). Tự động fallback về Mock.")
            return MockOfflineProvider().generate_with_tools(prompt, tools_schema, system_prompt)


def get_llm_provider() -> BaseLLMProvider:
    """Factory function khởi tạo Provider theo LLM_PROVIDER env variable"""
    provider_type = os.getenv("LLM_PROVIDER", "gemini").lower()
    
    if provider_type == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if key and key != "your_gemini_api_key_here":
            return GeminiProvider()
        else:
            return MockOfflineProvider()
    elif provider_type == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if key and key != "your_openai_api_key_here":
            return OpenAIProvider()
        else:
            return MockOfflineProvider()
    elif provider_type == "mock":
        return MockOfflineProvider()
    else:
        return MockOfflineProvider()
