# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/scrape/{ticker}")
def scrape_ticker(ticker: str):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="6mo")

        result = {
            "ticker": ticker,
            "next_report_date": str(info.get("earningsDate", "")),
            "volume_30d_avg": info.get("averageVolume", ""),
            "short_interest": "",  # Placeholder
            "short_percent_of_float": "",  # Placeholder
            "days_to_cover": "",  # Placeholder
            "volatility_daily": round(float(info.get("beta", 0)) / (252**0.5), 4),
            "sma_50d": info.get("fiftyDayAverage", ""),
            "sma_200d": info.get("twoHundredDayAverage", ""),
            "rsi_14d": "",  # Placeholder
            "market_cap": info.get("marketCap", ""),
            "liquidity_ratio": "",  # Placeholder
            "volatility_annualized": round(float(info.get("beta", 0)), 4),
            "historical_dates": [str(d.date()) for d in hist.index],
            "historical_prices": [round(float(p), 2) for p in hist["Close"]],
        }

        return result

    except Exception as e:
        return {"ticker": ticker, "error": str(e)}
