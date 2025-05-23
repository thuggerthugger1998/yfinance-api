import time
import yfinance as yf
import openai
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

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

@app.get("/scrape/{ticker}")
def scrape_ticker(ticker: str):
    try:
        info, hist = safe_yfinance_fetch(ticker)

        result = {
            "ticker": ticker,
            "next_report_date": str(info.get("earningsDate", "")),
            "volume_30d_avg": info.get("averageVolume", ""),
            "short_interest": "",
            "short_percent_of_float": "",
            "days_to_cover": "",
            "volatility_daily": round(float(info.get("beta", 0)) / (252**0.5), 4),
            "sma_50d": info.get("fiftyDayAverage", ""),
            "sma_200d": info.get("twoHundredDayAverage", ""),
            "rsi_14d": "",
            "market_cap": info.get("marketCap", ""),
            "liquidity_ratio": "",
            "volatility_annualized": round(float(info.get("beta", 0)), 4),
            "historical_dates": [str(d.date()) for d in hist.index],
            "historical_prices": [round(float(p), 2) for p in hist["Close"]],
        }

        return result

    except Exception as e:
        return {"ticker": ticker, "error": str(e)}
