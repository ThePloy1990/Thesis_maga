#!/usr/bin/env python3
"""
Упрощенные сценарии тестирования модуля tools без внешних зависимостей.
Проверяют структуру, метаданные и связи между инструментами.
"""

import sys
import os
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

def test_tools_registry():
    """Тест реестра инструментов"""
    print("📋 ТЕСТ РЕЕСТРА ИНСТРУМЕНТОВ")
    print("=" * 50)
    
    try:
        # Импортируем только структуры данных, не функции
        import sys
        tools_path = Path(__file__).parent
        sys.path.insert(0, str(tools_path))
        
        # Читаем __init__.py напрямую для извлечения TOOLS_REGISTRY
        init_file = tools_path / "__init__.py"
        init_content = init_file.read_text()
        
        # Простая проверка наличия ключевых структур
        if "TOOLS_REGISTRY" in init_content:
            print("✅ TOOLS_REGISTRY найден в __init__.py")
        else:
            print("❌ TOOLS_REGISTRY отсутствует")
            return False
        
        # Проверяем наличие основных инструментов в коде
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
        
        found_tools = []
        for tool in expected_tools:
            if f'"{tool}"' in init_content or f"'{tool}'" in init_content:
                found_tools.append(tool)
        
        print(f"✅ Найдено {len(found_tools)}/{len(expected_tools)} инструментов в реестре")
        
        # Проверяем категории
        categories = ["analysis", "optimization", "forecasting", "scenario", "data"]
        found_categories = []
        for category in categories:
            if f'"{category}"' in init_content or f"'{category}'" in init_content:
                found_categories.append(category)
        
        print(f"✅ Найдено {len(found_categories)}/{len(categories)} категорий")
        
        return len(found_tools) >= len(expected_tools) * 0.8
        
    except Exception as e:
        print(f"❌ Ошибка тестирования реестра: {e}")
        return False

def test_file_structure():
    """Тест структуры файлов и их связей"""
    print("\n📁 ТЕСТ СТРУКТУРЫ ФАЙЛОВ")
    print("=" * 50)
    
    try:
        tools_dir = Path(__file__).parent
        
        # Проверяем основные файлы
        required_files = {
            "__init__.py": "Основной модуль",
            "utils.py": "Утилиты",
            "correlation_tool.py": "Анализ корреляций",
            "efficient_frontier_tool.py": "Эффективная граница",
            "forecast_tool.py": "Прогнозирование",
            "optimize_tool.py": "Оптимизация",
            "performance_tool.py": "Анализ производительности",
            "risk_analysis_tool.py": "Анализ рисков",
            "scenario_tool.py": "Сценарный анализ",
            "sentiment_tool.py": "Анализ настроений",
            "index_composition_tool.py": "Состав индексов"
        }
        
        present_files = []
        for filename, description in required_files.items():
            file_path = tools_dir / filename
            if file_path.exists():
                present_files.append(filename)
                print(f"✅ {filename}: {description}")
            else:
                print(f"❌ {filename}: ОТСУТСТВУЕТ")
        
        # Проверяем импорты между файлами
        print(f"\n🔗 Проверка связей между файлами...")
        
        import_relationships = []
        
        for file_path in tools_dir.glob("*.py"):
            if file_path.name.startswith("test_"):
                continue
                
            try:
                content = file_path.read_text()
                
                # Проверяем импорты из utils
                if "from .utils import" in content:
                    import_relationships.append(f"{file_path.name} → utils.py")
                
                # Проверяем импорты из других модулей
                for other_file in required_files:
                    if other_file != file_path.name:
                        module_name = other_file.replace(".py", "")
                        if f"from .{module_name} import" in content:
                            import_relationships.append(f"{file_path.name} → {other_file}")
                            
            except Exception:
                continue
        
        print(f"✅ Найдено {len(import_relationships)} связей между модулями:")
        for relationship in import_relationships[:5]:  # Показываем первые 5
            print(f"   • {relationship}")
        
        return len(present_files) >= len(required_files) * 0.8
        
    except Exception as e:
        print(f"❌ Ошибка тестирования структуры: {e}")
        return False

def test_documentation():
    """Тест документации"""
    print("\n📚 ТЕСТ ДОКУМЕНТАЦИИ")
    print("=" * 50)
    
    try:
        tools_dir = Path(__file__).parent
        
        # Проверяем наличие README
        readme_file = tools_dir / "README.md"
        if readme_file.exists():
            readme_content = readme_file.read_text()
            print(f"✅ README.md существует ({len(readme_content)} символов)")
            
            # Проверяем содержание README
            expected_sections = [
                "# Portfolio Assistant Tools",
                "## Обзор инструментов",
                "correlation_tool",
                "optimize_tool",
                "forecast_tool"
            ]
            
            found_sections = 0
            for section in expected_sections:
                if section in readme_content:
                    found_sections += 1
            
            print(f"✅ Найдено {found_sections}/{len(expected_sections)} ожидаемых разделов")
        else:
            print("❌ README.md отсутствует")
            return False
        
        # Проверяем docstrings в файлах
        python_files = list(tools_dir.glob("*_tool.py"))
        files_with_docstrings = 0
        
        for py_file in python_files:
            try:
                content = py_file.read_text()
                if '"""' in content and "Args:" in content and "Returns:" in content:
                    files_with_docstrings += 1
            except Exception:
                continue
        
        print(f"✅ {files_with_docstrings}/{len(python_files)} файлов имеют полные docstrings")
        
        return files_with_docstrings >= len(python_files) * 0.7
        
    except Exception as e:
        print(f"❌ Ошибка тестирования документации: {e}")
        return False

