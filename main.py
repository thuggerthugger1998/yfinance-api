from fastapi import FastAPI
import yfinance as yf

app = FastAPI()

@app.get('/historical-prices/{tickers}/{startDate}/{endDate}')
async def historical_prices(tickers: str, startDate: str, endDate: str):
    try:
        ticker_list = tickers.split(',')
        data = yf.download(ticker_list, start=startDate, end=endDate, progress=False)
        dates = data.index.strftime('%Y-%m-%d').tolist()
        prices = {}
        names = {}
        for ticker in ticker_list:
            stock = yf.Ticker(ticker)
            prices[ticker] = data['Close'][ticker].tolist() if ticker in data['Close'] else []
            names[ticker] = stock.info.get('longName', ticker)  # Fallback to ticker if name not available
        return {"dates": dates, "prices": prices, "names": names}
    except Exception as e:
        return {"error": str(e)}
