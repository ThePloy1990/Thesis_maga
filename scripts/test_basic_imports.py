#!/usr/bin/env python3
"""
Самый простой тест импорта
"""

import sys
from pathlib import Path

# Добавляем корневую директорию проекта в sys.path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Прямой импорт
try:
    print("Пытаемся импортировать portfolio_optimizer напрямую...")
    from src.core.portfolio_optimizer import optimize_portfolio
    print("✅ Успешно импортирован optimize_portfolio")
    print(f"Имеется ли функция: {callable(optimize_portfolio)}")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    
# Проверка на наличие файла
import os
portfolio_path = os.path.join(project_root, "src", "core", "portfolio_optimizer.py")
print(f"\nПроверка наличия файла: {portfolio_path}")
print(f"Файл существует: {os.path.exists(portfolio_path)}")

# Печать sys.path
print("\nТекущие пути в sys.path:")
for path in sys.path:
    print(f"- {path}") 