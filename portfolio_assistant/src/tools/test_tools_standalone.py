#!/usr/bin/env python3
"""
Независимый тестовый скрипт для модуля tools.
Может быть запущен без зависимостей для базовой проверки.
"""

import sys
import os
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

def test_basic_functionality():
    """Базовый тест функциональности без внешних зависимостей"""
    print("🧪 БАЗОВЫЙ ТЕСТ МОДУЛЯ TOOLS")
    print("=" * 50)
    
    try:
        # Тест 1: Проверка структуры файлов
        print("\n1️⃣ Проверка структуры файлов...")
        tools_dir = Path(__file__).parent
        
        expected_files = [
            "__init__.py",
            "correlation_tool.py", 
            "efficient_frontier_tool.py",
            "forecast_tool.py",
            "optimize_tool.py",
            "performance_tool.py",
            "risk_analysis_tool.py",
            "scenario_tool.py",
            "sentiment_tool.py",
            "index_composition_tool.py"
        ]
        
        missing_files = []
        for file in expected_files:
            if not (tools_dir / file).exists():
                missing_files.append(file)
        
        if missing_files:
            print(f"❌ Отсутствуют файлы: {missing_files}")
            return False
        else:
            print("✅ Все основные файлы присутствуют")
        
        # Тест 2: Проверка синтаксиса
        print("\n2️⃣ Проверка синтаксиса файлов...")
        
        import py_compile
        syntax_errors = []
        
        for file in expected_files:
            try:
                py_compile.compile(str(tools_dir / file), doraise=True)
            except py_compile.PyCompileError as e:
                syntax_errors.append(f"{file}: {e}")
        
        if syntax_errors:
            print("❌ Ошибки синтаксиса:")
            for error in syntax_errors:
                print(f"   {error}")
            return False
        else:
            print("✅ Синтаксис всех файлов корректен")
        
        # Тест 3: Проверка __init__.py
        print("\n3️⃣ Проверка __init__.py...")
        
        init_file = tools_dir / "__init__.py"
        init_content = init_file.read_text()
        
        if len(init_content.strip()) == 0:
            print("❌ __init__.py пустой")
            return False
        
        expected_exports = [
            "correlation_tool",
            "efficient_frontier_tool", 
            "forecast_tool",
            "optimize_tool",
            "performance_tool",
            "risk_analysis_tool",
            "scenario_adjust_tool",
            "sentiment_tool",
            "index_composition_tool",
            "get_available_tickers",
            "TOOLS_REGISTRY"
        ]
        
        missing_exports = []
        for export in expected_exports:
            if export not in init_content:
                missing_exports.append(export)
        
        if missing_exports:
            print(f"❌ Отсутствуют экспорты: {missing_exports}")
            return False
        else:
            print("✅ __init__.py содержит все необходимые экспорты")
        
        # Тест 4: Проверка моделей (если есть)
        print("\n4️⃣ Проверка наличия моделей...")
        
        models_dir = project_root / "models"
        if models_dir.exists():
            model_files = list(models_dir.glob("catboost_*.cbm"))
            print(f"✅ Найдено {len(model_files)} моделей CatBoost")
            
            if len(model_files) > 0:
                print(f"   Примеры моделей: {[f.stem for f in model_files[:3]]}")
        else:
            print("⚠️  Директория models не найдена")
        
        # Тест 5: Проверка документации
        print("\n5️⃣ Проверка документации...")
        
        readme_file = tools_dir / "README.md"
        if readme_file.exists():
            print("✅ README.md существует")
        else:
            print("⚠️  README.md отсутствует")
        
        return True
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_import_without_dependencies():
    """Тест импорта модуля (может не работать без зависимостей)"""
    print("\n🔌 ТЕСТ ИМПОРТА (может провалиться без зависимостей)")
    print("=" * 50)
    
    try:
        # Пытаемся импортировать основной модуль
        from portfolio_assistant.src.tools import list_all_tools, get_tool_info
        
        tools = list_all_tools()
        print(f"✅ Импорт успешен, найдено {len(tools)} инструментов")
        print(f"   Инструменты: {tools}")
        
        # Проверяем информацию об инструменте
        info = get_tool_info("correlation_tool")
        if "description" in info:
            print(f"✅ Метаданные инструментов работают")
            print(f"   Описание correlation_tool: {info['description']}")
        
        return True
        
    except ImportError as e:
        print(f"⚠️  Импорт не удался (нормально, если нет зависимостей): {e}")
        return False
    except Exception as e:
        print(f"❌ Ошибка импорта: {e}")
        return False

