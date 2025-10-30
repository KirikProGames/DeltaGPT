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

# Безопасное получение ключей из Environment Variables
OPENROUTER_KEYS = [
    os.getenv("OPENROUTER_KEY_1"),  # Твой GPT-5 ключ
    os.getenv("OPENROUTER_KEY_2")   # Резервный ключ
]

# Фильтруем пустые значения
OPENROUTER_KEYS = [key for key in OPENROUTER_KEYS if key]

print(f"🔑 Загружено ключей: {len(OPENROUTER_KEYS)}")
for i, key in enumerate(OPENROUTER_KEYS):
    print(f"   Key {i+1}: {key[:20]}...")

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
        self.key_usage = {key: 0 for key in OPENROUTER_KEYS} if OPENROUTER_KEYS else {}
        self.load_chats()
    
    def get_api_key(self):
        """Выбирает случайный ключ"""
        if not OPENROUTER_KEYS:
            return None
        return random.choice(OPENROUTER_KEYS)
    
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
    
    def generate_fallback_response(self, user_message: str) -> str:
        """Генерация ответа когда API недоступно"""
        message_lower = user_message.lower()
        
        responses = [
            "Привет! Я DELTAGPT. В данный момент AI модели временно недоступны, но я могу помочь с базовыми вопросами.",
            "К сожалению, нейросети временно не отвечают. Вы можете попробовать позже или задать вопрос в другой форме.",
            "Сервис AI временно недоступен. Пока могу предложить: создание простого кода, объяснение концепций, помощь с идеями.",
            "Вот пример кода на Python:\n\n```python\n# Простой калькулятор\nprint('Привет! Я простой ассистент.')\n```",
            "Попробуйте переформулировать вопрос или обратиться позже, когда AI модели будут доступны."
        ]
        
        # Контекстные ответы
        if any(word in message_lower for word in ["привет", "hello", "hi", "здравствуй"]):
            return "Привет! 👋 К сожалению, AI системы временно недоступны. Чем еще могу помочь?"
        elif any(word in message_lower for word in ["код", "программир", "python", "javascript"]):
            return "Вот пример простого кода:\n\n```python\n# Приветствие на Python\ndef greet(name):\n    return f'Привет, {name}!'\n\nprint(greet('пользователь'))\n```"
        elif any(word in message_lower for word in ["помощь", "help", "команды"]):
            return "Доступные возможности:\n• Общие вопросы\n• Примеры кода\n• Объяснение концепций\n• Идеи для проектов\n\nДля полного AI функционала нужны рабочие API ключи."
        else:
            return random.choice(responses)
    
    async def try_openrouter_api(self, messages: List[Dict], model: str, max_tokens: int, temperature: float) -> Dict:
        """Попытка запроса к OpenRouter API"""
        try:
            api_key = self.get_api_key()
            if not api_key:
                return {"success": False, "error": "No API keys available"}
            
            print(f"🔄 Пробуем {model} с ключом: {api_key[:20]}...")
            
            openai_messages = []
            for msg in messages[-6:]:  # Маленький контекст для теста
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
                        "tokens_used": data.get("usage", {}).get("total_tokens", 0)
                    }
                else:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}: {response.text[:100]}"
                    }
                    
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def chat_completion(self, messages: List[Dict], chat_id: str = None, username: str = None, thinking_mode: str = "fast") -> Dict:
        try:
            # Если нет ключей - сразу fallback
            if not OPENROUTER_KEYS:
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
            
            mode_settings = {
                "fast": {"max_tokens": 1000, "temperature": 0.7},
                "deep": {"max_tokens": 2000, "temperature": 0.3},
                "creative": {"max_tokens": 1500, "temperature": 0.9}
            }
            
            settings = mode_settings.get(thinking_mode, mode_settings["fast"])
            
            # Простые стабильные модели
            models_to_try = [
                "google/gemini-2.0-flash-exp:free",
                "meta-llama/llama-3.1-8b-instruct:free",
                "microsoft/wizardlm-2-8x22b:free"
            ]
            
            for model in models_to_try:
                result = await self.try_openrouter_api(messages, model, settings["max_tokens"], settings["temperature"])
                
                if result["success"]:
                    if username:
                        self.user_manager.update_user_stats(username, result["tokens_used"])
                    
                    if chat_id:
                        self.add_message(chat_id, "assistant", result["response"], username, result["tokens_used"])
                    
                    return {
                        "success": True,
                        "response": result["response"],
                        "model": model,
                        "tokens_used": result["tokens_used"],
                        "context_length": len(messages),
                        "thinking_mode": thinking_mode
                    }
                else:
                    print(f"❌ {model}: {result['error']}")
            
            # Если все модели не сработали - fallback
            user_message = next((msg["content"] for msg in reversed(messages) if msg["role"] == "user"), "")
            fallback_response = self.generate_fallback_response(user_message)
            
            if chat_id:
                self.add_message(chat_id, "assistant", fallback_response, username, 0)
            
            return {
                "success": True,
                "response": fallback_response + "\n\n⚠️ AI модели временно недоступны. Используется упрощенный режим.",
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

# Debug endpoint для проверки ключей
@app.get("/debug/keys")
async def debug_keys():
    """Проверка работоспособности всех ключей"""
    results = []
    
    if not OPENROUTER_KEYS:
        return {"error": "❌ Нет API ключей в Environment Variables"}
    
    for i, key in enumerate(OPENROUTER_KEYS):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "google/gemini-2.0-flash-exp:free",
                        "messages": [{"role": "user", "content": "Say 'TEST' only"}],
                        "max_tokens": 5
                    },
                    timeout=10.0
                )
                
                results.append({
                    "key": f"Key_{i+1}",
                    "prefix": key[:20] + "...",
                    "status_code": response.status_code,
                    "status": "✅ Работает" if response.status_code == 200 else f"❌ Ошибка {response.status_code}",
                    "response": response.text[:100] if response.status_code != 200 else "Успех"
                })
                
        except Exception as e:
            results.append({
                "key": f"Key_{i+1}",
                "prefix": key[:20] + "...",
                "status_code": "Exception",
                "status": f"❌ {str(e)}",
                "response": None
            })
    
    return {
        "keys_loaded": len(OPENROUTER_KEYS),
        "results": results,
        "env_vars_checked": ["OPENROUTER_KEY_1", "OPENROUTER_KEY_2"]
    }

