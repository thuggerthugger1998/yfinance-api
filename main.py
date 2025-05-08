from fastapi import FastAPI
import yfinance as yf
from datetime import datetime

app = FastAPI()

@app.get('/historical-prices/{tickers}/{startDate}/{endDate}')
async def historical_prices(tickers: str, startDate: str, endDate: str):
    try:
        ticker_list = tickers.split(',')
        prices = {}
        names = {}
        dates_set = set()
        
        for ticker in ticker_list:
            try:
                # Fetch historical data using yfinance
                stock = yf.Ticker(ticker)
                hist = stock.history(start=startDate, end=endDate, interval="1d")
                
                if hist.empty:
                    print(f"No data found for ticker {ticker}")
                    prices[ticker] = []
                    names[ticker] = ticker
                    continue
                
                # Extract dates and prices
                ticker_dates = hist.index.strftime('%Y-%m-%d').tolist()
                ticker_prices = hist['Close'].tolist()
                
                # Determine currency
                currency = stock.info.get('currency', 'USD')
                
                if currency != 'USD':
                    # Fetch exchange rate data
                    exchange_ticker = f"{currency}USD=X"
                    exchange_stock = yf.Ticker(exchange_ticker)
                    exchange_hist = exchange_stock.history(start=startDate, end=endDate, interval="1d")
                    if not exchange_hist.empty:
                        exchange_rates = {date.strftime('%Y-%m-%d'): rate for date, rate in zip(exchange_hist.index, exchange_hist['Close'])}
                        # Convert prices to USD
                        ticker_prices = [price * exchange_rates.get(date, 1.0) if price is not None else None for date, price in zip(ticker_dates, ticker_prices)]
                
                prices[ticker] = ticker_prices
                names[ticker] = stock.info.get('longName', ticker)
                for date in ticker_dates:
                    dates_set.add(date)
            except Exception as e:
                print(f"Error processing ticker {ticker}: {str(e)}")
                prices[ticker] = []
                names[ticker] = ticker
                continue
        
        # Sort dates in ascending order
        dates = sorted(list(dates_set))
        
        # Align prices for each ticker to the unified date list
        aligned_prices = {}
        for ticker in ticker_list:
            if not prices[ticker]:
                aligned_prices[ticker] = [None] * len(dates)
                continue
            
            date_price_map = dict(zip(ticker_dates, prices[ticker]))
            aligned_prices[ticker] = [date_price_map.get(date, None) for date in dates]
        
        return {"dates": dates, "prices": aligned_prices, "names": names}
    except Exception as e:
        return {"error": str(e)}
