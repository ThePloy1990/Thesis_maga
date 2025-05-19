import os
import logging
import json
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import openai
import sqlite3
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.portfolio_optimizer import (
    load_price_data,
    calculate_returns,
    optimize_portfolio,
    calculate_var_cvar,
    backtest_strategy,
)
from core.llm_agents import forecast_tool
from core.visualization import (
    create_performance_chart,
    create_allocation_pie,
    create_reports_csv,
    create_reports_excel,
    create_pdf_report,
    get_dashboard_link
)

# Загрузка переменных из .env файла
load_dotenv()

# Загрузка ключей из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Попытка загрузить результаты оптимизации портфеля (если сформирован JSON)
PORTFOLIO_RESULTS_FILE = "portfolio_results.json"
try:
    with open(PORTFOLIO_RESULTS_FILE, "r", encoding="utf-8") as f:
        portfolio_results = json.load(f)
except Exception:
    portfolio_results = None

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Настройка БД пользователей
conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute(
    '''CREATE TABLE IF NOT EXISTS users (
         telegram_id TEXT PRIMARY KEY,
         name TEXT,
         email TEXT,
         risk_tolerance TEXT,
         horizon TEXT,
         goal TEXT
     )'''
)
conn.commit()

async def process_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get('registration_step')
    text = update.message.text
    # Шаг 0: имя
    if step == 0:
        context.user_data['profile']['name'] = text
        context.user_data['registration_step'] = 1
        await update.message.reply_text("Укажите ваш email (или отправьте '-' чтобы пропустить):")
    # Шаг 1: email
    elif step == 1:
        email = text if text != '-' else None
        context.user_data['profile']['email'] = email
        context.user_data['registration_step'] = 2
        await update.message.reply_text("Какой у вас риск-толерантность? (низкая/средняя/высокая):")
    # Шаг 2: риск
    elif step == 2:
        context.user_data['profile']['risk_tolerance'] = text
        context.user_data['registration_step'] = 3
        await update.message.reply_text("На какой срок вы инвестируете? (например: 1 год, 5 лет):")
    # Шаг 3: горизонт
    elif step == 3:
        context.user_data['profile']['horizon'] = text
        context.user_data['registration_step'] = 4
        await update.message.reply_text("Какая ваша цель инвестирования? (рост капитала/доп. доход/сбережение):")
    # Шаг 4: цель и завершение
    elif step == 4:
        context.user_data['profile']['goal'] = text
        # Сохраняем профиль в БД
        user_id = str(update.message.from_user.id)
        prof = context.user_data['profile']
        cursor.execute(
            'INSERT INTO users VALUES (?,?,?,?,?,?)',
            (user_id, prof['name'], prof['email'], prof['risk_tolerance'], prof['horizon'], prof['goal'])
        )
        conn.commit()
        await update.message.reply_text("Регистрация завершена! Спасибо.")
        # Сбрасываем состояние
        context.user_data.pop('registration_step', None)
        context.user_data.pop('profile', None)
    return

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает команду /start и приветствует пользователя"""
    await update.message.reply_text(
        "Привет! Я — бот для оптимизации портфеля. Для начала регистрации используйте команду /register."
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает команду /register и запускает опрос пользователя"""
    user_id = str(update.message.from_user.id)
    cursor.execute("SELECT * FROM users WHERE telegram_id=?", (user_id,))
    if cursor.fetchone():
        await update.message.reply_text("Вы уже зарегистрированы.")
        return
    context.user_data['registration_step'] = 0
    context.user_data['profile'] = {}
    await update.message.reply_text("Давайте создадим ваш профиль.\nКак вас зовут?")

