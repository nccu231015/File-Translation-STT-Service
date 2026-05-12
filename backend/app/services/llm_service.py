import asyncio
import ollama
import os
import json
from dotenv import load_dotenv
from opencc import OpenCC
import re

from typing import Any

load_dotenv()


def _env_int_bounded(key: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(os.getenv(key, str(default)))
    except ValueError:
        v = default
    return max(lo, min(v, hi))


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
            # Increasing timeout as per user requirements to allow large models ample time (5 min) for complex table processing
            timeout=300.0  
        )
        self.async_client = ollama.AsyncClient(
            host=self.ollama_host,
            timeout=300.0
        )

        # Per-request caps (backend .env). Does not replace host systemd OLLAMA_*; prevents huge default num_ctx from crashing ggml_cuda.
        self.ollama_num_ctx = _env_int_bounded("OLLAMA_NUM_CTX", 4096, 4096, 131072)
        _tp = _env_int_bounded("OLLAMA_TRANSLATE_MAX_PARALLEL", 15, 1, 32)
        self._translate_batch_sem = asyncio.Semaphore(_tp)
        print(
            f"[LLM] Ollama request options: num_ctx={self.ollama_num_ctx} | "
            f"translate_max_parallel={_tp}",
            flush=True,
        )

        self._ensure_model_exists()

    def _chat_options(self, **kwargs: Any) -> dict[str, Any]:
        opts: dict[str, Any] = {"num_ctx": self.ollama_num_ctx}
        for k, v in kwargs.items():
            if v is not None:
                opts[k] = v
        return opts

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

        # System message context
        context_message = {
            "role": "system",
            "content": f"[SYSTEM] User uploaded document '{filename}'. Below is the summary. Please answer follow-up questions based on this:\n\n{summary}",
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
        # Default system prompt for Chinese interaction (preserving cultural requirements)
        base_system_prompt = """You are a professional document AI assistant.
 
 RULES:
 1. You MUST use 'Traditional Chinese' (繁體中文).
 2. ABSOLUTELY NO 'Simplified Chinese'.
 3. Use Taiwan-standard terminology and phrases (e.g., '軟體' vs '软件').
 4. Use Traditional character forms ('體' vs '体').
 
 Please answer all user questions in Traditional Chinese."""
        
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
            # 3. Call Ollama (Using run-in-threadpool for async-friendliness with non-async client)
            from fastapi.concurrency import run_in_threadpool
            print(f"[LLM] Chat request (model: {self.model})...")
            
            response = await run_in_threadpool(
                lambda: self.client.chat(
                    model=self.model,
                    messages=messages,
                    options=self._chat_options(),
                )
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
            return "Sorry, I am currently unable to connect to the language model."

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
                lambda: self.client.chat(
                    model=self.model,
                    messages=messages,
                    format="json",
                    options=self._chat_options(temperature=0),
                )
            )
            content = response["message"]["content"]
            return json.loads(content)
        except Exception as e:
            print(f"[LLM JSON Error] {e}")
            return {}

    async def chat_with_tools(self, messages: list, tools: list, tool_executor_obj: Any) -> dict:
        """
        Full tool calling loop:
        1. AI decides which tool to use
        2. Execution of the tool via tool_executor_obj
        3. AI synthesizes final answer with tool result
        Returns: {"response": str, "chart_config": dict | None}
        """
        from fastapi.concurrency import run_in_threadpool
        
        try:
            # Step 1: LLM decides tool
            print(f"[LLM Tool] Deciding tool for {len(messages)} messages...")
            response = await run_in_threadpool(
                lambda: self.client.chat(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    options=self._chat_options(),
                )
            )

            # Check if LLM wants to call a tool
            if response.get("message", {}).get("tool_calls"):
                tool_calls = response["message"]["tool_calls"]
                
                # Append assistant tool call request to messages
                messages.append(response["message"])

                collected_chart_config = None  # will hold the first chart_config found

                for tool_call in tool_calls:
                    func_name = tool_call["function"]["name"]
                    func_args = tool_call["function"]["arguments"]
                    print(f"\n[AI Thought] -> Requesting Tool: {func_name}")
                    print(f"[Tool Params] -> {json.dumps(func_args, indent=2, ensure_ascii=False)}")
                    
                    # Execute tool (Run-in-threadpool as DB queries are blocking)
                    try:
                        tool_func = getattr(tool_executor_obj, func_name)
                        result = await run_in_threadpool(tool_func, **func_args)
                        
                        # Extract chart_config BEFORE sending to LLM (strip heavy data for synthesis)
                        if isinstance(result, dict) and "chart_config" in result:
                            collected_chart_config = result["chart_config"]
                        
                        # Build a lightweight copy for LLM synthesis
                        # Strip chart_config + raw time-series to prevent context overflow
                        HEAVY_KEYS = {"chart_config", "trend_data"}
                        slim_result = (
                            {k: v for k, v in result.items() if k not in HEAVY_KEYS}
                            if isinstance(result, dict) else result
                        )

                        # Append slimmed tool output to messages
                        messages.append({
                            "role": "tool",
                            "content": json.dumps(slim_result, ensure_ascii=False),
                        })
                    except Exception as te:
                        print(f"[LLM Tool Execute Error] {te}")
                        messages.append({
                            "role": "tool",
                            "content": f"Error executing tool: {te}",
                        })

                # Step 2: Final completion with data
                print("[LLM Tool] Synthesizing final answer with tool data...")
                
                # Collect all tool output text
                tool_results_text = ""
                for msg in messages:
                    if msg.get("role") == "tool":
                        tool_results_text += str(msg.get("content", "")) + "\n"
                
                # Extract original question
                original_question = next(
                    (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
                )

                # Build lean synthesis prompt (no tool history)
                synthesis_messages = [
                    {
                        "role": "system",
                        "content": (
                            "你是一位簡潔、專業的製造業數據分析師，服務的公司位於台灣。"
                            "《強制規定》：無論數據中是否包含英文，你的回覆必須全程使用繁體中文。"
                            "絕對禁止輸出任何英文句子或段落。數字、代號除外。"
                        )
                    },
                    # Few-shot: demonstrate correct Traditional Chinese response format
                    {
                        "role": "user",
                        "content": (
                            "使用者問題：目前哪些產線不良率最高？\n"
                            "\n查詢到的數據如下：\n"
                            "{\"status\":\"success\",\"data\":[{\"產線\":\"F2\",\"不良率百分比\":1.85},{\"產線\":\"T1\",\"不良率百分比\":0.76}]}\n"
                            "\n請用《繁體中文》回答。"
                        )
                    },
                    {
                        "role": "assistant",
                        "content": (
                            "根據今日查詢結果，不良率最高的產線如下：\n\n"
                            "| 產線 | 不良率 (%) |\n"
                            "|------|----------|\n"
                            "| F2 | 1.85 |\n"
                            "| T1 | 0.76 |\n\n"
                            "F2 產線的不良率顯著高於其他產線，建議優先調查其製程異常原因。"
                        )
                    },
                    # Actual synthesis request
                    {
                        "role": "user",
                        "content": f"""使用者問題：{original_question}

查詢到的數據如下：
{tool_results_text}

《重要》請使用《繁體中文》回答，不得出現英文段落。規範：
1. **數據表格化**：排行或數値必須優先使用 Markdown 表格呈現。
2. **數據一致性**：輸出的表格項數必須與數據源中的筆數對齊。
3. **專業解說**：在表格下方提供一段繁體中文的專業文字解說。"""
                    }
                ]
                
                try:
                    final_response = await run_in_threadpool(
                        lambda: self.client.chat(
                            model=self.model,
                            messages=synthesis_messages,
                            options=self._chat_options(),
                        )
                    )
                    content = final_response.get("message", {}).get("content", "").strip()
                    if not content:
                        content = tool_results_text
                    return {"response": content, "chart_config": collected_chart_config}
                except Exception as synth_e:
                    print(f"[LLM Synthesis Error] Fallback triggered: {synth_e}")
                    return {"response": tool_results_text, "chart_config": collected_chart_config}

            
            # Fallback if no tool call was made
            fallback_content = response.get("message", {}).get("content", "")
            return {"response": fallback_content, "chart_config": None}

        except Exception as e:
            print(f"[LLM Tool Loop Error] {e}")
            return {"response": "處理您的請求時發生工具調用錯誤。", "chart_config": None}

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

    def _parse_meeting_analysis_json(self, raw: str) -> dict | None:
        """
        Parse model output as JSON. Handles markdown fences and embedded JSON objects.
        """
        if not raw or not str(raw).strip():
            return None
        s = str(raw).strip()

        def _try_load(candidate: str) -> dict | None:
            c = candidate.strip()
            if not c:
                return None
            try:
                out = json.loads(c)
                return out if isinstance(out, dict) else None
            except json.JSONDecodeError:
                return None

        if r := _try_load(s):
            return r

        # Markdown code fence ```json ... ```
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", s, re.I)
        if m and (r := _try_load(m.group(1))):
            return r

        # First balanced {...} substring (handles preamble before JSON)
        start = s.find("{")
        if start != -1:
            depth = 0
            for i in range(start, len(s)):
                if s[i] == "{":
                    depth += 1
                elif s[i] == "}":
                    depth -= 1
                    if depth == 0:
                        if r := _try_load(s[start : i + 1]):
                            return r
                        break

        return None

    def _meeting_analysis_fallback_payload(self, raw_content: str) -> dict:
        """
        When JSON parsing fails, still return keys consumed by minutes API / n8n.
        Puts cleaned text into discussion_summary (same consumer path as success JSON).
        """
        text = (raw_content or "").strip()
        if text:
            text = self.s2tw.convert(text)
        else:
            text = "（模型未產出可解析的 JSON；可嘗試調高 num_predict 或重試。）"
        return {
            "attendees": "",
            "meeting_objective": "",
            "discussion_summary": text,
            "schedule_notes": "",
            "summary": text,
            "decisions": [],
            "action_items": [],
        }

    def analyze_meeting_transcript(
        self,
        text: str,
        model: str = None,
        temperature: float = 0.2,
        num_predict: int = 1024,
    ) -> dict:
        """
        Analyzes a meeting transcript to extract summary, decisions, and action items.
        Uses Map-Reduce for long texts.
        model: Ollama model override; None = use self.analysis_model.
        """
        _effective_model = model or self.analysis_model
        print(
            f"[LLM] analyze_meeting_transcript | "
            f"model={_effective_model} | temperature={temperature} | num_predict={num_predict}",
            flush=True,
        )
        # Capped prompt context via _chat_options(num_ctx); long transcripts still use map-reduce chunking below.
        chunk_size = 15000
        
        # Simple case: Short text (fits in one chunk)
        if len(text) <= chunk_size:
            return self._analyze_chunk(text, final=True, model=model, temperature=temperature, num_predict=num_predict)

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
            partial = self._analyze_chunk(chunk, final=False, model=model, temperature=temperature, num_predict=num_predict)
            if partial:
                partial_results.append(partial)

        # Reduce
        print("[LLM] Synthesizing final meeting minutes...")
        combined_text = "\n\n".join([json.dumps(p, ensure_ascii=False) for p in partial_results])
        final_result = self._analyze_chunk(combined_text, final=True, is_reduce_step=True, model=model, temperature=temperature, num_predict=num_predict)
        
        return final_result

    def _analyze_chunk(
        self,
        text: str,
        final: bool = False,
        is_reduce_step: bool = False,
        model: str = None,
        temperature: float = 0.2,
        num_predict: int = 1024,
    ) -> dict:
        """
        Helper to call LLM for meeting analysis.
        Returns a dict with 'summary', 'decisions', 'action_items'.
        model: Ollama model override; None = use self.analysis_model.
        """
        if is_reduce_step:
            prompt = (
                "[CRITICAL INSTRUCTION] You MUST write ALL output in TRADITIONAL CHINESE (繁體中文). "
                "Even if the input is in English, your output MUST be in Traditional Chinese. No exceptions.\n\n"
                "You are an expert meeting secretary. Compile a FINAL, HIGHLY DETAILED meeting minute based on the provided partial analysis segments.\n\n"
                "Context: Meeting between 業主方 (Client) and PM方 (PM Team).\n\n"
                "INSTRUCTIONS:\n"
                "1. INTEGRATE: Combine all partial summaries into a single, flowing narrative.\n"
                "2. EXPAND: Include as much detail as possible. Explain the 'Why' and 'How'.\n"
                "3. FORMAT: Output valid JSON.\n\n"
                "Output JSON structure:\n"
                "{\n"
                "  \"attendees\": \"字串，與會者名單/角色\",\n"
                "  \"meeting_objective\": \"詳細說明會議目的\",\n"
                "  \"discussion_summary\": \"非常詳細的摘要，按主題/標題組織，包含數字、日期與具體論點\",\n"
                "  \"schedule_notes\": \"詳細時程與截止日期\",\n"
                "  \"decisions\": [\"決議1（具體）\", \"決議2\"],\n"
                "  \"action_items\": [{\"task\": \"具體任務\", \"owner\": \"負責人\", \"deadline\": \"日期/時間\"}]\n"
                "}\n\n"
                "Rules:\n"
                "- 所有輸出必須使用繁體中文（台灣用語）。\n"
                "- BE VERBOSE: The user wants a detailed report, not a brief summary.\n"
                "- Output ONLY valid JSON."
            )
        else:
            prompt = (
                "[CRITICAL INSTRUCTION] You MUST write ALL output in TRADITIONAL CHINESE (繁體中文). "
                "Even if the input is in English, your output MUST be in Traditional Chinese. No exceptions.\n\n"
                "You are an expert meeting secretary. Analyze this meeting transcript segment.\n\n"
                "Context: Meeting between 業主方 (Client) and PM方 (PM Team).\n\n"
                "Output JSON structure:\n"
                "{\n"
                "  \"attendees\": \"與會者名單（若有提及）\",\n"
                "  \"meeting_objective\": \"會議目的（若有提及）\",\n"
                "  \"discussion_summary\": \"詳細摘要，記錄技術需求、爭議與共識\",\n"
                "  \"schedule_notes\": \"時程資訊\",\n"
                "  \"decisions\": [\"本段中找到的決議\"],\n"
                "  \"action_items\": [{\"task\": \"任務\", \"owner\": \"負責人\", \"deadline\": \"期限\"}]\n"
                "}\n\n"
                "Rules:\n"
                "- 所有輸出必須使用繁體中文（台灣用語）。\n"
                "- Output ONLY valid JSON."
            )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Transcript/Context:\n{text}"}
        ]

        try:
            # Use reasoning model for analysis (override if caller specifies a model)
            _model = model or self.analysis_model
            _options = self._chat_options(temperature=temperature, num_predict=num_predict)
            print(f"[LLM] _analyze_chunk model={_model} options={_options}", flush=True)
            response = self.client.chat(model=_model, messages=messages, format="json", options=_options)
            content = response["message"]["content"]
            
            # Clean and Parse JSON
            # Sometimes models output text before JSON despite format="json"
            content = self._clean_llm_response(content)

            data = self._parse_meeting_analysis_json(content)
            if data is None:
                print(
                    f"[LLM] JSON Parse Error (could not extract JSON). "
                    f"Raw length={len(content)} preview={content[:500]!r}...",
                    flush=True,
                )
                return self._meeting_analysis_fallback_payload(content)

            # Convert string fields to Traditional Chinese where applicable
            if isinstance(data.get("summary"), str):
                data["summary"] = self.s2tw.convert(data["summary"])
            for key in ("meeting_objective", "discussion_summary", "attendees", "schedule_notes"):
                if isinstance(data.get(key), str):
                    data[key] = self.s2tw.convert(data[key])
            if isinstance(data.get("decisions"), list):
                data["decisions"] = [self.s2tw.convert(str(d)) for d in data["decisions"]]
            if isinstance(data.get("action_items"), list):
                new_actions = []
                for item in data["action_items"]:
                    if isinstance(item, dict):
                        new_item = item.copy()
                        if "task" in item:
                            new_item["task"] = self.s2tw.convert(item["task"])
                        if "owner" in item:
                            new_item["owner"] = self.s2tw.convert(item["owner"])
                        if "deadline" in item:
                            new_item["deadline"] = self.s2tw.convert(item["deadline"])
                        new_actions.append(new_item)
                    else:
                        new_actions.append(self.s2tw.convert(str(item)))
                data["action_items"] = new_actions
            return data

        except Exception as e:
            print(f"[LLM] Analysis error: {e}")
            return self._meeting_analysis_fallback_payload(f"分析過程發生錯誤：{e}")


    def translate_analysis(self, analysis: dict, model: str = None) -> dict:
        """
        Translate Chinese meeting analysis fields into English.

        Input dict keys (same as analyze_meeting_transcript output):
          meeting_objective, discussion_summary, attendees,
          schedule_notes, decisions, action_items

        Returns the same JSON structure with values in English.
        Falls back to empty structure on error so docx can still be generated.
        model: Ollama model override; None = use self.translation_model.
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
            # Use translation model for speed (override if caller specifies a model)
            _model = model or self.translation_model
            print(f"[LLM] translate_analysis model={_model}", flush=True)
            response = self.client.chat(
                model=_model,
                messages=messages,
                format="json",
                options=self._chat_options(),
            )
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

    def _segment_translation_labels(self, detected_language: str) -> tuple[str, str, bool]:
        """
        Bilingual transcript: zh* <-> English pairing only.
        - zh*: source column = Traditional Chinese, target = English.
        - Any other Whisper code: English-side column -> Traditional Chinese (same prompts as en->zh).
        Returns (src_label, tgt_label, source_is_chinese).
        """
        raw = (detected_language or "").strip().lower()
        base = raw.split("-")[0] if raw else "en"
        if base.startswith("zh"):
            return ("Traditional Chinese", "English", True)
        return ("English", "Traditional Chinese (Taiwan)", False)

    def translate_segments(
        self,
        segments: list[dict],
        detected_language: str,
    ) -> list[dict]:
        """
        Translate segments for bilingual DOCX: Chinese (zh*) <-> English only.
        Non-Chinese Whisper codes use the same EN->zh-TW prompt as English.

        Each segment dict has: {start, end, text}
        Returns a list of {start, end, original, translated}.

        Strategy: batch segments (≤30 per call) and use numbered lines so
        the LLM output can be mapped 1-to-1 back to the original segments.
        """
        src_label, tgt_label, is_chinese = self._segment_translation_labels(detected_language)
        print(
            f"[LLM] translate_segments route: lang={detected_language!r} "
            f"-> {src_label} -> {tgt_label}",
            flush=True,
        )

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
                response = self.client.chat(
                    model=self.translation_model,
                    messages=messages,
                    options=self._chat_options(),
                )
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
        model: str = None,
    ) -> list[dict]:
        src_label, tgt_label, is_chinese = self._segment_translation_labels(detected_language)
        print(
            f"[LLM] translate_segments_async route: lang={detected_language!r} "
            f"-> {src_label} -> {tgt_label}",
            flush=True,
        )

        BATCH = 30
        _model = model or self.translation_model
        
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
                async with self._translate_batch_sem:
                    response = await self.async_client.chat(
                        model=_model,
                        messages=messages,
                        options=self._chat_options(),
                    )
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

        print(f"[LLM] Starting parallel translation for {len(tasks)} batches using {_model}...", flush=True)
        results_lists = await asyncio.gather(*tasks)

        # Flatten
        final_results = []
        for rl in results_lists:
            final_results.extend(rl)

        print(f"[LLM] translate_segments_async complete: {len(final_results)} segments", flush=True)
        return final_results
        
# Global instance
llm_service = LLMService()
