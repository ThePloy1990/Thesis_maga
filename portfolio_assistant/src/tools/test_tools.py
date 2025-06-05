"""
Тесты для модуля tools.

Содержит тесты для проверки функциональности всех инструментов.
"""

import logging
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Импортируем все инструменты
from . import (
    get_available_tickers,
    get_tool_info,
    list_all_tools,
    validate_tool_params,
    TOOLS_REGISTRY
)

logger = logging.getLogger(__name__)


class TestToolsModule(unittest.TestCase):
    """Тесты для основного модуля tools."""
    
    def test_tools_registry_completeness(self):
        """Проверяет что в реестре есть все ожидаемые инструменты."""
        expected_tools = [
            "correlation_tool",
            "efficient_frontier_tool",
            "forecast_tool",
            "optimize_tool",
            "performance_tool",
            "risk_analysis_tool",
            "scenario_tool",
            "sentiment_tool",
            "index_composition_tool"
        ]
        
        for tool in expected_tools:
            self.assertIn(tool, TOOLS_REGISTRY, f"Tool '{tool}' missing from registry")
    
    def test_list_all_tools(self):
        """Проверяет функцию получения списка всех инструментов."""
        tools = list_all_tools()
        self.assertIsInstance(tools, list)
        self.assertGreater(len(tools), 0)
        self.assertIn("correlation_tool", tools)
    
    def test_get_tool_info(self):
        """Проверяет функцию получения информации об инструменте."""
        # Тест получения информации о конкретном инструменте
        info = get_tool_info("correlation_tool")
        self.assertIsInstance(info, dict)
        self.assertIn("function", info)
        self.assertIn("description", info)
        self.assertIn("category", info)
        
        # Тест получения информации о несуществующем инструменте
        info = get_tool_info("nonexistent_tool")
        self.assertIn("error", info)
        
        # Тест получения информации о всех инструментах
        all_info = get_tool_info()
        self.assertIsInstance(all_info, dict)
        self.assertIn("correlation_tool", all_info)
    
    def test_validate_tool_params(self):
        """Проверяет валидацию параметров инструмента."""
        # Тест с корректными параметрами
        result = validate_tool_params("correlation_tool", {"tickers": ["AAPL", "MSFT"]})
        self.assertTrue(result["valid"])
        
        # Тест с отсутствующими обязательными параметрами
        result = validate_tool_params("correlation_tool", {})
        self.assertFalse(result["valid"])
        self.assertIn("error", result)
        
        # Тест с несуществующим инструментом
        result = validate_tool_params("nonexistent_tool", {})
        self.assertFalse(result["valid"])

    @patch('portfolio_assistant.src.tools.utils.Path.glob')
    def test_get_available_tickers(self, mock_glob):
        """Проверяет функцию получения доступных тикеров."""
        # Мокаем файлы моделей
        mock_file1 = MagicMock()
        mock_file1.stem = "catboost_AAPL"
        mock_file2 = MagicMock()
        mock_file2.stem = "catboost_MSFT"
        mock_file3 = MagicMock()
        mock_file3.stem = "catboost_TEST"  # Должен быть исключен
        
        mock_glob.return_value = [mock_file1, mock_file2, mock_file3]
        
        tickers = get_available_tickers()
        self.assertIsInstance(tickers, list)
        self.assertIn("AAPL", tickers)
        self.assertIn("MSFT", tickers)
        self.assertNotIn("TEST", tickers)  # Тестовые модели исключаются


class TestToolsIntegration(unittest.TestCase):
    """Интеграционные тесты для инструментов."""
    
    def setUp(self):
        """Настройка для тестов."""
        logging.basicConfig(level=logging.WARNING)  # Снижаем уровень логирования для тестов
    
    def test_tools_can_be_imported(self):
        """Проверяет что все инструменты можно импортировать."""
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
        
        # Проверяем что все функции вызываемы
        self.assertTrue(callable(correlation_tool))
        self.assertTrue(callable(efficient_frontier_tool))
        self.assertTrue(callable(forecast_tool))
        self.assertTrue(callable(optimize_tool))
        self.assertTrue(callable(performance_tool))
        self.assertTrue(callable(risk_analysis_tool))
        self.assertTrue(callable(scenario_adjust_tool))
        self.assertTrue(callable(sentiment_tool))
        self.assertTrue(callable(index_composition_tool))


class TestErrorHandling(unittest.TestCase):
    """Тесты обработки ошибок в инструментах."""
    
    def test_tools_handle_empty_input(self):
        """Проверяет обработку пустых входных данных."""
        from .correlation_tool import correlation_tool
        from .risk_analysis_tool import risk_analysis_tool
        
        # Тест correlation_tool с пустым списком
        result = correlation_tool(tickers=[])
        self.assertIn("error", result)
        
        # Тест risk_analysis_tool с None
        result = risk_analysis_tool(tickers=None)
        self.assertIn("error", result)
    
    def test_tools_handle_invalid_tickers(self):
        """Проверяет обработку недействительных тикеров."""
        from .correlation_tool import correlation_tool
        
        # Используем заведомо несуществующие тикеры
        result = correlation_tool(tickers=["NONEXISTENT1", "NONEXISTENT2"])
        self.assertIn("error", result)


def run_tests():
    """Запускает все тесты модуля tools."""
    logging.basicConfig(level=logging.INFO)
    
    # Создаем test suite
    suite = unittest.TestSuite()
    
    # Добавляем тесты
    suite.addTest(unittest.makeSuite(TestToolsModule))
    suite.addTest(unittest.makeSuite(TestToolsIntegration))
    suite.addTest(unittest.makeSuite(TestErrorHandling))
    
    # Запускаем тесты
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    run_tests()