from fastapi import FastAPI
from yahooquery import Ticker
import logging
import os
import time

app = FastAPI()

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
logger = logging.getLogger(__name__)

@app.get('/historical-prices/{tickers}/{startDate}/{endDate}')
async def historical_prices(tickers: str, startDate: str, endDate: str):
    try:
        ticker_list = tickers.split(',')
        prices = {}
        names = {}
        dates_set = set()
        errors = {}
        
        for ticker in ticker_list:
            try:
                stock = Ticker(ticker)
                hist = stock.history(start=startDate, end=endDate, interval="1d")
                
                if hist.empty:
                    logger.warning(f"No data found for ticker {ticker}")
                    prices[ticker] = []
                    names[ticker] = ticker
                    errors[ticker] = "No historical data returned"
                    continue
                
                # Extract dates and prices
                # Handle MultiIndex DataFrame
                if 'symbol' in hist.index.names:
                    hist = hist.xs(ticker, level='symbol')
                ticker_dates = hist.index.strftime('%Y-%m-%d').tolist()
                ticker_prices = hist['close'].tolist()
                
                # Get name
                summary = stock.summary_profile
                name = summary[ticker]['longName'] if ticker in summary and 'longName' in summary[ticker] else ticker
                
                prices[ticker] = ticker_prices
                names[ticker] = name
                for date in ticker_dates:
                    dates_set.add(date)
                
                # Add a delay to avoid rate limiting
                time.sleep(2)  # 2-second delay between requests
            except Exception as e:
                logger.error(f"Error processing ticker {ticker}: {str(e)}")
                prices[ticker] = []
                names[ticker] = ticker
                errors[ticker] = str(e)
                continue
        
        dates = sorted(list(dates_set))
        
        # Align prices
        aligned_prices = {}
        for ticker in ticker_list:
            ticker_prices = prices.get(ticker, [])
            if not ticker_prices:
                aligned_prices[ticker] = [None] * len(dates)
                continue
            date_price_map = dict(zip(ticker_dates, ticker_prices))
            aligned_prices[ticker] = [date_price_map.get(date, None) for date in dates]
        
        response = {"dates": dates, "prices": aligned_prices, "names": names}
        if errors:
            response["errors"] = errors
        return response
    except Exception as e:
        logger.error(f"Error in historical_prices: {str(e)}")
        return {"error": str(e)}
