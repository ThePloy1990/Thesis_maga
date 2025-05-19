"""
Пакет с основной функциональностью:
- Прогнозирование и анализ
- Оптимизация портфеля
- ИИ-агенты
- Визуализация
"""

from .portfolio_optimizer import (
    load_price_data,
    calculate_returns,
    optimize_portfolio,
    calculate_var_cvar,
    backtest_strategy,
    compute_correlation_matrix
)

from .forecast import (
    predict_with_catboost,
    get_available_models,
    batch_predict
)

from .llm_agents import (
    forecast_tool,
    optimize_tool,
    PortfolioManagerAgent
)

from .visualization import (
    create_performance_chart,
    create_allocation_pie,
    create_reports_csv,
    create_reports_excel,
    create_pdf_report,
    get_dashboard_link
)

from .model_manager import (
    ModelRegistry,
    ModelTrainer,
    predict_with_model_registry
)

__all__ = [
    # Portfolio optimization
    'load_price_data',
    'calculate_returns',
    'optimize_portfolio',
    'calculate_var_cvar',
    'backtest_strategy',
    'compute_correlation_matrix',
    
    # Forecasting
    'predict_with_catboost',
    'get_available_models',
    'batch_predict',
    
    # LLM agents
    'forecast_tool',
    'optimize_tool',
    'PortfolioManagerAgent',
    
    # Visualization
    'create_performance_chart',
    'create_allocation_pie',
    'create_reports_csv',
    'create_reports_excel',
    'create_pdf_report',
    'get_dashboard_link',
    
    # Model management
    'ModelRegistry',
    'ModelTrainer',
    'predict_with_model_registry'
] 