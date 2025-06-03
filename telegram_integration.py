"""
Интеграция Streamlit с Telegram для отправки отчетов по портфелю
"""

import json
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import os
from dotenv import load_dotenv

import telegram
from telegram.constants import ParseMode
import plotly.graph_objects as go
import plotly.io as pio
import pandas as pd

# Загрузка переменных окружения
load_dotenv()

logger = logging.getLogger(__name__)

# Telegram конфигурация
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DISCLAIMER = (
    "⚠️ *Данный контент носит информационный характер и "
    "не является индивидуальной инвестиционной рекомендацией. "
    "Инвестиции сопряжены с риском.*"
)

def format_portfolio_report(
    optimization_results: Dict,
    snapshot_data: Dict,
    performance_results: Optional[Dict] = None
) -> str:
    """
    Форматирует отчет по портфелю для отправки в Telegram
    """
    
    # Заголовок отчета
    report = "📈 *ОТЧЕТ ПО ОПТИМИЗИРОВАННОМУ ПОРТФЕЛЮ*\n\n"
    
    # Дата и метод
    report += f"📅 *Дата:* {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
    report += f"⚡ *Метод оптимизации:* {optimization_results.get('method', 'Не указан')}\n\n"
    
    # Основные метрики
    report += "💰 *ОСНОВНЫЕ МЕТРИКИ:*\n"
    report += f"• Ожидаемая доходность: *{optimization_results.get('exp_ret', 0) * 100:.2f}%* (год)\n"
    report += f"• Волатильность: *{optimization_results.get('risk', 0) * 100:.2f}%* (год)\n"
    report += f"• Коэффициент Шарпа: *{optimization_results.get('sharpe', 0):.3f}*\n"
    
    weights = optimization_results.get('weights', {})
    if weights:
        report += f"• Количество позиций: *{len([w for w in weights.values() if w > 0.001])}*\n\n"
        
        # Топ позиции
        report += "🏆 *ТОП-10 ПОЗИЦИЙ:*\n"
        sorted_weights = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:10]
        
        for i, (ticker, weight) in enumerate(sorted_weights, 1):
            if weight > 0.001:  # Показываем только значимые позиции
                report += f"{i}. *{ticker}*: {weight * 100:.2f}%\n"
    
    # Историческая производительность (если есть)
    if performance_results and not performance_results.get('error'):
        report += "\n📊 *ИСТОРИЧЕСКАЯ ПРОИЗВОДИТЕЛЬНОСТЬ:*\n"
        report += f"• Реальная доходность: *{performance_results.get('portfolio_return_annualized', 0) * 100:.2f}%*\n"
        report += f"• Максимальная просадка: *{performance_results.get('max_drawdown', 0) * 100:.2f}%*\n"
        report += f"• Alpha: *{performance_results.get('alpha', 0) * 100:.2f}%*\n"
        report += f"• Beta: *{performance_results.get('beta', 0):.3f}*\n"
    
    # Информация о снапшоте
    meta = snapshot_data.get('meta', {})
    if meta:
        report += "\n🗃️ *ДАННЫЕ СНАПШОТА:*\n"
        report += f"• Количество активов: *{len(snapshot_data.get('mu', {}))}*\n"
        report += f"• Горизонт прогноза: *{meta.get('horizon_days', 'N/A')} дней*\n"
        if meta.get('timestamp'):
            report += f"• Дата снапшота: *{meta.get('timestamp')[:10]}*\n"
    
    # Дисклеймер
    report += f"\n{DISCLAIMER}"
    
    return report


def create_portfolio_chart(weights: Dict[str, float]) -> bytes:
    """
    Создает круговую диаграмму портфеля и возвращает как байты изображения
    """
    # Фильтруем активы с весом > 1%
    significant_weights = {k: v for k, v in weights.items() if v > 0.01}
    other_weight = sum(v for v in weights.values() if v <= 0.01)
    
    if other_weight > 0:
        significant_weights['Прочие'] = other_weight
    
    # Создаем pie chart
    fig = go.Figure(data=[go.Pie(
        labels=list(significant_weights.keys()),
        values=list(significant_weights.values()),
        hole=0.4,
        textinfo='label+percent',
        textposition='auto',
        textfont=dict(size=14),
        marker=dict(
            colors=['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', 
                   '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9'],
            line=dict(color='white', width=2)
        )
    )])
    
    fig.update_layout(
        title=dict(
            text="Структура оптимизированного портфеля",
            x=0.5,
            font=dict(size=18, color='darkblue')
        ),
        font=dict(size=12),
        showlegend=True,
        width=800,
        height=600,
        margin=dict(t=80, b=50, l=50, r=50)
    )
    
    # Конвертируем в изображение
    img_bytes = pio.to_image(fig, format='png', engine='kaleido')
    return img_bytes


