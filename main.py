from fastapi import FastAPI
import yfinance as yf
from datetime import datetime
import logging
import os
import time
import retrying

app = FastAPI()

# Configure logging with dynamic log level
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
logger = logging.getLogger(__name__)

# Retry decorator for yfinance calls
@retrying.retry(stop_max_attempt_number=3, wait_fixed=2000)  # Retry 3 times with 2-second delay
def fetch_yfinance_data(ticker, start_date, end_date):
    stock = yf.Ticker(ticker)
    hist = stock.history(start=start_date, end=end_date, interval="1d")
    return stock, hist

@app.get('/historical-prices/{tickers}/{startDate}/{endDate}')
async def historical_prices(tickers: str, startDate: str, endDate: str):
    try:
        ticker_list = tickers.split(',')
        prices = {}
        names = {}
        dates_set = set()
        errors = {}  # Track errors for each ticker
        
        for ticker in ticker_list:
            try:
                # Fetch historical data using yfinance with retry
                stock, hist = fetch_yfinance_data(ticker, startDate, endDate)
                
                if hist.empty:
                    logger.warning(f"No data found for ticker {ticker}")
                    prices[ticker] = []
                    names[ticker] = ticker
                    errors[ticker] = "No historical data returned"
                    continue
                
                # Extract dates and prices
                ticker_dates = hist.index.strftime('%Y-%m-%d').tolist()
                ticker_prices = hist['Close'].tolist()
                
                # Determine currency
                currency = stock.info.get('currency', 'USD')
                
                if currency != 'USD':
                    # Fetch exchange rate data
                    exchange_ticker = f"{currency}USD=X"
                    exchange_stock, exchange_hist = fetch_yfinance_data(exchange_ticker, startDate, endDate)
                    if not exchange_hist.empty:
                        exchange_rates = {date.strftime('%Y-%m-%d'): rate for date, rate in zip(exchange_hist.index, exchange_hist['Close'])}
                        # Convert prices to USD
                        ticker_prices = [price * exchange_rates.get(date, 1.0) if price is not None else None for date, price in zip(ticker_dates, ticker_prices)]
                
                prices[ticker] = ticker_prices
                names[ticker] = stock.info.get('longName', ticker)
                for date in ticker_dates:
                    dates_set.add(date)
                
                # Add a delay to avoid rate limiting
                time.sleep(1)  # 1-second delay between requests
            except Exception as e:
                logger.error(f"Error processing ticker {ticker}: {str(e)}")
                prices[ticker] = []
                names[ticker] = ticker
                errors[ticker] = str(e)
                continue
        
        # Sort dates in ascending order
        dates = sorted(list(dates_set))
        
        # Align prices for each ticker to the unified date list
        aligned_prices = {}
        for ticker in ticker_list:
            ticker_prices = prices.get(ticker, [])
            if not ticker_prices:
                aligned_prices[ticker] = [None] * len(dates)
                continue
            
            ticker_dates = [date for date in dates_set if date in dict(zip(ticker_dates, ticker_prices))]
            date_price_map = dict(zip(ticker_dates, ticker_prices))
            aligned_prices[ticker] = [date_price_map.get(date, None) for date in dates]
        
        response = {"dates": dates, "prices": aligned_prices, "names": names}
        if errors:
            response["errors"] = errors
        return response
    except Exception as e:
        logger.error(f"Error in historical_prices: {str(e)}")
        return {"error": str(e)}
