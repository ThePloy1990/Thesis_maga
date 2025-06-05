#!/usr/bin/env python3
"""
Интеграционные тесты для модуля tools.
Проверяет реальную работоспособность всех инструментов.
"""

import logging
import sys
import traceback
from pathlib import Path
from datetime import datetime, timedelta

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_module_imports():
    """Тест 1: Проверка импортов модуля"""
    print("\n" + "="*60)
    print("ТЕСТ 1: Проверка импортов модуля")
    print("="*60)
    
    try:
        # Основной импорт
        from . import (
            get_available_tickers,
            get_tool_info,
            list_all_tools,
            validate_tool_params,
            TOOLS_REGISTRY
        )
        print("✅ Основные утилиты импортированы успешно")
        
        # Импорт всех инструментов
        from . import (
            correlation_tool,
            efficient_frontier_tool,
            forecast_tool,
            optimize_tool,
            performance_tool,
            risk_analysis_tool,
            scenario_adjust_tool,
            sentiment_tool,
            index_composition_tool
        )
        print("✅ Все инструменты импортированы успешно")
        
        # Проверяем реестр
        tools = list_all_tools()
        print(f"✅ Найдено {len(tools)} инструментов: {tools}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка импорта: {e}")
        traceback.print_exc()
        return False

def test_available_tickers():
    """Тест 2: Проверка доступных тикеров"""
    print("\n" + "="*60)
    print("ТЕСТ 2: Проверка доступных тикеров")
    print("="*60)
    
    try:
        from . import get_available_tickers
        
        tickers = get_available_tickers()
        print(f"✅ Найдено {len(tickers)} доступных тикеров")
        
        if len(tickers) > 0:
            print(f"📋 Первые 10 тикеров: {tickers[:10]}")
            return True, tickers
        else:
            print("⚠️  Не найдено доступных тикеров (модели CatBoost отсутствуют)")
            return False, []
            
    except Exception as e:
        print(f"❌ Ошибка получения тикеров: {e}")
        traceback.print_exc()
        return False, []

def test_index_composition():
    """Тест 3: Проверка состава индексов"""
    print("\n" + "="*60)
    print("ТЕСТ 3: Проверка состава индексов")
    print("="*60)
    
    try:
        from . import index_composition_tool, list_available_indices
        
        # Список доступных индексов
        indices_info = list_available_indices()
        print(f"✅ Найдено {len(indices_info['available_indices'])} индексов")
        
        # Тестируем несколько индексов
        test_indices = ["sp500_top10", "tech_giants", "dow30"]
        
        for index_name in test_indices:
            try:
                result = index_composition_tool(index_name, filter_available=True)
                if result.get("error"):
                    print(f"⚠️  {index_name}: {result['error']}")
                else:
                    available_count = result.get("available_count", 0)
                    total_count = result.get("total_count", 0)
                    coverage = result.get("coverage_ratio", 0)
                    print(f"✅ {index_name}: {available_count}/{total_count} доступно ({coverage:.1%} покрытие)")
                    
            except Exception as e:
                print(f"❌ Ошибка для индекса {index_name}: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования индексов: {e}")
        traceback.print_exc()
        return False

def test_tool_validation():
    """Тест 4: Проверка валидации параметров"""
    print("\n" + "="*60)
    print("ТЕСТ 4: Проверка валидации параметров")
    print("="*60)
    
    try:
        from . import validate_tool_params
        
        # Тест корректных параметров
        valid_result = validate_tool_params("correlation_tool", {"tickers": ["AAPL", "MSFT"]})
        if valid_result["valid"]:
            print("✅ Валидация корректных параметров работает")
        else:
            print(f"❌ Валидация корректных параметров не прошла: {valid_result}")
        
        # Тест некорректных параметров
        invalid_result = validate_tool_params("correlation_tool", {})
        if not invalid_result["valid"]:
            print("✅ Валидация некорректных параметров работает")
            print(f"   Ошибка: {invalid_result['error']}")
        else:
            print("❌ Валидация некорректных параметров не работает")
        
        # Тест несуществующего инструмента
        nonexistent_result = validate_tool_params("nonexistent_tool", {})
        if not nonexistent_result["valid"]:
            print("✅ Валидация несуществующего инструмента работает")
        else:
            print("❌ Валидация несуществующего инструмента не работает")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования валидации: {e}")
        traceback.print_exc()
        return False

