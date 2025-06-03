#!/usr/bin/env python3
"""
Тестирование forecast_tool после исправлений
"""

import logging
import sys
from pathlib import Path

# Добавляем путь к модулям
sys.path.append(str(Path(__file__).parent / "portfolio_assistant" / "src" / "tools"))

from forecast_tool import forecast_tool

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_forecast_multiple_tickers():
    """
    Тестируем forecast_tool на нескольких тикерах из проблемного списка
    """
    # Выбираем тикеры, для которых у нас есть модели
    test_tickers = [
        'PG', 'LIN', 'MTD', 'CMI', 'NRG', 'LEN', 'RL', 'FFIV', 
        'ES', 'IP', 'NEM', 'KMB', 'ROL', 'RMD', 'AOS', 'RCL', 
        'DG', 'VMC', 'PANW', 'LDOS', 'NFLX', 'NWSA', 'KEYS', 
        'MHK', 'CPB', 'D', 'SNPS', 'T', 'JNJ', 'PKG'
    ]
    
    results = {}
    successful_forecasts = 0
    failed_forecasts = 0
    
    logger.info(f"Начинаем тестирование {len(test_tickers)} тикеров...")
    print("="*80)
    
    for i, ticker in enumerate(test_tickers, 1):
        logger.info(f"[{i}/{len(test_tickers)}] Тестируем тикер: {ticker}")
        
        try:
            result = forecast_tool(ticker=ticker)
            results[ticker] = result
            
            if result.get('error'):
                logger.error(f"❌ {ticker}: {result['error']}")
                failed_forecasts += 1
            elif result.get('mu') is not None:
                mu = result['mu']
                sigma = result.get('sigma', 'N/A')
                logger.info(f"✅ {ticker}: mu={mu:.6f}, sigma={sigma}")
                successful_forecasts += 1
            else:
                logger.warning(f"⚠️  {ticker}: Неожиданный результат")
                failed_forecasts += 1
                
        except Exception as e:
            logger.error(f"❌ {ticker}: Исключение - {e}")
            results[ticker] = {"error": str(e)}
            failed_forecasts += 1
        
        print("-" * 40)
    
    # Итоговая статистика
    print("="*80)
    logger.info(f"РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    logger.info(f"✅ Успешных прогнозов: {successful_forecasts}")
    logger.info(f"❌ Неудачных прогнозов: {failed_forecasts}")
    logger.info(f"📊 Процент успеха: {(successful_forecasts/(successful_forecasts+failed_forecasts))*100:.1f}%")
    
    # Подробные результаты для успешных прогнозов
    print("\n" + "="*80)
    print("УСПЕШНЫЕ ПРОГНОЗЫ:")
    print("="*80)
    for ticker, result in results.items():
        if not result.get('error') and result.get('mu') is not None:
            mu = result['mu']
            sigma = result.get('sigma', 'N/A')
            horizon = result.get('horizon', '3 months')
            print(f"{ticker:6} | mu: {mu:8.6f} | sigma: {sigma:>8} | horizon: {horizon}")
    
    # Ошибки
    print("\n" + "="*80)
    print("ОШИБКИ:")
    print("="*80)
    for ticker, result in results.items():
        if result.get('error'):
            print(f"{ticker:6} | {result['error']}")
    
    return results

if __name__ == "__main__":
    logger.info("🚀 Запуск тестирования forecast_tool...")
    results = test_forecast_multiple_tickers()
    logger.info("✨ Тестирование завершено!") 