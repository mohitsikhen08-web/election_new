
import os
import uuid
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL missing. Check your .env file.")

app = FastAPI(title="Digital Jan Samvad API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Neon PostgreSQL connection
def connect():
    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
        connect_timeout=10
    )

# Initialize database
def init_db():
    with connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                reference TEXT PRIMARY KEY,
                language TEXT NOT NULL,
                area TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

init_db()


class Complaint(BaseModel):
    language: Literal["en", "hi", "pa"] = "en"
    area: str = Field(min_length=2, max_length=120)
    category: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=4, max_length=160)
    description: str = Field(min_length=10, max_length=3000)


class ChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    language: Literal["en", "hi", "pa"] = "en"


@app.get("/")
def home():
    return {
        "service": "Digital Jan Samvad",
        "status": "running",
        "database": "Neon PostgreSQL"
    }


@app.get("/api/health")
def health():
    try:
        with connect() as con:
            con.execute("SELECT 1")

        return {"ok": True, "database": "connected"}

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed"
        )


@app.post("/api/complaints", status_code=201)
def create_complaint(item: Complaint):
    reference = "DJS-" + uuid.uuid4().hex[:10].upper()
    created = datetime.now(timezone.utc).isoformat()

    with connect() as con:
        con.execute("""
            INSERT INTO complaints
            (reference, language, area, category, title,
             description, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            reference,
            item.language,
            item.area.strip(),
            item.category,
            item.title.strip(),
            item.description.strip(),
            "Received",
            created
        ))

    return {
        "reference": reference,
        "status": "Received",
        "created_at": created
    }


@app.get("/api/complaints/{reference}")
def track_complaint(reference: str):
    with connect() as con:
        row = con.execute("""
            SELECT reference, area, category, title,
                   status, created_at
            FROM complaints
            WHERE reference = %s
        """, (reference.upper(),)).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Reference not found"
        )

    return row


@app.get("/api/dashboard")
def dashboard():
    with connect() as con:
        total = con.execute(
            "SELECT COUNT(*) AS n FROM complaints"
        ).fetchone()["n"]

        categories = con.execute("""
            SELECT category, COUNT(*) AS count
            FROM complaints
            GROUP BY category
        """).fetchall()

        statuses = con.execute("""
            SELECT status, COUNT(*) AS count
            FROM complaints
            GROUP BY status
        """).fetchall()

    return {
        "total": total,
        "categories": categories,
        "statuses": statuses
    }


@app.post("/api/chat")
def chatbot(item: ChatMessage):
    msg = item.message.lower()

    if item.language == "hi":
        if any(x in msg for x in ["स्टेटस", "स्थिति", "ट्रैक"]):
            answer = "शिकायत ट्रैक पेज पर अपना रेफरेंस नंबर डालें।"
        else:
            answer = "मैं शिकायत दर्ज करने और रेफरेंस नंबर से स्थिति देखने में मदद कर सकता हूँ।"

    elif item.language == "pa":
        if any(x in msg for x in ["ਸਟੇਟਸ", "ਸਥਿਤੀ", "ਟ੍ਰੈਕ"]):
            answer = "ਸ਼ਿਕਾਇਤ ਟ੍ਰੈਕ ਪੇਜ ਉੱਤੇ ਆਪਣਾ ਰੈਫਰੈਂਸ ਨੰਬਰ ਭਰੋ।"
        else:
            answer = "ਮੈਂ ਸ਼ਿਕਾਇਤ ਦਰਜ ਕਰਨ ਅਤੇ ਸਥਿਤੀ ਦੇਖਣ ਵਿੱਚ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ।"

    else:
        if any(x in msg for x in ["status", "track", "reference"]):
            answer = "Open Track Complaint and enter your reference number."
        else:
            answer = "I can help you submit a complaint or track an existing request."

    return {"reply": answer}
