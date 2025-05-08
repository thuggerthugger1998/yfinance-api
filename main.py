from fastapi import FastAPI
import yfinance as yf
import numpy as np

app = FastAPI()

# Helper function to determine the currency of a ticker
def get_ticker_currency(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        currency = info.get('currency', 'USD')
        return currency
    except Exception as e:
        print(f"Error determining currency for ticker {ticker}: {str(e)}")
        return 'USD'  # Default to USD if currency cannot be determined

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
                
                # Determine the currency of the ticker
                currency = get_ticker_currency(ticker)
                if currency != 'USD':
                    # Fetch historical exchange rates (e.g., SEKUSD=X for SEK to USD)
                    exchange_ticker = f"{currency}USD=X"
                    exchange_data = yf.Ticker(exchange_ticker).history(start=startDate, end=endDate)
                    if exchange_data.empty:
                        print(f"No exchange rate data for {exchange_ticker}")
                        prices[ticker] = []
                        names[ticker] = ticker
                        continue
                    
                    # Create a dictionary of exchange rates by date
                    exchange_rates = {index.strftime('%Y-%m-%d'): rate for index, rate in zip(exchange_data.index, exchange_data['Close'])}
                    
                    # Convert prices to USD
                    ticker_prices = [price * exchange_rates.get(date, 1.0) if price is not None else None for date, price in zip(ticker_dates, ticker_prices)]
                
                prices[ticker] = ticker_prices
                names[ticker] = stock.info.get('longName', ticker)
                for date in ticker_dates:
                    dates_set.add(date)
            except Exception as e:
                prices[ticker] = []
                names[ticker] = ticker
                print(f"Error processing ticker {ticker}: {str(e)}")
                continue
        
        # Sort dates in ascending order to ensure consistency
        dates = sorted(list(dates_set))
        
        # Align prices for each ticker to the unified date list
        aligned_prices = {}
        for ticker in ticker_list:
            if not prices[ticker]:
                aligned_prices[ticker] = [None] * len(dates)
                continue
            
            # Re-fetch data to align with dates
            try:
                stock = yf.Ticker(ticker)
                ticker_data = stock.history(start=startDate, end=endDate, auto_adjust=True)
                date_price_map = {index.strftime('%Y-%m-%d'): price for index, price in zip(ticker_data.index, ticker_data['Close'])}
                
                # Determine currency again for alignment
                currency = get_ticker_currency(ticker)
                if currency != 'USD':
                    exchange_ticker = f"{currency}USD=X"
                    exchange_data = yf.Ticker(exchange_ticker).history(start=startDate, end=endDate)
                    exchange_rates = {index.strftime('%Y-%m-%d'): rate for index, rate in zip(exchange_data.index, exchange_data['Close'])}
                    aligned_prices[ticker] = [float(date_price_map[date]) * exchange_rates.get(date, 1.0) if (date in date_price_map and date_price_map[date] is not None and isinstance(date_price_map[date], (int, float)) and np.isfinite(date_price_map[date])) else None for date in dates]
                else:
                    aligned_prices[ticker] = [float(date_price_map[date]) if (date in date_price_map and date_price_map[date] is not None and isinstance(date_price_map[date], (int, float)) and np.isfinite(date_price_map[date])) else None for date in dates]
            except Exception as e:
                aligned_prices[ticker] = [None] * len(dates)
                print(f"Error aligning prices for ticker {ticker}: {str(e)}")
        
        return {"dates": dates, "prices": aligned_prices, "names": names}
    except Exception as e:
        return {"error": str(e)}
