import logging
from typing import Dict, List, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Определения составов популярных индексов (топ компаний)
INDEX_COMPOSITIONS = {
    "sp500_top10": ["AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "TSLA", "GOOG", "META", "BRK.B", "UNH"],
    "sp500_top20": ["AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "TSLA", "GOOG", "META", "BRK.B", "UNH", 
                    "XOM", "JNJ", "JPM", "PG", "V", "HD", "CVX", "MA", "ABBV", "PFE"],
    "dow30": ["AAPL", "MSFT", "UNH", "GS", "HD", "CAT", "AMGN", "MCD", "V", "BA", 
              "TRV", "AXP", "JPM", "IBM", "JNJ", "PG", "CVX", "MRK", "WMT", "DIS",
              "MMM", "NKE", "KO", "DOW", "CRM", "INTC", "CSCO", "VZ", "HON", "WBA"],
    "nasdaq_top10": ["AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "TSLA", "GOOG", "META", "AVGO", "COST"],
    "tech_giants": ["AAPL", "MSFT", "AMZN", "GOOGL", "GOOG", "META", "NVDA", "TSLA", "NFLX", "ORCL", "CRM", "ADBE"],
    "financial_sector": ["JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "AXP", "SPGI", "CME"],
    "energy_sector": ["XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "VLO", "PXD", "KMI"],
    "healthcare_sector": ["UNH", "JNJ", "PFE", "ABBV", "TMO", "ABT", "LLY", "MRK", "BMY", "AMGN"],
    "consumer_staples": ["PG", "KO", "PEP", "WMT", "COST", "CL", "MO", "MDLZ", "KMB", "GIS"]
}

def get_available_tickers() -> List[str]:
    """Получает список доступных тикеров на основе наличия моделей CatBoost."""
    models_path = Path(__file__).absolute().parent.parent.parent.parent / "models"
    available_tickers = []
    
    for model_file in models_path.glob("catboost_*.cbm"):
        ticker = model_file.stem.replace("catboost_", "")
        if ticker:
            available_tickers.append(ticker)
    
    return available_tickers

def index_composition_tool(
    index_name: str,
    filter_available: bool = True
) -> Dict[str, Any]:
    """
    Возвращает состав указанного индекса с проверкой доступности тикеров.
    
    Args:
        index_name: Название индекса (sp500_top10, dow30, nasdaq_top10, tech_giants, etc.)
        filter_available: Фильтровать только доступные в наших моделях тикеры
    
    Returns:
        Словарь с составом индекса и метаинформацией
    """
    logger.info(f"Getting composition for index: {index_name}")
    
    # Нормализуем название индекса
    index_key = index_name.lower().replace(" ", "_").replace("-", "_")
    
    # Проверяем доступность индекса
    if index_key not in INDEX_COMPOSITIONS:
        available_indices = list(INDEX_COMPOSITIONS.keys())
        return {
            "error": f"Индекс '{index_name}' не найден. Доступные индексы: {', '.join(available_indices)}",
            "tickers": [],
            "available_tickers": [],
            "unavailable_tickers": []
        }
    
    # Получаем состав индекса
    full_composition = INDEX_COMPOSITIONS[index_key]
    
    if not filter_available:
        return {
            "index_name": index_name,
            "tickers": full_composition,
            "total_count": len(full_composition),
            "available_tickers": full_composition,
            "unavailable_tickers": [],
            "error": None
        }
    
    # Фильтруем по доступным тикерам
    available_tickers = get_available_tickers()
    
    available_from_index = [ticker for ticker in full_composition if ticker in available_tickers]
    unavailable_from_index = [ticker for ticker in full_composition if ticker not in available_tickers]
    
    logger.info(f"Index {index_name}: {len(available_from_index)}/{len(full_composition)} tickers available")
    
    if not available_from_index:
        return {
            "error": f"Ни один тикер из индекса '{index_name}' не доступен в наших моделях",
            "index_name": index_name,
            "tickers": [],
            "available_tickers": [],
            "unavailable_tickers": unavailable_from_index,
            "total_count": len(full_composition)
        }
    
    return {
        "index_name": index_name,
        "tickers": available_from_index,
        "total_count": len(full_composition),
        "available_count": len(available_from_index),
        "available_tickers": available_from_index,
        "unavailable_tickers": unavailable_from_index,
        "coverage_ratio": len(available_from_index) / len(full_composition),
        "error": None
    }

def list_available_indices() -> Dict[str, Any]:
    """
    Возвращает список всех доступных индексов с описанием.
    
    Returns:
        Словарь с информацией о доступных индексах
    """
    indices_info = {
        "sp500_top10": "Топ-10 компаний S&P 500 по капитализации",
        "sp500_top20": "Топ-20 компаний S&P 500 по капитализации", 
        "dow30": "Все 30 компаний индекса Dow Jones",
        "nasdaq_top10": "Топ-10 компаний NASDAQ по капитализации",
        "tech_giants": "Крупнейшие технологические компании",
        "financial_sector": "Ведущие финансовые компании",
        "energy_sector": "Ведущие энергетические компании",
        "healthcare_sector": "Ведущие компании здравоохранения",
        "consumer_staples": "Товары повседневного спроса"
    }
    
    # Получаем доступность для каждого индекса
    available_tickers = get_available_tickers()
    results = {}
    
    for index_key, description in indices_info.items():
        composition = INDEX_COMPOSITIONS[index_key]
        available_count = len([t for t in composition if t in available_tickers])
        
        results[index_key] = {
            "description": description,
            "total_tickers": len(composition),
            "available_tickers": available_count,
            "coverage": available_count / len(composition)
        }
    
    return {
        "available_indices": results,
        "total_available_models": len(available_tickers)
    }

if __name__ == "__main__":
    # Тестирование
    logging.basicConfig(level=logging.INFO)
    
    # Тест получения индекса
    result = index_composition_tool("sp500_top10")
    print(f"SP500 Top 10: {result}")
    
    # Тест списка индексов  
    indices = list_available_indices()
    print(f"Available indices: {indices}") 