#!/usr/bin/env python3
"""
Тест импорта portfolio_optimizer
"""
import sys
import os
from pathlib import Path

# Путь к корню проекта
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Проверяем наличие файла
portfolio_path = os.path.join(project_root, "src", "core", "portfolio_optimizer.py")
print(f"Путь к файлу: {portfolio_path}")
print(f"Файл существует: {os.path.exists(portfolio_path)}")

# Загружаем модуль напрямую, без import
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("portfolio_optimizer", portfolio_path)
    portfolio = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(portfolio)
    
    print("\nМодуль загружен успешно")
    print(f"optimize_portfolio is callable: {callable(portfolio.optimize_portfolio)}")
except Exception as e:
    print(f"\nОшибка при загрузке модуля: {e}")

# Выводим содержимое директории src/core
print("\nСодержимое директории src/core:")
for item in os.listdir(os.path.join(project_root, "src", "core")):
    print(f"- {item}") 