async def forecast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возвращает прогноз по указанному тикеру"""
    if not context.args:
        await update.message.reply_text("Использование: /forecast <тикер> [горизонт]")
        return
    ticker = context.args[0]
    horizon = context.args[1] if len(context.args) > 1 else "1y"
    try:
        result = forecast_tool([ticker], horizon)
        prediction = result.get(ticker)
        await update.message.reply_text(f"Прогноз для {ticker} ({horizon}): {prediction}")
    except Exception as e:
        logger.error("Ошибка в forecast_tool: %s", e)
        await update.message.reply_text("Не удалось получить прогноз.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает входящие текстовые сообщения и перенаправляет их в LLM"""
    # Если идет регистрация, обрабатываем шаги опроса
    if context.user_data.get('registration_step') is not None:
        return await process_registration(update, context)
    user_text = update.message.text
    messages = [
        {"role": "system", "content": (
            "Вы — ассистент по оптимизации инвестиционного портфеля. "
            "Отвечайте строго в рамках этой тематики. "
            "Если вопрос выходит за рамки оптимизации портфеля, вежливо укажите, что можете помочь только с этой темой."
        )}
    ]
    # Добавляем в контекст текущие результаты оптимизации, если они есть
    if portfolio_results:
        messages.append({
            "role": "system",
            "content": (
                f"Текущие результаты оптимизации портфеля: "
                f"{json.dumps(portfolio_results, ensure_ascii=False)}"
            )
        })
    messages.append({"role": "user", "content": user_text})

    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.2,
            max_tokens=500,
        )
        answer = response.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка при запросе к OpenAI: {e}")
        answer = "Произошла ошибка при обращении к LLM."    

    await update.message.reply_text(answer)

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отображает главное меню через inline-клавиатуру"""
    keyboard = [
        [InlineKeyboardButton("📊 Мой портфель", callback_data="menu_portfolio")],
        [InlineKeyboardButton("⚙️ Оптимизация", callback_data="menu_optimize")],
        [InlineKeyboardButton("📝 Отчёты", callback_data="menu_reports")],
        [InlineKeyboardButton("🔔 Уведомления", callback_data="menu_notifications")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="menu_settings")],
        [InlineKeyboardButton("❓ Помощь", callback_data="menu_help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Главное меню:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка callback-запросов из inline-клавиатуры"""
    global portfolio_results
    query = update.callback_query
    await query.answer()
    data = query.data
    # Обработка пунктов меню
    if data == "menu_portfolio":
        if portfolio_results:
            text = (
                f"🏦 Ожидаемая доходность: {portfolio_results['expected_return']*100:.2f}%\n"
                f"📉 Волатильность: {portfolio_results['expected_volatility']*100:.2f}%\n"
                f"📈 Sharpe Ratio: {portfolio_results['sharpe_ratio']:.2f}\n"
                "📦 Оптимальные веса:\n" +
                "\n".join([f"{k}: {v*100:.1f}%" for k,v in portfolio_results['optimal_weights'].items()])
            )
        else:
            text = "Нет данных по портфелю. Сначала выполните оптимизацию."
        await query.edit_message_text(text)
    elif data == "menu_optimize":
        keyboard = [
            [InlineKeyboardButton("Max Sharpe", callback_data="opt_sharpe")],
            [InlineKeyboardButton("Max Return", callback_data="opt_return")],
            [InlineKeyboardButton("Min Volatility", callback_data="opt_volatility")],
            [InlineKeyboardButton("🔙 Назад", callback_data="menu_back")]
        ]
        await query.edit_message_text("Выберите цель оптимизации:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data in ["opt_sharpe","opt_return","opt_volatility"]:
        proc_map = {
            'opt_sharpe': ('максимального Sharpe', 'max_sharpe'),
            'opt_return': ('максимального дохода', 'target_return'),
            'opt_volatility': ('минимальной волатильности', 'min_volatility')
        }
        description, objective = proc_map[data]
        await query.edit_message_text(f"🔄 Выполняю оптимизацию для {description}. Пожалуйста, подождите...")
        try:
            import glob
            csv_files = glob.glob('data/sp500_ml_ready*.csv')
            if not csv_files:
                raise FileNotFoundError('CSV с ценами не найден.')
            latest_csv = max(csv_files, key=os.path.getctime)
            prices = load_price_data(latest_csv)
            if objective == 'target_return':
                target = 0.1  # пример таргета доходности 10%
                result = optimize_portfolio(prices, objective=objective, target_return=target)
            else:
                result = optimize_portfolio(prices, objective=objective)
            var, cvar = calculate_var_cvar(calculate_returns(prices), result['weights'], alpha=0.05)
            new_results = {
                'optimal_weights': result['weights'],
                'expected_return': result['expected_return'],
                'expected_volatility': result['volatility'],
                'sharpe_ratio': result['sharpe_ratio'],
                'risk_metrics': {'var_95': var, 'cvar_95': cvar}
            }
            with open(PORTFOLIO_RESULTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(new_results, f, ensure_ascii=False, indent=2)
            portfolio_results = new_results
            lines = [
                f"🏦 Ожидаемая доходность: {result['expected_return']*100:.2f}%",
                f"📉 Волатильность: {result['volatility']*100:.2f}%",
                f"📈 Sharpe Ratio: {result['sharpe_ratio']:.2f}",
                f"VaR (95%): {var:.4f}",
                f"CVaR (95%): {cvar:.4f}",
                "📦 Оптимальные веса:"
            ]
            for ticker, w in result['weights'].items():
                lines.append(f"{ticker}: {w*100:.1f}%")
            text = "\n".join(lines)
        except Exception as e:
            text = f"❌ Ошибка при оптимизации: {e}"
        await query.edit_message_text(text)
    elif data == "menu_reports":
        link = get_dashboard_link()
        await query.edit_message_text(
            f"📄 Отчёт доступен по ссылке:\n{link}"
        )
    elif data == "menu_notifications":
        await query.edit_message_text("🔔 Управление уведомлениями... (заглушка)")
    elif data == "menu_settings":
        await query.edit_message_text("⚙️ Настройки пользователя... (заглушка)")
    elif data == "menu_help":
        help_text = (
            "/start - начать бота\n"
            "/register - регистрация\n"
            "/menu - главное меню\n"
            "/forecast <тикер> [горизонт] - прогноз цены\n"
            "В меню доступны опции управления портфелем."
        )
        await query.edit_message_text(help_text)
    elif data == "menu_back":
        # Возврат к главному меню
        keyboard = [
            [InlineKeyboardButton("📊 Мой портфель", callback_data="menu_portfolio")],
            [InlineKeyboardButton("⚙️ Оптимизация", callback_data="menu_optimize")],
            [InlineKeyboardButton("📝 Отчёты", callback_data="menu_reports")],
            [InlineKeyboardButton("🔔 Уведомления", callback_data="menu_notifications")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="menu_settings")],
            [InlineKeyboardButton("❓ Помощь", callback_data="menu_help")]
        ]
        await query.edit_message_text("Главное меню:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await query.edit_message_text("Неизвестная команда.")

def main():
    """Запускает Telegram-бота"""
    if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
        logger.error("Не заданы переменные окружения TELEGRAM_BOT_TOKEN или OPENAI_API_KEY.")
        return

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("forecast", forecast))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Бот запущен...")
    app.run_polling()


def setup_bot():
    """
    Функция для инициализации и настройки бота, которая может быть импортирована другими модулями.
    Возвращает настроенный экземпляр бота, готовый к запуску.
    """
    if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
        logger.error("Не заданы переменные окружения TELEGRAM_BOT_TOKEN или OPENAI_API_KEY.")
        return None

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("forecast", forecast))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Бот настроен и готов к запуску")
    return app


if __name__ == "__main__":
    main() 