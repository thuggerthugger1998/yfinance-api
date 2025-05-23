import time
import os
import yfinance as yf
import openai
import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

# Load OpenAI API key securely from Render environment
openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

# Allow access from Sheets or any browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Retry handler for yfinance calls
def safe_yfinance_fetch(ticker: str, retries=3, delay=2):
    for attempt in range(retries):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period="6mo")
            return info, hist
        except Exception as e:
            if "429" in str(e) and attempt < retries - 1:
                time.sleep(delay)
            else:
                raise e

# Extract metrics for a single ticker
def extract_metrics(ticker: str):
    try:
        info, hist = safe_yfinance_fetch(ticker)
        return {
            "ticker": ticker,
            "next_report_date": str(info.get("earningsDate", "")),
            "volume_30d_avg": info.get("averageVolume", ""),
            "short_interest": "",  # Placeholder
            "short_percent_of_float": "",  # Placeholder
            "days_to_cover": "",  # Placeholder
            "volatility_daily": round(float(info.get("beta", 0)) / (252**0.5), 4),
            "sma_50d": info.get("fiftyDayAverage", ""),
            "sma_200d": info.get("twoHundredDayAverage", ""),
            "rsi_14d": "",  # Will plug in later
            "market_cap": info.get("marketCap", ""),
            "liquidity_ratio": "",  # Placeholder
            "volatility_annualized": round(float(info.get("beta", 0)), 4),
            "historical_dates": [str(d.date()) for d in hist.index],
            "historical_prices": [round(float(p), 2) for p in hist["Close"]],
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}

# Single ticker route
@app.get("/scrape/{ticker}")
def scrape_ticker(ticker: str):
    return extract_metrics(ticker)

# Batch ticker request model
class TickerBatchRequest(BaseModel):
    tickers: List[str]

# Batch ticker route
@app.post("/scrape_batch")
def scrape_batch(request: TickerBatchRequest):
    results = []
    for ticker in request.tickers:
        result = extract_metrics(ticker)
        results.append(result)
        time.sleep(1)  # rate-limiting safety delay
    return results
