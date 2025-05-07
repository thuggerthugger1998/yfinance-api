from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
from datetime import datetime

app = FastAPI()

# Enable CORS to allow Google Sheets to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/historical-prices/{tickers}/{start_date}/{end_date}")
async def get_historical_prices(tickers: str, start_date: str, end_date: str):
    try:
        # Parse tickers (comma-separated)
        ticker_list = tickers.split(",")
        data = {"dates": [], "prices": {ticker: [] for ticker in ticker_list}}
        
        # Fetch data for each ticker
        for ticker in ticker_list:
            stock = yf.Ticker(ticker)
            # Use 'Close' for beta calculations (adjusted for splits/dividends)
            hist = stock.history(start=start_date, end=end_date, interval="1d")
            if data["dates"] == []:
                data["dates"] = hist.index.strftime("%Y-%m-dd").tolist()
            data["prices"][ticker] = hist["Close"].tolist()
        
        return data
    except Exception as e:
        return {"error": str(e)}
