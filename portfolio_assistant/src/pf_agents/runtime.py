from agents import function_tool as _ft
from agents import Agent as _Agent
from agents import Runner as _Runner
from agents import guardrail as _guardrail # Убедимся, что импорт корректный (строчная 'g')

from typing import Callable, Any # Optional убран

# Re-export Agent, Runner, guardrail
Agent = _Agent
Runner = _Runner
guardrail = _guardrail


def function_tool(
    func: Callable[..., Any] # func теперь обязательный, не Optional
    # Убраны *, tool_name и sdk_kwargs
):
    """
    Простой враппер вокруг function_tool из SDK.
    Имя инструмента будет извлечено из func.__name__.
    Убедитесь, что func имеет правильный __name__ (и __doc__, __annotations__)
    перед вызовом этого враппера.
    """
    # Просто вызываем _ft с функцией. SDK сам разберется с деталями.
    return _ft(func)
