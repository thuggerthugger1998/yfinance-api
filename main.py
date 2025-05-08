from fastapi import FastAPI
import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import time

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
    
    adjusted_prices = prices.copy()
    for i in range(1, len(adjusted_prices)):
        if adjusted_prices[i] is None or adjusted_prices[i-1] is None:
            continue
        ratio = adjusted_prices[i] / adjusted_prices[i-1]
        if ratio > 5 or ratio < 0.2:  # Possible unadjusted split
            print(f"Possible unadjusted split for {ticker} at {dates[i]}: ratio = {ratio}")
            try:
                stock = yf.Ticker(ticker)
                splits = stock.splits
                split_date = dates[i]
                for split_date_index, split_ratio in splits.items():
                    split_date_str = split_date_index.strftime('%Y-%m-%d')
                    if split_date_str <= split_date:
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

                    # Filter outliers and validate split adjustments
                    ticker_prices = filter_outliers(ticker_prices)
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
                            break
                        
                        # Create a dictionary of exchange rates by date
                        exchange_rates = {index.strftime('%Y-%m-%d'): rate for index, rate in zip(exchange_data.index, exchange_data['Close'])}
                        
                        # Convert prices to USD
                        ticker_prices = [price * exchange_rates[date] if (price is not None and date in exchange_rates) else None for date, price in zip(ticker_dates, ticker_prices)]

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

        # Sort dates in ascending order
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
            print(f"Insufficient data for ticker {ticker}: stock data length={len(stock_daily)}, benchmark data length={len(bench_daily)}")
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
            if len(daily_returns) >= min_days:
                period_stock_returns = daily_returns['Stock'].tail(min_days)
                period_bench_returns = daily_returns['Benchmark'].tail(min_days)
                covariance = np.cov(period_stock_returns, period_bench_returns)[0, 1]
                variance = np.var(period_bench_returns)
                beta = covariance / variance if variance != 0 else "N/A"
                betas[tenor] = beta
            else:
                betas[tenor] = "N/A"
        
        # Calculate betas for monthly tenors
        for tenor, min_months in tenors_monthly.items():
            if len(monthly_returns) >= min_months:
                period_stock_returns = monthly_returns['Stock'].tail(min_months)
                period_bench_returns = monthly_returns['Benchmark'].tail(min_months)
                covariance = np.cov(period_stock_returns, period_bench_returns)[0, 1]
                variance = np.var(period_bench_returns)
                beta = covariance / variance if variance != 0 else "N/A"
                betas[tenor] = beta
            else:
                betas[tenor] = "N/A"
        
        return {"ticker": ticker, "benchmark": benchmark, "betas": betas}
    except Exception as e:
        print(f"Error in calculate_beta endpoint for ticker {ticker}: {str(e)}")
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
            "error": str(e)
        }
