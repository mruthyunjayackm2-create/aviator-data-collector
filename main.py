import os
from datetime import datetime, timezone
from decimal import Decimal

import psycopg
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Aviator Data Collector")

DATABASE_URL = os.getenv("DATABASE_URL")
API_KEY = os.getenv("API_KEY")


def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg.connect(DATABASE_URL)


def verify_key(key):
    if not API_KEY or key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.on_event("startup")
def setup_database():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rounds (
                id BIGSERIAL PRIMARY KEY,
                round_id TEXT UNIQUE NOT NULL,
                multiplier NUMERIC(12, 2) NOT NULL,
                recorded_at TIMESTAMPTZ NOT NULL,
                source TEXT NOT NULL
            )
        """)


class Round(BaseModel):
    round_id: str = Field(min_length=1, max_length=100)
    multiplier: Decimal = Field(gt=0)
    recorded_at: datetime
    source: str = Field(min_length=1, max_length=100)


@app.get("/")
def home():
    return {"status": "Aviator Data Collector is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/rounds")
def add_round(data: Round, x_api_key: str = Header()):
    verify_key(x_api_key)

    if data.recorded_at.tzinfo is None:
        raise HTTPException(
            status_code=400,
            detail="Timestamp must include a timezone"
        )

    with get_db() as conn:
        result = conn.execute("""
            INSERT INTO rounds
                (round_id, multiplier, recorded_at, source)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (round_id) DO NOTHING
            RETURNING round_id
        """, (
            data.round_id,
            data.multiplier,
            data.recorded_at,
            data.source
        )).fetchone()

    return {
        "saved": result is not None,
        "duplicate": result is None
    }


@app.get("/rounds")
def get_rounds(x_api_key: str = Header()):
    verify_key(x_api_key)

    with get_db() as conn:
        rows = conn.execute("""
            SELECT round_id, multiplier, recorded_at, source
            FROM rounds
            ORDER BY recorded_at DESC
            LIMIT 100
        """).fetchall()

    return [
        {
            "round_id": row[0],
            "multiplier": float(row[1]),
            "recorded_at": row[2].isoformat(),
            "source": row[3]
        }
        for row in rows
    ]
