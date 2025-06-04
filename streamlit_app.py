import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import json
import os
from datetime import datetime, timedelta
import yfinance as yf

# Настройка страницы
st.set_page_config(
    page_title="🚀 Portfolio Assistant",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Импорт наших модулей
import sys
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('./portfolio_assistant'))
sys.path.insert(0, os.path.abspath('./portfolio_assistant/src'))

# Импортируем функции напрямую
try:
    from portfolio_assistant.src.tools.optimize_tool import optimize_tool
    from portfolio_assistant.src.tools.performance_tool import performance_tool
    from portfolio_assistant.src.tools.forecast_tool import forecast_tool
    from portfolio_assistant.src.market_snapshot.registry import SnapshotRegistry
except ImportError as e:
    # Альтернативный способ импорта если первый не сработал
    try:
        sys.path.append('./portfolio_assistant/src')
        from tools.optimize_tool import optimize_tool
        from tools.performance_tool import performance_tool
        from tools.forecast_tool import forecast_tool
        from market_snapshot.registry import SnapshotRegistry
    except ImportError as e2:
        st.error(f"Ошибка импорта модулей: {e2}")
        st.stop()

# Импорт Telegram интеграции
try:
    from telegram_integration import (
        send_portfolio_report_sync,
        test_telegram_sync,
        validate_telegram_chat_id
    )
    TELEGRAM_AVAILABLE = True
except ImportError as e:
    st.warning("⚠️ Telegram интеграция недоступна. Установите python-telegram-bot для отправки отчетов.")
    TELEGRAM_AVAILABLE = False

# Импорт системы состояния пользователя
try:
    from portfolio_assistant.src.bot.state import (
        get_user_state,
        get_all_user_ids,
        update_positions,
        redis_client
    )
    USER_STATE_AVAILABLE = True
except ImportError as e:
    st.warning("⚠️ Система состояния пользователя недоступна.")
    USER_STATE_AVAILABLE = False

# Кастомные стили
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        text-align: center;
        background: linear-gradient(90deg, #1e3c72, #2a5298);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 2rem;
    }
    
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        margin: 0.5rem 0;
    }
    
    .positive {
        color: #00C851;
        font-weight: bold;
    }
    
    .negative {
        color: #ff4444;
        font-weight: bold;
    }
    
    .neutral {
        color: #ffbb33;
        font-weight: bold;
    }
    
    .stSelectbox > div > div {
        background-color: #f0f2f6;
    }
