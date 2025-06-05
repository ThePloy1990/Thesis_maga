# Portfolio Assistant Tools

Этот модуль содержит все инструменты для анализа портфелей и финансовых активов.

## Обзор инструментов

### 🔍 Аналитические инструменты

#### `correlation_tool`
Анализ корреляций между активами с визуализацией.

```python
from portfolio_assistant.src.tools import correlation_tool

result = correlation_tool(
    tickers=["AAPL", "MSFT", "GOOGL"],
    period_days=252,           # Период анализа (дней)
    correlation_type="pearson", # pearson, spearman, kendall
    rolling_window=30          # Окно для скользящей корреляции
)
```

**Возвращает:**
- Корреляционную матрицу
- Статистику корреляций
- Парные корреляции с интерпретацией
- Графики (сохраняются во временные файлы)

#### `risk_analysis_tool`
Углубленный анализ рисков портфеля и активов.

```python
from portfolio_assistant.src.tools import risk_analysis_tool

result = risk_analysis_tool(
    tickers=["AAPL", "MSFT", "TSLA"],
    weights={"AAPL": 0.4, "MSFT": 0.4, "TSLA": 0.2},
    confidence_level=0.95,      # Уровень доверия для VaR
    horizon_days=252            # Горизонт анализа
)
```

**Возвращает:**
- VaR и Expected Shortfall для каждого актива
- Максимальные просадки
- Статистика распределений (асимметрия, эксцесс)
- Портфельные метрики риска

#### `performance_tool`
Анализ реальной производительности портфеля.

```python
from portfolio_assistant.src.tools import performance_tool

result = performance_tool(
    weights={"AAPL": 0.5, "MSFT": 0.5},
    start_date="2023-01-01",
    end_date="2023-12-31",
    benchmark="^GSPC"           # S&P 500
)
```

**Возвращает:**
- Годовую доходность и волатильность
- Коэффициент Шарпа
- Alpha и Beta (CAPM)
- Максимальную просадку

#### `sentiment_tool`
Анализ настроений рынка по новостям.

```python
from portfolio_assistant.src.tools import sentiment_tool

result = sentiment_tool(
    ticker="AAPL",
    window_days=3               # Период анализа новостей
)
```

**Возвращает:**
- Оценку настроений (-1 до +1)
- Количество проанализированных статей
- Кэширование результатов

### 📈 Инструменты оптимизации

#### `optimize_tool`
Оптимизация портфеля различными методами.

```python
from portfolio_assistant.src.tools import optimize_tool

result = optimize_tool(
    tickers=["AAPL", "MSFT", "GOOGL", "TSLA"],
    method="hrp",               # hrp, markowitz, black_litterman, target_return
    max_weight=0.4,             # Максимальный вес актива
    risk_free_rate=0.001,
    target_return=0.15          # Для метода target_return
)
```

**Методы оптимизации:**
- **HRP (Hierarchical Risk Parity)** - современный метод, использует реальные исторические данные
- **Markowitz** - классическая теория портфеля
- **Black-Litterman** - улучшенный Markowitz с байесовским подходом
- **Target Return** - оптимизация под целевую доходность

#### `efficient_frontier_tool`
Построение эффективной границы портфеля.

```python
from portfolio_assistant.src.tools import efficient_frontier_tool

result = efficient_frontier_tool(
    tickers=["AAPL", "MSFT", "GOOGL"],
    num_portfolios=100,         # Количество точек на границе
    sector_filter="tech_giants" # Фильтр по сектору
)
```

**Возвращает:**
- Данные эффективной границы
- Оптимальные портфели (min volatility, max Sharpe)
- График эффективной границы

### 🔮 Прогнозирование

#### `forecast_tool`
Прогнозирование доходности и риска активов на 3 месяца.

```python
from portfolio_assistant.src.tools import forecast_tool

result = forecast_tool(
    ticker="AAPL",
    snapshot_id=None,           # Использовать снапшот или реальные данные
    lookback_days=180           # Период для расчета признаков
)
```

**Возвращает:**
- Ожидаемую 3-месячную доходность (mu)
- Дисперсию доходности (sigma)
- Горизонт прогноза

### 📊 Сценарный анализ

#### `scenario_tool`
Создание сценариев "что если" для портфеля.

