import ollama
import redis
import os
import json
from dotenv import load_dotenv
from opencc import OpenCC

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


# Global instance
llm_service = LLMService()
