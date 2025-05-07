from flask import Flask, jsonify
import yfinance as yf
import os

app = Flask(__name__)

@app.route('/historical-prices/<tickers>/<startDate>/<endDate>')
def historical_prices(tickers, startDate, endDate):
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
        return jsonify({"dates": dates, "prices": prices, "names": names})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
