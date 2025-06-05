"""
Portfolio Assistant Tools Module

Этот модуль содержит все инструменты для анализа портфеля:
- correlation_tool: Анализ корреляций между активами
- efficient_frontier_tool: Построение эффективной границы
- forecast_tool: Прогнозирование доходности и риска
- optimize_tool: Оптимизация портфеля различными методами
- performance_tool: Анализ производительности портфеля
- risk_analysis_tool: Углубленный анализ рисков
- scenario_tool: Создание сценариев "что если"
- sentiment_tool: Анализ настроений по новостям
- index_composition_tool: Работа с составом индексов
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Callable

logger = logging.getLogger(__name__)

# Импортируем все основные функции
from .correlation_tool import correlation_tool
from .efficient_frontier_tool import efficient_frontier_tool
from .forecast_tool import forecast_tool
from .optimize_tool import optimize_tool
from .performance_tool import performance_tool, calculate_quarterly_metrics
from .risk_analysis_tool import risk_analysis_tool
from .scenario_tool import scenario_adjust_tool
from .sentiment_tool import sentiment_tool
from .index_composition_tool import index_composition_tool, list_available_indices, INDEX_COMPOSITIONS

# Импортируем утилиты
from .utils import get_available_tickers

# Реестр всех доступных инструментов
TOOLS_REGISTRY: Dict[str, Dict[str, Any]] = {
    "correlation_tool": {
        "function": correlation_tool,
        "description": "Анализ корреляций между активами",
        "category": "analysis",
        "required_params": ["tickers"],
        "optional_params": ["period_days", "correlation_type", "rolling_window", "snapshot_id"]
    },
    "efficient_frontier_tool": {
        "function": efficient_frontier_tool,
        "description": "Построение эффективной границы портфеля",
        "category": "optimization",
        "required_params": ["tickers"],
        "optional_params": ["snapshot_id", "num_portfolios", "risk_free_rate", "max_weight", "min_weight", "target_returns", "sector_filter"]
    },
    "forecast_tool": {
        "function": forecast_tool,
        "description": "Прогнозирование доходности и риска актива",
        "category": "forecasting",
        "required_params": ["ticker"],
        "optional_params": ["snapshot_id", "lookback_days"]
    },
    "optimize_tool": {
        "function": optimize_tool,
        "description": "Оптимизация портфеля различными методами",
        "category": "optimization",
        "required_params": [],
        "optional_params": ["tickers", "snapshot_id", "risk_aversion", "method", "max_weight", "risk_free_rate", "min_weight", "target_return"]
    },
    "performance_tool": {
        "function": performance_tool,
        "description": "Анализ реальной производительности портфеля",
        "category": "analysis",
        "required_params": ["weights"],
        "optional_params": ["start_date", "end_date", "risk_free_rate", "benchmark"]
    },
    "risk_analysis_tool": {
        "function": risk_analysis_tool,
        "description": "Углубленный анализ рисков портфеля и активов",
        "category": "analysis",
        "required_params": ["tickers"],
        "optional_params": ["weights", "confidence_level", "horizon_days"]
    },
    "scenario_tool": {
        "function": scenario_adjust_tool,
        "description": "Создание сценариев 'что если' для портфеля",
        "category": "scenario",
        "required_params": ["tickers", "adjustments"],
        "optional_params": ["base_snapshot_id"]
    },
    "sentiment_tool": {
        "function": sentiment_tool,
        "description": "Анализ настроений рынка по новостям",
        "category": "analysis",
        "required_params": ["ticker"],
        "optional_params": ["window_days"]
    },
    "index_composition_tool": {
        "function": index_composition_tool,
        "description": "Получение состава популярных индексов",
        "category": "data",
        "required_params": ["index_name"],
        "optional_params": ["filter_available"]
    }
}

def get_tool_info(tool_name: str = None) -> Dict[str, Any]:
    """
    Возвращает информацию об инструменте или всех инструментах.
    
    Args:
        tool_name: Название инструмента (опционально)
    
    Returns:
        Информация об инструменте/инструментах
    """
    if tool_name:
        if tool_name in TOOLS_REGISTRY:
            return TOOLS_REGISTRY[tool_name]
        else:
            return {"error": f"Tool '{tool_name}' not found", "available_tools": list(TOOLS_REGISTRY.keys())}
    
    return TOOLS_REGISTRY

def get_tools_by_category(category: str) -> Dict[str, Dict[str, Any]]:
    """
    Возвращает инструменты определенной категории.
    
    Args:
        category: Категория инструментов (analysis, optimization, forecasting, scenario, data)
    
    Returns:
        Словарь инструментов указанной категории
    """
    return {name: info for name, info in TOOLS_REGISTRY.items() if info["category"] == category}

def list_all_tools() -> List[str]:
    """Возвращает список всех доступных инструментов."""
    return list(TOOLS_REGISTRY.keys())

def validate_tool_params(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Проверяет параметры для указанного инструмента.
    
    Args:
        tool_name: Название инструмента
        params: Параметры для проверки
    
    Returns:
        Результат валидации
    """
    if tool_name not in TOOLS_REGISTRY:
        return {"valid": False, "error": f"Unknown tool: {tool_name}"}
    
    tool_info = TOOLS_REGISTRY[tool_name]
    required_params = tool_info.get("required_params", [])
    missing_params = [p for p in required_params if p not in params]
    
    if missing_params:
        return {
            "valid": False, 
            "error": f"Missing required parameters: {missing_params}",
            "required": required_params,
            "optional": tool_info.get("optional_params", [])
        }
    
    return {"valid": True, "error": None}

# Экспортируем все основные функции и утилиты
__all__ = [
    # Основные инструменты
    "correlation_tool",
    "efficient_frontier_tool", 
    "forecast_tool",
    "optimize_tool",
    "performance_tool",
    "calculate_quarterly_metrics",
    "risk_analysis_tool",
    "scenario_adjust_tool",
    "sentiment_tool",
    "index_composition_tool",
    "list_available_indices",
    
    # Утилиты
    "get_available_tickers",
    "get_tool_info",
    "get_tools_by_category",
    "list_all_tools",
    "validate_tool_params",
    
    # Константы
    "TOOLS_REGISTRY",
    "INDEX_COMPOSITIONS"
] 