"""Helpers to run an LLM-based portfolio manager agent."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Dict, List

import openai

from portfolio_optimizer import (
    load_price_data,
    optimize_portfolio,
    calculate_returns,
    calculate_var_cvar,
)


@dataclass
class Tool:
    name: str
    description: str
    func: Callable[..., Dict]

    def schema(self) -> Dict:
        """Return OpenAI function schema."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {},
            },
        }


def function_tool(func: Callable[..., Dict]) -> Callable[..., Dict]:
    """Mark function as a tool."""
    func.is_tool = True
    return func


@function_tool
def forecast_tool(tickers: List[str], horizon: str) -> Dict:
    """Dummy forecast tool returning zero growth."""
    # Placeholder: replace with a real forecast model
    return {ticker: 0.0 for ticker in tickers}


@function_tool
def optimize_tool(price_csv: str, objective: str = "max_sharpe") -> Dict:
    """Optimize portfolio based on historical prices."""
    prices = load_price_data(price_csv)
    result = optimize_portfolio(prices, objective=objective)
    var, cvar = calculate_var_cvar(calculate_returns(prices), result["weights"], alpha=0.05)
    return {
        "optimal_weights": result["weights"],
        "expected_return": result["expected_return"],
        "expected_volatility": result["volatility"],
        "sharpe_ratio": result["sharpe_ratio"],
        "risk_metrics": {"var_95": var, "cvar_95": cvar},
    }


TOOLS = {
    "forecast_tool": forecast_tool,
    "optimize_tool": optimize_tool,
}


class PortfolioManagerAgent:
    """Minimal run loop for Portfolio‑Manager."""

    def __init__(self, client: openai.OpenAI | None = None) -> None:
        self.client = client or openai.OpenAI()

    def run(self, user_message: str) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "Вы — агент по оптимизации инвестиционного портфеля. "
                    "Планируйте вызовы инструментов и формируйте ответ пользователю."
                ),
            },
            {"role": "user", "content": user_message},
        ]
        tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": func.__doc__ or name,
                    "parameters": {},
                },
            }
            for name, func in TOOLS.items()
        ]
        while True:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=tools_schema,
                tool_choice="auto",
            )
            msg = response.choices[0].message
            messages.append(msg)
            if not msg.tool_calls:
                return msg.content
            for call in msg.tool_calls:
                func = TOOLS.get(call.function.name)
                if not func:
                    continue
                args = json.loads(call.function.arguments or "{}")
                result = func(**args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
