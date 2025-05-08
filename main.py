from fastapi import FastAPI
import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

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

# Helper function to align dates to the last trading day of each month
def align_to_monthly_last_trading_day(ticker, start_date, end_date):
    try:
        stock = yf.Ticker(ticker)
        # Fetch daily data to find the last trading day of each month
        data = stock.history(start=start_date, end=end_date, interval="1d", auto_adjust=True)
        if data.empty:
            return [], []
        
        # Group by month and select the last trading day
        data = data.groupby(pd.Grouper(freq='ME')).last().dropna()
        dates = data.index.strftime('%Y-%m-%d').tolist()
        prices = data['Close'].tolist()
        
        return dates, prices
    except Exception as e:
        print(f"Error aligning dates for ticker {ticker}: {str(e)}")
        return [], []

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
                # Align data to the last trading day of each month
                ticker_dates, ticker_prices = align_to_monthly_last_trading_day(ticker, startDate, endDate)
                
                if not ticker_prices:
                    prices[ticker] = []
                    names[ticker] = ticker
                    print(f"No data for ticker {ticker}")
                    continue
                
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
                    exchange_data = yf.Ticker(exchange_ticker).history(start=startDate, end=endDate, interval="1d")
                    if exchange_data.empty:
                        print(f"No exchange rate data for {exchange_ticker}")
                        prices[ticker] = []
                        names[ticker] = ticker
                        continue
                    
                    # Group exchange rates by month and select the last trading day
                    exchange_data = exchange_data.groupby(pd.Grouper(freq='ME')).last().dropna()
                    exchange_rates = {index.strftime('%Y-%m-%d'): rate for index, rate in zip(exchange_data.index, exchange_data['Close'])}
                    
                    # Convert prices to USD, ensuring no default if rate is missing
                    ticker_prices = [price * exchange_rates[date] if (price is not None and date in exchange_rates) else None for date, price in zip(ticker_dates, ticker_prices)]
                
                prices[ticker] = ticker_prices
                stock = yf.Ticker(ticker)
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
                ticker_dates, ticker_prices = align_to_monthly_last_trading_day(ticker, startDate, endDate)
                date_price_map = dict(zip(ticker_dates, ticker_prices))
                
                # Determine currency again for alignment
                currency = get_ticker_currency(ticker)
                if currency != 'USD':
                    exchange_ticker = f"{currency}USD=X"
                    exchange_data = yf.Ticker(exchange_ticker).history(start=startDate, end=endDate, interval="1d")
                    exchange_data = exchange_data.groupby(pd.Grouper(freq='ME')).last().dropna()
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

# Endpoint to calculate beta using log returns and return capping for multiple tenors
@app.get('/calculate_beta/{ticker}/{benchmark}/{startDate}/{endDate}')
async def calculate_beta(ticker: str, benchmark: str, startDate: str, endDate: str):
    try:
        # Fetch aligned monthly data for the ticker and benchmark
        stock_dates, stock_prices = align_to_monthly_last_trading_day(ticker, startDate, endDate)
        bench_dates, bench_prices = align_to_monthly_last_trading_day(benchmark, startDate, endDate)
        
        if not stock_prices or not bench_prices:
            return {"ticker": ticker, "benchmark": benchmark, "betas": {"1Y": "N/A", "2Y": "N/A", "3Y": "N/A", "5Y": "N/A"}, "error": "Insufficient data"}
        
        # Create pandas Series for alignment
        stock_series = pd.Series(stock_prices, index=stock_dates)
        bench_series = pd.Series(bench_prices, index=bench_dates)
        
        # Align dates between stock and benchmark
        common_dates = stock_series.index.intersection(bench_series.index)
        stock_series = stock_series.loc[common_dates]
        bench_series = bench_series.loc[common_dates]
        
        # Calculate log returns
        stock_returns = np.log(stock_series / stock_series.shift(1)).dropna()
        bench_returns = np.log(bench_series / bench_series.shift(1)).dropna()
        
        # Align returns after calculating
        common_dates = stock_returns.index.intersection(bench_returns.index)
        stock_returns = stock_returns.loc[common_dates]
        bench_returns = bench_returns.loc[common_dates]
        
        # Number of months available
        months_available = len(stock_returns)
        
        # Define tenors and their minimum required months
        tenors = {
            '1Y': 12,
            '2Y': 24,
            '3Y': 36,
            '5Y': 60
        }
        
        # Calculate betas for each tenor
        betas = {}
        for tenor, min_months in tenors.items():
            if months_available >= min_months:
                # Use the last 'min_months' data points
                period_stock_returns = stock_returns.tail(min_months)
                period_bench_returns = bench_returns.tail(min_months)
                
                # Cap returns at ±30% to handle outliers
                period_stock_returns = period_stock_returns.clip(lower=-0.3, upper=0.3)
                period_bench_returns = period_bench_returns.clip(lower=-0.3, upper=0.3)
                
                # Calculate beta
                covariance = np.cov(period_stock_returns, period_bench_returns)[0, 1]
                variance = np.var(period_bench_returns)
                beta = covariance / variance if variance != 0 else "N/A"
                betas[tenor] = beta
            else:
                betas[tenor] = "N/A"
        
        return {"ticker": ticker, "benchmark": benchmark, "betas": betas}
    except Exception as e:
        return {"ticker": ticker, "benchmark": benchmark, "betas": {"1Y": "N/A", "2Y": "N/A", "3Y": "N/A", "5Y": "N/A"}, "error": str(e)}
