# src/pf_agents/runtime.py
from agents import function_tool as _ft
from agents import Agent, Runner, guardrail
# from agents import UserMessage # Удаляем UserMessage, так как он не найден

# лёгкая прокладка – можно дописать логирование
def function_tool(func=None, *, tool_name: str | None = None, tool_description: str | None = None):
    if func:
        # Вызов как @function_tool
        # В этом случае _ft не ожидает tool_name или tool_description как keyword аргументы
        return _ft(func)
    else:
        # Вызов как @function_tool(tool_name=..., tool_description=...)
        # _ft должен вернуть декоратор, который примет func
        # Передаем только явно заданные аргументы
        kwargs = {}
        if tool_name is not None:
            kwargs['tool_name'] = tool_name
        if tool_description is not None:
            kwargs['tool_description'] = tool_description
        return _ft(**kwargs)

# Добавим также UserMessage, так как он упоминался в вашей шпаргалке
# и может понадобиться для Runner.run
# Если он в другом месте SDK, импорт нужно будет скорректировать
# Если он в другом месте SDK, импорт нужно будет скорректировать
# Если он в другом месте SDK, импорт нужно будет скорректировать 