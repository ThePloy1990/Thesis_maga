"""
Дополнительные компоненты для Streamlit приложения Portfolio Assistant
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import json

# Добавляем путь к нашим модулям
import sys
sys.path.append('./portfolio_assistant/src')

from tools.optimize_tool import optimize_tool


def show_optimization_comparison(snapshot_data, snapshot_id, risk_free_rate, max_weight):
    """
    Сравнение различных методов оптимизации
    """
    st.header("🔍 Сравнение методов оптимизации")
    
    methods = {
        "HRP": "hrp",
        "Markowitz": "markowitz", 
        "Black-Litterman": "black_litterman"
    }
    
    with st.spinner("⚖️ Сравниваем методы оптимизации..."):
        results = {}
        
        # Запускаем оптимизацию для каждого метода
        for method_name, method_code in methods.items():
            try:
                result = optimize_tool(
                    method=method_code,
                    snapshot_id=snapshot_id,
                    risk_free_rate=risk_free_rate,
                    max_weight=max_weight
                )
                
                if not result.get('error'):
                    results[method_name] = result
                else:
                    st.warning(f"⚠️ {method_name}: {result.get('error')}")
                    
            except Exception as e:
                st.error(f"❌ Ошибка в {method_name}: {str(e)}")
    
    if not results:
        st.error("Не удалось выполнить оптимизацию ни одним методом")
        return
    
    # Таблица сравнения метрик
    st.subheader("📊 Сравнение ключевых метрик")
    
    comparison_data = []
    for method, result in results.items():
        comparison_data.append({
            'Метод': method,
            'Ожидаемая доходность (%)': f"{result.get('exp_ret', 0) * 100:.2f}",
            'Волатильность (%)': f"{result.get('risk', 0) * 100:.2f}",
            'Коэффициент Шарпа': f"{result.get('sharpe', 0):.3f}",
            'Количество позиций': len([w for w in result.get('weights', {}).values() if w > 0.001])
        })
    
    df_comparison = pd.DataFrame(comparison_data)
    st.dataframe(df_comparison, use_container_width=True)
    
    # Визуализация сравнения
    col1, col2 = st.columns(2)
    
    with col1:
        # Bar chart метрик
        fig = go.Figure()
        
        metrics = ['Ожидаемая доходность (%)', 'Волатильность (%)', 'Коэффициент Шарпа']
        
        for method, result in results.items():
            fig.add_trace(go.Bar(
                name=method,
                x=metrics,
                y=[
                    result.get('exp_ret', 0) * 100,
                    result.get('risk', 0) * 100,
                    result.get('sharpe', 0)
                ],
                opacity=0.8
            ))
        
        fig.update_layout(
            title="Сравнение метрик оптимизации",
            barmode='group',
            height=400
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Scatter plot риск-доходность
        fig = go.Figure()
        
        colors = ['red', 'blue', 'green']
        for i, (method, result) in enumerate(results.items()):
            fig.add_trace(go.Scatter(
                x=[result.get('risk', 0) * 100],
                y=[result.get('exp_ret', 0) * 100],
                mode='markers',
                marker=dict(
                    size=15,
                    color=colors[i % len(colors)],
                    symbol='circle',
                    line=dict(width=2, color='white')
                ),
                name=method,
                hovertemplate=f'<b>{method}</b><br>Риск: %{{x:.2f}}%<br>Доходность: %{{y:.2f}}%<extra></extra>'
            ))
        
        fig.update_layout(
            title="Позиция методов на карте риск-доходность",
            xaxis_title="Риск (волатильность), %",
            yaxis_title="Ожидаемая доходность, %",
            height=400
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    # Сравнение весов портфелей
    st.subheader("⚖️ Сравнение весов активов")
    
    # Собираем все уникальные активы
    all_assets = set()
    for result in results.values():
        all_assets.update(result.get('weights', {}).keys())
    
    # Создаем DataFrame для сравнения весов
    weights_data = []
    for asset in sorted(all_assets):
        row = {'Актив': asset}
        for method, result in results.items():
            weight = result.get('weights', {}).get(asset, 0)
            row[method] = weight * 100
        weights_data.append(row)
    
    df_weights = pd.DataFrame(weights_data)
    
    # Фильтруем только активы с весом > 0.1% в хотя бы одном методе
    method_columns = [col for col in df_weights.columns if col != 'Актив']
    df_weights['max_weight'] = df_weights[method_columns].max(axis=1)
    df_filtered = df_weights[df_weights['max_weight'] > 0.1].copy()
    df_filtered = df_filtered.drop('max_weight', axis=1)
    df_filtered = df_filtered.sort_values(method_columns[0], ascending=False)
    
    # Показываем топ-20 активов
    st.dataframe(df_filtered.head(20), use_container_width=True)
    
    # Heatmap весов
    if len(df_filtered) > 0:
        fig = go.Figure(data=go.Heatmap(
            z=df_filtered[method_columns].values.T,
            x=df_filtered['Актив'].values,
            y=method_columns,
            colorscale='Viridis',
            hovertemplate='Актив: %{x}<br>Метод: %{y}<br>Вес: %{z:.2f}%<extra></extra>'
        ))
        
        fig.update_layout(
            title="Тепловая карта весов активов по методам",
            height=300,
            xaxis_title="Активы",
            yaxis_title="Методы оптимизации"
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    return results


def show_risk_analysis(snapshot_data, weights):
    """
    Расширенный анализ рисков портфеля
    """
    st.header("⚠️ Анализ рисков портфеля")
    
    mu_data = snapshot_data.get('mu', {})
    sigma_data = snapshot_data.get('sigma', {})
    
    if not mu_data or not sigma_data:
        st.error("Недостаточно данных для анализа рисков")
        return
    
    # Основные риск-метрики
    col1, col2, col3, col4 = st.columns(4)
    
    # Вычисляем метрики портфеля
    portfolio_return = sum(weights.get(asset, 0) * ret for asset, ret in mu_data.items())
    
    portfolio_variance = 0
    for asset1, weight1 in weights.items():
        for asset2, weight2 in weights.items():
            if asset1 in sigma_data and asset2 in sigma_data.get(asset1, {}):
                portfolio_variance += weight1 * weight2 * sigma_data[asset1][asset2]
    
    portfolio_volatility = np.sqrt(portfolio_variance) if portfolio_variance > 0 else 0
    
    with col1:
        st.metric(
            "📈 Портфельная доходность",
            f"{portfolio_return * 100:.2f}%"
        )
    
    with col2:
        st.metric(
            "📊 Портфельная волатильность",
            f"{portfolio_volatility * 100:.2f}%"
        )
    
    with col3:
        # Упрощенный VaR (95%)
        var_95 = portfolio_return - 1.645 * portfolio_volatility
        st.metric(
            "⚠️ VaR (95%)",
            f"{var_95 * 100:.2f}%",
            help="Value at Risk - потенциальные потери с вероятностью 5%"
        )
    
    with col4:
        # Диверсификационный рейтинг
        effective_positions = len([w for w in weights.values() if w > 0.01])
        diversification_score = min(effective_positions / 10, 1.0)  # Максимум 10 для полной диверсификации
        st.metric(
            "🎯 Рейтинг диверсификации",
            f"{diversification_score:.1%}",
            help="Мера диверсификации портфеля (0-100%)"
        )
    
    st.markdown("---")
    
    # Анализ вкладов активов в риск
    st.subheader("📊 Вклад активов в портфельный риск")
    
    risk_contributions = []
    
    for asset, weight in weights.items():
        if weight > 0.001 and asset in mu_data:  # Только значимые позиции
            # Упрощенный расчет маргинального вклада в риск
            marginal_risk = 0
            for other_asset, other_weight in weights.items():
                if other_asset in sigma_data.get(asset, {}):
                    marginal_risk += other_weight * sigma_data[asset][other_asset]
            
            risk_contrib = weight * marginal_risk / portfolio_variance if portfolio_variance > 0 else 0
            
            risk_contributions.append({
                'Актив': asset,
                'Вес (%)': weight * 100,
                'Вклад в риск (%)': risk_contrib * 100,
                'Ожидаемая доходность (%)': mu_data[asset] * 100
            })
    
    df_risk = pd.DataFrame(risk_contributions)
    df_risk = df_risk.sort_values('Вклад в риск (%)', ascending=False)
    
    # Топ-15 по вкладу в риск
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Bar chart вкладов в риск
        top_risk = df_risk.head(15)
        
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=top_risk['Актив'],
            y=top_risk['Вклад в риск (%)'],
            name='Вклад в риск',
            marker_color='lightcoral',
            opacity=0.8
        ))
        
        fig.update_layout(
            title="Топ-15 активов по вкладу в портфельный риск",
            xaxis_title="Активы",
            yaxis_title="Вклад в риск (%)",
            height=400
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Таблица топ рисковых активов
        st.write("**Топ рисковые активы:**")
        st.dataframe(
            df_risk.head(10)[['Актив', 'Вес (%)', 'Вклад в риск (%)']],
            use_container_width=True,
            height=400
        )
    
    # Scatter plot: вес vs вклад в риск
    st.subheader("🎯 Эффективность активов: вес vs вклад в риск")
    
    fig = go.Figure()
    
    # Добавляем точки активов
    fig.add_trace(go.Scatter(
        x=df_risk['Вес (%)'],
        y=df_risk['Вклад в риск (%)'],
        mode='markers',
        marker=dict(
            size=df_risk['Ожидаемая доходность (%)'] * 2,  # Размер пропорционален доходности
            color=df_risk['Ожидаемая доходность (%)'],
            colorscale='RdYlGn',
            colorbar=dict(title="Ожидаемая доходность (%)"),
            line=dict(width=1, color='white')
        ),
        text=df_risk['Актив'],
        hovertemplate='<b>%{text}</b><br>Вес: %{x:.2f}%<br>Вклад в риск: %{y:.2f}%<br>Доходность: %{marker.color:.2f}%<extra></extra>',
        name='Активы'
    ))
    
    # Добавляем диагональную линию (идеальное соответствие)
    max_val = max(df_risk['Вес (%)'].max(), df_risk['Вклад в риск (%)'].max())
    fig.add_trace(go.Scatter(
        x=[0, max_val],
        y=[0, max_val],
        mode='lines',
        line=dict(dash='dash', color='gray'),
        name='Идеальное соответствие',
        hoverinfo='skip'
    ))
    
    fig.update_layout(
        title="Соотношение веса актива и его вклада в риск портфеля",
        xaxis_title="Вес в портфеле (%)",
        yaxis_title="Вклад в портфельный риск (%)",
        height=500,
        showlegend=True
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Выводы и рекомендации
    st.subheader("💡 Выводы и рекомендации")
    
    # Анализируем соотношение риск/вес
    df_risk['risk_weight_ratio'] = df_risk['Вклад в риск (%)'] / df_risk['Вес (%)']
    high_risk_assets = df_risk[df_risk['risk_weight_ratio'] > 1.5].head(5)
    low_risk_assets = df_risk[df_risk['risk_weight_ratio'] < 0.5].head(5)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if not high_risk_assets.empty:
            st.warning("⚠️ **Активы с высоким относительным риском:**")
            for _, asset in high_risk_assets.iterrows():
                st.write(f"• {asset['Актив']}: риск {asset['risk_weight_ratio']:.1f}x от веса")
    
    with col2:
        if not low_risk_assets.empty:
            st.success("✅ **Эффективные активы (низкий относительный риск):**")
            for _, asset in low_risk_assets.iterrows():
                st.write(f"• {asset['Актив']}: риск {asset['risk_weight_ratio']:.1f}x от веса")
    
    return df_risk


def create_portfolio_report(optimization_results, performance_results, snapshot_data):
    """
    Создание краткого отчета по портфелю
    """
    st.header("📋 Отчет по портфелю")
    
    # Основная информация
    meta = snapshot_data.get('meta', {})
    
    st.markdown(f"""
    ### 📊 Сводка по портфелю
    
    **Дата анализа:** {datetime.now().strftime('%d.%m.%Y %H:%M')}
    
    **Снапшот данных:** {meta.get('timestamp', 'N/A')[:19] if meta.get('timestamp') else 'N/A'}
    
    **Количество активов в снапшоте:** {len(snapshot_data.get('mu', {}))}
    
    **Горизонт прогноза:** {meta.get('horizon_days', 'N/A')} дней
    
    ---
    
    ### ⚡ Результаты оптимизации
    
    **Метод оптимизации:** {optimization_results.get('method', 'N/A')}
    
    **Ожидаемая годовая доходность:** {optimization_results.get('exp_ret', 0) * 100:.2f}%
    
    **Годовая волатильность:** {optimization_results.get('risk', 0) * 100:.2f}%
    
    **Коэффициент Шарпа:** {optimization_results.get('sharpe', 0):.3f}
    
    **Количество позиций:** {len([w for w in optimization_results.get('weights', {}).values() if w > 0.001])}
    
    ---
    
    ### 📈 Историческая производительность
    """)
    
    if performance_results and not performance_results.get('error'):
        st.markdown(f"""
        **Период анализа:** {performance_results.get('analysis_period', 'N/A')}
        
        **Реальная годовая доходность:** {performance_results.get('portfolio_return_annualized', 0) * 100:.2f}%
        
        **Доходность бенчмарка:** {performance_results.get('benchmark_return', 0) * 100:.2f}%
        
        **Alpha:** {performance_results.get('alpha', 0) * 100:.2f}%
        
        **Beta:** {performance_results.get('beta', 0):.3f}
        
        **Максимальная просадка:** {performance_results.get('max_drawdown', 0) * 100:.2f}%
        """)
    else:
        st.markdown("*Данные о производительности недоступны*")
    
    # Топ позиции
    weights = optimization_results.get('weights', {})
    if weights:
        top_positions = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:10]
        
        st.markdown("### 🏆 Топ-10 позиций в портфеле")
        
        positions_df = pd.DataFrame([
            {'Тикер': ticker, 'Вес (%)': f"{weight * 100:.2f}%"}
            for ticker, weight in top_positions
        ])
        
        st.dataframe(positions_df, use_container_width=True)
    
    # Кнопка для скачивания отчета
    if st.button("📥 Экспорт отчета в JSON"):
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'snapshot_meta': meta,
            'optimization_results': optimization_results,
            'performance_results': performance_results,
            'top_positions': dict(top_positions[:10]) if weights else {}
        }
        
        st.download_button(
            label="💾 Скачать отчет",
            data=json.dumps(report_data, indent=2, ensure_ascii=False),
            file_name=f"portfolio_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        ) 