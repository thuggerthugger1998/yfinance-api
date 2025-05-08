from fastapi import FastAPI
import yfinance as yf
import pandas as pd
import numpy as np
import time

app = FastAPI()

@app.get('/historical-prices/{tickers}/{startDate}/{endDate}')
async def historical_prices(tickers: str, startDate: str, endDate: str):
    try:
        ticker_list = tickers.split(',')
        prices = {}
        names = {}
        dates_set = set()
        max_retries = 3
        retry_delay = 2  # seconds

        for ticker in ticker_list:
            attempt = 0
            success = False
            while attempt < max_retries and not success:
                try:
                    # Fetch daily data
                    stock = yf.download(ticker, start=startDate, end=endDate, interval="1d", auto_adjust=True)
                    if stock.empty:
                        print(f"No data for ticker {ticker} after {attempt + 1} attempts")
                        prices[ticker] = []
                        names[ticker] = ticker
                        break

                    # Extract dates and close prices
                    ticker_dates = stock.index.strftime('%Y-%m-%d').tolist()
                    ticker_prices = stock['Close'].tolist()

                    # Replace NaN, inf, -inf with None
                    ticker_prices = [None if (price is None or isinstance(price, float) and (np.isnan(price) or not np.isfinite(price))) else float(price) for price in ticker_prices]

                    # Check if there are any non-null prices
                    if not any(price is not None for price in ticker_prices):
                        print(f"No valid price data for ticker {ticker} after {attempt + 1} attempts")
                        prices[ticker] = []
                        names[ticker] = ticker
                        break

                    prices[ticker] = ticker_prices
                    stock_info = yf.Ticker(ticker).info
                    names[ticker] = stock_info.get('longName', ticker)
                    for date in ticker_dates:
                        dates_set.add(date)
                    success = True

                except Exception as e:
                    attempt += 1
                    print(f"Error fetching data for ticker {ticker} (attempt {attempt}/{max_retries}): {str(e)}")
                    if attempt < max_retries:
                        time.sleep(retry_delay)
                    else:
                        prices[ticker] = []
                        names[ticker] = ticker
                        print(f"Failed to fetch data for ticker {ticker} after {max_retries} attempts")

        # Sort dates
        dates = sorted(list(dates_set)) if dates_set else []

        # Align prices to dates
        aligned_prices = {}
        for ticker in ticker_list:
            if not prices[ticker]:
                aligned_prices[ticker] = [None] * len(dates) if dates else []
                continue

            date_price_map = dict(zip(ticker_dates, prices[ticker]))
            aligned_prices[ticker] = [date_price_map.get(date, None) for date in dates]

        return {"dates": dates, "prices": aligned_prices, "names": names}
    except Exception as e:
        print(f"Error in historical_prices endpoint: {str(e)}")
        return {"error": str(e)}

@app.get('/calculate_beta/{ticker}/{benchmark}/{startDate}/{endDate}')
async def calculate_beta(ticker: str, benchmark: str, startDate: str, endDate: str):
    try:
        # Fetch daily data
        stock_daily = yf.download(ticker, start=startDate, end=endDate, interval="1d", auto_adjust=True)['Close']
        bench_daily = yf.download(benchmark, start=startDate, end=endDate, interval="1d", auto_adjust=True)['Close']
        
        if stock_daily.empty or bench_daily.empty:
            return {
                "ticker": ticker,
                "benchmark": benchmark,
                "betas": {
                    "30D": "N/A",
                    "90D": "N/A",
                    "180D": "N/A",
                    "1Y": "N/A",
                    "2Y": "N/A",
                    "3Y": "N/A",
                    "5Y": "N/A"
                },
                "error": "Insufficient data"
            }
        
        # Align daily data
        data_daily = pd.concat([stock_daily, bench_daily], axis=1, join='inner').dropna()
        data_daily.columns = ['Stock', 'Benchmark']
        
        # Compute daily log returns
        daily_returns = np.log(data_daily / data_daily.shift(1)).dropna()
        
        # Resample to monthly data (last trading day of each month)
        stock_monthly = stock_daily.resample('ME').last().dropna()
        bench_monthly = bench_daily.resample('ME').last().dropna()
        
        # Align monthly data
        data_monthly = pd.concat([stock_monthly, bench_monthly], axis=1, join='inner').dropna()
        data_monthly.columns = ['Stock', 'Benchmark']
        
        # Compute monthly log returns
        monthly_returns = np.log(data_monthly / data_monthly.shift(1)).dropna()
        
        # Define tenors for daily returns (trading days)
        tenors_daily = {
            '30D': 21,   # ~1 month
            '90D': 63,   # ~3 months
            '180D': 126, # ~6 months
            '1Y': 252    # ~1 year
        }
        
        # Define tenors for monthly returns (months)
        tenors_monthly = {
            '2Y': 24,
            '3Y': 36,
            '5Y': 60
        }
        
        betas = {}
        
        # Calculate betas for daily tenors
        for tenor, min_days in tenors_daily.items():
