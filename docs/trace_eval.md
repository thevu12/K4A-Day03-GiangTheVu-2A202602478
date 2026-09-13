# 📊 BÁO CÁO THU HOẠCH NGHIỆM THU BÀI LAB 3 (BƯỚC 3 — SUBMISSION ARTIFACT)

> **Họ và Tên Học viên:** Giang Thế Vũ  
> **Mã Sinh Viên / Mã Học viên:** 2A202602478  
> **Chủ đề Lựa chọn:** Gợi ý 1.1 — Trợ lý Học vụ & Tra cứu Lịch thi VinUni (tra cứu GPA/hồ sơ học vụ và đặt lịch tư vấn với Cố vấn)  

---

## 1. BẢNG CHẤM ĐIỂM AGENTIC FIT SCORING MATRIX (ĐÁNH GIÁ CHỦ ĐỀ)

| Tiêu chí Đánh giá | Mức độ (1 - 5) | Giải trình chi tiết lý do chọn điểm |
| :--- | :---: | :--- |
| **1. Multi-step Reasoning** | 4 / 5 | Sinh viên thường không hỏi một phát là xong. Ví dụ: tra cứu hồ sơ SV2026001 → đọc tên cố vấn từ Observation → mới đặt lịch đúng người, đúng giờ. Cần tách thành chuỗi Thought → Action → Observation, không giải được bằng 1 lượt sinh text. |
| **2. Tool Interaction** | 5 / 5 | GPA, trạng thái học tập, cố vấn và booking **không nằm trong kiến thức tĩnh của LLM**. Agent bắt buộc gọi MCP Server: `academic_query` (đọc mock DB) và `schedule_appointment` (ghi lịch hẹn). Chatbot Baseline không làm được việc này. |
| **3. Dynamic Decision** | 4 / 5 | Bước sau phụ thuộc Observation: `SUCCESS` thì lấy `advisor`/`gpa` để trả lời hoặc đặt lịch; `NOT_FOUND` (mã SV9999999) thì từ chối booking và không bịa dữ liệu. Không thể hard-code một kịch bản cố định cho mọi câu hỏi. |
| **4. Long Horizon Goal** | 3 / 5 | Mục tiêu xuyên suốt một phiên là “hỗ trợ đúng sinh viên đó”: giữ `student_id`, tên cố vấn và khung giờ qua nhiều bước. Chưa cần memory dài ngày hay tự lập kế hoạch nhiều phiên, nên không chấm 5. |
| **TỔNG ĐIỂM AGENTIC FIT** | **16 / 20** | *Tổng > 12/20: bài toán phù hợp triển khai ReAct Agent + MCP, không nên dừng ở Chatbot Baseline.* |

---

## 2. TRÍCH XUẤT KẾT QUẢ WATERFALL TRACE LOG (SAU KHI CHẠY TEST SUITE TRÊN API THẬT)

> Đã chạy `python src/app.py --all` trên **Gemini API thật** (`LLM_PROVIDER=gemini`, model `gemini-3.6-flash`). Thought có cụm **"Gemini quyết định gọi công cụ"** / **"Gemini phản hồi trực tiếp"** — không phải Mock Offline.

Đoạn trích TC04 (multi-step ReAct) từ `docs/trace_waterfall.json`:

```json
[
  {
    "step": 1,
    "query": "Sinh viên SV2026001 muốn gặp đúng cố vấn học tập được gán trong hồ sơ. Hãy tra cứu thông tin học vụ trước, rồi đặt lịch hẹn tư vấn với đúng cố vấn đó vào 09:00 ngày 20/09/2026.",
    "action_type": "TOOL_EXECUTION",
    "thought": "Gemini quyết định gọi công cụ 'academic_query' với tham số: {\"student_id\": \"SV2026001\"}",
    "tool_name": "academic_query",
    "arguments": { "student_id": "SV2026001" },
    "observation": {
      "status": "SUCCESS",
      "student_id": "SV2026001",
      "data": {
        "full_name": "Nguyễn Văn An",
        "class": "AI-K4",
        "gpa": 3.85,
        "email": "an.nv@vinuni.edu.vn",
        "status": "Đang học",
        "advisor": "PGS.TS Nguyễn Văn A"
      }
    },
    "latency_ms": 12224.81
  },
  {
    "step": 2,
    "action_type": "TOOL_EXECUTION",
    "thought": "Gemini quyết định gọi công cụ 'schedule_appointment' với tham số: {\"advisor_name\": \"PGS.TS Nguyễn Văn A\", \"datetime_str\": \"09:00 20/09/2026\", \"student_id\": \"SV2026001\"}",
    "tool_name": "schedule_appointment",
    "arguments": {
      "advisor_name": "PGS.TS Nguyễn Văn A",
      "datetime_str": "09:00 20/09/2026",
      "student_id": "SV2026001"
    },
    "observation": {
      "status": "SUCCESS",
      "booking_id": "BK-SV2026001-99",
      "datetime": "09:00 20/09/2026",
      "advisor": "PGS.TS Nguyễn Văn A"
    },
    "latency_ms": 13149.26
  },
  {
    "step": 3,
    "action_type": "FINAL_ANSWER",
    "thought": "Gemini phản hồi trực tiếp bằng văn bản (không cần gọi công cụ).",
    "output": "Đặt lịch thành công với PGS.TS Nguyễn Văn A vào 09:00 ngày 20/09/2026 (Booking ID: BK-SV2026001-99).",
    "latency_ms": 14539.35
  }
]
```

Chuỗi Thought → Action → Observation → Final Answer trên LLM thật:

| Test | Kết quả | Tool MCP |
| :--- | :--- | :--- |
| TC01 FAQ | Gemini trả lời trực tiếp, không gọi tool | 0 |
| TC02 Tra cứu SV2026001 | GPA 3.85, cố vấn PGS.TS Nguyễn Văn A | `academic_query` |
| TC03 Đặt lịch 14:00 15/09/2026 | Booking `BK-SV2026001-99` | `schedule_appointment` |
| TC04 Đa bước | Tra cứu cố vấn → đặt lịch 09:00 20/09/2026 | `academic_query` + `schedule_appointment` |
| TC05 SV9999999 | `NOT_FOUND`, không bịa GPA | `academic_query` |

---

## 3. TỔNG KẾT KẾT QUẢ NGHIỆM THU & NỘP BÀI

- [x] Đã điền API Key thật trong `.env` và xác nhận Agent chạy mượt mà trên LLM API thật (Gemini `gemini-3.6-flash`).
- **Tổng số Test Cases đã chạy thành công:** 5 / 5 test cases.
- **Số lượt gọi Tool qua MCP Server chính xác:** 5 lượt (`academic_query` × 3, `schedule_appointment` × 2).
- **Kết quả đẩy Repo nộp bài:** [ ] Đã Commit và Push mã nguồn thành công lên GitHub cá nhân.

---

> ✅ **HOÀN TẤT NỘP BÀI:** Sao chép đường link GitHub Repository cá nhân của bạn và dán vào ô nộp bài trên hệ thống LMS VLearn để hoàn tất Bài Lab 3!
