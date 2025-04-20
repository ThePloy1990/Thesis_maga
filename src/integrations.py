import yfinance as yf
from typing import List, Dict


def get_real_time_prices(tickers: List[str]) -> Dict[str, float]:
    """Заглушка: возвращает текущие цены акций из Yahoo Finance"""
    prices = {}
    for ticker in tickers:
        try:
            data = yf.Ticker(ticker)
            prices[ticker] = data.info.get("regularMarketPrice")
        except Exception:
            prices[ticker] = None
    return prices

# TODO: добавить интеграцию с брокерскими API внутри этого модуля 