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

# Helper function to filter outliers in price data
def filter_outliers(prices):
    if not prices or len([p for p in prices if p is not None]) < 2:
        return prices
    
    # Convert prices to a list for processing, preserving None values
    filtered_prices = prices.copy()
    for i in range(1, len(filtered_prices) - 1):
        if filtered_prices[i] is None:
            continue
        prev_price = filtered_prices[i-1]
        next_price = filtered_prices[i+1]
        current_price = filtered_prices[i]
        
        # Check if current price is an outlier (e.g., >10x or <0.1x of adjacent prices)
        if prev_price is not None and next_price is not None:
            if (current_price > prev_price * 10 and current_price > next_price * 10) or \
               (current_price < prev_price * 0.1 and current_price < next_price * 0.1):
                filtered_prices[i] = None
                print(f"Filtered outlier price {current_price} at index {i}")
    
    return filtered_prices

# Helper function to validate split adjustments
def validate_split_adjustments(ticker, prices, dates):
    if not prices or len([p for p in prices if p is not None]) < 2:
        return prices
    
    # Check for sudden jumps that might indicate unadjusted splits
    adjusted_prices = prices.copy()
    for i in range(1, len(adjusted_prices)):
        if adjusted_prices[i] is None or adjusted_prices[i-1] is None:
            continue
        ratio = adjusted_prices[i] / adjusted_prices[i-1]
        if ratio > 5 or ratio < 0.2:  # Possible unadjusted split
            print(f"Possible unadjusted split for {ticker} at {dates[i]}: ratio = {ratio}")
            # Attempt to fetch split events and adjust manually
            try:
                stock = yf.Ticker(ticker)
                splits = stock.splits
                split_date = dates[i]
                for split_date_index, split_ratio in splits.items():
                    split_date_str = split_date_index.strftime('%Y-%m-%d')
                    if split_date_str <= split_date:
                        # Adjust prices before the split
                        for j in range(i):
                            if adjusted_prices[j] is not None:
                                adjusted_prices[j] = adjusted_prices[j] * split_ratio
                        print(f"Manually adjusted split for {ticker} at {split_date_str} with ratio {split_ratio}")
            except Exception as e:
                print(f"Error adjusting splits for {ticker}: {str(e)}")
    
    return adjusted_prices

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
                
                # Filter outliers in the price data
                ticker_prices = filter_outliers(ticker_prices)
                
                # Validate split adjustments
                ticker_prices = validate_split_adjustments(ticker, ticker_prices, ticker_dates)
                
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
                    
                    # Convert prices to USD, ensuring no default if rate is missing
                    ticker_prices = [price * exchange_rates[date] if (price is not None and date in exchange_rates) else None for date, price in zip(ticker_dates, ticker_prices)]
                
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
                    aligned_prices[ticker] = [float(date_price_map[date]) * exchange_rates[date] if (date in date_price_map and date in exchange_rates and date_price_map[date] is not None and isinstance(date_price_map[date], (int, float)) and np.isfinite(date_price_map[date])) else None for date in dates]
                else:
                    aligned_prices[ticker] = [float(date_price_map[date]) if (date in date_price_map and date_price_map[date] is not None and isinstance(date_price_map[date], (int, float)) and np.isfinite(date_price_map[date])) else None for date in dates]
            except Exception as e:
                aligned_prices[ticker] = [None] * len(dates)
                print(f"Error aligning prices for ticker {ticker}: {str(e)}")
        
        return {"dates": dates, "prices": aligned_prices, "names": names}
    except Exception as e:
        return {"error": str(e)}
