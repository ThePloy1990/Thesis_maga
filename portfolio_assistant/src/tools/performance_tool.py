import logging
import pandas as pd
import numpy as np
import yfinance as yf
import statsmodels.api as sm
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def performance_tool(
    weights: Dict[str, float],
    start_date: str = None,
    end_date: str = None,
    risk_free_rate: float = 0.001,
    benchmark: str = "^GSPC"  # S&P 500 по умолчанию
) -> Dict:
    """
    Рассчитывает реальные метрики производительности портфеля на исторических данных.
    
    Args:
        weights: Словарь с весами активов {ticker: weight}
        start_date: Начальная дата для анализа (YYYY-MM-DD). По умолчанию - 3 месяца назад.
        end_date: Конечная дата для анализа (YYYY-MM-DD). По умолчанию - сегодня.
        risk_free_rate: Безрисковая ставка (годовая). По умолчанию 0.1%.
        benchmark: Тикер рыночного индекса для расчета Alpha/Beta. По умолчанию S&P 500.
    
    Returns:
        Словарь с метриками:
        - portfolio_return_annualized: Годовая доходность портфеля
        - portfolio_volatility_annualized: Годовая волатильность
        - sharpe_ratio: Коэффициент Шарпа (реальный)
        - alpha: Alpha (годовая избыточная доходность)
        - beta: Beta (чувствительность к рынку)
        - max_drawdown: Максимальная просадка
        - total_return: Общая доходность за период
        - benchmark_return: Доходность бенчмарка за период
    """
    
    if not weights:
        return {"error": "Веса портфеля не предоставлены"}
    
    # Устанавливаем даты по умолчанию
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    if not start_date:
        # По умолчанию берем 3 месяца назад для соответствия горизонту прогноза
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    
    logger.info(f"Analyzing portfolio performance from {start_date} to {end_date}")
    
    try:
        # Определяем количество кварталов для расчетов
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        quarters_count = ((end_dt.year - start_dt.year) * 12 + (end_dt.month - start_dt.month)) / 3
        
        # Загружаем цены активов (квартальные данные для соответствия с прогнозами)
        tickers = list(weights.keys())
        logger.info(f"Downloading price data for {len(tickers)} assets: {tickers}")
        
        prices = yf.download(tickers, start=start_date, end=end_date, interval="3mo")["Close"]
        
        if prices.empty:
            return {"error": "Не удалось загрузить ценовые данные"}
        
        # Если только один актив, yfinance возвращает Series, конвертируем в DataFrame
        if isinstance(prices, pd.Series):
            prices = prices.to_frame(tickers[0])
        
        # Проверяем наличие данных для всех активов
        missing_tickers = [t for t in tickers if t not in prices.columns]
        if missing_tickers:
            logger.warning(f"Отсутствуют данные для тикеров: {missing_tickers}")
            # Удаляем отсутствующие тикеры из портфеля и перенормализуем веса
            available_weights = {t: w for t, w in weights.items() if t not in missing_tickers}
            total_weight = sum(available_weights.values())
            if total_weight > 0:
                weights = {t: w/total_weight for t, w in available_weights.items()}
                prices = prices[list(weights.keys())]
            else:
                return {"error": "Нет доступных данных ни для одного актива"}
        
        # Рассчитываем квартальные доходности
        returns = prices.pct_change().dropna()
        
        if returns.empty:
            return {"error": "Недостаточно данных для расчета доходностей"}
        
        # Рассчитываем взвешенную доходность портфеля
        weights_series = pd.Series(weights)
        portfolio_returns = (returns * weights_series).sum(axis=1)
        
        # Загружаем данные бенчмарка
        logger.info(f"Downloading benchmark data for {benchmark}")
        benchmark_data = yf.download(benchmark, start=start_date, end=end_date, interval="3mo")["Close"]
        benchmark_returns = benchmark_data.pct_change().dropna()
        
        # Убеждаемся что benchmark_returns это Series
        if isinstance(benchmark_returns, pd.DataFrame):
            if benchmark_returns.shape[1] == 1:
                benchmark_returns = benchmark_returns.iloc[:, 0]
            else:
                logger.warning("Multiple benchmark columns, taking first")
                benchmark_returns = benchmark_returns.iloc[:, 0]
        
        # Совмещаем данные портфеля и бенчмарка
        combined_data = pd.DataFrame({
            "portfolio": portfolio_returns,
            "benchmark": benchmark_returns
        }).dropna()
        
        if combined_data.empty:
            return {"error": "Нет пересекающихся данных портфеля и бенчмарка"}
        
        # ===== РАСЧЕТ МЕТРИК =====
        
        # 1. Годовая доходность (аннуализация из квартальных данных)
        portfolio_mean_return = combined_data["portfolio"].mean()
        portfolio_return_annualized = portfolio_mean_return * 4  # 4 квартала в году
        
        # 2. Годовая волатильность
        portfolio_volatility_annualized = combined_data["portfolio"].std() * np.sqrt(4)
        
        # 3. Коэффициент Шарпа
        excess_returns = combined_data["portfolio"] - (risk_free_rate / 4)  # Квартальная безрисковая ставка
        if portfolio_volatility_annualized > 0:
            sharpe_ratio = (excess_returns.mean() * 4) / portfolio_volatility_annualized
        else:
            sharpe_ratio = 0
        
        # 4. Alpha и Beta через регрессию CAPM
        X = sm.add_constant(combined_data["benchmark"])  # Добавляем константу для регрессии
        y = combined_data["portfolio"]
        
        # Убеждаемся что y и X имеют правильную размерность (1D)
        if isinstance(y, pd.DataFrame):
            y = y.iloc[:, 0] if y.shape[1] == 1 else y.squeeze()
        if isinstance(X, pd.DataFrame) and X.shape[0] == 1:
            # Если X имеет только одну строку, не можем выполнить регрессию
            logger.warning("Insufficient data points for regression analysis")
            beta = 1.0  # Дефолтная бета
            alpha_annualized = 0.0  # Дефолтная альфа
        else:
            try:
                model = sm.OLS(y, X).fit()
                beta = float(model.params["benchmark"])
                alpha_quarterly = float(model.params["const"])
                alpha_annualized = alpha_quarterly * 4  # Годовая Alpha
            except Exception as e:
                logger.warning(f"Error in CAPM regression: {e}. Using default values.")
                beta = 1.0
                alpha_annualized = 0.0
        
        # 5. Максимальная просадка
        cumulative_returns = (1 + combined_data["portfolio"]).cumprod()
        rolling_max = cumulative_returns.expanding().max()
        drawdown = (cumulative_returns - rolling_max) / rolling_max
        max_drawdown = drawdown.min()
        
        # 6. Общая доходность за период
        total_return = cumulative_returns.iloc[-1] - 1
        
        # 7. Доходность бенчмарка за период
        benchmark_cumulative = (1 + combined_data["benchmark"]).cumprod()
        benchmark_total_return = benchmark_cumulative.iloc[-1] - 1
        
        logger.info(f"Portfolio analysis completed successfully")
        
        return {
            "portfolio_return_annualized": float(portfolio_return_annualized),
            "portfolio_volatility_annualized": float(portfolio_volatility_annualized),
            "sharpe_ratio": float(sharpe_ratio),
            "alpha": float(alpha_annualized),
            "beta": float(beta),
            "max_drawdown": float(max_drawdown),
            "total_return": float(total_return),
            "benchmark_return": float(benchmark_total_return),
            "analysis_period": f"{start_date} to {end_date}",
            "quarters_analyzed": round(quarters_count, 1),
            "benchmark_used": benchmark,
            "risk_free_rate": risk_free_rate
        }
        
    except Exception as e:
        logger.error(f"Error in performance analysis: {str(e)}")
        return {"error": f"Ошибка анализа производительности: {str(e)}"}


def calculate_quarterly_metrics(
    weights: Dict[str, float],
    periods: int = 4,  # Количество кварталов для анализа
    risk_free_rate: float = 0.001  # Снижена с 0.02 до 0.001
) -> Dict:
    """
    Рассчитывает метрики портфеля за несколько кварталов (для валидации 3-месячных прогнозов).
    
    Args:
        weights: Веса портфеля
        periods: Количество кварталов для анализа
        risk_free_rate: Безрисковая ставка (годовая)
    
    Returns:
        Словарь с квартальными метриками
    """
    
    # Рассчитываем стартовую дату (periods кварталов назад)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=periods * 90)  # Примерно 90 дней в квартале
    
    return performance_tool(
        weights=weights,
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        risk_free_rate=risk_free_rate
    )


if __name__ == "__main__":
    # Тест инструмента
    logging.basicConfig(level=logging.INFO)
    
    test_weights = {
        "AAPL": 0.3,
        "MSFT": 0.3,
        "GOOGL": 0.2,
        "TSLA": 0.2
    }
    
    result = performance_tool(test_weights)
    print("Performance Analysis Result:")
    for key, value in result.items():
        if isinstance(value, float):
            print(f"{key}: {value:.4f}")
        else:
            print(f"{key}: {value}") 