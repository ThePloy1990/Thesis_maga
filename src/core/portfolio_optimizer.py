import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple, List
from pypfopt import EfficientFrontier, risk_models, expected_returns


def load_price_data(csv_path: str) -> pd.DataFrame:
    """Загружает исторические цены из CSV-файла с колонкой Date"""
    prices = pd.read_csv(csv_path, parse_dates=['Date'], index_col='Date')
    return prices


def calculate_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Вычисляет дневные доходности из цен"""
    returns = prices.pct_change().dropna()
    return returns


def optimize_portfolio(
    prices: pd.DataFrame,
    objective: str = 'max_sharpe',
    target_return: Optional[float] = None,
    min_weight: float = 0.0,
    max_weight: float = 1.0,
    per_asset_bounds: Optional[Dict[str, Tuple[float,float]]] = None,
    group_constraints: Optional[List[Tuple[List[str], float, float]]] = None
) -> Dict:
    """
    Оптимизация портфеля по заданной цели:
      - 'max_sharpe'       : максимизация Sharpe ratio
      - 'min_volatility'   : минимизация волатильности
      - 'target_return'    : достижение целевого дохода (требуется target_return)

    Возвращает словарь с ключами:
      'weights', 'expected_return', 'volatility', 'sharpe_ratio'
    """
    returns = calculate_returns(prices)
    mu = expected_returns.mean_historical_return(prices)
    S = risk_models.sample_cov(prices)
    # Создаём фронтир: глобальные или детальные ограничения
    if per_asset_bounds:
        ef = EfficientFrontier(mu, S)
        # Ограничения по каждой бумаге
        tickers = list(mu.index)
        for ticker, (low, high) in per_asset_bounds.items():
            if ticker in tickers:
                idx = tickers.index(ticker)
                ef.add_constraint(lambda w, idx=idx, low=low: w[idx] >= low)
                ef.add_constraint(lambda w, idx=idx, high=high: w[idx] <= high)
    else:
        ef = EfficientFrontier(mu, S, weight_bounds=(min_weight, max_weight))
    # Групповые ограничения (сектора/регионы)
    if group_constraints:
        tickers = list(mu.index)
        for group, min_sum, max_sum in group_constraints:
            indices = [tickers.index(t) for t in group if t in tickers]
            ef.add_constraint(lambda w, indices=indices, min_sum=min_sum: sum(w[i] for i in indices) >= min_sum)
            ef.add_constraint(lambda w, indices=indices, max_sum=max_sum: sum(w[i] for i in indices) <= max_sum)

    if objective == 'max_sharpe':
        eff_weights = ef.max_sharpe()
    elif objective == 'min_volatility':
        eff_weights = ef.min_volatility()
    elif objective == 'target_return':
        if target_return is None:
            raise ValueError("Для objective='target_return' необходимо указать target_return")
        eff_weights = ef.efficient_return(target_return)
    else:
        raise ValueError(f"Неизвестная цель оптимизации: {objective}")

    cleaned = ef.clean_weights()
    exp_ret, vol, sr = ef.portfolio_performance(verbose=False)

    return {
        'weights': cleaned,
        'expected_return': exp_ret,
        'volatility': vol,
        'sharpe_ratio': sr
    }


def calculate_var_cvar(
    returns: pd.DataFrame,
    weights: Dict[str, float],
    alpha: float = 0.05
) -> Tuple[float, float]:
    """Рассчитывает VaR и CVaR портфеля на уровне значимости alpha"""
    port_rets = returns.dot(pd.Series(weights))
    var = np.percentile(port_rets, alpha * 100)
    cvar = port_rets[port_rets <= var].mean()
    return var, cvar


def monte_carlo_simulations(
    returns: pd.DataFrame,
    num_simulations: int = 10000
) -> Tuple[np.ndarray, List[np.ndarray]]:
    """Проводит Monte Carlo симуляции случайных портфелей"""
    n = returns.shape[1]
    results = np.zeros((num_simulations, 3))  # ret, vol, sharpe
    weight_list: List[np.ndarray] = []

    mu = returns.mean() * 252
    cov = returns.cov() * 252

    for i in range(num_simulations):
        w = np.random.dirichlet(np.ones(n), size=1)[0]
        weight_list.append(w)
        ret = np.dot(mu, w)
        vol = np.sqrt(np.dot(w.T, np.dot(cov, w)))
        sharpe = ret / vol if vol > 0 else np.nan
        results[i] = np.array([ret, vol, sharpe])

    return results, weight_list


def backtest_strategy(
    prices: pd.DataFrame,
    weights: Dict[str, float]
) -> pd.Series:
    """Простой бэктест: фиксированная аллокация и кумулятивная доходность"""
    returns = calculate_returns(prices)
    w = pd.Series(weights)
    port_rets = returns.dot(w)
    cum_returns = (1 + port_rets).cumprod()
    return cum_returns


def compute_correlation_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    """Возвращает корреляционную матрицу доходностей"""
    returns = calculate_returns(prices)
    return returns.corr() 