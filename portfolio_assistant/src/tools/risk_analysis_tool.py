import logging
import numpy as np
import pandas as pd
import yfinance as yf
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, timezone
from pathlib import Path
from scipy import stats

logger = logging.getLogger(__name__)

def get_available_tickers() -> List[str]:
    """Получает список доступных тикеров на основе наличия моделей CatBoost."""
    models_path = Path(__file__).absolute().parent.parent.parent.parent / "models"
    available_tickers = []
    
    for model_file in models_path.glob("catboost_*.cbm"):
        ticker = model_file.stem.replace("catboost_", "")
        if ticker:
            available_tickers.append(ticker)
    
    return available_tickers

def risk_analysis_tool(
    tickers: List[str] = None,
    weights: Dict[str, float] = None,
    confidence_level: float = 0.95,
    horizon_days: int = 252  # 1 год торговых дней
) -> Dict[str, Any]:
    """
    Выполняет углубленный анализ рисков для портфеля или отдельных активов.
    
    Args:
        tickers: Список тикеров для анализа
        weights: Веса активов в портфеле (опционально)
        confidence_level: Уровень доверия для VaR (по умолчанию 95%)
        horizon_days: Горизонт анализа в торговых днях
    
    Returns:
        Словарь с детальной информацией о рисках
    """
    logger.info(f"Performing risk analysis for tickers: {tickers}")
    
    # Проверяем доступность тикеров
    available_tickers = get_available_tickers()
    
    if not tickers:
        return {
            "error": "Не указаны тикеры для анализа",
            "available_tickers": available_tickers[:10]  # Показываем первые 10 для примера
        }
    
    # Фильтруем доступные тикеры
    valid_tickers = [t for t in tickers if t in available_tickers]
    invalid_tickers = [t for t in tickers if t not in available_tickers]
    
    if invalid_tickers:
        logger.warning(f"Недоступные тикеры: {invalid_tickers}")
    
    if not valid_tickers:
        return {
            "error": f"Ни один из указанных тикеров не доступен. Недоступные: {invalid_tickers}",
            "available_tickers": available_tickers[:10]
        }
    
    try:
        # Загружаем исторические данные
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=horizon_days + 100)  # Добавляем буфер для расчетов
        
        logger.info(f"Загружаем данные с {start_date.strftime('%Y-%m-%d')} по {end_date.strftime('%Y-%m-%d')}")
        
        # Собираем данные по всем тикерам
        prices_data = {}
        returns_data = {}
        
        for ticker in valid_tickers:
            try:
                ticker_data = yf.download(
                    ticker, 
                    start=start_date.strftime("%Y-%m-%d"), 
                    end=end_date.strftime("%Y-%m-%d"),
                    progress=False,
                    auto_adjust=True
                )
                
                if ticker_data.empty:
                    logger.warning(f"Нет данных для {ticker}")
                    continue
                
                # Получаем цены закрытия
                close_column = 'Close'
                if isinstance(ticker_data.columns, pd.MultiIndex):
                    try:
                        close_prices = ticker_data.xs('Close', level=0, axis=1)
                        if isinstance(close_prices, pd.DataFrame) and len(close_prices.columns) == 1:
                            close_prices = close_prices.iloc[:, 0]
                    except:
                        close_prices = ticker_data.iloc[:, 3]  # Обычно Close - 4-я колонка
                else:
                    close_prices = ticker_data[close_column]
                
                # Рассчитываем логарифмические доходности
                log_returns = np.log(close_prices / close_prices.shift(1)).dropna()
                
                prices_data[ticker] = close_prices
                returns_data[ticker] = log_returns
                
                logger.info(f"Загружено {len(log_returns)} наблюдений для {ticker}")
                
            except Exception as e:
                logger.error(f"Ошибка загрузки данных для {ticker}: {e}")
                continue
        
        if not returns_data:
            return {
                "error": "Не удалось загрузить данные ни для одного тикера",
                "requested_tickers": tickers,
                "valid_tickers": valid_tickers
            }
        
        # Создаем DataFrame с доходностями
        returns_df = pd.DataFrame(returns_data)
        returns_df = returns_df.dropna()
        
        if returns_df.empty:
            return {
                "error": "После обработки данных не осталось наблюдений",
                "requested_tickers": tickers,
                "loaded_tickers": list(returns_data.keys())
            }
        
        # Базовая статистика
        results = {
            "analysis_period": {
                "start_date": returns_df.index[0].strftime('%Y-%m-%d'),
                "end_date": returns_df.index[-1].strftime('%Y-%m-%d'),
                "observations": len(returns_df),
                "tickers_analyzed": list(returns_df.columns)
            },
            "individual_risks": {},
            "portfolio_risk": None,
            "correlations": {},
            "var_analysis": {},
            "drawdown_analysis": {}
        }
        
        # Анализ рисков отдельных активов
        for ticker in returns_df.columns:
            ticker_returns = returns_df[ticker]
            
            # Базовая статистика
            annual_return = ticker_returns.mean() * 252
            annual_volatility = ticker_returns.std() * np.sqrt(252)
            
            # VaR и Expected Shortfall
            var_daily = np.percentile(ticker_returns, (1 - confidence_level) * 100)
            var_annual = var_daily * np.sqrt(252)
            es_daily = ticker_returns[ticker_returns <= var_daily].mean() if len(ticker_returns[ticker_returns <= var_daily]) > 0 else var_daily
            es_annual = es_daily * np.sqrt(252)
            
            # Максимальная просадка
            cumulative = (1 + ticker_returns).cumprod()
            running_max = cumulative.expanding().max()
            drawdown = (cumulative - running_max) / running_max
            max_drawdown = drawdown.min()
            
            # Тестирование нормальности (Jarque-Bera)
            jb_stat, jb_pvalue = stats.jarque_bera(ticker_returns.dropna())
            
            results["individual_risks"][ticker] = {
                "annual_return": float(annual_return),
                "annual_volatility": float(annual_volatility),
                "sharpe_ratio": float(annual_return / annual_volatility) if annual_volatility > 0 else 0,
                "var_daily_95": float(var_daily),
                "var_annual_95": float(var_annual),
                "expected_shortfall_daily": float(es_daily),
                "expected_shortfall_annual": float(es_annual),
                "max_drawdown": float(max_drawdown),
                "skewness": float(ticker_returns.skew()),
                "kurtosis": float(ticker_returns.kurtosis()),
                "jarque_bera_stat": float(jb_stat),
                "jarque_bera_pvalue": float(jb_pvalue),
                "is_normal_distribution": bool(jb_pvalue > 0.05)
            }
        
        # Корреляционный анализ
        correlation_matrix = returns_df.corr()
        results["correlations"] = {
            "correlation_matrix": correlation_matrix.round(4).to_dict(),
            "average_correlation": float(correlation_matrix.values[np.triu_indices_from(correlation_matrix.values, 1)].mean()),
            "max_correlation": float(correlation_matrix.values[np.triu_indices_from(correlation_matrix.values, 1)].max()),
            "min_correlation": float(correlation_matrix.values[np.triu_indices_from(correlation_matrix.values, 1)].min())
        }
        
        # Анализ портфеля (если предоставлены веса)
        if weights and len(weights) > 0:
            # Нормализуем веса для тикеров, которые есть в данных
            portfolio_weights = {}
            total_weight = 0
            
            for ticker in returns_df.columns:
                if ticker in weights:
                    portfolio_weights[ticker] = weights[ticker]
                    total_weight += weights[ticker]
            
            if total_weight > 0:
                # Нормализуем веса
                portfolio_weights = {k: v/total_weight for k, v in portfolio_weights.items()}
                
                # Рассчитываем портфельные доходности
                portfolio_returns = sum(returns_df[ticker] * weight for ticker, weight in portfolio_weights.items())
                
                # Портфельная статистика
                portfolio_annual_return = portfolio_returns.mean() * 252
                portfolio_annual_volatility = portfolio_returns.std() * np.sqrt(252)
                
                # Портфельный VaR
                portfolio_var_daily = np.percentile(portfolio_returns, (1 - confidence_level) * 100)
                portfolio_var_annual = portfolio_var_daily * np.sqrt(252)
                
                # Максимальная просадка портфеля
                portfolio_cumulative = (1 + portfolio_returns).cumprod()
                portfolio_running_max = portfolio_cumulative.expanding().max()
                portfolio_drawdown = (portfolio_cumulative - portfolio_running_max) / portfolio_running_max
                portfolio_max_drawdown = portfolio_drawdown.min()
                
                results["portfolio_risk"] = {
                    "weights": portfolio_weights,
                    "annual_return": float(portfolio_annual_return),
                    "annual_volatility": float(portfolio_annual_volatility),
                    "sharpe_ratio": float(portfolio_annual_return / portfolio_annual_volatility) if portfolio_annual_volatility > 0 else 0,
                    "var_daily_95": float(portfolio_var_daily),
                    "var_annual_95": float(portfolio_var_annual),
                    "max_drawdown": float(portfolio_max_drawdown),
                    "diversification_ratio": float(sum(portfolio_weights[ticker] * results["individual_risks"][ticker]["annual_volatility"] 
                                                     for ticker in portfolio_weights) / portfolio_annual_volatility) if portfolio_annual_volatility > 0 else 1
                }
        
        # VaR анализ на разных уровнях доверия
        var_levels = [0.90, 0.95, 0.99]
        results["var_analysis"] = {
            "confidence_levels": {}
        }
        
        for level in var_levels:
            level_results = {}
            for ticker in returns_df.columns:
                var_daily = np.percentile(returns_df[ticker], (1 - level) * 100)
                level_results[ticker] = {
                    "var_daily": float(var_daily),
                    "var_annual": float(var_daily * np.sqrt(252))
                }
            results["var_analysis"]["confidence_levels"][f"{level:.0%}"] = level_results
        
        return results
        
    except Exception as e:
        logger.error(f"Ошибка при анализе рисков: {e}", exc_info=True)
        return {
            "error": f"Ошибка при анализе рисков: {str(e)}",
            "requested_tickers": tickers,
            "valid_tickers": valid_tickers
        }

if __name__ == "__main__":
    # Тестирование
    logging.basicConfig(level=logging.INFO)
    
    # Тест анализа рисков
    test_tickers = ["AAPL", "MSFT", "TSLA"]
    test_weights = {"AAPL": 0.4, "MSFT": 0.4, "TSLA": 0.2}
    
    result = risk_analysis_tool(tickers=test_tickers, weights=test_weights)
    print(f"Risk analysis result: {result}") 