```python
from portfolio_assistant.src.tools import scenario_adjust_tool

result = scenario_adjust_tool(
    tickers=["AAPL", "MSFT"],
    adjustments={"AAPL": -5.0, "MSFT": 3.0},  # Изменения в %
    base_snapshot_id=None       # Базовый снапшот
)
```

**Возвращает:**
- ID нового сценарного снапшота
- Примененные корректировки

### 📋 Данные и композиция

#### `index_composition_tool`
Получение состава популярных индексов.

```python
from portfolio_assistant.src.tools import index_composition_tool

result = index_composition_tool(
    index_name="sp500_top10",
    filter_available=True       # Только доступные тикеры
)
```

**Доступные индексы:**
- `sp500_top10/top20` - топ компании S&P 500
- `dow30` - индекс Dow Jones
- `nasdaq_top10` - топ NASDAQ
- `tech_giants` - технологические гиганты
- `financial_sector` - финансовый сектор
- `energy_sector` - энергетический сектор
- `healthcare_sector` - здравоохранение
- `consumer_staples` - товары первой необходимости

## Утилиты модуля

### Центральные функции

```python
from portfolio_assistant.src.tools import (
    get_available_tickers,      # Список доступных тикеров
    get_tool_info,              # Информация об инструментах
    list_all_tools,             # Список всех инструментов
    validate_tool_params,       # Валидация параметров
    TOOLS_REGISTRY              # Реестр всех инструментов
)

# Получить список всех доступных тикеров
tickers = get_available_tickers()

# Информация о конкретном инструменте
info = get_tool_info("correlation_tool")

# Валидация параметров
validation = validate_tool_params("correlation_tool", {"tickers": ["AAPL"]})
```

## Общие принципы работы

### Проверка доступности тикеров
Все инструменты автоматически проверяют доступность тикеров на основе наличия моделей CatBoost в директории `models/`.

### Обработка ошибок
Все инструменты возвращают стандартизированные ответы:
```python
{
    "error": "Описание ошибки",
    "available_tickers": ["AAPL", "MSFT", ...],  # При ошибках с тикерами
    # ... другие поля зависят от инструмента
}
```

### Снапшоты рынка
Многие инструменты могут работать с готовыми снапшотами рынка (`snapshot_id`) или загружать данные в реальном времени.

### Логирование
Все инструменты используют стандартное Python логирование. Установите уровень `logging.INFO` для подробной информации.

## Примеры использования

### Полный анализ портфеля

```python
from portfolio_assistant.src.tools import *

# 1. Получаем доступные тикеры
tickers = get_available_tickers()[:5]  # Берем первые 5

# 2. Анализ корреляций
correlations = correlation_tool(tickers=tickers)

# 3. Оптимизация портфеля
portfolio = optimize_tool(tickers=tickers, method="hrp")

if not portfolio.get("error"):
    weights = portfolio["weights"]
    
    # 4. Анализ рисков
    risks = risk_analysis_tool(tickers=list(weights.keys()), weights=weights)
    
    # 5. Анализ производительности
    performance = performance_tool(weights=weights)
    
    print(f"Портфель: {weights}")
    print(f"Ожидаемая доходность: {portfolio['exp_ret']:.2%}")
    print(f"Риск: {portfolio['risk']:.2%}")
    print(f"Коэффициент Шарпа: {portfolio['sharpe']:.3f}")
```

### Работа с индексами

```python
# Получить состав технологических гигантов
tech_composition = index_composition_tool("tech_giants")

if not tech_composition.get("error"):
    tech_tickers = tech_composition["tickers"]
    
    # Оптимизировать портфель из технологических компаний
    tech_portfolio = optimize_tool(tickers=tech_tickers, method="markowitz")
```

## Требования

- Python 3.8+
- pandas, numpy, matplotlib, seaborn
- yfinance для загрузки данных
- pypfopt для оптимизации портфеля
- catboost для прогнозирования
- transformers, torch для анализа настроений
- newsapi-python для новостей
- redis для кэширования

## Расширение модуля

Для добавления нового инструмента:

1. Создайте файл `new_tool.py` в директории `tools/`
2. Реализуйте основную функцию
3. Добавьте информацию в `TOOLS_REGISTRY` в `__init__.py`
4. Добавьте импорт в `__all__` список
5. Создайте тесты в `test_tools.py`

Модуль автоматически подхватит новый инструмент при следующем импорте.