import json
import glob
import os
from pathlib import Path

import streamlit as st
import matplotlib.pyplot as plt
import plotly.graph_objects as go

from portfolio_optimizer import load_price_data, backtest_strategy

RESULTS_PATH = Path("data/portfolio_results.json")


def load_results():
    if RESULTS_PATH.exists():
        with open(RESULTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    st.error("Results file not found")
    return None


def load_latest_prices():
    csv_files = glob.glob("data/sp500_ml_ready*.csv")
    if not csv_files:
        return None
    latest = max(csv_files, key=os.path.getctime)
    return load_price_data(latest)


def performance_chart(prices, weights):
    cum_returns = backtest_strategy(prices, weights)
    fig, ax = plt.subplots(figsize=(8, 5))
    cum_returns.plot(ax=ax)
    ax.set_title("Накопительная доходность")
    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative Return")
    st.pyplot(fig)


def allocation_pie(weights):
    labels = list(weights.keys())
    sizes = [v * 100 for v in weights.values()]
    fig = go.Figure(data=[go.Pie(labels=labels, values=sizes, hole=0.4)])
    fig.update_layout(title="Оптимальная аллокация (%)")
    st.plotly_chart(fig)


def main():
    results = load_results()
    if not results:
        return

    st.title("Отчёт по портфелю")
    st.metric("Ожидаемая доходность", f"{results['expected_return']*100:.2f}%")
    st.metric("Волатильность", f"{results['expected_volatility']*100:.2f}%")
    st.metric("Sharpe Ratio", f"{results['sharpe_ratio']:.2f}")

    prices = load_latest_prices()
    if prices is not None:
        st.subheader("Доходность портфеля")
        performance_chart(prices, results['optimal_weights'])
    else:
        st.warning("Не удалось найти ценовые данные для построения графика доходности")

    st.subheader("Структура портфеля")
    allocation_pie(results['optimal_weights'])


if __name__ == "__main__":
    from streamlit.web import cli as stcli
    import sys

    if st._is_running_with_streamlit:
        main()
    else:
        sys.argv = ["streamlit", "run", __file__]
        sys.exit(stcli.main())