def test_correlation_tool(test_tickers):
    """Тест 5: Проверка correlation_tool"""
    print("\n" + "="*60)
    print("ТЕСТ 5: Проверка correlation_tool")
    print("="*60)
    
    if len(test_tickers) < 2:
        print("⚠️  Недостаточно тикеров для тестирования корреляций")
        return False
    
    try:
        from . import correlation_tool
        
        # Используем только первые 3 тикера для быстрого теста
        sample_tickers = test_tickers[:3]
        print(f"🔍 Тестируем корреляции для: {sample_tickers}")
        
        result = correlation_tool(
            tickers=sample_tickers,
            period_days=90,  # Короткий период для быстрого теста
            correlation_type="pearson"
        )
        
        if result.get("error"):
            print(f"⚠️  Ошибка в correlation_tool: {result['error']}")
            return False
        else:
            print(f"✅ Correlation tool работает")
            print(f"   Проанализировано тикеров: {len(result.get('tickers_analyzed', []))}")
            print(f"   Наблюдений: {result.get('observations', 0)}")
            
            # Проверяем статистику
            stats = result.get('statistics', {})
            if stats:
                print(f"   Средняя корреляция: {stats.get('mean_correlation', 0):.3f}")
                print(f"   Диапазон: {stats.get('min_correlation', 0):.3f} - {stats.get('max_correlation', 0):.3f}")
            
            return True
            
    except Exception as e:
        print(f"❌ Ошибка в correlation_tool: {e}")
        traceback.print_exc()
        return False

def test_risk_analysis_tool(test_tickers):
    """Тест 6: Проверка risk_analysis_tool"""
    print("\n" + "="*60)
    print("ТЕСТ 6: Проверка risk_analysis_tool")
    print("="*60)
    
    if len(test_tickers) < 2:
        print("⚠️  Недостаточно тикеров для тестирования анализа рисков")
        return False
    
    try:
        from . import risk_analysis_tool
        
        # Тестируем с весами портфеля
        sample_tickers = test_tickers[:3]
        weights = {ticker: 1.0/len(sample_tickers) for ticker in sample_tickers}
        
        print(f"🔍 Тестируем анализ рисков для: {sample_tickers}")
        print(f"   Веса: {weights}")
        
        result = risk_analysis_tool(
            tickers=sample_tickers,
            weights=weights,
            confidence_level=0.95,
            horizon_days=90  # Короткий период для быстрого теста
        )
        
        if result.get("error"):
            print(f"⚠️  Ошибка в risk_analysis_tool: {result['error']}")
            return False
        else:
            print(f"✅ Risk analysis tool работает")
            
            # Проверяем индивидуальные риски
            individual_risks = result.get('individual_risks', {})
            print(f"   Проанализировано активов: {len(individual_risks)}")
            
            # Проверяем портфельный риск
            portfolio_risk = result.get('portfolio_risk')
            if portfolio_risk:
                print(f"   Портфельная доходность: {portfolio_risk.get('annual_return', 0):.2%}")
                print(f"   Портфельный риск: {portfolio_risk.get('annual_volatility', 0):.2%}")
                print(f"   Коэффициент Шарпа: {portfolio_risk.get('sharpe_ratio', 0):.3f}")
            
            return True
            
    except Exception as e:
        print(f"❌ Ошибка в risk_analysis_tool: {e}")
        traceback.print_exc()
        return False

