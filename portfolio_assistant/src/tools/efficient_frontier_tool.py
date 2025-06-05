import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import tempfile
import matplotlib.pyplot as plt
from pypfopt import EfficientFrontier, risk_models, expected_returns
from pypfopt.plotting import plot_efficient_frontier

# Импортируем централизованную функцию
from .utils import get_available_tickers

logger = logging.getLogger(__name__)

def efficient_frontier_tool(
    tickers: List[str] = None,
    snapshot_id: str = None,
    num_portfolios: int = 100,
    risk_free_rate: float = 0.001,
    max_weight: float = 1.0,
    min_weight: float = 0.0,
    target_returns: List[float] = None,
    sector_filter: str = None
) -> Dict[str, Any]:
    """
    Строит эффективную границу для указанных активов.
    
    Args:
        tickers: Список тикеров для построения границы
        snapshot_id: ID снапшота (опционально)  
        num_portfolios: Количество портфелей на границе
        risk_free_rate: Безрисковая ставка
        max_weight: Максимальный вес актива
        min_weight: Минимальный вес актива
        target_returns: Список целевых доходностей (опционально)
        sector_filter: Фильтр по сектору (tech_giants, financial_sector, etc.)
    
    Returns:
        Словарь с данными эффективной границы и путем к графику
    """
    logger.info(f"Building efficient frontier for tickers: {tickers}")
    
    # Фильтрация по сектору, если указан
    if sector_filter:
        from .index_composition_tool import INDEX_COMPOSITIONS
        
        if sector_filter in INDEX_COMPOSITIONS:
            sector_tickers = INDEX_COMPOSITIONS[sector_filter]
            if tickers:
                # Пересечение указанных тикеров с сектором
                tickers = [t for t in tickers if t in sector_tickers]
            else:
                # Используем все тикеры сектора
                tickers = sector_tickers
            logger.info(f"Applied sector filter '{sector_filter}': {len(tickers)} tickers")
        else:
            available_sectors = list(INDEX_COMPOSITIONS.keys())
            return {
                "error": f"Неизвестный сектор '{sector_filter}'. Доступные: {', '.join(available_sectors)}",
                "available_sectors": available_sectors
            }
    
    # Проверяем доступность тикеров
    available_tickers = get_available_tickers()
    
    if not tickers:
        return {
            "error": "Не указаны тикеры для построения эффективной границы",
            "available_tickers": available_tickers[:10]
        }
    
    # Фильтруем доступные тикеры
    valid_tickers = [t for t in tickers if t in available_tickers]
    invalid_tickers = [t for t in tickers if t not in available_tickers]
    
    if invalid_tickers:
        logger.warning(f"Недоступные тикеры: {invalid_tickers}")
    
    if len(valid_tickers) < 3:
        return {
            "error": f"Для построения эффективной границы требуется минимум 3 доступных тикера, найдено {len(valid_tickers)}",
            "available_tickers": available_tickers[:10],
            "invalid_tickers": invalid_tickers
        }
    
    try:
        # Получаем данные из снапшота или загружаем исторические
        if snapshot_id:
            from ..market_snapshot.registry import SnapshotRegistry
            registry = SnapshotRegistry()
            snapshot = registry.load(snapshot_id)
            
            if not snapshot:
                return {"error": f"Снапшот '{snapshot_id}' не найден"}
            
            # Фильтруем данные по доступным тикерам
            mu_dict = {k: v for k, v in snapshot.mu.items() if k in valid_tickers}
            sigma_dict = {k: {k2: v2 for k2, v2 in v.items() if k2 in valid_tickers} 
                         for k, v in snapshot.sigma.items() if k in valid_tickers}
            
            if len(mu_dict) < 3:
                return {
                    "error": f"В снапшоте недостаточно данных для указанных тикеров: {len(mu_dict)}/3 минимум",
                    "available_in_snapshot": list(mu_dict.keys()),
                    "requested_tickers": valid_tickers
                }
            
            # Преобразуем в pandas структуры
            mu = pd.Series(mu_dict)
            S = pd.DataFrame(sigma_dict).loc[mu.index, mu.index]
            
            logger.info(f"Используем данные снапшота {snapshot_id} для {len(mu)} тикеров")
            
        else:
            # Загружаем исторические данные
            import yfinance as yf
            from datetime import datetime, timedelta, timezone
            
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=2*365)  # 2 года данных
            
            logger.info(f"Загружаем исторические данные с {start_date.strftime('%Y-%m-%d')}")
            
            # Собираем данные по всем тикерам
            price_data = {}
            
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
                    
                    price_data[ticker] = close_prices
                    
                except Exception as e:
                    logger.error(f"Ошибка загрузки данных для {ticker}: {e}")
                    continue
            
            if len(price_data) < 3:
                return {
                    "error": f"Удалось загрузить данные только для {len(price_data)} тикеров, нужно минимум 3",
                    "loaded_tickers": list(price_data.keys()),
                    "failed_tickers": [t for t in valid_tickers if t not in price_data]
                }
            
            # Создаем DataFrame с ценами
            prices_df = pd.DataFrame(price_data)
            prices_df = prices_df.dropna()
            
            if prices_df.empty or len(prices_df) < 60:
                return {
                    "error": "Недостаточно исторических данных для анализа",
                    "observations": len(prices_df) if not prices_df.empty else 0
                }
            
            # Рассчитываем ожидаемые доходности и ковариационную матрицу
            mu = expected_returns.mean_historical_return(prices_df, frequency=252)
            S = risk_models.sample_cov(prices_df, frequency=252)
            
            logger.info(f"Рассчитаны показатели для {len(mu)} тикеров на основе {len(prices_df)} наблюдений")
        
        # Фиксируем проблемы с ковариационной матрицей
        S = risk_models.fix_nonpositive_semidefinite(S, fix_method='spectral')
        
        # Строим эффективную границу
        ef = EfficientFrontier(mu, S, weight_bounds=(min_weight, max_weight))
        
        # Получаем минимальную и максимальную доходности
        ef_max_sharpe = EfficientFrontier(mu, S, weight_bounds=(min_weight, max_weight))
        ef_max_sharpe.max_sharpe(risk_free_rate=risk_free_rate)
        max_sharpe_ret, max_sharpe_vol, _ = ef_max_sharpe.portfolio_performance(risk_free_rate=risk_free_rate)
        
        ef_min_vol = EfficientFrontier(mu, S, weight_bounds=(min_weight, max_weight))
        ef_min_vol.min_volatility()
        min_vol_ret, min_vol_vol, _ = ef_min_vol.portfolio_performance(risk_free_rate=risk_free_rate)
        
        # Определяем диапазон целевых доходностей
        if target_returns:
            target_rets = target_returns
        else:
            ret_range = max_sharpe_ret - min_vol_ret
            target_rets = np.linspace(
                min_vol_ret, 
                min_vol_ret + ret_range * 1.2,  # Немного расширяем диапазон
                num_portfolios
            )
        
        # Строим портфели для каждой целевой доходности
        frontier_data = {
            "returns": [],
            "volatilities": [],
            "sharpe_ratios": [],
            "weights": []
        }
        
        successful_portfolios = 0
        
        for target_ret in target_rets:
            try:
                ef_temp = EfficientFrontier(mu, S, weight_bounds=(min_weight, max_weight))
                ef_temp.efficient_return(target_ret)
                ret, vol, sharpe = ef_temp.portfolio_performance(risk_free_rate=risk_free_rate)
                weights = ef_temp.clean_weights()
                
                frontier_data["returns"].append(float(ret))
                frontier_data["volatilities"].append(float(vol))
                frontier_data["sharpe_ratios"].append(float(sharpe))
                frontier_data["weights"].append(weights)
                
                successful_portfolios += 1
                
            except Exception as e:
                logger.debug(f"Не удалось построить портфель для доходности {target_ret:.4f}: {e}")
                continue
        
        if successful_portfolios < 5:
            return {
                "error": f"Удалось построить только {successful_portfolios} портфелей на эффективной границе",
                "min_vol_portfolio": {"return": min_vol_ret, "volatility": min_vol_vol},
                "max_sharpe_portfolio": {"return": max_sharpe_ret, "volatility": max_sharpe_vol}
            }
        
        # Создаем график эффективной границы
        plt.figure(figsize=(12, 8))
        
        # Строим эффективную границу
        plt.scatter(frontier_data["volatilities"], frontier_data["returns"], 
                   c=frontier_data["sharpe_ratios"], cmap='viridis', marker='o', s=50, alpha=0.7)
        plt.colorbar(label='Коэффициент Шарпа')
        
        # Отмечаем специальные портфели
        plt.scatter(min_vol_vol, min_vol_ret, color='red', marker='*', s=300, 
                   label=f'Минимальный риск\n(σ={min_vol_vol:.3f}, μ={min_vol_ret:.3f})')
        plt.scatter(max_sharpe_vol, max_sharpe_ret, color='orange', marker='*', s=300,
                   label=f'Максимальный Шарп\n(σ={max_sharpe_vol:.3f}, μ={max_sharpe_ret:.3f})')
        
        # Строим линию рынка капитала
        max_ret = max(frontier_data["returns"])
        vol_range = np.linspace(0, max(frontier_data["volatilities"]) * 1.1, 100)
        market_line = risk_free_rate + (max_sharpe_ret - risk_free_rate) / max_sharpe_vol * vol_range
        plt.plot(vol_range, market_line, 'r--', alpha=0.7, label=f'Линия рынка капитала\n(rf={risk_free_rate:.3f})')
        
        plt.xlabel('Волатильность (риск)')
        plt.ylabel('Ожидаемая доходность')
        plt.title(f'Эффективная граница ({len(valid_tickers)} активов)')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Сохраняем график
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
            plt.savefig(tmp_file.name, dpi=300, bbox_inches='tight')
            plt.close()
            plot_path = tmp_file.name
        
        # Дополнительная аналитика
        # Портфель с максимальным коэффициентом Шарпа
        max_sharpe_idx = np.argmax(frontier_data["sharpe_ratios"])
        optimal_portfolio = {
            "return": frontier_data["returns"][max_sharpe_idx],
            "volatility": frontier_data["volatilities"][max_sharpe_idx], 
            "sharpe_ratio": frontier_data["sharpe_ratios"][max_sharpe_idx],
            "weights": frontier_data["weights"][max_sharpe_idx]
        }
        
        results = {
            "frontier_data": frontier_data,
            "num_portfolios": successful_portfolios,
            "optimal_portfolio": optimal_portfolio,
            "min_volatility_portfolio": {
                "return": float(min_vol_ret),
                "volatility": float(min_vol_vol),
                "weights": ef_min_vol.clean_weights()
            },
            "max_sharpe_portfolio": {
                "return": float(max_sharpe_ret),
                "volatility": float(max_sharpe_vol),
                "weights": ef_max_sharpe.clean_weights()
            },
            "analysis_params": {
                "tickers": valid_tickers,
                "risk_free_rate": risk_free_rate,
                "weight_bounds": (min_weight, max_weight),
                "using_snapshot": bool(snapshot_id)
            },
            "plot_path": plot_path,
            "error": None
        }
        
        logger.info(f"Построена эффективная граница с {successful_portfolios} портфелями")
        return results
        
    except Exception as e:
        logger.error(f"Ошибка при построении эффективной границы: {e}", exc_info=True)
        return {
            "error": f"Ошибка при построении эффективной границы: {str(e)}",
            "requested_tickers": tickers,
            "valid_tickers": valid_tickers
        }

if __name__ == "__main__":
    # Тестирование
    logging.basicConfig(level=logging.INFO)
    
    # Тест построения эффективной границы
    test_tickers = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"]
    
    result = efficient_frontier_tool(tickers=test_tickers, sector_filter="tech_giants")
    print(f"Efficient frontier result: {result.get('analysis_params', 'Error occurred')}") 