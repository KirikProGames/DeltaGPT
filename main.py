from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import requests
import os
import json
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import uvicorn
import base64
from PIL import Image
import io
from openai import OpenAI
import jwt
from jwt.exceptions import InvalidTokenError
import aiofiles

app = FastAPI(title="DELTAGPT - Advanced AI Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Конфигурация
SECRET_KEY = "deltagpt-secret-key-2024"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 дней

# OpenRouter токены
OPENROUTER_TOKENS = [
    "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"
]

# Файлы хранения
CHATS_FILE = "chats.json"
USERS_FILE = "users.json"
PROJECTS_FILE = "projects.json"

security = HTTPBearer()

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
    project_id: Optional[str] = None
    participants: List[str] = []
    total_tokens: int = 0
    thinking_mode: str = "fast"

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
    total_requests: int = 0
    total_tokens: int = 0
    is_google_auth: bool = False
    google_id: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict

class TokenData(BaseModel):
    username: str = None

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
    
    def create_access_token(self, data: dict, expires_delta: timedelta = None):
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    def verify_token(self, token: str):
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                return None
            return TokenData(username=username)
        except InvalidTokenError:
            return None
    
    async def create_user(self, username: str, password: str = None, email: str = None, 
                         is_google: bool = False, google_id: str = None, avatar: str = None):
        async with aiofiles.open(self.users_file, 'r', encoding='utf-8') as f:
            data = json.loads(await f.read())
        
        if username in data["users"]:
            return False, "Пользователь уже существует"
        
        # Проверка email
        if email:
            for user_data in data["users"].values():
                if user_data.get("email") == email:
                    return False, "Email уже используется"
        
        user_id = secrets.token_hex(16)
        now = datetime.now().isoformat()
        
        user_data = {
            "id": user_id,
            "username": username,
            "email": email,
            "avatar": avatar,
            "tier": "premium" if is_google else "free",
            "created_at": now,
            "last_login": now,
            "total_requests": 0,
            "total_tokens": 0,
            "is_google_auth": is_google,
            "google_id": google_id
        }
        
        if not is_google and password:
            user_data["password"] = self.hash_password(password)
        
        data["users"][username] = user_data
        
        async with aiofiles.open(self.users_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        
        return True, user_data
    
    async def authenticate_user(self, username: str, password: str = None):
        async with aiofiles.open(self.users_file, 'r', encoding='utf-8') as f:
            data = json.loads(await f.read())
        
        if username not in data["users"]:
            return False, "Пользователь не найден"
        
        user_data = data["users"][username]
        
        if not user_data.get("is_google_auth", False):
            if password is None:
                return False, "Требуется пароль"
            if user_data.get("password") != self.hash_password(password):
                return False, "Неверный пароль"
        
        user_data["last_login"] = datetime.now().isoformat()
        async with aiofiles.open(self.users_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        
        return True, user_data
    
    async def get_user_by_username(self, username: str):
        async with aiofiles.open(self.users_file, 'r', encoding='utf-8') as f:
            data = json.loads(await f.read())
        
        return data["users"].get(username)
    
    async def get_user_by_email(self, email: str):
        async with aiofiles.open(self.users_file, 'r', encoding='utf-8') as f:
            data = json.loads(await f.read())
        
        for user_data in data["users"].values():
            if user_data.get("email") == email:
                return user_data
        return None
    
    async def update_user_stats(self, username: str, tokens_used: int = 0):
        async with aiofiles.open(self.users_file, 'r', encoding='utf-8') as f:
            data = json.loads(await f.read())
        
        if username in data["users"]:
            data["users"][username]["total_requests"] += 1
            data["users"][username]["total_tokens"] += tokens_used
            async with aiofiles.open(self.users_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))

class ProjectManager:
    def __init__(self):
        self.projects_file = PROJECTS_FILE
        self.init_database()
    
    def init_database(self):
        if not os.path.exists(self.projects_file):
            with open(self.projects_file, 'w', encoding='utf-8') as f:
                json.dump({"projects": {}}, f, ensure_ascii=False, indent=2)
    
    async def create_project(self, name: str, description: str, owner_id: str):
        async with aiofiles.open(self.projects_file, 'r', encoding='utf-8') as f:
            data = json.loads(await f.read())
        
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
        
        async with aiofiles.open(self.projects_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        
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
                        messages = [ChatMessage(**msg) for msg in chat_data.get("messages", [])]
                        self.sessions[chat_id] = ChatSession(
                            id=chat_id,
                            title=chat_data.get("title", "Новый чат"),
                            messages=messages,
                            created_at=chat_data.get("created_at", datetime.now().isoformat()),
                            updated_at=chat_data.get("updated_at", datetime.now().isoformat()),
                            project_id=chat_data.get("project_id"),
                            participants=chat_data.get("participants", []),
                            total_tokens=chat_data.get("total_tokens", 0),
                            thinking_mode=chat_data.get("thinking_mode", "fast")
                        )
                print(f"✅ Загружено {len(self.sessions)} чатов")
        except Exception as e:
            print(f"❌ Ошибка загрузки чатов: {e}")
            self.sessions = {}
    
    async def save_chats(self):
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
                    "participants": chat.participants,
                    "total_tokens": chat.total_tokens,
                    "thinking_mode": chat.thinking_mode
                }
            
            async with aiofiles.open(CHATS_FILE, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(chats_data, ensure_ascii=False, indent=2))
            print(f"💾 Сохранено {len(chats_data)} чатов")
        except Exception as e:
            print(f"❌ Ошибка сохранения чатов: {e}")
    
    async def create_chat(self, title: str = "Новый чат", project_id: str = None, 
                         user_id: str = None, thinking_mode: str = "fast") -> str:
        chat_id = str(uuid.uuid4())
        participants = [user_id] if user_id else []
        
        self.sessions[chat_id] = ChatSession(
            id=chat_id,
            title=title,
            messages=[],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            project_id=project_id,
            participants=participants,
            thinking_mode=thinking_mode
        )
        await self.save_chats()
        return chat_id
    
    async def add_message(self, chat_id: str, role: str, content: str, 
                         user_id: str = None, tokens: int = 0):
        if chat_id not in self.sessions:
            chat_id = await self.create_chat(user_id=user_id)
        
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
        
        await self.save_chats()
    
    def get_chat_history(self, chat_id: str) -> List[Dict]:
        if chat_id in self.sessions:
            return [msg.dict() for msg in self.sessions[chat_id].messages]
        return []
    
    async def get_user_chats(self, user_id: str) -> List[Dict]:
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
    
    async def chat_completion(self, messages: List[Dict], chat_id: str = None, 
                            username: str = None, thinking_mode: str = "fast") -> Dict:
        try:
            mode_settings = {
                "fast": {"max_tokens": 2000, "temperature": 0.7, "model": "google/gemini-2.0-flash-exp:free"},
                "deep": {"max_tokens": 4000, "temperature": 0.3, "model": "microsoft/wizardlm-2-8x22b:free"},
                "creative": {"max_tokens": 3000, "temperature": 0.9, "model": "qwen/qwen-2.5-72b-instruct:free"}
            }
            
            settings = mode_settings.get(thinking_mode, mode_settings["fast"])
            
            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=OPENROUTER_TOKENS[0],
            )
            
            system_prompt = """Ты DELTAGPT - мощный AI ассистент. Отвечай подробно и помогай пользователям.
Всегда отвечай на русском языке. Будь полезным и дружелюбным.
Форматируй ответы чисто, используй код-блоки для программирования."""
            
            openai_messages = [{"role": "system", "content": system_prompt}]
            
            for msg in messages[-10:]:  # Берем последние 10 сообщений для контекста
                openai_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            models_to_try = [
                settings["model"],
                "google/gemini-2.0-flash-exp:free",
                "meta-llama/llama-3-8b-instruct:free", 
                "microsoft/wizardlm-2-8x22b:free",
                "qwen/qwen-2.5-72b-instruct:free"
            ]
            
            for model in models_to_try:
                try:
                    print(f"🔄 Пробуем модель: {model} (режим: {thinking_mode})")
                    
                    completion = client.chat.completions.create(
                        model=model,
                        messages=openai_messages,
                        max_tokens=settings["max_tokens"],
                        temperature=settings["temperature"],
                        extra_headers={
                            "HTTP-Referer": "http://localhost:8000",
                            "X-Title": "DELTAGPT",
                        }
                    )
                    
                    assistant_message = completion.choices[0].message.content
                    tokens_used = completion.usage.total_tokens if completion.usage else self.estimate_tokens(assistant_message)
                    
                    if username:
                        await self.user_manager.update_user_stats(username, tokens_used)
                    
                    if chat_id:
                        await self.add_message(chat_id, "assistant", assistant_message, username, tokens_used)
                    
                    return {
                        "success": True,
                        "response": assistant_message,
                        "model": model,
                        "tokens_used": tokens_used,
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

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token_data = deltagpt.user_manager.verify_token(credentials.credentials)
    if token_data is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await deltagpt.user_manager.get_user_by_username(token_data.username)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# Основные маршруты
@app.get("/")
async def serve_html():
    try:
        async with aiofiles.open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=await f.read())
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
        
        success, result = await deltagpt.user_manager.create_user(username, password, email)
        if success:
            access_token = deltagpt.user_manager.create_access_token(
                data={"sub": username}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            )
            return JSONResponse({
                "success": True, 
                "user": result, 
                "access_token": access_token,
                "token_type": "bearer",
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
        
        success, result = await deltagpt.user_manager.authenticate_user(username, password)
        if success:
            access_token = deltagpt.user_manager.create_access_token(
                data={"sub": username}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            )
            return JSONResponse({
                "success": True, 
                "user": result,
                "access_token": access_token,
                "token_type": "bearer"
            })
        else:
            return JSONResponse({"success": False, "message": result})
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Ошибка: {str(e)}"})

# Google OAuth
@app.post("/auth/google")
async def google_auth(request: Request):
    try:
        data = await request.json()
        google_token = data.get("token")
        
        # В реальном приложении здесь должна быть верификация Google token
        # Для демо создаем пользователя на основе Google данных
        google_data = data.get("profile")
        email = google_data.get("email")
        name = google_data.get("name")
        google_id = google_data.get("sub")
        avatar = google_data.get("picture")
        
        # Генерируем username из email
        username = email.split('@')[0]
        
        # Проверяем существует ли пользователь
        existing_user = await deltagpt.user_manager.get_user_by_email(email)
        if existing_user:
            user_data = existing_user
        else:
            success, user_data = await deltagpt.user_manager.create_user(
                username=username,
                email=email,
                is_google=True,
                google_id=google_id,
                avatar=avatar
            )
            if not success:
                return JSONResponse({"success": False, "message": user_data})
        
        access_token = deltagpt.user_manager.create_access_token(
            data={"sub": user_data["username"]}, 
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        
        return JSONResponse({
            "success": True,
            "user": user_data,
            "access_token": access_token,
            "token_type": "bearer"
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Ошибка Google auth: {str(e)}"})

# API чата
@app.post("/api/chat")
async def chat_api(request: Request, current_user: dict = Depends(get_current_user)):
    try:
        data = await request.json()
        message = data.get("message", "")
        chat_id = data.get("chat_id")
        thinking_mode = data.get("thinking_mode", "fast")
        
        if not message:
            return JSONResponse({"success": False, "response": "Пустое сообщение"})
        
        if not chat_id:
            chat_id = await deltagpt.create_chat(
                user_id=current_user["id"], 
                thinking_mode=thinking_mode
            )
        
        await deltagpt.add_message(chat_id, "user", message, current_user["id"])
        
        history = deltagpt.get_chat_history(chat_id)
        
        result = await deltagpt.chat_completion(
            history, chat_id, current_user["username"], thinking_mode
        )
        result["chat_id"] = chat_id
        
        return JSONResponse(result)
        
    except Exception as e:
        return JSONResponse({
            "success": False, 
            "response": f"❌ Server error: {str(e)}"
        })

# API чатов пользователя
@app.get("/api/chats/user/{username}")
async def get_user_chats(username: str, current_user: dict = Depends(get_current_user)):
    try:
        if current_user["username"] != username:
            return JSONResponse({"success": False, "message": "Access denied"})
        
        chats = await deltagpt.get_user_chats(current_user["id"])
        return JSONResponse({"success": True, "chats": chats})
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)})

# API получения конкретного чата
@app.get("/api/chat/{chat_id}")
async def get_chat(chat_id: str, current_user: dict = Depends(get_current_user)):
    try:
        history = deltagpt.get_chat_history(chat_id)
        chat_info = None
        
        if chat_id in deltagpt.sessions:
            chat = deltagpt.sessions[chat_id]
            if current_user["id"] not in chat.participants and chat.participants:
                return JSONResponse({"success": False, "message": "Access denied"})
            
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
async def clear_chat(chat_id: str, current_user: dict = Depends(get_current_user)):
    try:
        if chat_id in deltagpt.sessions:
            if current_user["id"] not in deltagpt.sessions[chat_id].participants and deltagpt.sessions[chat_id].participants:
                return JSONResponse({"success": False, "message": "Access denied"})
            
            deltagpt.sessions[chat_id].messages = []
            deltagpt.sessions[chat_id].total_tokens = 0
            await deltagpt.save_chats()
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)})

