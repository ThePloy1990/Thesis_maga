import logging
import numpy as np
import pandas as pd
import yfinance as yf
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import matplotlib.pyplot as plt
import seaborn as sns

logger = logging.getLogger(__name__)

# Импортируем централизованную функцию вместо дублирования
def get_available_tickers() -> List[str]:
    """Получает список доступных тикеров на основе наличия моделей CatBoost."""
    models_path = Path(__file__).absolute().parent.parent.parent.parent / "models"
    available_tickers = []
    
    try:
        for model_file in models_path.glob("catboost_*.cbm"):
            ticker = model_file.stem.replace("catboost_", "")
            if ticker and ticker.upper() not in ["TEST", "DUMMY"]:
                available_tickers.append(ticker)
        return sorted(available_tickers)
    except Exception as e:
        logger.error(f"Error scanning for available tickers: {e}")
        return []

def correlation_tool(
    tickers: List[str] = None,
    period_days: int = 252,  # 1 год по умолчанию
    correlation_type: str = "pearson",  # pearson, spearman, kendall
    rolling_window: int = None,  # Для скользящей корреляции
    snapshot_id: str = None
) -> Dict[str, Any]:
    """
    Рассчитывает корреляции между указанными активами.
    
    Args:
        tickers: Список тикеров для анализа корреляций
        period_days: Период анализа в днях
        correlation_type: Тип корреляции (pearson, spearman, kendall)
        rolling_window: Окно для скользящей корреляции (опционально)
        snapshot_id: ID снапшота для использования готовых данных
    
    Returns:
        Словарь с корреляционными данными и путем к графику
    """
    logger.info(f"Calculating correlations for tickers: {tickers}")
    
    # Проверяем доступность тикеров
    available_tickers = get_available_tickers()
    
    if not tickers or len(tickers) < 2:
        return {
            "error": "Для анализа корреляций требуется минимум 2 тикера",
            "available_tickers": available_tickers[:10]
        }
    
    # Фильтруем доступные тикеры
    valid_tickers = [t for t in tickers if t in available_tickers]
    invalid_tickers = [t for t in tickers if t not in available_tickers]
    
    if invalid_tickers:
        logger.warning(f"Недоступные тикеры: {invalid_tickers}")
    
    if len(valid_tickers) < 2:
        return {
            "error": f"Доступно только {len(valid_tickers)} тикера из {len(tickers)}, нужно минимум 2",
            "available_tickers": available_tickers[:10],
            "invalid_tickers": invalid_tickers
        }
    
    try:
        # Загружаем исторические данные
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=period_days + 100)  # Добавляем буфер
        
        logger.info(f"Загружаем данные с {start_date.strftime('%Y-%m-%d')} по {end_date.strftime('%Y-%m-%d')}")
        
        # Собираем данные по всем тикерам
        price_data = {}
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
                if isinstance(ticker_data.columns, pd.MultiIndex):
                    try:
                        close_prices = ticker_data.xs('Close', level=0, axis=1)
                        if isinstance(close_prices, pd.DataFrame) and len(close_prices.columns) == 1:
                            close_prices = close_prices.iloc[:, 0]
                    except:
                        close_prices = ticker_data.iloc[:, 3]
                else:
                    close_prices = ticker_data['Close']
                
                # Рассчитываем логарифмические доходности
                log_returns = np.log(close_prices / close_prices.shift(1)).dropna()
                
                price_data[ticker] = close_prices
                returns_data[ticker] = log_returns
                
                logger.info(f"Загружено {len(log_returns)} наблюдений для {ticker}")
                
            except Exception as e:
                logger.error(f"Ошибка загрузки данных для {ticker}: {e}")
                continue
        
        if len(returns_data) < 2:
            return {
                "error": f"Удалось загрузить данные только для {len(returns_data)} тикеров",
                "loaded_tickers": list(returns_data.keys()),
                "failed_tickers": [t for t in valid_tickers if t not in returns_data]
            }
        
        # Создаем DataFrame с доходностями
        returns_df = pd.DataFrame(returns_data)
        returns_df = returns_df.dropna()
        
        if returns_df.empty or len(returns_df) < 30:
            return {
                "error": "Недостаточно данных для корреляционного анализа",
                "observations": len(returns_df) if not returns_df.empty else 0
            }
        
        # Ограничиваем период анализа
        if len(returns_df) > period_days:
            returns_df = returns_df.tail(period_days)
        
        # Рассчитываем корреляционную матрицу
        if correlation_type.lower() == "pearson":
            correlation_matrix = returns_df.corr(method='pearson')
        elif correlation_type.lower() == "spearman":
            correlation_matrix = returns_df.corr(method='spearman')
        elif correlation_type.lower() == "kendall":
            correlation_matrix = returns_df.corr(method='kendall')
        else:
            return {
                "error": f"Неизвестный тип корреляции: {correlation_type}. Доступные: pearson, spearman, kendall"
            }
        
        # Создаем результирующую структуру
        results = {
            "correlation_matrix": correlation_matrix.round(4).to_dict(),
            "tickers_analyzed": list(returns_df.columns),
            "observations": len(returns_df),
            "analysis_period": {
                "start_date": returns_df.index[0].strftime('%Y-%m-%d'),
                "end_date": returns_df.index[-1].strftime('%Y-%m-%d'),
                "days": len(returns_df)
            },
            "correlation_type": correlation_type,
            "statistics": {},
            "pairwise_correlations": {},
            "rolling_correlations": None,
            "plot_paths": []
        }
        
        # Статистика корреляций
        corr_values = correlation_matrix.values
        upper_triangle = corr_values[np.triu_indices_from(corr_values, 1)]
        
        results["statistics"] = {
            "mean_correlation": float(np.mean(upper_triangle)),
            "median_correlation": float(np.median(upper_triangle)),
            "std_correlation": float(np.std(upper_triangle)),
            "min_correlation": float(np.min(upper_triangle)),
            "max_correlation": float(np.max(upper_triangle)),
            "num_pairs": len(upper_triangle)
        }
        
        # Парные корреляции с деталями
        for i, ticker1 in enumerate(returns_df.columns):
            for j, ticker2 in enumerate(returns_df.columns):
                if i < j:  # Избегаем дублирования
                    correlation_value = correlation_matrix.loc[ticker1, ticker2]
                    
                    # Дополнительная статистика для пары
                    returns1 = returns_df[ticker1]
                    returns2 = returns_df[ticker2]
                    
                    # Коэффициент детерминации (R²)
                    r_squared = correlation_value ** 2
                    
                    results["pairwise_correlations"][f"{ticker1}_{ticker2}"] = {
                        "correlation": float(correlation_value),
                        "r_squared": float(r_squared),
                        "interpretation": _interpret_correlation(correlation_value),
                        "volatility_1": float(returns1.std() * np.sqrt(252)),  # Годовая волатильность
                        "volatility_2": float(returns2.std() * np.sqrt(252)),
                        "mean_return_1": float(returns1.mean() * 252),  # Годовая доходность
                        "mean_return_2": float(returns2.mean() * 252)
                    }
        
        # Скользящие корреляции (если запрошены)
        if rolling_window and rolling_window > 10:
            rolling_correlations = {}
            
            for i, ticker1 in enumerate(returns_df.columns):
                for j, ticker2 in enumerate(returns_df.columns):
                    if i < j:
                        rolling_corr = returns_df[ticker1].rolling(window=rolling_window).corr(returns_df[ticker2])
                        rolling_corr = rolling_corr.dropna()
                        
                        if len(rolling_corr) > 0:
                            rolling_correlations[f"{ticker1}_{ticker2}"] = {
                                "values": rolling_corr.tolist(),
                                "dates": [d.strftime('%Y-%m-%d') for d in rolling_corr.index],
                                "mean": float(rolling_corr.mean()),
                                "std": float(rolling_corr.std()),
                                "min": float(rolling_corr.min()),
                                "max": float(rolling_corr.max())
                            }
            
            results["rolling_correlations"] = rolling_correlations
        
        # Создаем тепловую карту корреляций
        plt.figure(figsize=(12, 10))
        
        # Основная тепловая карта
        mask = np.triu(np.ones_like(correlation_matrix, dtype=bool))  # Маска для верхнего треугольника
        sns.heatmap(
            correlation_matrix, 
            annot=True, 
            cmap='RdBu_r', 
            center=0,
            fmt='.3f',
            square=True,
            mask=mask,
            cbar_kws={"shrink": .8}
        )
        
        plt.title(f'Корреляционная матрица ({correlation_type.title()})\n'
                 f'{len(returns_df.columns)} активов, {len(returns_df)} наблюдений')
        plt.tight_layout()
        
        # Сохраняем основной график
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
            plt.savefig(tmp_file.name, dpi=300, bbox_inches='tight')
            plt.close()
            results["plot_paths"].append(tmp_file.name)
        
        # Если есть скользящие корреляции, создаем дополнительный график
        if rolling_window and results["rolling_correlations"]:
            _create_rolling_correlation_plot(results["rolling_correlations"], rolling_window, results["plot_paths"])
        
        # Определяем наиболее/наименее коррелированные пары
        pairs_with_corr = []
        for pair, data in results["pairwise_correlations"].items():
            pairs_with_corr.append((pair, data["correlation"]))
        
        pairs_with_corr.sort(key=lambda x: abs(x[1]), reverse=True)
        
        results["top_correlations"] = {
            "highest_positive": [p for p in pairs_with_corr if p[1] > 0][:5],
            "highest_negative": [p for p in pairs_with_corr if p[1] < 0][:5],
            "lowest_absolute": sorted(pairs_with_corr, key=lambda x: abs(x[1]))[:5]
        }
        
        logger.info(f"Корреляционный анализ завершен для {len(returns_df.columns)} активов")
        return results
        
    except Exception as e:
        logger.error(f"Ошибка при корреляционном анализе: {e}", exc_info=True)
        return {
            "error": f"Ошибка при корреляционном анализе: {str(e)}",
            "requested_tickers": tickers,
            "valid_tickers": valid_tickers
        }

