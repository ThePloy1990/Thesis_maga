import pandas as pd
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from fpdf import FPDF
from typing import Dict


def create_performance_chart(cum_returns: pd.Series, output_path: str):
    """Строит график накопительной доходности и сохраняет в файл"""
    plt.figure(figsize=(8,5))
    cum_returns.plot(title='Накопительная доходность')
    plt.xlabel('Date')
    plt.ylabel('Cumulative Return')
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def create_allocation_pie(weights: Dict[str, float], output_path: str):
    """Строит круговую диаграмму аллокации и сохраняет в файл"""
    labels = list(weights.keys())
    sizes = [v*100 for v in weights.values()]
    fig = go.Figure(data=[go.Pie(labels=labels, values=sizes, hole=0.4)])
    fig.update_layout(title='Оптимальная аллокация (%)')
    fig.write_image(output_path)


def create_reports_csv(results: Dict, output_path: str):
    """Сохраняет результаты оптимизации в CSV"""
    df = pd.DataFrame.from_dict(results.get('optimal_weights'), orient='index', columns=['weight'])
    df['weight'] = df['weight']*100
    df.to_csv(output_path)


def create_reports_excel(results: Dict, output_path: str):
    """Сохраняет результаты оптимизации в Excel"""
    df = pd.DataFrame.from_dict(results.get('optimal_weights'), orient='index', columns=['weight'])
    df['weight'] = df['weight']*100
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Weights')
        metrics = pd.DataFrame({
            'expected_return': [results.get('expected_return')],
            'volatility': [results.get('expected_volatility')],
            'sharpe_ratio': [results.get('sharpe_ratio')]
        })
        metrics.to_excel(writer, sheet_name='Metrics', index=False)


def create_pdf_report(results: Dict, perf_path: str, alloc_path: str, output_path: str):
    """Генерирует простой PDF отчет со вставленными графиками"""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, 'Отчет по оптимизации портфеля', ln=True, align='C')
    pdf.ln(5)
    pdf.image(perf_path, w=180)
    pdf.ln(5)
    pdf.image(alloc_path, w=180)
    pdf.ln(5)
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 8, f"Ожидаемая доходность: {results.get('expected_return')*100:.2f}%", ln=True)
    pdf.cell(0, 8, f"Волатильность: {results.get('expected_volatility')*100:.2f}%", ln=True)
    pdf.cell(0, 8, f"Sharpe Ratio: {results.get('sharpe_ratio'):.2f}", ln=True)
    pdf.output(output_path)


def get_dashboard_link() -> str:
    """Возвращает ссылку на веб-дашборд (заглушка)"""
    return 'https://example.com/dashboard' 