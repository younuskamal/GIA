"""
GIA API - Unified Gateway
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
import threading
import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import from new structure
from core.config import PROJECT_NAME, VERSION, DESCRIPTION, LLM_MODE, SYSTEM_PROMPT, DISCLAIMER
from core.db import get_price_range, get_latest_price, get_recent_news
from core.registry import ModelManager
from engine.inference import GoldAnalysisModel
from services.llm import call_hybrid_llm
from services.scheduler import run_scheduler, manual_train_trigger

# Instance
gold_model = GoldAnalysisModel()

app = FastAPI(title=PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatMessage(BaseModel):
    message: str

@app.get("/")
async def root():
    return {"service": PROJECT_NAME, "version": VERSION, "status": "active"}

@app.get("/analysis/technical")
async def get_technical_analysis():
    res = gold_model.analyze()
    if res['success']: return res
    raise HTTPException(status_code=500, detail=res['error'])

@app.post("/train/manual")
async def trigger_manual_training():
    return manual_train_trigger()

@app.get("/model/status")
async def get_model_status():
    manager = ModelManager()
    return {
        "status": gold_model.manager.get_model_status_info(),
        "registry": manager.get_registry()
    }

@app.post("/chat")
async def chat(message: ChatMessage):
    user_msg = message.message.strip()
    # Simple logic for now, using the new inference engine
    analysis = gold_model.analyze()
    
    context = f"Current Analysis: {analysis['decision']} (Conf: {analysis['confidence']}%)\n"
    prompt = SYSTEM_PROMPT.format(historical_context=context, confidence=analysis['confidence'])
    
    result = await call_hybrid_llm(user_msg, prompt)
    return {
        "response": result["response"],
        "confidence": analysis['confidence'] / 100.0,
        "metadata": {"source": result["source"], "model": result["model"]}
    }

if __name__ == "__main__":
    import uvicorn
    # Start scheduler
    threading.Thread(target=run_scheduler, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8000)
