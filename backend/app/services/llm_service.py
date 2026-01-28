import ollama
import redis
import os
import json
from dotenv import load_dotenv
from opencc import OpenCC
import re

load_dotenv()


class LLMService:
    def __init__(self, model="qwen2.5:7b"):
        self.model = model
        print(f"LLM Service initialized with model: {self.model}")

        # Initialize OpenCC for simplified to traditional Chinese conversion
        self.s2tw = OpenCC("s2tw")  # Simplified to Traditional (Taiwan standard)

        # Redis Connection
        self.redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST"),
            port=os.getenv("REDIS_PORT"),
            password=os.getenv("REDIS_PASSWORD"),
            username=os.getenv("REDIS_USERNAME"),
            db=os.getenv("REDIS_DB", 0),
            decode_responses=True,
        )
        try:
            self.redis_client.ping()
            print("Successfully connected to Redis.")
        except redis.ConnectionError as e:
            print(f"Failed to connect to Redis: {e}")

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
        Adds a document summary to the Redis chat history as context.
        """
        redis_key = f"chat_history:{session_id}"

        context_message = {
            "role": "system",
            "content": f"[系統訊息] 使用者已上傳文件 '{filename}'。以下是該文件的摘要內容，請根據此內容回答後續問題：\n\n{summary}",
        }

        try:
            self.redis_client.rpush(redis_key, json.dumps(context_message))
            self.redis_client.expire(redis_key, 86400)
            print(f"Document context for '{filename}' added to Redis.")
        except Exception as e:
            print(f"Error adding document context to Redis: {e}")

    def chat(self, prompt: str, session_id: str = "default_session"):
        """
        Sends a prompt to the Ollama model with context from Redis.
        """
        system_prompt = """你是一個專業的文件 AI 助手。

重要規則：
1. 你必須使用「繁體中文」（Traditional Chinese，正體中文）回答。
2. 絕對不可以使用「简体中文」（Simplified Chinese）。
3. 使用台灣用語和詞彙，例如：「軟體」而非「软件」，「網路」而非「网络」。
4. 字形必須是繁體：「體」而非「体」，「國」而非「国」。

請用繁體中文回答使用者的問題。"""
        redis_key = f"chat_history:{session_id}"

        # 1. Retrieve history
        # We store messages as JSON strings in a Redis List
        history_items = self.redis_client.lrange(redis_key, 0, -1)
        messages = [{"role": "system", "content": system_prompt}]

        for item in history_items:
            try:
                messages.append(json.loads(item))
            except json.JSONDecodeError:
                continue

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

            # 4. Save to Redis
            # Save User Message
            self.redis_client.rpush(redis_key, json.dumps(user_message))
            # Save Assistant Message
            assistant_message = {"role": "assistant", "content": assistant_content}
            self.redis_client.rpush(redis_key, json.dumps(assistant_message))

            # Optional: Set TTL for the session (e.g., 1 day)
            self.redis_client.expire(redis_key, 86400)

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
        chunk_size = 3000
        
        # Simple case: Short text
        if len(text) <= chunk_size:
            return self._analyze_chunk(text, final=True)

        # Long text: Map-Reduce
        print("[LLM] Transcript is long. Starting Map-Reduce analysis...")
        chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
        partial_results = []

        for idx, chunk in enumerate(chunks):
            print(f"[LLM] Analyzing chunk {idx + 1}/{len(chunks)}...")
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
                "Expert meeting secretary. Synthesize partial results into DETAILED meeting minutes (Traditional Chinese, zh-TW).\n\n"
                "Context: Meeting between 業主方 (Client) and PM方 (PM Team).\n\n"
                "Output JSON with keys:\n"
                "- attendees: List of participant names/roles (in Traditional Chinese)\n"
                "- meeting_objective: Detailed explanation of purpose (Translate to Traditional Chinese)\n"
                "- discussion_summary: COMPREHENSIVE summary in Traditional Chinese. Organize by topics. Include specific arguments and numbers.\n"
                "- schedule_notes: Detailed timeline and deadlines (Translate to Traditional Chinese)\n"
                "- decisions: All conclusive decisions made (Translate to Traditional Chinese). Be specific.\n"
                "- action_items: [{'task': 'Task in Traditional Chinese', 'owner': 'Name/Role (Chinese)', 'deadline': 'Date'}]\n\n"
                "Rules:\n"
                "- OUTPUT LANGUAGE: MUST BE TRADITIONAL CHINESE (Taiwan) ONLY. Do not output English unless it's a specific technical term.\n"
                "- RETAIN DETAILS: Do not omit important technical details.\n"
                "- Output ONLY valid JSON"
            )
        else:
            prompt = (
                "Expert meeting secretary. Analyze transcript segment (Traditional Chinese, zh-TW).\n\n"
                "Context: Meeting between 業主方 (Client) and PM方 (PM Team).\n\n"
                "Output JSON with keys:\n"
                "- attendees: List of names/roles (in Traditional Chinese)\n"
                "- meeting_objective: Discussed purpose (Translate to Traditional Chinese)\n"
                "- discussion_summary: DETAILED summary in Traditional Chinese. Capture requirements and issues.\n"
                "- schedule_notes: Timeline info (Translate to Traditional Chinese)\n"
                "- decisions: Clear decisions ONLY (Translate to Traditional Chinese)\n"
                "- action_items: [{'task': 'Task in Chinese', 'owner': 'Name (Chinese)', 'deadline': '...'}]\n\n"
                "Rules:\n"
                "- OUTPUT LANGUAGE: MUST BE TRADITIONAL CHINESE (Taiwan) ONLY.\n"
                "- Focus on SUBSTANCE and DETAILS.\n"
                "- Output ONLY valid JSON"
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