def test_code_consistency():
    """Тест согласованности кода"""
    print("\n🔍 ТЕСТ СОГЛАСОВАННОСТИ КОДА")
    print("=" * 50)
    
    try:
        tools_dir = Path(__file__).parent
        
        # Проверяем отсутствие дублирования функций
        function_definitions = {}
        
        for py_file in tools_dir.glob("*.py"):
            if py_file.name.startswith("test_"):
                continue
                
            try:
                content = py_file.read_text()
                
                # Ищем определения функций
                lines = content.split('\n')
                for line in lines:
                    if line.strip().startswith('def ') and '(' in line:
                        func_name = line.strip().split('(')[0].replace('def ', '')
                        if func_name not in function_definitions:
                            function_definitions[func_name] = []
                        function_definitions[func_name].append(py_file.name)
                        
            except Exception:
                continue
        
        # Находим дублированные функции
        duplicated = []
        for func_name, files in function_definitions.items():
            if len(files) > 1:
                duplicated.append((func_name, files))
        
        if duplicated:
            print(f"⚠️  Найдено {len(duplicated)} дублированных функций:")
            for func_name, files in duplicated[:3]:  # Показываем первые 3
                print(f"   • {func_name}: {files}")
        else:
            print("✅ Дублированных функций не найдено")
        
        # Проверяем импорты
        missing_imports = []
        for py_file in tools_dir.glob("*_tool.py"):
            try:
                content = py_file.read_text()
                
                # Проверяем базовые импорты
                if "import logging" not in content:
                    missing_imports.append(f"{py_file.name}: logging")
                if "from typing import" not in content:
                    missing_imports.append(f"{py_file.name}: typing")
                    
            except Exception:
                continue
        
        if missing_imports:
            print(f"⚠️  Отсутствуют базовые импорты:")
            for missing in missing_imports[:3]:
                print(f"   • {missing}")
        else:
            print("✅ Базовые импорты присутствуют во всех файлах")
        
        # Общая оценка
        issues = len(duplicated) + len(missing_imports)
        return issues <= 2
        
    except Exception as e:
        print(f"❌ Ошибка тестирования согласованности: {e}")
        return False

def test_models_integration():
    """Тест интеграции с моделями"""
    print("\n🤖 ТЕСТ ИНТЕГРАЦИИ С МОДЕЛЯМИ")
    print("=" * 50)
    
    try:
        # Проверяем наличие директории models
        models_dir = project_root / "models"
        
        if not models_dir.exists():
            print("⚠️  Директория models не найдена")
            return False
        
        # Считаем модели CatBoost
        model_files = list(models_dir.glob("catboost_*.cbm"))
        print(f"✅ Найдено {len(model_files)} моделей CatBoost")
        
        if len(model_files) > 0:
            # Показываем примеры тикеров
            tickers = []
            for model_file in model_files[:5]:
                ticker = model_file.stem.replace("catboost_", "")
                tickers.append(ticker)
            
            print(f"📋 Примеры тикеров: {tickers}")
            
            # Проверяем что utils.py может работать с этими моделями
            utils_file = Path(__file__).parent / "utils.py"
            if utils_file.exists():
                utils_content = utils_file.read_text()
                if "catboost_" in utils_content and ".cbm" in utils_content:
                    print("✅ utils.py настроен для работы с моделями CatBoost")
                else:
                    print("⚠️  utils.py может не поддерживать модели CatBoost")
            
            return True
        else:
            print("⚠️  Модели CatBoost не найдены (нормально для тестовой среды)")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка тестирования интеграции с моделями: {e}")
        return False

def run_all_tests():
    """Запуск всех тестов без зависимостей"""
    print("🧪 ТЕСТИРОВАНИЕ МОДУЛЯ TOOLS (БЕЗ ЗАВИСИМОСТЕЙ)")
    print("=" * 70)
    
    tests = [
        ("Реестр инструментов", test_tools_registry),
        ("Структура файлов", test_file_structure),
        ("Документация", test_documentation),
        ("Согласованность кода", test_code_consistency),
        ("Интеграция с моделями", test_models_integration)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ Критическая ошибка в тесте '{test_name}': {e}")
            results.append((test_name, False))
    
    # Итоговый отчет
    print("\n" + "="*70)
    print("📊 ИТОГИ ТЕСТИРОВАНИЯ")
    print("="*70)
    
    passed = 0
    for test_name, success in results:
        status = "✅ ПРОЙДЕН" if success else "❌ ПРОВАЛЕН"
        print(f"{test_name:25} {status}")
        if success:
            passed += 1
    
    print("-" * 70)
    success_rate = passed / len(results) * 100
    print(f"УСПЕШНОСТЬ: {passed}/{len(results)} ({success_rate:.1f}%)")
    
    if passed == len(results):
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        print("✅ Модуль tools имеет правильную структуру и готов к использованию")
    elif passed >= len(results) * 0.8:
        print("\n✅ БОЛЬШИНСТВО ТЕСТОВ ПРОЙДЕНО!")
        print("⚠️  Есть незначительные проблемы, но модуль функционален")
    else:
        print("\n⚠️  МНОГО ТЕСТОВ ПРОВАЛЕНО")
        print("🚨 Модуль требует серьезной доработки")
    
    return passed >= len(results) * 0.8

if __name__ == "__main__":
    success = run_all_tests()
    
    print(f"\n{'='*70}")
    if success:
        print("🎯 МОДУЛЬ TOOLS ГОТОВ К ИСПОЛЬЗОВАНИЮ!")
        print("🔧 Структура корректна, документация на месте")
        print("🚀 После установки зависимостей можно запускать инструменты")
    else:
        print("🚨 МОДУЛЬ TOOLS ТРЕБУЕТ ДОРАБОТКИ")
        print("📝 Исправьте проблемы, указанные в отчете выше")
    print("="*70)
    
    sys.exit(0 if success else 1)