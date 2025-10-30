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
import random
from openai import OpenAI  # Добавляем официальный SDK

app = FastAPI(title="DELTAGPT - Advanced AI Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API ключи - DeepSeek + OpenRouter
DEEPSEEK_API_KEY = "sk-29b953857b824c7f949e0f2b4a2c2f86"  # Ваш ключ
OPENROUTER_KEYS = [
    os.getenv("OPENROUTER_KEY_1"),
    os.getenv("OPENROUTER_KEY_2")
]
OPENROUTER_KEYS = [key for key in OPENROUTER_KEYS if key]

print("🔑 Загружено API ключей:")
print(f"   DeepSeek: {DEEPSEEK_API_KEY[:20]}...")
print(f"   OpenRouter: {len(OPENROUTER_KEYS)} ключей")

# Инициализация DeepSeek клиента
deepseek_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

# Файлы хранения
CHATS_FILE = "chats.json"
USERS_FILE = "users.json"

# ... (остальные классы остаются без изменений до метода try_deepseek_api)

class DeltaGPT:
    # ... (все предыдущие методы остаются без изменений)
    
    async def try_deepseek_api(self, messages: List[Dict], max_tokens: int, temperature: float) -> Dict:
        """Запрос к DeepSeek API через официальный SDK"""
        try:
            print("🔄 Пробуем DeepSeek API (официальный SDK)...")
            
            # Форматируем сообщения для DeepSeek
            deepseek_messages = []
            for msg in messages[-10:]:
                deepseek_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            # Используем официальный SDK как в гайде
            response = deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=deepseek_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False
            )
            
            print(f"✅ DeepSeek ответ получен успешно!")
            
            return {
                "success": True,
                "response": response.choices[0].message.content,
                "tokens_used": response.usage.total_tokens if response.usage else self.estimate_tokens(response.choices[0].message.content),
                "model": "deepseek-chat"
            }
                    
        except Exception as e:
            error_msg = f"DeepSeek Exception: {str(e)}"
            print(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}
    
    async def try_openrouter_api(self, messages: List[Dict], model: str, max_tokens: int, temperature: float) -> Dict:
        """Запрос к OpenRouter API (остается как было)"""
        try:
            if not OPENROUTER_KEYS:
                return {"success": False, "error": "No OpenRouter keys"}
            
            import httpx  # Импортируем здесь для OpenRouter
            
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

    # ... (остальные методы остаются без изменений)

# Инициализация
deltagpt = DeltaGPT()

# ... (остальной код маршрутов остается без изменений)
