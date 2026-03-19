import ollama
import os
import json
from dotenv import load_dotenv
from opencc import OpenCC
import re
from typing import Any

load_dotenv()


class LLMService:
    def __init__(self, model="gpt-oss:20b", analysis_model="qwen3:latest", translation_model="qwen3:latest"):
        self.model = model
        self.analysis_model = analysis_model
        self.translation_model = translation_model
        print(f"LLM Service initialized with main model: {self.model}", flush=True)

        # Initialize OpenCC for simplified to traditional Chinese conversion
        self.s2tw = OpenCC("s2tw")  # Simplified to Traditional (Taiwan standard)

        # In-memory chat history storage (no Redis needed)
        # Format: {session_id: [messages]}
        self.chat_history = {}
        print("Using in-memory chat history storage (no Redis)")

        # Configure Ollama Host
        self.ollama_host = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        print(f"LLM Service connected to Ollama at: {self.ollama_host}")

        self.client = ollama.Client(
            host=self.ollama_host,
            timeout=300.0  # 配合使用者要求，給予大模型極長的思考時間 (5分鐘) 去整理超長表格
        )
        self.async_client = ollama.AsyncClient(
            host=self.ollama_host,
            timeout=300.0
        )

        self._ensure_model_exists()

    def _ensure_model_exists(self):
        """
        Checks if the required models exist on the (remote) server. If not, pulls them.
        """
        try:
            print(f"Ollama Server: {self.ollama_host}", flush=True)
            print(f"Role Routing: Main={self.model}, Analysis={self.analysis_model}, Translation={self.translation_model}", flush=True)
            
            response = self.client.list()
            available_models = [m.get("name", "") for m in response.get("models", [])]

            # Use unique models set to avoid redundant tasks
            unique_models = set([self.model, self.analysis_model, self.translation_model])

            for m_name in unique_models:
                # Find which roles use this model
                roles = []
                if m_name == self.model: roles.append("Main")
                if m_name == self.analysis_model: roles.append("Analysis")
                if m_name == self.translation_model: roles.append("Translation")
                
                role_label = "/".join(roles)
                model_exists = any(m_name in am for am in available_models)
                
                if not model_exists:
                    print(f"Model '{m_name}' ({role_label}) not found. Pulling...", flush=True)
                    self.client.pull(m_name)
                    print(f"Model '{m_name}' ({role_label}) pulled successfully.", flush=True)
                    available_models.append(m_name)
                else:
                    print(f"Model '{m_name}' ({role_label}) is ready.", flush=True)

        except Exception as e:
            print(f"Warning: Failed to check model states: {e}", flush=True)

    def add_document_context(
        self, filename: str, summary: str, session_id: str = "default_session"
    ):
        """
        Adds a document summary to the chat history as context.
        """
        if session_id not in self.chat_history:
            self.chat_history[session_id] = []

        context_message = {
            "role": "system",
            "content": f"[系統訊息] 使用者已上傳文件 '{filename}'。以下是該文件的摘要內容，請根據此內容回答後續問題:\n\n{summary}",
        }

        try:
            self.chat_history[session_id].append(context_message)
            print(f"Document context for '{filename}' added to chat history.")
        except Exception as e:
            print(f"Error adding document context: {e}")

    async def chat(self, prompt: str, session_id: str = "default_session", system_prompt: str = None):
        """
        Sends a prompt to the Ollama model with in-memory chat history.
        """
        base_system_prompt = """你是一個專業的文件 AI 助手。
 
 重要規則：
 1. 你必須使用「繁體中文」（Traditional Chinese，正體中文）回答。
 2. 絕對不可以使用「简体中文」（Simplified Chinese）。
 3. 使用台灣用語和詞彙，例如：「軟體」而非「软件」，「網路」而非「网络」。
 4. 字形必須是繁體：「體」而非「体」，「國」而非「国」。
 
 請用繁體中文回答使用者的問題。"""
        
        actual_system_prompt = system_prompt if system_prompt else base_system_prompt

        # 1. Retrieve history from memory
        if session_id not in self.chat_history:
            self.chat_history[session_id] = []
        
        messages = [{"role": "system", "content": actual_system_prompt}]
        messages.extend(self.chat_history[session_id])

        # 2. Add current user message
        user_message = {"role": "user", "content": prompt}
        messages.append(user_message)

        try:
            # 3. Call Ollama via Client (Run-in-threadpool to keep it async-friendly)
            from fastapi.concurrency import run_in_threadpool
            print(f"[LLM] Chat request (model: {self.model})...")
            
            response = await run_in_threadpool(
                self.client.chat, 
                model=self.model, 
                messages=messages
            )
            assistant_content = response["message"]["content"]

            # Convert simplified Chinese to traditional Chinese (Taiwan)
            assistant_content = self.s2tw.convert(assistant_content)

            # 4. Save to memory
            self.chat_history[session_id].append(user_message)
            assistant_message = {"role": "assistant", "content": assistant_content}
            self.chat_history[session_id].append(assistant_message)

            return assistant_content
        except Exception as e:
            print(f"[LLM Error] {e}")
            return "抱歉，我現在無法連接到語言模型。"

    async def chat_json(self, messages: list, system_prompt: str = None) -> dict:
        """
        Special chat method that enforces JSON output format.
        Useful for Agents (Router, Tool Caller).
        """
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages
            
        try:
            from fastapi.concurrency import run_in_threadpool
            response = await run_in_threadpool(
                self.client.chat,
                model=self.model,
                messages=messages,
                format="json",
                options={"temperature": 0} # Deterministic for routing
            )
            content = response["message"]["content"]
            return json.loads(content)
        except Exception as e:
            print(f"[LLM JSON Error] {e}")
            return {}

    async def chat_with_tools(self, messages: list, tools: list, tool_executor_obj: Any) -> str:
        """
        Full tool calling loop: 
        1. AI decides which tool to use
        2. Execution of the tool via tool_executor_obj
        3. AI synthesizes final answer with tool result
        """
        from fastapi.concurrency import run_in_threadpool
        
        try:
            # Step 1: LLM decides tool
            print(f"[LLM Tool] Deciding tool for {len(messages)} messages...")
            response = await run_in_threadpool(
                self.client.chat,
                model=self.model,
                messages=messages,
                tools=tools
            )

            # Check if LLM wants to call a tool
            if response.get("message", {}).get("tool_calls"):
                tool_calls = response["message"]["tool_calls"]
                
                # Append assistant tool call request to messages
                messages.append(response["message"])

                for tool_call in tool_calls:
                    func_name = tool_call["function"]["name"]
                    func_args = tool_call["function"]["arguments"]
                    print(f"\n[AI Thought] -> Requesting Tool: {func_name}")
                    print(f"[Tool Params] -> {json.dumps(func_args, indent=2, ensure_ascii=False)}")
                    
                    # Execute tool (Run-in-threadpool as DB queries are blocking)
                    try:
                        tool_func = getattr(tool_executor_obj, func_name)
                        result = await run_in_threadpool(tool_func, **func_args)
                        
                        # Append tool output to messages
                        messages.append({
                            "role": "tool",
                            "content": json.dumps(result, ensure_ascii=False),
                        })
                    except Exception as te:
                        print(f"[LLM Tool Execute Error] {te}")
                        messages.append({
                            "role": "tool",
                            "content": f"Error executing tool: {te}",
                        })

                # Step 2: Final completion with data — 用全新精簡對話完成彙整，避免 LLM 重新進入 tool-calling 模式
                print("[LLM Tool] Synthesizing final answer with tool data...")
                
                # 收集所有 tool 回傳結果
                tool_results_text = ""
                for msg in messages:
                    if msg.get("role") == "tool":
                        tool_results_text += str(msg.get("content", "")) + "\n"
                
                # 取出原始問題
                original_question = next(
                    (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
                )
                
                # 建立全新的精簡訊息陣列，完全不帶 tool 歷史
                synthesis_messages = [
                    {
                        "role": "system",
                        "content": "你是一位簡潔、專業的製造業數據分析師。請直接根據提供的數據作答，不要廢話。"
                    },
                    {
                        "role": "user",
                        "content": f"""使用者問題：{original_question}

查詢到的數據如下：
{tool_results_text}

請根據以上數據回答使用者問題。規範：
1. **數據一致性鐵律**：
   - 輸出的表格項數必須與數據源中的數組長度絕對對齊。
   - 若原始計數（如活線數）與清單長度（如去重後的工單數）不同，請務必在分析中說明：「目前共計 X 條活線，分屬 Y 個不同工單」之類的明確解釋，不可混淆兩者數字。
2. **排行與數據表格化**：排行或數值必須優先使用 Markdown 網格表格呈現。
3. **專業數據解說**：在表格下方提供一段具建設性的專業文字解說。**不須使用「亮點」、「風險」或「建議」等固定標題段落**，而是以連貫的專業語言闡述目前的數據現狀（例如：達成率分布、產能狀態等）。"""
                    }
                ]
                
                try:
                    final_response = await run_in_threadpool(
                        self.client.chat,
                        model=self.model,
                        messages=synthesis_messages
                    )
                    content = final_response.get("message", {}).get("content", "").strip()
                    if not content:
                        return tool_results_text
                    return content
                except Exception as synth_e:
                    print(f"[LLM Synthesis Error] Fallback triggered: {synth_e}")
                    return tool_results_text

            
            # Fallback if no tool call was made
            fallback_content = response.get("message", {}).get("content", "")
            return fallback_content

        except Exception as e:
            print(f"[LLM Tool Loop Error] {e}")
            return "處理您的請求時發生工具調用錯誤。"


    def _clean_llm_response(self, text: str) -> str:
        """
        Removes common conversational filler prefixes and <think> blocks from LLM output.
        """
        # 1. Remove <think>...</think> blocks (common in reasoning models)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

        # 2. Remove localized filler prefixes
        prefixes_to_remove = [
            "Here is the result:",
            "Sure!",
            "Summary:",
            "Action Items:",
            "好的，",
            "當然，",
            "這是分析結果：",
        ]

        cleaned = text.strip()
        for prefix in prefixes_to_remove:
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix) :].strip()

        return cleaned

    def analyze_meeting_transcript(self, text: str) -> dict:
        """
        Analyzes a meeting transcript to extract summary, decisions, and action items.
        Uses Map-Reduce for long texts.
        """
        print("[LLM] Starting meeting analysis...")
        # DeepSeek/gpt-oss models support large context windows.
        # We use a 15000 character chunk size to balance detail and stability.
        chunk_size = 15000
        
        # Simple case: Short text (fits in one chunk)
        if len(text) <= chunk_size:
            return self._analyze_chunk(text, final=True)

        # Long text: Map-Reduce
        print("[LLM] Transcript is long. Starting Map-Reduce analysis...")
        
        # Smart Chunking: Split by lines to avoid cutting sentences
        lines = text.split('\n')
        chunks = []
        current_chunk = []
        current_length = 0
        
        for line in lines:
            if current_length + len(line) > chunk_size and current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_length = 0
            current_chunk.append(line)
            current_length += len(line) + 1 # +1 for newline
            
        if current_chunk:
            chunks.append("\n".join(current_chunk))

        partial_results = []
        
        for idx, chunk in enumerate(chunks):
            print(f"[LLM] Analyzing chunk {idx + 1}/{len(chunks)} (Length: {len(chunk)})...")
            partial = self._analyze_chunk(chunk, final=False)
            if partial:
                partial_results.append(partial)

        # Reduce
        print("[LLM] Synthesizing final meeting minutes...")
        combined_text = "\n\n".join([json.dumps(p, ensure_ascii=False) for p in partial_results])
        final_result = self._analyze_chunk(combined_text, final=True, is_reduce_step=True)
        
        return final_result

    def _analyze_chunk(self, text: str, final: bool = False, is_reduce_step: bool = False) -> dict:
        """
        Helper to call LLM for meeting analysis. 
        Returns a dict with 'summary', 'decisions', 'action_items'.
        """
        if is_reduce_step:
            prompt = (
                "You are an expert meeting secretary. Compile a FINAL, HIGHLY DETAILED meeting minute based on the provided partial analysis segments.\n\n"
                "Context: Meeting between 業主方 (Client) and PM方 (PM Team).\n\n"
                "INSTRUCTIONS:\n"
                "1. INTEGRATE: Combine all partial summaries into a single, flowing narrative.\n"
                "2. EXPAND: Include as much detail as possible. Explain the 'Why' and 'How'.\n"
                "3. FORMAT: Output valid JSON.\n\n"
                "Output JSON structure:\n"
                "{\n"
                "  \"attendees\": \"String list of names/roles\",\n"
                "  \"meeting_objective\": \"Detailed explanation of meeting purpose\",\n"
                "  \"discussion_summary\": \"A VERY LONG, COMPREHENSIVE summary. Organize by topics/headings. Include numbers, dates, and specific arguments.\",\n"
                "  \"schedule_notes\": \"Detailed timeline and deadlines\",\n"
                "  \"decisions\": [\"Decision 1 (Specific)\", \"Decision 2\"],\n"
                "  \"action_items\": [{\"task\": \"Specific Task\", \"owner\": \"Name\", \"deadline\": \"Date/Time\"}]\n"
                "}\n\n"
                "Rules:\n"
                "- OUTPUT LANGUAGE: TRADITIONAL CHINESE (Taiwan) ONLY.\n"
                "- BE VERBOSE: The user wants a detailed report, not a brief summary.\n"
                "- Output ONLY valid JSON."
            )
        else:
            prompt = (
                "You are an expert meeting secretary. Analyze this meeting transcript segment.\n\n"
                "Context: Meeting between 業主方 (Client) and PM方 (PM Team).\n\n"
                "Output JSON structure:\n"
                "{\n"
                "  \"attendees\": \"Names (if mentioned)\",\n"
                "  \"meeting_objective\": \"Purpose (if mentioned)\",\n"
                "  \"discussion_summary\": \"Detailed summary. Capture technical requirements, disputes, and agreements.\",\n"
                "  \"schedule_notes\": \"Time info\",\n"
                "  \"decisions\": [\"Decision found in this segment\"],\n"
                "  \"action_items\": [{\"task\": \"Task\", \"owner\": \"Owner\", \"deadline\": \"Due\"}]\n"
                "}\n\n"
                "Rules:\n"
                "- OUTPUT LANGUAGE: TRADITIONAL CHINESE (Taiwan) ONLY.\n"
                "- Output ONLY valid JSON."
            )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Transcript/Context:\n{text}"}
        ]

        try:
            # Use reasoning model for analysis
            response = self.client.chat(model=self.analysis_model, messages=messages, format="json")
            content = response["message"]["content"]
            
            # Clean and Parse JSON
            # Sometimes models output text before JSON despite format="json"
            content = self._clean_llm_response(content)
            
            try:
                data = json.loads(content)
                # Convert to Traditional Chinese
                if isinstance(data.get("summary"), str):
                    data["summary"] = self.s2tw.convert(data["summary"])
                if isinstance(data.get("decisions"), list):
                    data["decisions"] = [self.s2tw.convert(str(d)) for d in data["decisions"]]
                if isinstance(data.get("action_items"), list):
                    new_actions = []
                    for item in data["action_items"]:
                        if isinstance(item, dict):
                            # Convert fields inside dict
                            new_item = item.copy()
                            if "task" in item: new_item["task"] = self.s2tw.convert(item["task"])
                            if "owner" in item: new_item["owner"] = self.s2tw.convert(item["owner"])
                            if "deadline" in item:  new_item["deadline"] = self.s2tw.convert(item["deadline"])
                            new_actions.append(new_item)
                        else:
                            # Fallback for string items
                            new_actions.append(self.s2tw.convert(str(item)))
                    data["action_items"] = new_actions
                return data
            except json.JSONDecodeError:
                print(f"[LLM] JSON Parse Error: {content[:100]}...")
                return {
                    "summary": self.s2tw.convert(content), 
                    "decisions": [], 
                    "action_items": []
                }

        except Exception as e:
            print(f"[LLM] Analysis error: {e}")
            return {"summary": "分析失敗", "decisions": [], "action_items": []}


    def translate_analysis(self, analysis: dict) -> dict:
        """
        Translate Chinese meeting analysis fields into English.

        Input dict keys (same as analyze_meeting_transcript output):
          meeting_objective, discussion_summary, attendees,
          schedule_notes, decisions, action_items

        Returns the same JSON structure with values in English.
        Falls back to empty structure on error so docx can still be generated.
        """
        print("[LLM] Translating analysis to English for bilingual meeting minutes...", flush=True)

        try:
            analysis_json = json.dumps(analysis, ensure_ascii=False, indent=2)
        except Exception:
            analysis_json = str(analysis)

        prompt = (
            "You are a professional translator. "
            "Translate ALL text values in the following JSON from Traditional Chinese to English.\n"
            "Rules:\n"
            "- Keep the same JSON structure and keys exactly as-is.\n"
            "- Translate ONLY the values (strings and string items in lists).\n"
            "- For action_items, translate the 'task', 'owner', and 'deadline' fields.\n"
            "- For 'owner' fields, translate job titles or roles into English (e.g. 'UI/UX 設計師' -> 'UI/UX Designer'). Only keep personal names (like 'John') unchanged.\n"
            "- Output ONLY valid JSON, nothing else.\n\n"
            f"Input JSON:\n{analysis_json}"
        )

        messages = [
            {"role": "system", "content": "You translate JSON values from Chinese to English. Output only valid JSON."},
            {"role": "user", "content": prompt},
        ]

        try:
            # Use translation model for speed
            response = self.client.chat(model=self.translation_model, messages=messages, format="json")
            content = self._clean_llm_response(response["message"]["content"])
            translated = json.loads(content)
            print("[LLM] Analysis translation complete.", flush=True)
            return translated
        except Exception as e:
            print(f"[LLM] translate_analysis error: {e}", flush=True)
            return {
                "meeting_objective": "",
                "discussion_summary": "",
                "attendees": [],
                "schedule_notes": "",
                "decisions": [],
                "action_items": [],
            }

    def translate_segments(
        self,
        segments: list[dict],
        detected_language: str,
    ) -> list[dict]:
        """
        Translate Whisper segments to the paired language:
          Chinese (zh / zh-TW / zh-CN)  →  English
          English (en)                   →  Chinese (Traditional, Taiwan)
          Other                          →  Chinese (Traditional, Taiwan)

        Each segment dict has: {start, end, text}
        Returns a list of {start, end, original, translated}.

        Strategy: batch segments (≤30 per call) and use numbered lines so
        the LLM output can be mapped 1-to-1 back to the original segments.
        """
        is_chinese = detected_language.lower().startswith("zh")
        if is_chinese:
            src_label = "Traditional Chinese"
            tgt_label = "English"
        else:
            src_label = "English"
            tgt_label = "Traditional Chinese (Taiwan)"

        BATCH = 30
        results: list[dict] = []

        for batch_start in range(0, len(segments), BATCH):
            batch = segments[batch_start: batch_start + BATCH]

            # Build a numbered list for the LLM
            numbered_lines = "\n".join(
                f"{i + 1}. {seg['text'].strip()}"
                for i, seg in enumerate(batch)
            )

            system_prompt = (
                f"You are a professional translator. "
                f"Translate each numbered line from {src_label} to {tgt_label}.\n"
                "Rules:\n"
                "- Keep the same numbering (1., 2., 3., …).\n"
                "- Translate ONLY the text; do NOT add commentary or explanations.\n"
                "- Output ONLY the numbered translated lines, nothing else.\n"
                "- Preserve proper nouns, dates, and numbers as-is.\n"
                f"- Target language: {tgt_label}."
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": numbered_lines},
            ]

            translated_lines: list[str] = [""] * len(batch)
            try:
                # Use translation model for speed
                response = self.client.chat(model=self.translation_model, messages=messages)
                raw = response["message"]["content"].strip()

                # Parse "N. translated text" lines
                for line in raw.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    # Match lines starting with a number and period/dot
                    m = re.match(r"^(\d+)[.、．]\s*(.*)", line)
                    if m:
                        idx = int(m.group(1)) - 1
                        if 0 <= idx < len(batch):
                            translated_lines[idx] = self.s2tw.convert(m.group(2).strip()) if not is_chinese else m.group(2).strip()

            except Exception as e:
                print(f"[LLM] translate_segments batch error: {e}", flush=True)

            for i, seg in enumerate(batch):
                results.append({
                    "start": seg["start"],
                    "end": seg["end"],
                    "original": seg["text"].strip(),
                    "translated": translated_lines[i],
                })

        print(f"[LLM] translate_segments complete: {len(results)} segments", flush=True)
        return results


    async def translate_segments_async(
        self,
        segments: list[dict],
        detected_language: str,
    ) -> list[dict]:
        is_chinese = detected_language.lower().startswith("zh")
        if is_chinese:
            src_label = "Traditional Chinese"
            tgt_label = "English"
        else:
            src_label = "English"
            tgt_label = "Traditional Chinese (Taiwan)"

        BATCH = 30
        
        async def process_batch(batch: list[dict]) -> list[dict]:
            numbered_lines = "\n".join(
                f"{i + 1}. {seg['text'].strip()}" for i, seg in enumerate(batch)
            )

            system_prompt = (
                f"You are a professional translator. "
                f"Translate each numbered line from {src_label} to {tgt_label}.\n"
                "Rules:\n"
                "- Keep the same numbering (1., 2., 3., …).\n"
                "- Translate ONLY the text; do NOT add commentary or explanations.\n"
                "- Output ONLY the numbered translated lines, nothing else.\n"
                "- Preserve proper nouns, dates, and numbers as-is.\n"
                f"- Target language: {tgt_label}."
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": numbered_lines},
            ]

            translated_lines: list[str] = [""] * len(batch)
            try:
                response = await self.async_client.chat(model=self.translation_model, messages=messages)
                raw = response["message"]["content"].strip()

                for line in raw.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    m = re.match(r"^(\d+)[.、．]\s*(.*)", line)
                    if m:
                        idx = int(m.group(1)) - 1
                        if 0 <= idx < len(batch):
                            translated_lines[idx] = self.s2tw.convert(m.group(2).strip()) if not is_chinese else m.group(2).strip()
            except Exception as e:
                print(f"[LLM] translate_segments_async batch error: {e}", flush=True)

            batch_results = []
            for i, seg in enumerate(batch):
                batch_results.append({
                    "start": seg["start"],
                    "end": seg["end"],
                    "original": seg["text"].strip(),
                    "translated": translated_lines[i],
                })
            return batch_results

        import asyncio
        tasks = []
        for batch_start in range(0, len(segments), BATCH):
            tasks.append(process_batch(segments[batch_start: batch_start + BATCH]))

        print(f"[LLM] Starting parallel translation for {len(tasks)} batches using {self.translation_model}...", flush=True)
        results_lists = await asyncio.gather(*tasks)

        # Flatten
        final_results = []
        for rl in results_lists:
            final_results.extend(rl)

        print(f"[LLM] translate_segments_async complete: {len(final_results)} segments", flush=True)
        return final_results
        
# Global instance
llm_service = LLMService()
