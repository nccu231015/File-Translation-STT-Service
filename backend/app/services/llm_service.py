import ollama
import os
import json
from dotenv import load_dotenv
from opencc import OpenCC
import re

load_dotenv()


class LLMService:
    def __init__(self, model="gpt-oss:20b"):
        self.model = model
        print(f"LLM Service initialized with model: {self.model}", flush=True)

        # Initialize OpenCC for simplified to traditional Chinese conversion
        self.s2tw = OpenCC("s2tw")  # Simplified to Traditional (Taiwan standard)

        # In-memory chat history storage (no Redis needed)
        # Format: {session_id: [messages]}
        self.chat_history = {}
        print("Using in-memory chat history storage (no Redis)")

        # Configure Ollama Host
        self.ollama_host = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        print(f"LLM Service connected to Ollama at: {self.ollama_host}")

        self.client = ollama.Client(host=self.ollama_host)

        self._ensure_model_exists()

    def _ensure_model_exists(self):
        """
        Checks if the model exists on the (remote) server. If not, pulls it.
        """
        try:
            print(f"Checking available Ollama models at {self.ollama_host}...")
            # Use self.client to check models
            response = self.client.list()

            available_models = []
            if "models" in response:
                for m in response["models"]:
                    available_models.append(m.get("name") or m.get("model"))

            model_exists = any(self.model in m for m in available_models)

            if not model_exists:
                print(
                    f"Model '{self.model}' not found on remote server. Pulling now... This may take a while."
                )
                self.client.pull(self.model)
                print(f"Model '{self.model}' pulled successfully.")
            else:
                print(f"Model '{self.model}' is ready on remote server.")

        except Exception as e:
            print(f"Warning: Failed to check or pull model automatically: {e}")

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

    def chat(self, prompt: str, session_id: str = "default_session"):
        """
        Sends a prompt to the Ollama model with in-memory chat history.
        """
        system_prompt = """你是一個專業的文件 AI 助手。

重要規則：
1. 你必須使用「繁體中文」（Traditional Chinese，正體中文）回答。
2. 絕對不可以使用「简体中文」（Simplified Chinese）。
3. 使用台灣用語和詞彙，例如：「軟體」而非「软件」，「網路」而非「网络」。
4. 字形必須是繁體：「體」而非「体」，「國」而非「国」。

請用繁體中文回答使用者的問題。"""
        
        # 1. Retrieve history from memory
        if session_id not in self.chat_history:
            self.chat_history[session_id] = []
        
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.chat_history[session_id])

        # 2. Add current user message
        user_message = {"role": "user", "content": prompt}
        messages.append(user_message)

        try:
            # 3. Call Ollama via Client
            print(f"Context length: {len(messages)} messages")
            response = self.client.chat(model=self.model, messages=messages)
            assistant_content = response["message"]["content"]

            # Convert simplified Chinese to traditional Chinese (Taiwan)
            assistant_content = self.s2tw.convert(assistant_content)

            # 4. Save to memory
            self.chat_history[session_id].append(user_message)
            assistant_message = {"role": "assistant", "content": assistant_content}
            self.chat_history[session_id].append(assistant_message)

            return assistant_content
        except Exception as e:
            print(f"Error communicating with Ollama: {e}")
            return "抱歉，我現在無法連接到語言模型。"



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
                "You are an expert meeting secretary. Your task is to compile a FINAL, HIGHLY DETAILED meeting minute based on the provided partial analysis segments.\n\n"
                "Context: Meeting between 業主方 (Client) and PM方 (PM Team).\n\n"
                "INSTRUCTIONS:\n"
                "1. INTEGRATE: Combine all partial summaries into a single, flowing narrative. Do not just list them.\n"
                "2. EXPAND: Include as much detail as possible from the source. Do not summarize briefly; explain the 'Why' and 'How'.\n"
                "3. FORMAT: Output valid JSON.\n\n"
                "Output JSON structure:\n"
                "{\n"
                "  \"attendees\": \"String list of names/roles (in Traditional Chinese)\",\n"
                "  \"meeting_objective\": \"Detailed explanation of meeting purpose (Traditional Chinese)\",\n"
                "  \"discussion_summary\": \"A VERY LONG, COMPREHENSIVE summary in Traditional Chinese. Organize by clear topics/headings. Include numbers, dates, and specific arguments mentioned beyond just high-level points.\",\n"
                "  \"schedule_notes\": \"Detailed timeline and deadlines (Traditional Chinese)\",\n"
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
                "You are an expert meeting secretary. Analyze this specific segment of a meeting transcript.\n\n"
                "Context: Meeting between 業主方 (Client) and PM方 (PM Team).\n\n"
                "INSTRUCTIONS:\n"
                "1. EXTRACT detailed points. Do not be vague.\n"
                "2. Identify specific decisions and action items.\n\n"
                "Output JSON structure:\n"
                "{\n"
                "  \"attendees\": \"Names (if mentioned)\",\n"
                "  \"meeting_objective\": \"Purpose (if mentioned)\",\n"
                "  \"discussion_summary\": \"Detailed summary of this segment in Traditional Chinese. Capture technical requirements, disputes, and agreements.\",\n"
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
            response = self.client.chat(model=self.model, messages=messages, format="json")
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


# Global instance
llm_service = LLMService()