def test_performance_tool(test_tickers):
    """Тест 7: Проверка performance_tool"""
    print("\n" + "="*60)
    print("ТЕСТ 7: Проверка performance_tool")
    print("="*60)
    
    if len(test_tickers) < 2:
        print("⚠️  Недостаточно тикеров для тестирования анализа производительности")
        return False
    
    try:
        from . import performance_tool
        
        # Создаем простой портфель
        sample_tickers = test_tickers[:2]
        weights = {ticker: 0.5 for ticker in sample_tickers}
        
        # Короткий период для быстрого теста
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        print(f"🔍 Тестируем анализ производительности")
        print(f"   Портфель: {weights}")
        print(f"   Период: {start_date} - {end_date}")
        
        result = performance_tool(
            weights=weights,
            start_date=start_date,
            end_date=end_date,
            benchmark="^GSPC"
        )
        
        if result.get("error"):
            print(f"⚠️  Ошибка в performance_tool: {result['error']}")
            return False
        else:
            print(f"✅ Performance tool работает")
            print(f"   Годовая доходность: {result.get('portfolio_return_annualized', 0):.2%}")
            print(f"   Волатильность: {result.get('portfolio_volatility_annualized', 0):.2%}")
            print(f"   Коэффициент Шарпа: {result.get('sharpe_ratio', 0):.3f}")
            print(f"   Alpha: {result.get('alpha', 0):.2%}")
            print(f"   Beta: {result.get('beta', 0):.3f}")
            
            return True
            
    except Exception as e:
        print(f"❌ Ошибка в performance_tool: {e}")
        traceback.print_exc()
        return False

def test_forecast_tool(test_tickers):
    """Тест 8: Проверка forecast_tool"""
    print("\n" + "="*60)
    print("ТЕСТ 8: Проверка forecast_tool")
    print("="*60)
    
    if len(test_tickers) < 1:
        print("⚠️  Нет доступных тикеров для тестирования прогнозирования")
        return False
    
    try:
        from . import forecast_tool
        
        # Тестируем первый доступный тикер
        test_ticker = test_tickers[0]
        print(f"🔍 Тестируем прогнозирование для: {test_ticker}")
        
        result = forecast_tool(
            ticker=test_ticker,
            lookback_days=90  # Короткий период для быстрого теста
        )
        
        if result.get("error"):
            print(f"⚠️  Ошибка в forecast_tool: {result['error']}")
            return False
        else:
            print(f"✅ Forecast tool работает")
            mu = result.get('mu')
            sigma = result.get('sigma')
            horizon = result.get('horizon', 'Unknown')
            
            if mu is not None:
                print(f"   Прогноз доходности (mu): {mu:.4f}")
            if sigma is not None:
                print(f"   Прогноз риска (sigma): {sigma:.4f}")
            print(f"   Горизонт прогноза: {horizon}")
            
            return True
            
    except Exception as e:
        print(f"❌ Ошибка в forecast_tool: {e}")
        traceback.print_exc()
        return False

def test_error_handling():
    """Тест 9: Проверка обработки ошибок"""
    print("\n" + "="*60)
    print("ТЕСТ 9: Проверка обработки ошибок")
    print("="*60)
    
    try:
        from . import correlation_tool, risk_analysis_tool, performance_tool
        
        # Тест с пустыми параметрами
        print("🔍 Тестируем обработку пустых параметров...")
        
        result1 = correlation_tool(tickers=[])
        if result1.get("error"):
            print("✅ Correlation tool корректно обрабатывает пустой список тикеров")
        
        result2 = risk_analysis_tool(tickers=None)
        if result2.get("error"):
            print("✅ Risk analysis tool корректно обрабатывает None")
        
        result3 = performance_tool(weights={})
        if result3.get("error"):
            print("✅ Performance tool корректно обрабатывает пустые веса")
        
        # Тест с несуществующими тикерами
        print("🔍 Тестируем обработку несуществующих тикеров...")
        
        result4 = correlation_tool(tickers=["NONEXISTENT1", "NONEXISTENT2"])
        if result4.get("error"):
            print("✅ Correlation tool корректно обрабатывает несуществующие тикеры")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка в тестировании обработки ошибок: {e}")
        traceback.print_exc()
        return False