</style>
""", unsafe_allow_html=True)

# Заголовок
st.markdown('<h1 class="main-header">🚀 Portfolio Assistant</h1>', unsafe_allow_html=True)
st.markdown("---")

# Sidebar для настроек
st.sidebar.header("⚙️ Настройки портфеля")

# Выбор пользователя (если доступна система состояния)
selected_user_id = None
user_state = None

if USER_STATE_AVAILABLE:
    st.sidebar.subheader("👤 Выбор пользователя")
    
    def get_user_list():
        """Получает список пользователей из Redis"""
        try:
            user_ids = get_all_user_ids()
            if user_ids:
                return sorted(user_ids)
            return []
        except Exception as e:
            st.sidebar.error(f"Ошибка получения пользователей: {e}")
            return []
    
    user_ids = get_user_list()
    
    if user_ids:
        # Выбор из существующих пользователей
        user_option = st.sidebar.radio(
            "Источник данных:",
            ["Существующий пользователь", "Ввести User ID", "Новый портфель"]
        )
        
        if user_option == "Существующий пользователь":
            selected_user_id = st.sidebar.selectbox(
                "Выберите пользователя:",
                options=user_ids,
                help="Выберите пользователя из списка"
            )
        elif user_option == "Ввести User ID":
            selected_user_id = st.sidebar.number_input(
                "Введите User ID:",
                min_value=1,
                value=1,
                help="Введите ID пользователя вручную"
            )
        else:  # Новый портфель
            selected_user_id = None
    else:
        # Если нет пользователей, предлагаем ввести ID
        user_option = st.sidebar.radio(
            "Источник данных:",
            ["Ввести User ID", "Новый портфель"]
        )
        
        if user_option == "Ввести User ID":
            selected_user_id = st.sidebar.number_input(
                "Введите User ID:",
                min_value=1,
                value=1,
                help="Введите ID пользователя вручную"
            )
        else:
            selected_user_id = None
    
    # Загружаем состояние пользователя если выбран
    if selected_user_id:
        try:
            user_state = get_user_state(selected_user_id)
            st.sidebar.success(f"✅ Загружены данные пользователя {selected_user_id}")
            
            # Показываем информацию о пользователе
            with st.sidebar.expander("📊 Информация о пользователе"):
                st.write(f"**Risk Profile:** {user_state.get('risk_profile', 'не указан')}")
                st.write(f"**Budget:** ${user_state.get('budget', 0):,.2f}")
                positions = user_state.get('positions', {})
                st.write(f"**Позиций в портфеле:** {len(positions)}")
                if positions:
                    st.write("**Текущие позиции:**")
                    for ticker, amount in list(positions.items())[:5]:  # Показываем первые 5
                        st.write(f"• {ticker}: {amount:.2f}")
                    if len(positions) > 5:
                        st.write(f"... и еще {len(positions)-5}")
        except Exception as e:
            st.sidebar.error(f"Ошибка загрузки пользователя: {e}")
            user_state = None
else:
    st.sidebar.info("💡 Система состояния пользователя недоступна. Используется режим нового портфеля.")

# Загрузка доступных снапшотов
def get_available_snapshots():
    snapshots_dir = "./local/snapshots"
    if os.path.exists(snapshots_dir):
        files = [f for f in os.listdir(snapshots_dir) if f.endswith('.json')]
        return sorted(files, reverse=True)  # Новые сверху
    return []

# Выбор снапшота
snapshots = get_available_snapshots()
if snapshots:
    selected_snapshot = st.sidebar.selectbox(
        "📊 Выберите снапшот данных",
        options=snapshots,
        index=0,
        help="Выберите снапшот рыночных данных для анализа"
    )
    snapshot_id = selected_snapshot.replace('.json', '')
else:
    st.sidebar.error("⚠️ Снапшоты не найдены!")
    st.stop()

# Параметры оптимизации
st.sidebar.subheader("🎯 Параметры оптимизации")

optimization_method = st.sidebar.selectbox(
    "Метод оптимизации",
    ["hrp", "markowitz", "black_litterman"],
    index=0,
    help="HRP - иерархический паритет риска, Markowitz - классическая оптимизация"
)

risk_free_rate = st.sidebar.slider(
    "Безрисковая ставка (%)",
    min_value=0.0,
    max_value=5.0,
    value=0.1,
    step=0.1,
    help="Безрисковая ставка для расчета коэффициента Шарпа"
) / 100

max_weight = st.sidebar.slider(
    "Максимальный вес актива (%)",
    min_value=5,
    max_value=50,
    value=40,
    step=5,
    help="Максимальная доля одного актива в портфеле"
) / 100

# Загрузка и кеширование данных
@st.cache_data
def load_snapshot_data(snapshot_id):
    """Загрузка данных снапшота"""
    try:
        with open(f"./local/snapshots/{snapshot_id}.json", 'r') as f:
            data = json.load(f)
        return data
    except Exception as e:
        st.error(f"Ошибка загрузки снапшота: {e}")
        return None

@st.cache_data
def optimize_portfolio(method, snapshot_id, risk_free, max_w):
    """Оптимизация портфеля с кешированием"""
    return optimize_tool(
        method=method,
        snapshot_id=snapshot_id,
        risk_free_rate=risk_free,
        max_weight=max_w
    )

@st.cache_data
def get_performance_data(weights, risk_free):
    """Получение данных о производительности"""
    return performance_tool(weights=weights, risk_free_rate=risk_free)

# Основная логика
def main():
    # Загружаем данные снапшота
    snapshot_data = load_snapshot_data(snapshot_id)
    if not snapshot_data:
        st.error("Не удалось загрузить данные снапшота")
        return
    
    # Создаем вкладки
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Обзор портфеля", 
        "⚡ Оптимизация", 
        "📈 Производительность", 
        "🔮 Прогнозы",
        "🗃️ Снапшот данных",
        "📱 Telegram отчет"
    ])
    
    # Инициализируем переменные для передачи данных между вкладками
    optimization_results = None
    performance_results = None
    
    with tab1:
        show_portfolio_overview(snapshot_data, user_state, selected_user_id)
    
    with tab2:
        optimization_results = show_optimization_results(snapshot_data, user_state, selected_user_id)
    
    with tab3:
        performance_results = show_performance_analysis(user_state, selected_user_id)
    
    with tab4:
        show_forecasts(snapshot_data)
    
    with tab5:
        show_snapshot_details(snapshot_data)
    
    with tab6:
        # Получаем данные из session state если они есть
        opt_results = st.session_state.get('optimization_results', optimization_results)
        perf_results = st.session_state.get('performance_results', performance_results)
        show_telegram_sender(opt_results, snapshot_data, perf_results)

def show_portfolio_overview(snapshot_data, user_state, selected_user_id):
    """Обзор портфеля"""
    st.header("📊 Обзор портфеля")
    
    # Если есть данные пользователя, показываем его портфель
    if user_state and user_state.get('positions'):
        positions = user_state.get('positions', {})
        budget = user_state.get('budget', 0)
        
        st.subheader(f"💼 Портфель пользователя {selected_user_id}")
        
        # Рассчитываем стоимость портфеля
        prices = snapshot_data.get('prices', {})
        total_value = 0
        portfolio_data = []
        
        for ticker, shares in positions.items():
            price = prices.get(ticker, 100.0)  # Дефолтная цена если нет в снапшоте
            value = shares * price
            total_value += value
            
            portfolio_data.append({
                'Тикер': ticker,
                'Количество акций': shares,
                'Цена за акцию': price,
                'Общая стоимость': value,
                'Доля (%)': 0  # Рассчитаем после
            })
        
        # Рассчитываем доли
        for item in portfolio_data:
            item['Доля (%)'] = (item['Общая стоимость'] / total_value * 100) if total_value > 0 else 0
        
        # Показываем метрики
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("💰 Общая стоимость портфеля", f"${total_value:,.2f}")
        with col2:
            st.metric("🎯 Бюджет пользователя", f"${budget:,.2f}")
        with col3:
            usage_pct = (total_value / budget * 100) if budget > 0 else 0
            st.metric("📊 Использование бюджета", f"{usage_pct:.1f}%")
        with col4:
            st.metric("📈 Количество позиций", len(positions))
        
        # Таблица позиций
        if portfolio_data:
            df_portfolio = pd.DataFrame(portfolio_data)
            st.dataframe(
                df_portfolio.style.format({
                    'Количество акций': '{:.4f}',
                    'Цена за акцию': '${:.2f}',
                    'Общая стоимость': '${:,.2f}',
                    'Доля (%)': '{:.2f}%'
                }),
                use_container_width=True
            )
            
            # График распределения портфеля
            fig = px.pie(
                df_portfolio,
                values='Общая стоимость',
                names='Тикер',
                title="Распределение портфеля по стоимости"
            )
            st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
    
    # Общая информация о снапшоте
    st.subheader("📊 Информация о рыночных данных")
    meta = snapshot_data.get('meta', {})
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "📅 Дата снапшота",
            meta.get('timestamp', 'N/A')[:10] if meta.get('timestamp') else 'N/A'
        )
    
    with col2:
        st.metric(
            "📈 Количество активов",
            len(snapshot_data.get('mu', {}))
        )
    
    with col3:
        st.metric(
            "⏱️ Горизонт прогноза",
            f"{meta.get('horizon_days', 'N/A')} дней"
        )
    
    with col4:
        st.metric(
            "🎯 Средняя ожидаемая доходность",
            f"{np.mean(list(snapshot_data.get('mu', {}).values())) * 100:.2f}%"
        )
    
    st.markdown("---")
    
    # Топ активов по ожидаемой доходности
    st.subheader("🏆 Топ активов по ожидаемой доходности")
    
    mu_data = snapshot_data.get('mu', {})
    if mu_data:
        df_returns = pd.DataFrame(list(mu_data.items()), columns=['Тикер', 'Ожидаемая доходность'])
        df_returns['Ожидаемая доходность (%)'] = df_returns['Ожидаемая доходность'] * 100
        df_returns = df_returns.sort_values('Ожидаемая доходность', ascending=False)
        
        # Топ 10 и аутсайдеры
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**🔥 Топ 10 лидеров:**")
            top_10 = df_returns.head(10)
            
            fig = px.bar(
                top_10, 
                x='Ожидаемая доходность (%)', 
                y='Тикер',
                orientation='h',
                color='Ожидаемая доходность (%)',
                color_continuous_scale='RdYlGn',
                title="Лучшие активы"
            )
            fig.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.write("**📉 Топ 10 аутсайдеров:**")
            bottom_10 = df_returns.tail(10)
            
            fig = px.bar(
                bottom_10, 
                x='Ожидаемая доходность (%)', 
                y='Тикер',
                orientation='h',
                color='Ожидаемая доходность (%)',
                color_continuous_scale='RdYlGn',
                title="Худшие активы"
            )
            fig.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

def show_optimization_results(snapshot_data, user_state, selected_user_id):
    """Результаты оптимизации"""
    st.header("⚡ Результаты оптимизации портфеля")
    
    # Опции оптимизации
    optimization_source = st.radio(
        "Источник для оптимизации:",
        ["Новый портфель", "Использовать существующий портфель пользователя"] if user_state and user_state.get('positions') else ["Новый портфель"]
    )
    
    input_tickers = []
    
    if optimization_source == "Использовать существующий портфель пользователя" and user_state:
        positions = user_state.get('positions', {})
        input_tickers = list(positions.keys())
        st.info(f"📊 Будет использован существующий портфель с {len(input_tickers)} активами: {', '.join(input_tickers[:5])}{'...' if len(input_tickers) > 5 else ''}")
    else:
        st.info("🆕 Создается новый портфель с помощью автоматической оптимизации")
    
    # Запускаем оптимизацию
    with st.spinner("🔄 Оптимизируем портфель..."):
        if input_tickers:
            # Оптимизируем с использованием конкретных тикеров
            result = optimize_tool(
                tickers=input_tickers,
                snapshot_id=snapshot_id,
                method=optimization_method,
                risk_aversion=1.0,  # Можно добавить в sidebar
            )
        else:
            # Стандартная оптимизация
            result = optimize_tool(
                method=optimization_method, 
                snapshot_id=snapshot_id, 
                risk_free_rate=risk_free_rate, 
                max_weight=max_weight
            )
    
    if result.get('error'):
        st.error(f"❌ Ошибка оптимизации: {result['error']}")
        return None
    
    weights = result.get('weights', {})
    if not weights:
        st.error("❌ Не удалось получить веса портфеля")
        return None
    
    # Сохраняем результаты в session state
    st.session_state.optimization_results = result
    st.session_state.portfolio_weights = weights
    
    # Метрики портфеля
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "📈 Ожидаемая доходность",
            f"{result.get('exp_ret', 0) * 100:.2f}%",
            help="Годовая ожидаемая доходность портфеля"
        )
    
    with col2:
        st.metric(
            "⚡ Волатильность",
            f"{result.get('risk', 0) * 100:.2f}%",
            help="Годовая волатильность портфеля"
        )
    
    with col3:
        sharpe = result.get('sharpe', 0)
        sharpe_color = "normal"
        if sharpe > 1:
            sharpe_color = "normal"
        elif sharpe > 0.5:
            sharpe_color = "normal"
        
        st.metric(
            "🎯 Коэффициент Шарпа",
            f"{sharpe:.3f}",
            help="Отношение избыточной доходности к риску"
        )
    
    with col4:
        st.metric(
            "📊 Количество позиций",
            len([w for w in weights.values() if w > 0.001]),
            help="Количество активов с весом > 0.1%"
        )
    
    st.markdown("---")
    
    # Визуализация весов портфеля
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("🥧 Структура портфеля")
        
        # Фильтруем активы с весом > 1%
        significant_weights = {k: v for k, v in weights.items() if v > 0.01}
        other_weight = sum(v for v in weights.values() if v <= 0.01)
        
        if other_weight > 0:
            significant_weights['Прочие'] = other_weight
        
        # Pie chart
        fig = go.Figure(data=[go.Pie(
            labels=list(significant_weights.keys()),
            values=list(significant_weights.values()),
            hole=0.4,
            textinfo='label+percent',
            textposition='auto',
            hovertemplate='<b>%{label}</b><br>Вес: %{value:.1%}<extra></extra>'
        )])
        
        fig.update_layout(
            title="Распределение весов портфеля",
            font=dict(size=14),
            showlegend=True,
            height=500
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("📋 Детальные веса")
        
        # Таблица весов
        df_weights = pd.DataFrame([
            {'Тикер': ticker, 'Вес (%)': weight * 100}
            for ticker, weight in sorted(weights.items(), key=lambda x: x[1], reverse=True)
            if weight > 0.001
        ])
        
        st.dataframe(
            df_weights,
            use_container_width=True,
            height=400
        )
    
    # Risk-Return scatter
    st.subheader("📊 Анализ риск-доходность")
    
    mu_data = snapshot_data.get('mu', {})
    sigma_data = snapshot_data.get('sigma', {})
    
    if mu_data and sigma_data:
        # Создаем данные для scatter plot
        tickers = []
        returns = []
        risks = []
        portfolio_weights_list = []
        
        for ticker in mu_data.keys():
            if ticker in sigma_data:
                tickers.append(ticker)
                returns.append(mu_data[ticker] * 100)
                risks.append(np.sqrt(sigma_data[ticker][ticker]) * 100)  # Стандартное отклонение
                portfolio_weights_list.append(weights.get(ticker, 0) * 100)
        
        # Scatter plot
        fig = go.Figure()
        
        # Добавляем точки активов
        fig.add_trace(go.Scatter(
            x=risks,
            y=returns,
            mode='markers',
            marker=dict(
                size=[max(w*2, 5) for w in portfolio_weights_list],  # Размер пропорционален весу
                color=portfolio_weights_list,
                colorscale='Viridis',
                colorbar=dict(title="Вес в портфеле (%)"),
                line=dict(width=1, color='white')
            ),
            text=tickers,
            hovertemplate='<b>%{text}</b><br>Риск: %{x:.2f}%<br>Доходность: %{y:.2f}%<extra></extra>',
            name='Активы'
        ))
        
        # Добавляем точку портфеля
        portfolio_return = result.get('exp_ret', 0) * 100
        portfolio_risk = result.get('risk', 0) * 100
        
        fig.add_trace(go.Scatter(
            x=[portfolio_risk],
            y=[portfolio_return],
            mode='markers',
            marker=dict(
                size=20,
                color='red',
                symbol='star',
                line=dict(width=2, color='white')
            ),
            name='Портфель',
            hovertemplate='<b>Оптимальный портфель</b><br>Риск: %{x:.2f}%<br>Доходность: %{y:.2f}%<extra></extra>'
        ))
        
        fig.update_layout(
            title="Карта риск-доходность",
            xaxis_title="Риск (волатильность), %",
            yaxis_title="Ожидаемая доходность, %",
            height=500,
            showlegend=True
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    # Информационное сообщение для пользователя
    st.info("💡 Портфель оптимизирован! Перейдите во вкладку '📱 Telegram отчет' для отправки результатов.")
    
    # Кнопка сохранения результатов в базу данных пользователя
    if USER_STATE_AVAILABLE and selected_user_id:
        st.markdown("---")
        st.subheader("💾 Сохранение результатов")
        
        budget = user_state.get('budget', 10000) if user_state else 10000
        budget_input = st.number_input(
            "Бюджет для расчета позиций ($):",
            min_value=100,
            value=budget,
            step=100,
            help="Бюджет пользователя для конвертации весов в количество акций"
        )
        
        if st.button("💾 Сохранить портфель в базу данных", type="primary"):
            try:
                # Конвертируем веса в позиции
                from portfolio_assistant.src.market_snapshot.registry import SnapshotRegistry
                
                # Получаем цены из снапшота
                registry = SnapshotRegistry()
                snapshot = registry.load(snapshot_id)
                prices = {}
                if snapshot and hasattr(snapshot, 'prices') and snapshot.prices:
                    prices = snapshot.prices
                
                # Конвертируем веса в позиции
                new_positions = {}
                total_allocated = 0.0
                
                for ticker, weight_percent in weights.items():
                    stock_price = prices.get(ticker, 100.0)
                    allocation_amount = budget_input * weight_percent
                    shares_count = allocation_amount / stock_price
                    new_positions[ticker] = shares_count
                    total_allocated += allocation_amount
                
                # Сохраняем позиции в базу данных
                success = update_positions(selected_user_id, new_positions)
                
                if success:
                    st.success(f"✅ Портфель успешно сохранен для пользователя {selected_user_id}!")
                    st.info(f"💰 Общее вложение: ${total_allocated:,.2f} из ${budget_input:,.2f} ({(total_allocated/budget_input)*100:.1f}%)")
                    
                    # Показываем детали сохраненных позиций
                    with st.expander("📊 Детали сохраненных позиций"):
                        for ticker, shares in new_positions.items():
                            price = prices.get(ticker, 100.0)
                            value = shares * price
                            weight = weights.get(ticker, 0) * 100
                            st.write(f"**{ticker}:** {shares:.4f} акций × ${price:.2f} = ${value:.2f} ({weight:.2f}%)")
                else:
                    st.error("❌ Ошибка при сохранении портфеля в базу данных")
                    
            except Exception as e:
                st.error(f"❌ Ошибка: {str(e)}")
    
    return result

def show_performance_analysis(user_state, selected_user_id):
    """Анализ производительности"""
    st.header("📈 Анализ производительности портфеля")
    
    # Проверяем наличие весов из оптимизации
    if 'portfolio_weights' not in st.session_state:
        st.warning("⚠️ Сначала выполните оптимизацию портфеля во вкладке 'Оптимизация'")
        return None
    
    weights = st.session_state.portfolio_weights
    
    # Настройки анализа
    col1, col2 = st.columns(2)
    
    with col1:
        start_date = st.date_input(
            "Дата начала анализа",
            value=datetime.now() - timedelta(days=90),
            help="Начальная дата для анализа производительности"
        )
    
    with col2:
        end_date = st.date_input(
            "Дата окончания анализа",
            value=datetime.now(),
            help="Конечная дата для анализа производительности"
        )
    
    # Запуск анализа
    with st.spinner("📊 Анализируем производительность..."):
        perf_result = performance_tool(
            weights=weights,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            risk_free_rate=risk_free_rate
        )
    
    if perf_result.get('error'):
        st.error(f"❌ Ошибка анализа: {perf_result['error']}")
        return None
    
    # Сохраняем результаты в session state
    st.session_state.performance_results = perf_result
    
    # Метрики производительности
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        ann_return = perf_result.get('portfolio_return_annualized', 0)
        st.metric(
            "📈 Годовая доходность",
            f"{ann_return * 100:.2f}%",
            delta=f"vs бенчмарк: {(ann_return - perf_result.get('benchmark_return', 0)) * 100:.2f}%"
        )
    
    with col2:
        volatility = perf_result.get('portfolio_volatility_annualized', 0)
        st.metric(
            "⚡ Волатильность",
            f"{volatility * 100:.2f}%"
        )
    
    with col3:
        sharpe = perf_result.get('sharpe_ratio', 0)
        st.metric(
            "🎯 Коэффициент Шарпа",
            f"{sharpe:.3f}"
        )
    
    with col4:
        max_dd = perf_result.get('max_drawdown', 0)
        st.metric(
            "📉 Макс. просадка",
            f"{max_dd * 100:.2f}%"
        )
    
    # Дополнительные метрики
    col1, col2, col3 = st.columns(3)
    
    with col1:
        alpha = perf_result.get('alpha', 0)
        st.metric(
            "α Alpha",
            f"{alpha * 100:.2f}%",
            help="Избыточная доходность относительно рынка"
        )
    
    with col2:
        beta = perf_result.get('beta', 0)
        st.metric(
            "β Beta",
            f"{beta:.3f}",
            help="Чувствительность к рыночным движениям"
        )
    
    with col3:
        total_return = perf_result.get('total_return', 0)
        st.metric(
            "📊 Общая доходность",
            f"{total_return * 100:.2f}%",
            help=f"За период {perf_result.get('analysis_period', 'N/A')}"
        )
    
    st.markdown("---")
    
    # Историческая производительность отдельных активов (топ-10 по весу)
    st.subheader("📈 Историческая производительность активов")
    
    # Берем топ-10 активов по весу
    top_assets = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:10]
    asset_tickers = [asset[0] for asset in top_assets]
    
    if len(asset_tickers) > 0:
        with st.spinner("📊 Загружаем исторические данные..."):
            try:
                # Загружаем данные
                data = yf.download(
                    asset_tickers,
                    start=start_date,
                    end=end_date,
                    progress=False
                )['Close']
                
                if not data.empty:
                    # Нормализуем к начальному значению
                    normalized_data = data / data.iloc[0] * 100
                    
                    # График
                    fig = go.Figure()
                    
                    for ticker in asset_tickers:
                        if ticker in normalized_data.columns:
                            weight_pct = weights[ticker] * 100
                            fig.add_trace(go.Scatter(
                                x=normalized_data.index,
                                y=normalized_data[ticker],
                                name=f"{ticker} ({weight_pct:.1f}%)",
                                line=dict(width=2),
                                hovertemplate=f'<b>{ticker}</b><br>Дата: %{{x}}<br>Цена: %{{y:.2f}}<extra></extra>'
                            ))
                    
                    fig.update_layout(
                        title="Динамика цен активов портфеля (нормализовано к 100)",
                        xaxis_title="Дата",
                        yaxis_title="Цена (базовый индекс = 100)",
                        height=500,
                        hovermode='x unified'
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                
            except Exception as e:
                st.error(f"Ошибка загрузки исторических данных: {e}")
    
    return perf_result

def show_forecasts(snapshot_data):
    """Прогнозы"""
    st.header("🔮 Прогнозы и сценарный анализ")
    
    if 'portfolio_weights' not in st.session_state:
        st.warning("⚠️ Сначала выполните оптимизацию портфеля во вкладке 'Оптимизация'")
        return
    
    weights = st.session_state.portfolio_weights
    
    # Выбор активов для прогноза
    available_assets = list(weights.keys())
    top_assets_tickers = [item[0] for item in sorted(weights.items(), key=lambda x: x[1], reverse=True)[:5]]
    selected_assets = st.multiselect(
        "Выберите активы для детального прогноза",
        available_assets,
        default=top_assets_tickers  # Топ-5 по весу (только тикеры)
    )
    
    if not selected_assets:
        st.info("Выберите активы для анализа прогнозов")
        return
    
    # Настройки прогноза
    col1, col2 = st.columns(2)
    
    with col1:
        forecast_horizon = st.selectbox(
            "Горизонт прогноза",
            [30, 60, 90, 180],
            index=2,
            help="Количество дней для прогноза"
        )
    
    with col2:
        confidence_level = st.slider(
            "Уровень доверия (%)",
            min_value=80,
            max_value=99,
            value=95,
            help="Уровень доверия для доверительных интервалов"
        )
    
    # Создаем прогнозы
    mu_data = snapshot_data.get('mu', {})
    sigma_data = snapshot_data.get('sigma', {})
    
    if mu_data and sigma_data:
        st.subheader("📊 Сценарный анализ доходности")
        
        # Создаем сценарии
        scenarios = {
            "Оптимистичный": 1.5,
            "Базовый": 1.0,
            "Пессимистичный": 0.5
        }
        
        scenario_results = []
        
        for scenario_name, multiplier in scenarios.items():
            portfolio_return = 0
            portfolio_risk = 0
            
            # Рассчитываем ожидаемую доходность и риск портфеля для сценария
            for asset in selected_assets:
                if asset in mu_data and asset in weights:
                    asset_return = mu_data[asset] * multiplier
                    asset_weight = weights[asset]
                    portfolio_return += asset_return * asset_weight
            
            # Упрощенный расчет риска портфеля
            for i, asset1 in enumerate(selected_assets):
                for j, asset2 in enumerate(selected_assets):
                    if asset1 in sigma_data and asset2 in sigma_data[asset1]:
                        w1 = weights.get(asset1, 0)
                        w2 = weights.get(asset2, 0)
                        cov = sigma_data[asset1][asset2]
                        portfolio_risk += w1 * w2 * cov
            
            portfolio_risk = np.sqrt(portfolio_risk) if portfolio_risk > 0 else 0
            
            scenario_results.append({
                'Сценарий': scenario_name,
                'Ожидаемая доходность (%)': portfolio_return * 100,
                'Риск (%)': portfolio_risk * 100,
                'Коэффициент Шарпа': (portfolio_return - risk_free_rate) / portfolio_risk if portfolio_risk > 0 else 0
            })
        
        # Отображаем результаты сценариев
        df_scenarios = pd.DataFrame(scenario_results)
        
        fig = go.Figure()
        
        colors = ['green', 'blue', 'red']
        for i, scenario in enumerate(scenario_results):
            fig.add_trace(go.Bar(
                name=scenario['Сценарий'],
                x=['Доходность (%)', 'Риск (%)', 'Коэф. Шарпа'],
                y=[scenario['Ожидаемая доходность (%)'], scenario['Риск (%)'], scenario['Коэффициент Шарпа']],
                marker_color=colors[i],
                opacity=0.8
            ))
        
        fig.update_layout(
            title="Сценарный анализ портфеля",
            xaxis_title="Метрики",
            yaxis_title="Значения",
            barmode='group',
            height=400
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Таблица сценариев
        st.dataframe(df_scenarios, use_container_width=True)

def show_snapshot_details(snapshot_data):
    """Детали снапшота"""
    st.header("🗃️ Детали снапшота данных")
    
    # Метаданные
    meta = snapshot_data.get('meta', {})
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📋 Метаданные")
        st.json(meta)
    
    with col2:
        st.subheader("📊 Статистика")
        
        mu_data = snapshot_data.get('mu', {})
        sigma_data = snapshot_data.get('sigma', {})
        
        if mu_data:
            returns = list(mu_data.values())
            st.metric("Среднее ожидаемой доходности", f"{np.mean(returns)*100:.2f}%")
            st.metric("Медиана ожидаемой доходности", f"{np.median(returns)*100:.2f}%")
            st.metric("Стд. отклонение доходности", f"{np.std(returns)*100:.2f}%")
            st.metric("Мин. ожидаемая доходность", f"{np.min(returns)*100:.2f}%")
            st.metric("Макс. ожидаемая доходность", f"{np.max(returns)*100:.2f}%")
    
    # Детальная таблица данных
    st.subheader("📈 Ожидаемые доходности активов")
    
    if mu_data:
        df_full = pd.DataFrame([
            {
                'Тикер': ticker,
                'Ожидаемая доходность (%)': ret * 100,
                'Волатильность (%)': np.sqrt(sigma_data.get(ticker, {}).get(ticker, 0)) * 100 if sigma_data else 0
            }
            for ticker, ret in mu_data.items()
        ])
        
        df_full = df_full.sort_values('Ожидаемая доходность (%)', ascending=False)
        
        # Добавляем цветовое кодирование
        def color_negative_red(val):
            color = 'red' if val < 0 else 'green' if val > 10 else 'black'
            return f'color: {color}'
        
        styled_df = df_full.style.map(color_negative_red, subset=['Ожидаемая доходность (%)'])
        
        st.dataframe(styled_df, use_container_width=True, height=600)
    
    # Корреляционная матрица (для первых 20 активов)
    if sigma_data:
        st.subheader("🔗 Корреляционная матрица (топ-20 активов)")
        
        # Берем первые 20 активов
        top_assets = list(sigma_data.keys())[:20]
        
        # Создаем корреляционную матрицу
        corr_matrix = []
        for asset1 in top_assets:
            row = []
            for asset2 in top_assets:
                if asset1 in sigma_data and asset2 in sigma_data[asset1]:
                    # Корреляция = ковариация / (стд1 * стд2)
                    cov = sigma_data[asset1][asset2]
                    std1 = np.sqrt(sigma_data[asset1][asset1])
                    std2 = np.sqrt(sigma_data[asset2][asset2])
                    corr = cov / (std1 * std2) if std1 > 0 and std2 > 0 else 0
                    row.append(corr)
                else:
                    row.append(0)
            corr_matrix.append(row)
        
        # Heatmap
        fig = go.Figure(data=go.Heatmap(
            z=corr_matrix,
            x=top_assets,
            y=top_assets,
            colorscale='RdBu',
            zmid=0,
            hovertemplate='%{x} vs %{y}<br>Корреляция: %{z:.3f}<extra></extra>'
        ))
        
        fig.update_layout(
            title="Корреляционная матрица активов",
            height=600
        )
        
        st.plotly_chart(fig, use_container_width=True)

def show_telegram_sender(optimization_results, snapshot_data, performance_results=None):
    """Интерфейс для отправки отчета в Telegram"""
    
    if not TELEGRAM_AVAILABLE:
        st.warning("📱 Telegram интеграция недоступна. Установите библиотеку python-telegram-bot:")
        st.code("pip install python-telegram-bot")
        return
    
    st.header("📱 Отправить отчет в Telegram")
    
    # Проверяем наличие результатов оптимизации
    if not optimization_results or optimization_results.get('error'):
        st.warning("⚠️ Сначала выполните оптимизацию портфеля во вкладке 'Оптимизация'")
        return
    
    st.markdown("""
    Отправьте красивый отчет по оптимизированному портфелю прямо в Telegram! 
    
    **Что будет отправлено:**
    - 📈 Подробный текстовый отчет с метриками
    - 📊 Красивая диаграмма структуры портфеля  
    - 📄 JSON файл с детальными данными
    """)
    
    # Поле для ввода Chat ID
    col1, col2 = st.columns([2, 1])
    
    with col1:
        chat_id = st.text_input(
            "🆔 Telegram Chat ID или @username",
            placeholder="Введите ваш Chat ID (например: 123456789) или @username",
            help="Чтобы узнать ваш Chat ID, напишите @userinfobot в Telegram"
        )
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)  # Отступ
        if st.button("🧪 Тест"):
            if chat_id and validate_telegram_chat_id(chat_id):
                with st.spinner("Отправляем тестовое сообщение..."):
                    success = test_telegram_sync(chat_id)
                    if success:
                        st.success("✅ Тест успешен! Telegram подключен.")
                    else:
                        st.error("❌ Ошибка подключения. Проверьте Chat ID.")
            else:
                st.error("❌ Введите корректный Chat ID")
    
    # Дополнительные настройки
    st.subheader("⚙️ Настройки отправки")
    
    include_performance = st.checkbox(
        "📊 Включить анализ производительности",
        value=bool(performance_results and not performance_results.get('error')),
        help="Добавить в отчет исторические метрики производительности"
    )
    
    include_chart = st.checkbox(
        "📈 Включить диаграмму портфеля",
        value=True,
        help="Отправить красивую круговую диаграмму структуры портфеля"
    )
    
    # Превью отчета
    with st.expander("👀 Предварительный просмотр отчета"):
        if TELEGRAM_AVAILABLE:
            try:
                from telegram_integration import format_portfolio_report
                preview_text = format_portfolio_report(
                    optimization_results,
                    snapshot_data,
                    performance_results if include_performance else None
                )
                st.markdown(preview_text)
            except Exception as e:
                st.error(f"Ошибка создания превью: {e}")
    
    # Кнопка отправки
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col2:
        if st.button("🚀 Отправить отчет в Telegram", type="primary", use_container_width=True):
            if not chat_id:
                st.error("❌ Введите Chat ID")
                return
                
            if not validate_telegram_chat_id(chat_id):
                st.error("❌ Некорректный формат Chat ID")
                return
            
            # Подготавливаем данные для отправки
            perf_data = performance_results if include_performance and performance_results and not performance_results.get('error') else None
            
            with st.spinner("📤 Отправляем отчет в Telegram..."):
                success = send_portfolio_report_sync(
                    chat_id=chat_id,
                    optimization_results=optimization_results,
                    snapshot_data=snapshot_data,
                    performance_results=perf_data
                )
                
                if success:
                    st.success("🎉 Отчет успешно отправлен в Telegram!")
                    st.balloons()
                    
                    # Сохраняем Chat ID для будущих отправок
                    if 'telegram_chat_id' not in st.session_state:
                        st.session_state.telegram_chat_id = chat_id
                else:
                    st.error("❌ Ошибка отправки. Проверьте подключение и Chat ID.")
    
    # Инструкция по получению Chat ID
    with st.expander("❓ Как получить Chat ID?"):
        st.markdown("""
        **Способ 1 - Через бота @userinfobot:**
        1. Найдите бота @userinfobot в Telegram
        2. Нажмите /start
        3. Скопируйте ваш User ID
        
        **Способ 2 - Через бота @getidsbot:**
        1. Найдите бота @getidsbot в Telegram  
        2. Нажмите /start
        3. Получите ваш Chat ID
        
        **Способ 3 - Использовать @username:**
        Если у вас есть публичный username, можете использовать @ваш_username
        
        **Для групп:**
        Добавьте бота в группу и используйте отрицательный ID группы
        """)

if __name__ == "__main__":
    main() 