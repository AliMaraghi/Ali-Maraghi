"""Four standalone local tools, no OS/swarm/avatar framing - see README.md.

1. POST /dating/draft           {"profile_text": "..."}            -> {"drafts": "..."}
2. POST /csv/categorize         {"csv_text": "..."}                -> {"totals_pence": {...}, ...}
3. POST /tax/calculate          {"data": {...}, "rules": {...}}    -> {"summary": "...", ...}
4. GET  /rss/latest                                                -> {"titles": [...]}
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import csv_parser
import dating
import rss_fetcher
import tax_calculator
from anthropic_client import AnthropicError
from budget_guard import BudgetDenied, check_and_increment

app = FastAPI(title="Local Tools")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class DatingRequest(BaseModel):
    profile_text: str


class CsvRequest(BaseModel):
    csv_text: str


class TaxRequest(BaseModel):
    data: dict
    rules: dict


@app.post("/dating/draft")
def dating_draft(req: DatingRequest):
    try:
        check_and_increment("dating")
        drafts = dating.generate_openers(req.profile_text)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except BudgetDenied as exc:
        raise HTTPException(402, str(exc))
    except AnthropicError as exc:
        raise HTTPException(502, str(exc))
    return {"drafts": drafts}


@app.post("/csv/categorize")
def csv_categorize(req: CsvRequest):
    try:
        transactions = csv_parser.parse_transactions(req.csv_text)
    except csv_parser.CsvParseError as exc:
        raise HTTPException(400, str(exc))
    try:
        check_and_increment("csv")
        result = csv_parser.categorize(transactions)
    except BudgetDenied as exc:
        raise HTTPException(402, str(exc))
    except AnthropicError as exc:
        raise HTTPException(502, str(exc))
    return result


@app.post("/tax/calculate")
def tax_calculate(req: TaxRequest):
    try:
        return tax_calculator.calculate(req.data, req.rules)
    except tax_calculator.TaxCalculatorError as exc:
        raise HTTPException(400, str(exc))


@app.get("/rss/latest")
def rss_latest():
    return {"titles": rss_fetcher.latest_titles()}


@app.get("/health")
def health():
    return {"status": "ok"}