# Простой тест API
@app.get("/debug/test")
async def debug_test():
    """Простой тест API"""
    test_messages = [{"role": "user", "content": "Ответь одним словом: ТЕСТ"}]
    
    result = await deltagpt.chat_completion(test_messages)
    return {
        "api_test": result,
        "openrouter_keys_loaded": len(OPENROUTER_KEYS),
        "timestamp": datetime.now().isoformat()
    }

# Аутентификация и остальные API маршруты...
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
    print("🚀 DELTAGPT FALLBACK запускается...")
    print(f"🔑 Ключей в Environment Variables: {len(OPENROUTER_KEYS)}")
    print("🎯 Режимы: Быстрый / Глубокое / Креативный")
    print("🔄 Fallback система: АКТИВНА")
    print("🌐 Открой: http://localhost:8000")
    print("🔧 Debug: http://localhost:8000/debug/keys")
    print("🧪 Тест: http://localhost:8000/debug/test")
    
    if not OPENROUTER_KEYS:
        print("❌ ВНИМАНИЕ: Нет API ключей в Environment Variables!")
        print("📝 Добавь на Render в Settings → Environment Variables:")
        print("   OPENROUTER_KEY_1 = твой-ключ-1")
        print("   OPENROUTER_KEY_2 = твой-ключ-2")
    else:
        print("✅ Ключи загружены из Environment Variables")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
