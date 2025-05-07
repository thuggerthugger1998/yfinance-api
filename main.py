from fastapi import FastAPI
import yfinance as yf
import numpy as np

app = FastAPI()

@app.get('/historical-prices/{tickers}/{startDate}/{endDate}')
async def historical_prices(tickers: str, startDate: str, endDate: str):
    try:
        ticker_list = tickers.split(',')
        prices = {}
        names = {}
        dates_set = set()
        
        # Process each ticker independently
        for ticker in ticker_list:
            try:
                stock = yf.Ticker(ticker)
                data = stock.history(start=startDate, end=endDate, auto_adjust=True)
                if data.empty:
                    prices[ticker] = []
                    names[ticker] = ticker
                    print(f"No data for ticker {ticker}")
                    continue
                
                # Extract dates and prices
                ticker_dates = data.index.strftime('%Y-%m-%d').tolist()
                ticker_prices = data['Close'].tolist()
                
                # Replace NaN, inf, and -inf with None (null in JSON)
                ticker_prices = [None if (price is None or isinstance(price, float) and (np.isnan(price) or not np.isfinite(price))) else float(price) for price in ticker_prices]
                
                prices[ticker] = ticker_prices
                names[ticker] = stock.info.get('longName', ticker)
                for date in ticker_dates:
                    dates_set.add(date)
            except Exception as e:
                prices[ticker] = []
                names[ticker] = ticker
                print(f"Error processing ticker {ticker}: {str(e)}")
        
        # Sort dates in ascending order to ensure consistency
        dates = sorted(list(dates_set))
        
        # Align prices for each ticker to the unified date list
        aligned_prices = {}
        for ticker in ticker_list:
            if not prices[ticker]:
                aligned_prices[ticker] = [None] * len(dates)
                continue
            
            # Re-fetch data to align with dates (in case of retry logic)
            try:
                stock = yf.Ticker(ticker)
                ticker_data = stock.history(start=startDate, end=endDate, auto_adjust=True)
                date_price_map = {index.strftime('%Y-%m-%d'): price for index, price in zip(ticker_data.index, ticker_data['Close'])}
                aligned_prices[ticker] = [float(date_price_map[date]) if (date in date_price_map and date_price_map[date] is not None and isinstance(date_price_map[date], (int, float)) and np.isfinite(date_price_map[date])) else None for date in dates]
            except Exception as e:
                aligned_prices[ticker] = [None] * len(dates)
                print(f"Error aligning prices for ticker {ticker}: {str(e)}")
        
        return {"dates": dates, "prices": aligned_prices, "names": names}
    except Exception as e:
        return {"error": str(e)}