async def send_portfolio_to_telegram(
    chat_id: str,
    optimization_results: Dict,
    snapshot_data: Dict,
    performance_results: Optional[Dict] = None,
    include_chart: bool = True
) -> bool:
    """
    Отправляет отчет по портфелю в Telegram
    
    Args:
        chat_id: ID чата/пользователя в Telegram
        optimization_results: Результаты оптимизации портфеля
        snapshot_data: Данные снапшота
        performance_results: Результаты анализа производительности (опционально)
        include_chart: Включить ли диаграмму портфеля
        
    Returns:
        True если отправка успешна, False иначе
    """
    
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN не найден в переменных окружения")
        return False
    
    try:
        # Создаем бота
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
        
        # Форматируем отчет
        report_text = format_portfolio_report(
            optimization_results, 
            snapshot_data, 
            performance_results
        )
        
        # Отправляем текстовый отчет
        await bot.send_message(
            chat_id=chat_id,
            text=report_text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
        # Отправляем диаграмму (если requested)
        if include_chart and optimization_results.get('weights'):
            try:
                chart_bytes = create_portfolio_chart(optimization_results['weights'])
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=chart_bytes,
                    caption="📊 Визуализация структуры портфеля"
                )
            except Exception as e:
                logger.error(f"Ошибка отправки диаграммы: {e}")
                await bot.send_message(
                    chat_id=chat_id,
                    text="⚠️ Не удалось отправить диаграмму портфеля"
                )
        
        # Отправляем JSON файл с детальными данными
        portfolio_data = {
            'timestamp': datetime.now().isoformat(),
            'optimization_results': optimization_results,
            'snapshot_meta': snapshot_data.get('meta', {}),
            'performance_results': performance_results,
            'weights': optimization_results.get('weights', {}),
            'summary': {
                'expected_return': optimization_results.get('exp_ret', 0),
                'risk': optimization_results.get('risk', 0),
                'sharpe_ratio': optimization_results.get('sharpe', 0),
                'num_positions': len([w for w in optimization_results.get('weights', {}).values() if w > 0.001])
            }
        }
        
        json_data = json.dumps(portfolio_data, indent=2, ensure_ascii=False).encode('utf-8')
        
        await bot.send_document(
            chat_id=chat_id,
            document=json_data,
            filename=f"portfolio_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            caption="📄 Детальные данные портфеля в JSON формате"
        )
        
        logger.info(f"Отчет по портфелю успешно отправлен в Telegram чат {chat_id}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка отправки в Telegram: {e}")
        return False


def validate_telegram_chat_id(chat_id: str) -> bool:
    """
    Проверяет валидность ID чата Telegram
    """
    if not chat_id:
        return False
        
    # ID чата может быть числом или начинаться с @
    if chat_id.startswith('@'):
        return len(chat_id) > 1
    
    try:
        int(chat_id)
        return True
    except ValueError:
        return False


async def test_telegram_connection(chat_id: str) -> bool:
    """
    Тестирует соединение с Telegram и отправляет тестовое сообщение
    """
    if not TELEGRAM_TOKEN:
        return False
        
    try:
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
        await bot.send_message(
            chat_id=chat_id,
            text="🧪 Тест подключения к Portfolio Assistant успешен! ✅",
            parse_mode=ParseMode.MARKDOWN
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка тестирования Telegram: {e}")
        return False


# Функция-обертка для синхронного вызова из Streamlit
def send_portfolio_report_sync(
    chat_id: str,
    optimization_results: Dict,
    snapshot_data: Dict,
    performance_results: Optional[Dict] = None
) -> bool:
    """
    Синхронная обертка для отправки отчета в Telegram
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            send_portfolio_to_telegram(
                chat_id, 
                optimization_results, 
                snapshot_data, 
                performance_results
            )
        )
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Ошибка синхронной отправки: {e}")
        return False


def test_telegram_sync(chat_id: str) -> bool:
    """
    Синхронная обертка для тестирования Telegram
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(test_telegram_connection(chat_id))
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Ошибка тестирования: {e}")
        return False 