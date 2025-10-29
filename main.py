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

app = FastAPI(title="DELTAGPT - Advanced AI Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenRouter токены
OPENROUTER_API_KEY = "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"

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
            print(f"💾 Сохранено {len(chats_data)} чатов")
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
    
    async def chat_completion(self, messages: List[Dict], chat_id: str = None, username: str = None, thinking_mode: str = "fast") -> Dict:
        try:
            mode_settings = {
                "fast": {"max_tokens": 4000, "temperature": 0.7},
                "deep": {"max_tokens": 8000, "temperature": 0.3},
                "creative": {"max_tokens": 6000, "temperature": 0.9}
            }
            
            settings = mode_settings.get(thinking_mode, mode_settings["fast"])
            
            system_prompt = """Ты DELTAGPT - мощный AI ассистент. Отвечай подробно и помогай пользователям.
Всегда отвечай на русском языке. Будь полезным и дружелюбным.
Форматируй ответы чисто, используй код-блоки для программирования."""
            
            openai_messages = [{"role": "system", "content": system_prompt}]
            
            for msg in messages[-15:]:  # Увеличили контекст
                openai_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            # ПРИОРИТЕТНЫЕ МОДЕЛИ для безлимитного ключа
            models_to_try = [
                # Платные мощные модели
                "openai/gpt-4",
                "anthropic/claude-3.5-sonnet",
                "google/gemini-2.0-flash-thinking-exp",
                "meta-llama/llama-3.1-70b-instruct",
                
                # Бесплатные но стабильные
                "google/gemini-2.0-flash-exp:free",
                "anthropic/claude-3.5-sonnet:free", 
                "meta-llama/llama-3.1-8b-instruct:free",
                "microsoft/wizardlm-2-8x22b:free"
            ]
            
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://deltagpt.onrender.com",
                "X-Title": "DELTAGPT"
            }
            
            async with httpx.AsyncClient() as client:
                for model in models_to_try:
                    try:
                        print(f"🔄 Пробуем модель: {model}")
                        
                        payload = {
                            "model": model,
                            "messages": openai_messages,
                            "max_tokens": settings["max_tokens"],
                            "temperature": settings["temperature"],
                            "stream": False
                        }
                        
                        response = await client.post(
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers=headers,
                            json=payload,
                            timeout=60.0  # Увеличили таймаут
                        )
                        
                        print(f"📥 Ответ от {model}: {response.status_code}")
                        
                        if response.status_code == 200:
                            data = response.json()
                            assistant_message = data["choices"][0]["message"]["content"]
                            tokens_used = data.get("usage", {}).get("total_tokens", self.estimate_tokens(assistant_message))
                            
                            if username:
                                self.user_manager.update_user_stats(username, tokens_used)
                            
                            if chat_id:
                                self.add_message(chat_id, "assistant", assistant_message, username, tokens_used)
                            
                            return {
                                "success": True,
                                "response": assistant_message,
                                "model": model,
                                "tokens_used": tokens_used,
                                "context_length": len(messages),
                                "thinking_mode": thinking_mode
                            }
                        else:
                            error_text = response.text[:200] if response.text else "No error message"
                            print(f"❌ Ошибка {response.status_code} от {model}: {error_text}")
                            continue
                            
                    except httpx.TimeoutException:
                        print(f"⏰ Таймаут для модели: {model}")
                        continue
                    except Exception as e:
                        print(f"❌ Исключение для {model}: {str(e)}")
                        continue
            
            return {
                "success": False,
                "response": "❌ Все модели недоступны. Попробуйте позже или проверьте API ключ.",
                "model": "unknown",
                "tokens_used": 0,
                "context_length": len(messages)
            }
                
        except Exception as e:
            print(f"❌ Критическая ошибка в chat_completion: {str(e)}")
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

# Аутентификация
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

# API чата
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

# API чатов пользователя
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

# API получения конкретного чата
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

# API очистки чата
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

# API удаления чата
@app.delete("/api/chat/{chat_id}")
async def delete_chat(chat_id: str):
    try:
        if chat_id in deltagpt.sessions:
            del deltagpt.sessions[chat_id]
            deltagpt.save_chats()
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)})

# Debug endpoint для проверки ключа
@app.get("/debug/key")
async def debug_key():
    """Проверка работоспособности ключа"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                timeout=10.0
            )
            
            return {
                "status_code": response.status_code,
                "response": response.text,
                "key_prefix": OPENROUTER_API_KEY[:20] + "..."
            }
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    print("🚀 DELTAGPT ULTRA запускается...")
    print("🎯 Модели: GPT-4, Claude 3.5, Gemini 2.0")
    print("🧠 Режимы: Быстрый / Глубокое / Креативный") 
    print("💎 Безлимитный API ключ: АКТИВНО")
    print("💾 Сохранение чатов: АКТИВНО")
    print("🌐 Открой: http://localhost:8000")
    print("🔧 Debug: http://localhost:8000/debug/key")
    uvicorn.run(app, host="0.0.0.0", port=8000)


