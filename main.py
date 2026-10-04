import csv
import io
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")

engine = (
    create_engine(DATABASE_URL, pool_pre_ping=True)
    if DATABASE_URL
    else None
)

app = FastAPI(
    title="DataVortex AI API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    if engine:
        with engine.begin() as db:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id BIGSERIAL PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    date DATE,
                    description TEXT,
                    category TEXT,
                    amount NUMERIC(14,2) NOT NULL,
                    type TEXT NOT NULL DEFAULT 'expense'
                )
            """))


@app.get("/")
def root():
    return FileResponse("index.html")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "database": bool(engine)
    }


@app.get("/auth/demo")
def demo_token():
    payload = {
        "org_id": "demo",
        "exp": datetime.now(timezone.utc) + timedelta(hours=24)
    }

    token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm="HS256"
    )

    return {
        "access_token": token
    }


def org_from_token(token: str):
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=["HS256"]
        )

        return payload.get("org_id", "demo")

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Token inválido"
        )


@app.post("/transactions/upload")
async def upload_transactions(
    file: UploadFile = File(...),
    token: str = "demo"
):
    if not engine:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL não configurada"
        )

    content = (
        await file.read()
    ).decode("utf-8-sig")

    rows = csv.DictReader(
        io.StringIO(content)
    )

    org = org_from_token(token)
    count = 0

    with engine.begin() as db:
        for row in rows:

            raw_amount = (
                row.get("amount")
                or row.get("valor")
                or "0"
            )

            amount = float(
                raw_amount.replace(",", ".")
            )

            db.execute(
                text("""
                    INSERT INTO transactions
                    (
                        org_id,
                        date,
                        description,
                        category,
                        amount,
                        type
                    )
                    VALUES
                    (
                        :org,
                        :date,
                        :description,
                        :category,
                        :amount,
                        :type
                    )
                """),
                {
                    "org": org,
                    "date": (
                        row.get("date")
                        or row.get("data")
                    ),
                    "description": (
                        row.get("description")
                        or row.get("descricao")
                    ),
                    "category": (
                        row.get("category")
                        or row.get("categoria")
                    ),
                    "amount": abs(amount),
                    "type": (
                        row.get("type")
                        or row.get("tipo")
                        or "expense"
                    )
                }
            )

            count += 1

    return {
        "inserted": count
    }


@app.get("/analytics/summary")
def analytics(token: str = "demo"):

    if not engine:
        return {
            "revenue": 0,
            "expenses": 0,
            "margin": 0,
            "cashflow": 0
        }

    org = org_from_token(token)

    with engine.begin() as db:
        result = db.execute(
            text("""
                SELECT
                    COALESCE(
                        SUM(
                            CASE
                                WHEN type = 'revenue'
                                THEN amount
                                ELSE 0
                            END
                        ),
                        0
                    ) AS revenue,

                    COALESCE(
                        SUM(
                            CASE
                                WHEN type <> 'revenue'
                                THEN amount
                                ELSE 0
                            END
                        ),
                        0
                    ) AS expenses

                FROM transactions

                WHERE org_id = :org
            """),
            {
                "org": org
            }
        ).mappings().one()

    revenue = float(result["revenue"])
    expenses = float(result["expenses"])

    cashflow = revenue - expenses

    margin = (
        cashflow / revenue * 100
        if revenue
        else 0
    )

    return {
        "revenue": revenue,
        "expenses": expenses,
        "margin": margin,
        "cashflow": cashflow
  }
