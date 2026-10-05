import csv
import io
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")

engine = (
    create_engine(
        DATABASE_URL.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1
        ),
        pool_pre_ping=True
    )
    if DATABASE_URL
    else None
)

app = FastAPI(
    title="DataVortex AI API",
    version="1.1.0"
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
    database_ok = False

    if engine:
        try:
            with engine.connect() as db:
                db.execute(text("SELECT 1"))

            database_ok = True

        except Exception:
            database_ok = False

    return {
        "status": "ok",
        "database": database_ok
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


def normalize_key(value):
    value = (value or "").strip().lower()

    return "".join(
        c
        for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )


def row_value(row, *names):
    normalized = {
        normalize_key(k): v
        for k, v in row.items()
        if k
    }

    for name in names:
        value = normalized.get(
            normalize_key(name)
        )

        if value not in (None, ""):
            return value.strip()

    return ""


def parse_amount(value):
    raw = str(value or "0").strip()

    raw = re.sub(
        r"[^0-9,.-]",
        "",
        raw
    )

    if "," in raw and "." in raw:

        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "")
            raw = raw.replace(",", ".")

        else:
            raw = raw.replace(",", "")

    elif "," in raw:
        raw = raw.replace(".", "")
        raw = raw.replace(",", ".")

    return abs(float(raw or 0))


def parse_date(value):
    value = str(value or "").strip()

    if not value:
        return None

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(
                value,
                fmt
            ).date()

        except ValueError:
            pass

    return None


def normalize_type(value):
    key = normalize_key(value)

    revenue_types = {
        "entrada",
        "receita",
        "revenue",
        "income",
        "credito",
        "credit"
    }

    if key in revenue_types:
        return "revenue"

    return "expense"


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

            description = row_value(
                row,
                "description",
                "descricao",
                "descrição"
            )

            category = row_value(
                row,
                "category",
                "categoria"
            )

            if not category:
                category = "Sem categoria"

            raw_type = row_value(
                row,
                "type",
                "tipo"
            )

            if not raw_type:
                raw_type = "Saída"

            amount = parse_amount(
                row_value(
                    row,
                    "amount",
                    "valor"
                )
            )

            date = parse_date(
                row_value(
                    row,
                    "date",
                    "data"
                )
            )

            if not description and not amount:
                continue

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
                    "date": date,
                    "description": description,
                    "category": category,
                    "amount": amount,
                    "type": normalize_type(
                        raw_type
                    )
                }
            )

            count += 1

    return {
        "inserted": count
    }


@app.get("/analytics/summary")
def analytics(
    token: str = "demo"
):
    if not engine:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL não configurada"
        )

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
                    ) AS expenses,

                    COUNT(*) AS transactions

                FROM transactions

                WHERE org_id = :org
            """),
            {
                "org": org
            }
        ).mappings().one()

    revenue = float(
        result["revenue"]
    )

    expenses = float(
        result["expenses"]
    )

    cashflow = (
        revenue - expenses
    )

    margin = (
        cashflow / revenue * 100
        if revenue
        else 0
    )

    return {
        "revenue": revenue,
        "expenses": expenses,
        "margin": margin,
        "cashflow": cashflow,
        "transactions": int(
            result["transactions"]
        )
          }
