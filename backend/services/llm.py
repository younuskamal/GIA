"""
خدمة LLM - نظام Hybrid للذكاء الاصطناعي
يدعم Local (LM Studio) + Cloud API
"""
import httpx
import time
import os
import sys
from pathlib import Path

# Add root backend to sys.path
BASE_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_BACKEND not in sys.path:
    sys.path.append(BASE_BACKEND)

from core.config import LM_STUDIO_URL, LM_STUDIO_MODEL, CLOUD_API_KEY, CLOUD_API_URL, CLOUD_MODEL

# ==================== Local LLM ====================
async def call_lm_studio(user_message: str, system_prompt: str) -> dict:
    """استدعاء LM Studio (Local)"""
    start_time = time.time()
    
    # Merge system prompt with user message for better compatibility with local templates
    combined_message = f"{system_prompt}\n\nUser Message: {user_message}"
    
    payload = {
        "model": LM_STUDIO_MODEL,
        "messages": [
            {"role": "user", "content": combined_message}
        ],
        "temperature": 0.5,
        "max_tokens": 1024,
        "stream": False
    }
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(LM_STUDIO_URL, json=payload)
            if response.status_code == 400:
                return {
                    "success": False,
                    "error": "bad_request",
                    "message": f"LM Studio 400: {response.text}"
                }
            
            response.raise_for_status()
            data = response.json()
            
            assistant_message = data["choices"][0]["message"]["content"]
            processing_time = int((time.time() - start_time) * 1000)
            
            return {
                "success": True,
                "response": assistant_message,
                "model": data.get("model", LM_STUDIO_MODEL),
                "processing_time_ms": processing_time,
                "source": "lm_studio_local"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": "local_failed",
            "message": str(e)
        }

# ==================== Cloud API (Groq) ====================
async def call_cloud_api(user_message: str, system_prompt: str) -> dict:
    """استدعاء Cloud API (Groq)"""
    if not CLOUD_API_KEY:
        return {
            "success": False,
            "error": "not_configured",
            "message": "Groq API Key missing."
        }
    
    start_time = time.time()
    
    payload = {
        "model": CLOUD_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.5,
        "max_tokens": 1024
    }
    
    headers = {
        "Authorization": f"Bearer {CLOUD_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(CLOUD_API_URL, json=payload, headers=headers)
            if response.status_code == 400:
                return {
                    "success": False,
                    "error": "bad_request",
                    "message": f"Groq 400: {response.text}"
                }
                
            response.raise_for_status()
            data = response.json()
            
            assistant_message = data["choices"][0]["message"]["content"]
            processing_time = int((time.time() - start_time) * 1000)
            
            return {
                "success": True,
                "response": assistant_message,
                "model": CLOUD_MODEL,
                "processing_time_ms": processing_time,
                "source": "groq_cloud"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": "cloud_failed",
            "message": str(e)
        }

# ==================== Hybrid System ====================
async def call_hybrid_llm(user_message: str, system_prompt: str) -> dict:
    """نظام هجين ذكي للرد"""
    llm_mode = os.getenv("LLM_MODE", "auto")
    
    if llm_mode == "local":
        return await call_lm_studio(user_message, system_prompt)
    elif llm_mode == "api":
        return await call_cloud_api(user_message, system_prompt)
    
    # Auto Mode (Fallback)
    # 1. Try Local
    local_res = await call_lm_studio(user_message, system_prompt)
    if local_res["success"]:
        return local_res
        
    # 2. Try Cloud if Local fails
    print(f"⚠️ Local LLM failed: {local_res['message']}. Trying Cloud...")
    cloud_res = await call_cloud_api(user_message, system_prompt)
    if cloud_res["success"]:
        return cloud_res
        
    # All failed
    return {
        "success": False,
        "error": "all_failed",
        "message": f"Local: {local_res['message']} | Cloud: {cloud_res['message']}"
    }
