from fastapi import FastAPI
import requests
import re
from datetime import datetime

app = FastAPI()

def get_yahoo_cookie_crumb():
    """Retrieve the A1 cookie and crumb from Yahoo Finance."""
    url = "https://finance.yahoo.com"
    session = requests.Session()
    response = session.get(url)
    
    # Get the A1 cookie
    cookie = session.cookies.get_dict().get('A1')
    if not cookie:
        raise ValueError("Cookie A1 not found")
    
    # Extract crumb using regex
    crumb_pattern = r'"crumb":"(.*?)"'
    match = re.search(crumb_pattern, response.text)
    if match:
        crumb = match.group(1)
    else:
        # Save HTML for debugging
        with open('response.html', 'w') as f:
            f.write(response.text)
        raise ValueError("Crumb not found in response. HTML saved to response.html")
    
    return session, cookie, crumb

def fetch_historical_data(ticker, startDate, endDate, session, crumb):
    """Fetch historical data for a ticker using the session, cookie, and crumb."""
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {
        'period1': int(datetime.strptime(startDate, "%Y-%m-%d").timestamp()),
        'period2': int(datetime.strptime(endDate, "%Y-%m-%d").timestamp()),
        'interval': '1d',
        'crumb': crumb
    }
    headers = {
        'Cookie': f'A1={session.cookies.get_dict().get("A1")}'
    }
    
    response = session.get(url, params=params, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if 'chart' in data and 'result' in data['chart'] and data['chart']['result']:
            return data['chart']['result'][0]
        else:
            raise Exception("No data found in response")
    else:
        raise Exception(f"Failed to fetch data: {response.status_code}")

@app.get('/historical-prices/{tickers}/{startDate}/{endDate}')
async def historical_prices(tickers: str, startDate: str, endDate: str):
    try:
        ticker_list = tickers.split(',')
        prices = {}
        names = {}
        dates_set = set()
        
        # Get session, cookie, and crumb
        session, cookie, crumb = get_yahoo_cookie_crumb()
        
        for ticker in ticker_list:
            try:
                # Fetch historical data with authentication
                data = fetch_historical_data(ticker, startDate, endDate, session, crumb)
                timestamps = data['timestamp']
                closes = data['indicators']['quote'][0]['close']
                
                # Convert timestamps to dates
                ticker_dates = [datetime.fromtimestamp(ts).strftime('%Y-%m-%d') for ts in timestamps]
                ticker_prices = [float(price) if price is not None else None for price in closes]
                
                # Determine currency
                try:
                    currency = data['meta']['currency']
                except KeyError:
                    currency = 'USD'
                
                if currency != 'USD':
                    # Fetch exchange rate data
                    exchange_ticker = f"{currency}USD=X"
                    exchange_data = fetch_historical_data(exchange_ticker, startDate, endDate, session, crumb)
                    exchange_timestamps = exchange_data['timestamp']
                    exchange_closes = exchange_data['indicators']['quote'][0]['close']
                    exchange_rates = {datetime.fromtimestamp(ts).strftime('%Y-%m-%d'): rate for ts, rate in zip(exchange_timestamps, exchange_closes)}
                    
                    # Convert prices to USD
                    ticker_prices = [price * exchange_rates.get(date, 1.0) if price is not None else None for date, price in zip(ticker_dates, ticker_prices)]
                
                prices[ticker] = ticker_prices
                names[ticker] = data['meta']['longName'] if 'longName' in data['meta'] else ticker
                for date in ticker_dates:
                    dates_set.add(date)
            except Exception as e:
                prices[ticker] = []
                names[ticker] = ticker
                print(f"Error processing ticker {ticker}: {str(e)}")
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