# API удаления чата
@app.delete("/api/chat/{chat_id}")
async def delete_chat(chat_id: str, current_user: dict = Depends(get_current_user)):
    try:
        if chat_id in deltagpt.sessions:
            if current_user["id"] not in deltagpt.sessions[chat_id].participants and deltagpt.sessions[chat_id].participants:
                return JSONResponse({"success": False, "message": "Access denied"})
            
            del deltagpt.sessions[chat_id]
            await deltagpt.save_chats()
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)})

# Экспорт чата
@app.get("/api/chat/{chat_id}/export")
async def export_chat(chat_id: str, current_user: dict = Depends(get_current_user)):
    try:
        if chat_id not in deltagpt.sessions:
            return JSONResponse({"success": False, "message": "Чат не найден"})
        
        chat = deltagpt.sessions[chat_id]
        if current_user["id"] not in chat.participants and chat.participants:
            return JSONResponse({"success": False, "message": "Access denied"})
        
        export_data = {
            "title": chat.title,
            "created_at": chat.created_at,
            "updated_at": chat.updated_at,
            "total_messages": len(chat.messages),
            "total_tokens": chat.total_tokens,
            "messages": [msg.dict() for msg in chat.messages]
        }
        
        return JSONResponse({
            "success": True,
            "export_data": export_data,
            "filename": f"deltagpt_chat_{chat_id[:8]}.json"
        })
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)})

if __name__ == "__main__":
    print("🚀 DELTAGPT MODERN запускается...")
    print("🎯 Модели: Gemini 2.0, Llama 3, WizardLM")
    print("🧠 Режимы: Быстрый / Глубокое / Креативный")
    print("🔐 Аутентификация: JWT + Google OAuth")
    print("💾 Сохранение чатов: АКТИВНО")
    print("🌐 Открой: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
