from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests
import os
import json
import uuid
import hashlib
import secrets
from datetime import datetime
from typing import List, Dict, Optional
import uvicorn
import base64
from PIL import Image
import io
from openai import OpenAI

app = FastAPI(title="DELTAGPT - Unlimited AI Collaboration")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Только рабочий токен
OPENROUTER_TOKENS = [
    "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"
]

# Хранилище
CHATS_FILE = "chats.json"
USERS_FILE = "users.json"
PROJECTS_FILE = "projects.json"

class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: str
    user_id: Optional[str] = None

class ChatSession(BaseModel):
    id: str
    title: str
    messages: List[ChatMessage]
    created_at: str
    updated_at: str
    project_id: Optional[str] = None
    participants: List[str] = []

class Project(BaseModel):
    id: str
    name: str
    description: str
    owner_id: str
    members: List[str]
    created_at: str
    updated_at: str
    chat_sessions: List[str] = []

class User(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    password: Optional[str] = None
    avatar: Optional[str] = None
    tier: str = "free"
    created_at: str
    last_login: str
    images_uploaded_today: int = 0
    last_upload_date: Optional[str] = None
    total_requests: int = 0
    is_google_auth: bool = False

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
    
    def create_user(self, username: str, password: str = None, email: str = None, is_google: bool = False):
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
            "tier": "premium" if is_google else "free",
            "created_at": now,
            "last_login": now,
            "images_uploaded_today": 0,
            "last_upload_date": now,
            "total_requests": 0,
            "is_google_auth": is_google
        }
        
        if not is_google and password:
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
        
        if not user_data.get("is_google_auth", False):
            if password is None:
                return False, "Требуется пароль"
            if user_data.get("password") != self.hash_password(password):
                return False, "Неверный пароль"
        
        user_data["last_login"] = datetime.now().isoformat()
        with open(self.users_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return True, user_data
    
    def get_user_by_username(self, username: str):
        with open(self.users_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return data["users"].get(username)
    
    def update_user_requests(self, username: str):
        with open(self.users_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if username in data["users"]:
            data["users"][username]["total_requests"] += 1
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

class ProjectManager:
    def __init__(self):
        self.projects_file = PROJECTS_FILE
        self.init_database()
    
    def init_database(self):
        if not os.path.exists(self.projects_file):
            with open(self.projects_file, 'w', encoding='utf-8') as f:
                json.dump({"projects": {}}, f, ensure_ascii=False, indent=2)
    
    def create_project(self, name: str, description: str, owner_id: str):
        with open(self.projects_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        project_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        project_data = {
            "id": project_id,
            "name": name,
            "description": description,
            "owner_id": owner_id,
            "members": [owner_id],
            "created_at": now,
            "updated_at": now,
            "chat_sessions": []
        }
        
        data["projects"][project_id] = project_data
        
        with open(self.projects_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return project_data

class DeltaGPT:
    def __init__(self):
        self.sessions: Dict[str, ChatSession] = {}
        self.user_manager = UserManager()
        self.project_manager = ProjectManager()
        self.load_chats()
    
    def load_chats(self):
        try:
            if os.path.exists(CHATS_FILE):
                with open(CHATS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for chat_id, chat_data in data.items():
                        # Восстанавливаем сообщения
                        messages = [ChatMessage(**msg) for msg in chat_data.get("messages", [])]
                        self.sessions[chat_id] = ChatSession(
                            id=chat_id,
                            title=chat_data.get("title", "Безымянный чат"),
                            messages=messages,
                            created_at=chat_data.get("created_at", datetime.now().isoformat()),
                            updated_at=chat_data.get("updated_at", datetime.now().isoformat()),
                            project_id=chat_data.get("project_id"),
                            participants=chat_data.get("participants", [])
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
                    "project_id": chat.project_id,
                    "participants": chat.participants
                }
            
            with open(CHATS_FILE, 'w', encoding='utf-8') as f:
                json.dump(chats_data, f, ensure_ascii=False, indent=2)
            print(f"💾 Сохранено {len(chats_data)} чатов")
        except Exception as e:
            print(f"❌ Ошибка сохранения чатов: {e}")
    
    def create_chat(self, title: str = "Новый чат", project_id: str = None, user_id: str = None) -> str:
        chat_id = str(uuid.uuid4())
        participants = [user_id] if user_id else []
        
        self.sessions[chat_id] = ChatSession(
            id=chat_id,
            title=title,
            messages=[],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            project_id=project_id,
            participants=participants
        )
        self.save_chats()
        return chat_id
    
    def add_message(self, chat_id: str, role: str, content: str, user_id: str = None):
        if chat_id not in self.sessions:
            # Если чата нет, создаем новый
            chat_id = self.create_chat(user_id=user_id)
        
        message = ChatMessage(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            user_id=user_id
        )
        self.sessions[chat_id].messages.append(message)
        self.sessions[chat_id].updated_at = datetime.now().isoformat()
        
        # Обновляем заголовок если это первое сообщение
        if len(self.sessions[chat_id].messages) == 1:
            clean_content = content.replace('\n', ' ').strip()
            self.sessions[chat_id].title = clean_content[:40] + "..." if len(clean_content) > 40 else clean_content
        
        # Добавляем пользователя в участники если его там нет
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
                user_chats.append({
                    "id": chat.id,
                    "title": chat.title,
                    "last_message": chat.messages[-1].content if chat.messages else "Нет сообщений",
                    "updated_at": chat.updated_at,
                    "message_count": len(chat.messages)
                })
        
        return sorted(user_chats, key=lambda x: x['updated_at'], reverse=True)
    
    def chat_completion(self, messages: List[Dict], chat_id: str = None, username: str = None, thinking_mode: str = "fast") -> Dict:
        try:
            # Настройки в зависимости от режима мышления
            mode_settings = {
                "fast": {"max_tokens": 2000, "temperature": 0.7},
                "deep": {"max_tokens": 4000, "temperature": 0.3}
            }
            
            settings = mode_settings.get(thinking_mode, mode_settings["fast"])
            
            # Создаем клиент OpenAI с OpenRouter
            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=OPENROUTER_TOKENS[0],
            )
            
            system_prompt = """Ты DELTAGPT - мощный AI ассистент. Отвечай подробно и помогай пользователям.
Всегда отвечай на русском языке. Будь полезным и дружелюбным.
Форматируй ответы чисто, без Markdown разметки (**жирный**, ### заголовки)."""
            
            # Формируем сообщения для OpenAI API
            openai_messages = [{"role": "system", "content": system_prompt}]
            
            for msg in messages:
                openai_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            # Пробуем разные модели
            models_to_try = [
                "google/gemini-2.0-flash-exp:free",
                "meta-llama/llama-3-8b-instruct:free", 
                "microsoft/wizardlm-2-8x22b:free",
                "qwen/qwen-2.5-72b-instruct:free"
            ]
            
            for model in models_to_try:
                try:
                    print(f"🔄 Пробуем модель: {model} (режим: {thinking_mode})")
                    
                    completion = client.chat.completions.create(
                        extra_headers={
                            "HTTP-Referer": "http://localhost:8000",
                            "X-Title": "DELTAGPT",
                        },
                        model=model,
                        messages=openai_messages,
                        max_tokens=settings["max_tokens"],
                        temperature=settings["temperature"]
                    )
                    
                    assistant_message = completion.choices[0].message.content
                    
                    # Обновляем статистику пользователя
                    if username:
                        self.user_manager.update_user_requests(username)
                    
                    if chat_id:
                        self.add_message(chat_id, "assistant", assistant_message, username)
                    
                    return {
                        "success": True,
                        "response": assistant_message,
                        "model": model,
                        "context_length": len(messages),
                        "thinking_mode": thinking_mode
                    }
                    
                except Exception as e:
                    print(f"❌ Модель {model} не сработала: {str(e)}")
                    continue
            
            return {
                "success": False,
                "response": "❌ Все модели недоступны. Попробуйте позже.",
                "model": "unknown",
                "context_length": len(messages)
            }
                
        except Exception as e:
            return {
                "success": False,
                "response": f"❌ Ошибка: {str(e)}",
                "model": "unknown",
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
            return JSONResponse({"success": True, "user": result, "message": "Регистрация успешна"})
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
            return JSONResponse({"success": True, "user": result})
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
        
        # Создаем новый чат если не передан chat_id
        if not chat_id:
            chat_id = deltagpt.create_chat(user_id=username)
        
        # Добавляем сообщение пользователя
        deltagpt.add_message(chat_id, "user", message, username)
        
        # Получаем историю чата
        history = deltagpt.get_chat_history(chat_id)
        
        # Отправляем в AI
        result = deltagpt.chat_completion(history, chat_id, username, thinking_mode)
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
                "message_count": len(chat.messages)
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

if __name__ == "__main__":
    print("🚀 DELTAGPT ULTRA запускается...")
    print("🎯 Модели: Gemini 2.0, Llama 3, WizardLM")
    print("🧠 Режимы: Быстрый / Глубокое мышление")
    print("💾 Сохранение чатов: АКТИВНО")
    print("🌐 Открой: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)