def _interpret_correlation(correlation: float) -> str:
    """Интерпретирует значение корреляции."""
    abs_corr = abs(correlation)
    direction = "положительная" if correlation > 0 else "отрицательная"
    
    if abs_corr >= 0.8:
        strength = "очень сильная"
    elif abs_corr >= 0.6:
        strength = "сильная"
    elif abs_corr >= 0.4:
        strength = "умеренная"
    elif abs_corr >= 0.2:
        strength = "слабая"
    else:
        strength = "очень слабая"
    
    return f"{strength} {direction} корреляция"

def _create_rolling_correlation_plot(rolling_data: Dict[str, Any], window: int, plot_paths: List[str]) -> None:
    """Создает график скользящих корреляций."""
    plt.figure(figsize=(14, 8))
    
    for pair, data in rolling_data.items():
        dates = pd.to_datetime(data["dates"])
        values = data["values"]
        plt.plot(dates, values, label=pair, alpha=0.7, linewidth=2)
    
    plt.axhline(y=0, color='black', linestyle='--', alpha=0.3)
    plt.axhline(y=0.5, color='green', linestyle=':', alpha=0.5, label='Умеренная корреляция')
    plt.axhline(y=-0.5, color='red', linestyle=':', alpha=0.5)
    
    plt.title(f'Скользящие корреляции (окно: {window} дней)')
    plt.xlabel('Дата')
    plt.ylabel('Корреляция')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    # Сохраняем график скользящих корреляций
    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
        plt.savefig(tmp_file.name, dpi=300, bbox_inches='tight')
        plt.close()
        plot_paths.append(tmp_file.name)

if __name__ == "__main__":
    # Тестирование
    logging.basicConfig(level=logging.INFO)
    
    # Тест корреляционного анализа
    test_tickers = ["AAPL", "MSFT", "GOOGL", "TSLA"]
    
    result = correlation_tool(
        tickers=test_tickers,
        period_days=252,
        correlation_type="pearson",
        rolling_window=30
    )
    
    print(f"Correlation analysis result: {result.get('statistics', 'Error occurred')}") 