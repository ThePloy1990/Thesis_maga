from agents import function_tool as _ft
from agents import Agent as _Agent
from agents import Runner as _Runner
from agents import guardrail as _guardrail # Убедимся, что импорт корректный (строчная 'g')

from typing import Optional, Callable, Any

# Re-export Agent, Runner, guardrail
Agent = _Agent
Runner = _Runner
guardrail = _guardrail


def function_tool(
    func: Optional[Callable[..., Any]] = None,
    *,
    tool_name: Optional[str] = None,
    strict_json_schema: bool = True, # Параметр из SDK, по умолчанию True
    # Другие параметры SDK, такие как 'description', могут быть добавлены сюда при необходимости
):
    """
    Враппер вокруг function_tool из SDK для обеспечения кастомизации
    и соответствия ожидаемому пути импорта `pf_agents.function_tool`.

    Передает `tool_name` как `name` в SDK, если указан.
    Передает `strict_json_schema` в SDK.
    """
    
    # Подготовка аргументов для нижележащего function_tool (_ft) из SDK
    sdk_kwargs = {}
    if tool_name:
        sdk_kwargs['name'] = tool_name
    
    # Всегда передаем strict_json_schema; если не указано вызывающей стороной, используется значение по умолчанию.
    sdk_kwargs['strict_json_schema'] = strict_json_schema

    if func is None:
        # Вызов с круглыми скобками, например, @function_tool(tool_name="my_tool", strict_json_schema=False)
        # Сам _ft обрабатывает этот паттерн (func=None возвращает декоратор).
        # Таким образом, мы вызываем _ft с func=None и нашими kwargs.
        # _ft вернет свой собственный декоратор, который примет функцию.
        return _ft(**sdk_kwargs) # func неявно None при таком вызове _ft
    else:
        # Вызов без круглых скобок, например, @function_tool
        # func - это декорируемая функция.
        return _ft(func, **sdk_kwargs) 