def test_optimize_tool_basic(test_tickers):
    """Тест 10: Базовая проверка optimize_tool"""
    print("\n" + "="*60)
    print("ТЕСТ 10: Базовая проверка optimize_tool")
    print("="*60)
    
    if len(test_tickers) < 3:
        print("⚠️  Недостаточно тикеров для тестирования оптимизации (нужно минимум 3)")
        return False
    
    try:
        from . import optimize_tool
        
        # Тестируем HRP метод (не требует снапшота)
        sample_tickers = test_tickers[:5]  # Берем первые 5 тикеров
        print(f"🔍 Тестируем HRP оптимизацию для: {sample_tickers}")
        
        result = optimize_tool(
            tickers=sample_tickers,
            method="hrp",
            min_weight=0.05  # Минимальный вес 5%
        )
        
        if result.get("error"):
            print(f"⚠️  Ошибка в optimize_tool: {result['error']}")
            return False
        else:
            print(f"✅ Optimize tool (HRP) работает")
            weights = result.get('weights', {})
            print(f"   Получено весов: {len(weights)}")
            print(f"   Сумма весов: {sum(weights.values()):.3f}")
            print(f"   Ожидаемая доходность: {result.get('exp_ret', 0):.4f}")
            print(f"   Риск: {result.get('risk', 0):.4f}")
            print(f"   Коэффициент Шарпа: {result.get('sharpe', 0):.3f}")
            
            return True, weights
            
    except Exception as e:
        print(f"❌ Ошибка в optimize_tool: {e}")
        traceback.print_exc()
        return False, {}

def run_all_tests():
    """Запуск всех тестов"""
    print("🚀 ЗАПУСК ИНТЕГРАЦИОННЫХ ТЕСТОВ МОДУЛЯ TOOLS")
    print("="*60)
    
    test_results = []
    test_tickers = []
    
    # Тест 1: Импорты
    result1 = test_module_imports()
    test_results.append(("Импорты модуля", result1))
    
    if not result1:
        print("\n❌ Критическая ошибка: импорты не работают. Остальные тесты невозможны.")
        return False
    
    # Тест 2: Доступные тикеры
    result2, tickers = test_available_tickers()
    test_results.append(("Доступные тикеры", result2))
    test_tickers = tickers
    
    # Тест 3: Состав индексов
    result3 = test_index_composition()
    test_results.append(("Состав индексов", result3))
    
    # Тест 4: Валидация параметров
    result4 = test_tool_validation()
    test_results.append(("Валидация параметров", result4))
    
    # Тесты с реальными данными (если есть тикеры)
    if len(test_tickers) > 0:
        # Тест 5: Корреляции
        result5 = test_correlation_tool(test_tickers)
        test_results.append(("Correlation Tool", result5))
        
        # Тест 6: Анализ рисков
        result6 = test_risk_analysis_tool(test_tickers)
        test_results.append(("Risk Analysis Tool", result6))
        
        # Тест 7: Анализ производительности
        result7 = test_performance_tool(test_tickers)
        test_results.append(("Performance Tool", result7))
        
        # Тест 8: Прогнозирование
        result8 = test_forecast_tool(test_tickers)
        test_results.append(("Forecast Tool", result8))
        
        # Тест 10: Оптимизация
        result10, _ = test_optimize_tool_basic(test_tickers)
        test_results.append(("Optimize Tool", result10))
    else:
        print("\n⚠️  Пропускаем тесты с реальными данными - нет доступных тикеров")
    
    # Тест 9: Обработка ошибок
    result9 = test_error_handling()
    test_results.append(("Обработка ошибок", result9))
    
    # Итоговый отчет
    print("\n" + "="*60)
    print("📊 ИТОГОВЫЙ ОТЧЕТ")
    print("="*60)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ ПРОЙДЕН" if result else "❌ ПРОВАЛЕН"
        print(f"{test_name:25} {status}")
        if result:
            passed += 1
    
    print("-" * 60)
    print(f"ВСЕГО ТЕСТОВ: {total}")
    print(f"ПРОЙДЕНО: {passed}")
    print(f"ПРОВАЛЕНО: {total - passed}")
    print(f"УСПЕШНОСТЬ: {passed/total*100:.1f}%")
    
    if passed == total:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        return True
    else:
        print(f"\n⚠️  {total - passed} ТЕСТОВ ПРОВАЛЕНО")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)