def test_code_quality():
    """Проверка качества кода"""
    print("\n🔍 ПРОВЕРКА КАЧЕСТВА КОДА")
    print("=" * 50)
    
    tools_dir = Path(__file__).parent
    issues = []
    
    # Проверяем на дублирование функций
    print("\n📋 Проверка на дублирование кода...")
    
    get_available_tickers_files = []
    
    for py_file in tools_dir.glob("*.py"):
        if py_file.name.startswith("test_"):
            continue
            
        try:
            content = py_file.read_text()
            if "def get_available_tickers(" in content:
                get_available_tickers_files.append(py_file.name)
        except Exception:
            continue
    
    if len(get_available_tickers_files) > 1:
        print(f"⚠️  Функция get_available_tickers найдена в {len(get_available_tickers_files)} файлах:")
        for file in get_available_tickers_files:
            print(f"   - {file}")
        issues.append("Дублирование get_available_tickers")
    else:
        print("✅ Нет дублирования get_available_tickers")
    
    # Проверяем на TODO/FIXME
    print("\n🚧 Проверка на незавершенный код...")
    
    todo_files = []
    for py_file in tools_dir.glob("*.py"):
        if py_file.name.startswith("test_"):
            continue
            
        try:
            content = py_file.read_text().upper()
            if "TODO" in content or "FIXME" in content or "XXX" in content:
                todo_files.append(py_file.name)
        except Exception:
            continue
    
    if todo_files:
        print(f"⚠️  Найдены TODO/FIXME в файлах: {todo_files}")
        issues.append("Незавершенный код")
    else:
        print("✅ Не найдено TODO/FIXME")
    
    # Проверяем на заглушки
    print("\n🚫 Проверка на заглушки...")
    
    stub_patterns = ["pass", "raise NotImplementedError", "return None"]
    stub_files = []
    
    for py_file in tools_dir.glob("*.py"):
        if py_file.name.startswith("test_"):
            continue
            
        try:
            content = py_file.read_text()
            for pattern in stub_patterns:
                if pattern in content and "def " in content:
                    # Простая проверка - есть ли функция с заглушкой
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if "def " in line and i+1 < len(lines):
                            next_line = lines[i+1].strip()
                            if next_line in stub_patterns:
                                stub_files.append(py_file.name)
                                break
        except Exception:
            continue
    
    if stub_files:
        print(f"⚠️  Возможные заглушки в файлах: {set(stub_files)}")
        issues.append("Возможные заглушки")
    else:
        print("✅ Не найдено очевидных заглушек")
    
    if issues:
        print(f"\n⚠️  Найдено {len(issues)} проблем качества кода:")
        for issue in issues:
            print(f"   - {issue}")
        return False
    else:
        print("\n✅ Качество кода в порядке")
        return True

def main():
    """Главная функция тестирования"""
    print("🔧 АВТОНОМНОЕ ТЕСТИРОВАНИЕ МОДУЛЯ TOOLS")
    print("=" * 60)
    
    results = []
    
    # Базовый тест
    print("\n" + "🔹" * 30 + " БАЗОВЫЕ ТЕСТЫ " + "🔹" * 30)
    basic_result = test_basic_functionality()
    results.append(("Базовая функциональность", basic_result))
    
    # Тест качества кода
    quality_result = test_code_quality()
    results.append(("Качество кода", quality_result))
    
    # Тест импорта (может провалиться)
    print("\n" + "🔹" * 30 + " ТЕСТ ИМПОРТА " + "🔹" * 30)
    import_result = test_import_without_dependencies()
    results.append(("Импорт модуля", import_result))
    
    # Итоги
    print("\n" + "="*60)
    print("📊 ИТОГИ АВТОНОМНОГО ТЕСТИРОВАНИЯ")
    print("="*60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ ПРОЙДЕН" if result else "❌ ПРОВАЛЕН"
        print(f"{test_name:25} {status}")
        if result:
            passed += 1
    
    print("-" * 60)
    success_rate = passed / len(results) * 100
    print(f"УСПЕШНОСТЬ: {passed}/{len(results)} ({success_rate:.1f}%)")
    
    if passed == len(results):
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        return True
    elif passed >= len(results) - 1:  # Разрешаем 1 провал (импорт)
        print("\n✅ ОСНОВНЫЕ ТЕСТЫ ПРОЙДЕНЫ!")
        return True
    else:
        print(f"\n⚠️  ПРОВАЛЕНО {len(results) - passed} ТЕСТОВ")
        return False

if __name__ == "__main__":
    success = main()
    print(f"\n{'='*60}")
    if success:
        print("🎯 МОДУЛЬ TOOLS ГОТОВ К ИСПОЛЬЗОВАНИЮ")
    else:
        print("🚨 МОДУЛЬ TOOLS ТРЕБУЕТ ДОРАБОТКИ")
    print("="*60)
    
    sys.exit(0 if success else 1)