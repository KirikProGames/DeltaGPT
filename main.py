from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import json
import uuid
import hashlib
import secrets
from datetime import datetime
from typing import List, Dict, Optional
import uvicorn
import httpx
import random

app = FastAPI(title="DELTAGPT - Advanced AI Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API ключи - DeepSeek + OpenRouter
DEEPSEEK_API_KEY = "sk-29b953857b824c7f949e0f2b4a2c2f86"
OPENROUTER_KEYS = [
    os.getenv("OPENROUTER_KEY_1"),
    os.getenv("OPENROUTER_KEY_2")
]
OPENROUTER_KEYS = [key for key in OPENROUTER_KEYS if key]

print("🔑 Загружено API ключей:")
print(f"   DeepSeek: {DEEPSEEK_API_KEY[:20]}...")
print(f"   OpenRouter: {len(OPENROUTER_KEYS)} ключей")

# Файлы хранения
CHATS_FILE = "chats.json"
USERS_FILE = "users.json"

class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: str
    user_id: Optional[str] = None
    tokens: Optional[int] = 0

class ChatSession(BaseModel):
    id: str
    title: str
    messages: List[ChatMessage]
    created_at: str
    updated_at: str
    participants: List[str] = []
    total_tokens: int = 0
    thinking_mode: str = "fast"

class User(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    password: Optional[str] = None
    avatar: Optional[str] = None
    tier: str = "free"
    created_at: str
    last_login: str
    total_requests: int = 0
    total_tokens: int = 0

class UserManager:
    def __init__(self):
        self.users_file = USERS_FILE
        self.init_database()
    
    def init_database(self):
        if not os.path.exists(self.users_file):
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump({"users": {}}, f, ensure_ascii=False, indent=2)
    
    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()
    
    def create_user(self, username: str, password: str = None, email: str = None):
        with open(self.users_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if username in data["users"]:
            return False, "Пользователь уже существует"
        
        user_id = secrets.token_hex(16)
        now = datetime.now().isoformat()
        
        user_data = {
            "id": user_id,
            "username": username,
            "email": email,
            "tier": "free",
            "created_at": now,
            "last_login": now,
            "total_requests": 0,
            "total_tokens": 0
        }
        
        if password:
            user_data["password"] = self.hash_password(password)
        
        data["users"][username] = user_data
        
        with open(self.users_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return True, user_data
    
    def authenticate_user(self, username: str, password: str = None):
        with open(self.users_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if username not in data["users"]:
            return False, "Пользователь не найден"
        
        user_data = data["users"][username]
        
        if password and user_data.get("password") != self.hash_password(password):
            return False, "Неверный пароль"
        
        user_data["last_login"] = datetime.now().isoformat()
        with open(self.users_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return True, user_data
    
    def get_user_by_username(self, username: str):
        with open(self.users_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return data["users"].get(username)
    
    def update_user_stats(self, username: str, tokens_used: int = 0):
        with open(self.users_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if username in data["users"]:
            data["users"][username]["total_requests"] += 1
            data["users"][username]["total_tokens"] += tokens_used
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

class DeltaGPT:
    def __init__(self):
        self.sessions: Dict[str, ChatSession] = {}
        self.user_manager = UserManager()
        self.load_chats()
    
    def load_chats(self):
        try:
            if os.path.exists(CHATS_FILE):
                with open(CHATS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for chat_id, chat_data in data.items():
                        messages = [ChatMessage(**msg) for msg in chat_data.get("messages", [])]
                        self.sessions[chat_id] = ChatSession(
                            id=chat_id,
                            title=chat_data.get("title", "Новый чат"),
                            messages=messages,
                            created_at=chat_data.get("created_at", datetime.now().isoformat()),
                            updated_at=chat_data.get("updated_at", datetime.now().isoformat()),
                            participants=chat_data.get("participants", []),
                            total_tokens=chat_data.get("total_tokens", 0),
                            thinking_mode=chat_data.get("thinking_mode", "fast")
                        )
                print(f"✅ Загружено {len(self.sessions)} чатов")
        except Exception as e:
            print(f"❌ Ошибка загрузки чатов: {e}")
            self.sessions = {}
    
    def save_chats(self):
        try:
            chats_data = {}
            for chat_id, chat in self.sessions.items():
                chats_data[chat_id] = {
                    "id": chat.id,
                    "title": chat.title,
                    "messages": [msg.dict() for msg in chat.messages],
                    "created_at": chat.created_at,
                    "updated_at": chat.updated_at,
                    "participants": chat.participants,
                    "total_tokens": chat.total_tokens,
                    "thinking_mode": chat.thinking_mode
                }
            
            with open(CHATS_FILE, 'w', encoding='utf-8') as f:
                json.dump(chats_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ Ошибка сохранения чатов: {e}")
    
    def create_chat(self, title: str = "Новый чат", user_id: str = None, thinking_mode: str = "fast") -> str:
        chat_id = str(uuid.uuid4())
        participants = [user_id] if user_id else []
        
        self.sessions[chat_id] = ChatSession(
            id=chat_id,
            title=title,
            messages=[],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            participants=participants,
            thinking_mode=thinking_mode
        )
        self.save_chats()
        return chat_id
    
    def add_message(self, chat_id: str, role: str, content: str, user_id: str = None, tokens: int = 0):
        if chat_id not in self.sessions:
            chat_id = self.create_chat(user_id=user_id)
        
        message = ChatMessage(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            tokens=tokens
        )
        self.sessions[chat_id].messages.append(message)
        self.sessions[chat_id].updated_at = datetime.now().isoformat()
        self.sessions[chat_id].total_tokens += tokens
        
        if len(self.sessions[chat_id].messages) == 1:
            clean_content = content.replace('\n', ' ').strip()
            self.sessions[chat_id].title = clean_content[:40] + "..." if len(clean_content) > 40 else clean_content
        
        if user_id and user_id not in self.sessions[chat_id].participants:
            self.sessions[chat_id].participants.append(user_id)
        
        self.save_chats()
    
    def get_chat_history(self, chat_id: str) -> List[Dict]:
        if chat_id in self.sessions:
            return [msg.dict() for msg in self.sessions[chat_id].messages]
        return []
    
    def get_user_chats(self, user_id: str) -> List[Dict]:
        user_chats = []
        for chat in self.sessions.values():
            if user_id in chat.participants or not chat.participants:
                last_message = chat.messages[-1].content if chat.messages else "Нет сообщений"
                user_chats.append({
                    "id": chat.id,
                    "title": chat.title,
                    "last_message": last_message,
                    "updated_at": chat.updated_at,
                    "message_count": len(chat.messages),
                    "total_tokens": chat.total_tokens,
                    "thinking_mode": chat.thinking_mode
                })
        
        return sorted(user_chats, key=lambda x: x['updated_at'], reverse=True)
    
    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4
    
    async def try_deepseek_api(self, messages: List[Dict], max_tokens: int, temperature: float) -> Dict:
        """Запрос к DeepSeek API"""
        try:
            print("🔄 Пробуем DeepSeek API...")
            
            # Форматируем сообщения для DeepSeek
            deepseek_messages = []
            for msg in messages[-10:]:
                deepseek_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url="https://api.deepseek.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": deepseek_messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "stream": False
                    },
                    timeout=30.0
                )
                
                print(f"📥 DeepSeek ответ: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "response": data["choices"][0]["message"]["content"],
                        "tokens_used": data.get("usage", {}).get("total_tokens", self.estimate_tokens(data["choices"][0]["message"]["content"])),
                        "model": "deepseek-chat"
                    }
                else:
                    return {
                        "success": False,
                        "error": f"DeepSeek HTTP {response.status_code}: {response.text[:200]}"
                    }
                    
        except Exception as e:
            return {"success": False, "error": f"DeepSeek Exception: {str(e)}"}
    
    async def try_openrouter_api(self, messages: List[Dict], model: str, max_tokens: int, temperature: float) -> Dict:
        """Запрос к OpenRouter API"""
        try:
            if not OPENROUTER_KEYS:
                return {"success": False, "error": "No OpenRouter keys"}
            
            api_key = random.choice(OPENROUTER_KEYS)
            print(f"🔄 Пробуем {model}...")
            
            openai_messages = []
            for msg in messages[-8:]:
                openai_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://deltagpt.onrender.com",
                        "X-Title": "DELTAGPT",
                    },
                    json={
                        "model": model,
                        "messages": openai_messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature
                    },
                    timeout=20.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "response": data["choices"][0]["message"]["content"],
                        "tokens_used": data.get("usage", {}).get("total_tokens", 0),
                        "model": model
                    }
                else:
                    return {
                        "success": False,
                        "error": f"OpenRouter {response.status_code}: {response.text[:100]}"
                    }
                    
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def generate_fallback_response(self, user_message: str) -> str:
        """Fallback когда все API недоступны"""
        message_lower = user_message.lower().strip()
        
        if len(message_lower) <= 2:
            return "Привет! 👋 Напиши свой вопрос - я готов помочь!"
        
        if any(word in message_lower for word in ["привет", "hello", "hi"]):
            return "Привет! 🚀 Я DELTAGPT - твой AI ассистент. Задай любой вопрос!"
        
        return "Интересный вопрос! 💡 К сожалению, в данный момент AI системы временно недоступны. Попробуй обновить страницу или напиши позже."
    
    async def chat_completion(self, messages: List[Dict], chat_id: str = None, username: str = None, thinking_mode: str = "fast") -> Dict:
        try:
            mode_settings = {
                "fast": {"max_tokens": 2000, "temperature": 0.7},
                "deep": {"max_tokens": 4000, "temperature": 0.3},
                "creative": {"max_tokens": 3000, "temperature": 0.9}
            }
            
            settings = mode_settings.get(thinking_mode, mode_settings["fast"])
            
            # 1. Пробуем DeepSeek в первую очередь
            deepseek_result = await self.try_deepseek_api(messages, settings["max_tokens"], settings["temperature"])
            if deepseek_result["success"]:
                if username:
                    self.user_manager.update_user_stats(username, deepseek_result["tokens_used"])
                
                if chat_id:
                    self.add_message(chat_id, "assistant", deepseek_result["response"], username, deepseek_result["tokens_used"])
                
                return {
                    "success": True,
                    "response": deepseek_result["response"],
                    "model": deepseek_result["model"],
                    "tokens_used": deepseek_result["tokens_used"],
                    "context_length": len(messages),
                    "thinking_mode": thinking_mode
                }
            
            # 2. Если DeepSeek не сработал, пробуем OpenRouter
            openrouter_models = [
                "google/gemini-2.0-flash-exp:free",
                "meta-llama/llama-3.1-8b-instruct:free",
                "microsoft/wizardlm-2-8x22b:free"
            ]
            
            for model in openrouter_models:
                openrouter_result = await self.try_openrouter_api(messages, model, settings["max_tokens"], settings["temperature"])
                if openrouter_result["success"]:
                    if username:
                        self.user_manager.update_user_stats(username, openrouter_result["tokens_used"])
                    
                    if chat_id:
                        self.add_message(chat_id, "assistant", openrouter_result["response"], username, openrouter_result["tokens_used"])
                    
                    return {
                        "success": True,
                        "response": openrouter_result["response"],
                        "model": openrouter_result["model"],
                        "tokens_used": openrouter_result["tokens_used"],
                        "context_length": len(messages),
                        "thinking_mode": thinking_mode
                    }
            
            # 3. Если все API не сработали - fallback
            user_message = next((msg["content"] for msg in reversed(messages) if msg["role"] == "user"), "")
            fallback_response = self.generate_fallback_response(user_message)
            
            if chat_id:
                self.add_message(chat_id, "assistant", fallback_response, username, 0)
            
            return {
                "success": True,
                "response": fallback_response,
                "model": "fallback",
                "tokens_used": 0,
                "context_length": len(messages),
                "thinking_mode": thinking_mode
            }
                
        except Exception as e:
            print(f"❌ Критическая ошибка: {str(e)}")
            return {
                "success": False,
                "response": f"❌ Ошибка сервера: {str(e)}",
                "model": "unknown",
                "tokens_used": 0,
                "context_length": len(messages)
            }

# Инициализация
deltagpt = DeltaGPT()

# Статические файлы
app.mount("/static", StaticFiles(directory="."), name="static")

# Основные маршруты
@app.get("/")
async def serve_html():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>DELTAGPT - File not found</h1>")

@app.get("/style.css")
async def serve_css():
    return FileResponse("style.css")

@app.get("/script.js")
async def serve_js():
    return FileResponse("script.js")

# Debug endpoint для проверки API
@app.get("/debug/api")
async def debug_api():
    """Проверка всех API"""
    results = {}
    
    # Тест DeepSeek
    deepseek_test = await deltagpt.try_deepseek_api(
        [{"role": "user", "content": "Ответь одним словом: ПРИВЕТ"}],
        10, 0.1
    )
    results["deepseek"] = deepseek_test
    
    # Тест OpenRouter
    if OPENROUTER_KEYS:
        openrouter_test = await deltagpt.try_openrouter_api(
            [{"role": "user", "content": "Ответь одним словом: ПРИВЕТ"}],
            "google/gemini-2.0-flash-exp:free",
            10, 0.1
        )
        results["openrouter"] = openrouter_test
    
    return {
        "deepseek_key": DEEPSEEK_API_KEY[:20] + "...",
        "openrouter_keys": len(OPENROUTER_KEYS),
        "results": results
    }

# Тест AI
@app.get("/debug/test-ai")
async def test_ai():
    """Тест AI функционала"""
    test_messages = [{"role": "user", "content": "Напиши короткое приветствие на русском"}]
    
    result = await deltagpt.chat_completion(test_messages)
    return {
        "ai_test": result,
        "timestamp": datetime.now().isoformat()
    }

# Остальные маршруты (аутентификация, API чата и т.д.) остаются без изменений
@app.post("/register")
async def register(request: Request):
    try:
        data = await request.json()
        username = data.get("username")
        password = data.get("password")
        email = data.get("email")
        
        success, result = deltagpt.user_manager.create_user(username, password, email)
        if success:
            return JSONResponse({
                "success": True, 
                "user": result,
                "message": "Регистрация успешна"
            })
        else:
            return JSONResponse({"success": False, "message": result})
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Ошибка: {str(e)}"})

@app.post("/login")
async def login(request: Request):
    try:
        data = await request.json()
        username = data.get("username")
        password = data.get("password")
        
        success, result = deltagpt.user_manager.authenticate_user(username, password)
        if success:
            return JSONResponse({
                "success": True, 
                "user": result
            })
        else:
            return JSONResponse({"success": False, "message": result})
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Ошибка: {str(e)}"})

@app.post("/api/chat")
async def chat_api(request: Request):
    try:
        data = await request.json()
        message = data.get("message", "")
        chat_id = data.get("chat_id")
        username = data.get("username")
        thinking_mode = data.get("thinking_mode", "fast")
        
        if not message:
            return JSONResponse({"success": False, "response": "Пустое сообщение"})
        
        if not chat_id:
            chat_id = deltagpt.create_chat(user_id=username, thinking_mode=thinking_mode)
        
        deltagpt.add_message(chat_id, "user", message, username)
        
        history = deltagpt.get_chat_history(chat_id)
        
        result = await deltagpt.chat_completion(history, chat_id, username, thinking_mode)
        result["chat_id"] = chat_id
        
        return JSONResponse(result)
        
    except Exception as e:
        return JSONResponse({
            "success": False, 
            "response": f"❌ Server error: {str(e)}"
        })

# Остальные API маршруты...
@app.get("/api/chats/user/{username}")
async def get_user_chats(username: str):
    try:
        user = deltagpt.user_manager.get_user_by_username(username)
        if not user:
            return JSONResponse({"success": False, "message": "Пользователь не найден"})
        
        chats = deltagpt.get_user_chats(user["id"])
        return JSONResponse({"success": True, "chats": chats})
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)})

@app.get("/api/chat/{chat_id}")
async def get_chat(chat_id: str):
    try:
        history = deltagpt.get_chat_history(chat_id)
        chat_info = None
        
        if chat_id in deltagpt.sessions:
            chat = deltagpt.sessions[chat_id]
            chat_info = {
                "id": chat.id,
                "title": chat.title,
                "created_at": chat.created_at,
                "updated_at": chat.updated_at,
                "message_count": len(chat.messages),
                "total_tokens": chat.total_tokens,
                "thinking_mode": chat.thinking_mode
            }
        
        return JSONResponse({
            "success": True, 
            "messages": history,
            "chat_info": chat_info
        })
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)})

@app.post("/api/chat/{chat_id}/clear")
async def clear_chat(chat_id: str):
    try:
        if chat_id in deltagpt.sessions:
            deltagpt.sessions[chat_id].messages = []
            deltagpt.sessions[chat_id].total_tokens = 0
            deltagpt.save_chats()
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)})

@app.delete("/api/chat/{chat_id}")
async def delete_chat(chat_id: str):
    try:
        if chat_id in deltagpt.sessions:
            del deltagpt.sessions[chat_id]
            deltagpt.save_chats()
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)})

if __name__ == "__main__":
    print("🚀 DELTAGPT DEEPSEEK запускается...")
    print(f"🔑 DeepSeek API ключ: {DEEPSEEK_API_KEY[:20]}...")
    print(f"🔑 OpenRouter ключей: {len(OPENROUTER_KEYS)}")
    print("🎯 Модели: DeepSeek Chat + Gemini + Llama")
    print("🧠 Режимы: Быстрый / Глубокое / Креативный")
    print("🌐 Открой: http://localhost:8000")
    print("🔧 Debug API: http://localhost:8000/debug/api")
    print("🧪 Тест AI: http://localhost:8000/debug/test-ai")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
