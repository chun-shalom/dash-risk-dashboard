# 仪表盘_最终决战版_V5.py

import os
import traceback
import pandas as pd
import chardet
from dash import Dash, dcc, html, Input, Output
import plotly.graph_objects as go
from itertools import cycle

# ===== 1) 基础配置和数据加载 (保持不变) =====
CSV_PATH = Path(__file__).parent / "data" / "doc_risk_scores_k7.csv"

CATS = ["市场风险", "信用风险", "操作风险", "法律合规风险", "技术风险"]

def read_csv_smart(path_or_url: str) -> pd.DataFrame:
    try:
        with open(path_or_url, "rb") as f: enc = chardet.detect(f.read(50_000)).get("encoding") or "utf-8"
        return pd.read_csv(path_or_url, encoding=enc, low_memory=False)
    except FileNotFoundError: return pd.DataFrame(columns=['company', 'year', 'industry'] + [f'RD_{i}' for i in range(7)])

raw = read_csv_smart(CSV_PATH)
if not raw.empty:
    raw.columns = [c.strip() for c in raw.columns]
    if "industry" not in raw.columns: raw["industry"] = "未指定"
    for i in range(7):
        col = f'RD_{i}'
        if col in raw.columns: raw[col] = pd.to_numeric(raw[col], errors='coerce')
    raw["市场风险"] = raw.get("RD_0", 0); raw["信用风险"] = raw.get("RD_1", 0)
    raw["操作风险"] = raw.get("RD_2", 0) + raw.get("RD_5", 0); raw["法律合规风险"] = raw.get("RD_3", 0)
    raw["技术风险"] = raw.get("RD_4", 0) + raw.get("RD_6", 0)
    wide = raw[["company", "year", "industry"] + CATS].copy()
    wide.fillna(0, inplace=True); wide["综合"] = wide[CATS].mean(axis=1)
else:
    wide = pd.DataFrame(columns=["company", "year", "industry"] + CATS + ["综合"])

YEARS = sorted(list(pd.unique(wide["year"]))) if not wide.empty else []
DIMENSIONS = [{"label": "综合均值", "value": "综合"}] + [{"label": cat, "value": cat} for cat in CATS]

# ===== 2) 色彩定义 (保持不变) =====
PRECISE_PALETTE = ['#9CD4CA', '#6EC5C5', '#479FB6', '#2775A4', '#004B92']
precise_heatmap_scale = [[0.0, PRECISE_PALETTE[0]],[0.25, PRECISE_PALETTE[1]],[0.5, PRECISE_PALETTE[2]],[0.75, PRECISE_PALETTE[3]],[1.0, PRECISE_PALETTE[4]]]
chart_colors = {'background': 'rgba(0,0,0,0)', 'text': '#caf0f8', 'text_highlight': '#ffffff', 'grid': 'rgba(0, 119, 182, 0.5)',}

app = Dash(__name__, title="可视化风险仪表盘", suppress_callback_exceptions=True, assets_folder='assets')
server = app.server

# ===== 3) 应用布局 (修复热力图布局) =====
app.layout = html.Div(style={'height': '100vh', 'display': 'flex', 'flexDirection': 'column'}, children=[
    html.H1("上市公司风险可视化仪表盘", className="main-title"),
    html.Div(id="app-body", children=[
        html.Div(id="left-sidebar", children=[
            html.H2("筛选器", className="sidebar-title"),
            html.Div([html.Label("选择年份", className="control-label"), dcc.Dropdown(id="year", options=[{"label": str(y), "value": y} for y in YEARS], value=YEARS[-1] if YEARS else None, clearable=False)]),
            html.Div([html.Label("选择公司（雷达图）", className="control-label"), dcc.Dropdown(id="company-radar", options=[], value=None, clearable=False)]),
            html.Div([html.Label("选择对比公司（条形图）", className="control-label"), dcc.Dropdown(id="companies-compare", options=[], value=[], multi=True)]),
            html.Div([html.Label("选择对比维度（条形图）", className="control-label"), dcc.Dropdown(id="dimension-compare", options=DIMENSIONS, value="综合", clearable=False)]),
        ]),
        html.Div(id="main-content", children=[
            html.Div(className="top-chart-grid", children=[
                html.Div(className="chart-container", children=[dcc.Graph(id="radar", style={'height': '100%'})]),
                html.Div(className="chart-container", children=[dcc.Graph(id="bars", style={'height': '100%'})])
            ]),
            # <--- 核心修复: 为热力图容器添加新类，并设置图表高度为100% ---
            html.Div(className="chart-container heatmap-wrapper", children=[
                dcc.Graph(id="heatmap", style={'height': '100%'})
            ])
        ])
    ])
])

# ===== 4) 回调函数 (保持上次修复，逻辑不变) =====
@app.callback(
    [Output("company-radar", "options"), Output("company-radar", "value"), Output("companies-compare", "options"), Output("companies-compare", "value")],
    Input("year", "value")
)
def update_company_options(year):
    if not year or wide.empty: return [], None, [], []
    dfy = wide[wide["year"] == year]; companies = [{"label": c, "value": c} for c in sorted(dfy["company"].unique())]
    default_radar_company = companies[0]['value'] if companies else None
    default_compare_companies = [c['value'] for c in companies[:5]] if len(companies) >= 5 else [c['value'] for c in companies]
    return companies, default_radar_company, companies, default_compare_companies

def create_base_figure(title_text=""):
    fig = go.Figure()
    fig.update_layout(paper_bgcolor=chart_colors['background'], plot_bgcolor=chart_colors['background'], font_color=chart_colors['text'], title_font_color=chart_colors['text_highlight'], title_text=title_text, title_x=0.5, margin=dict(l=100, r=40, t=60, b=40))
    return fig

@app.callback(Output("radar", "figure"), [Input("company-radar", "value"), Input("year", "value")])
def update_radar(company, year):
    if not company or not year or wide.empty: return create_base_figure("请选择公司和年份")
    dff = wide[(wide["company"] == company) & (wide["year"] == year)]
    if dff.empty: return create_base_figure(f"无 {company} 在 {year} 的数据")
    fig = create_base_figure(f"{company} ({year}) 风险雷达图")
    values = dff[CATS].iloc[0].values
    radar_color = PRECISE_PALETTE[2]; radar_fill_color = 'rgba(71, 159, 182, 0.4)'
    fig.add_trace(go.Scatterpolar(r=values, theta=CATS, fill='toself', line_color=radar_color, fillcolor=radar_fill_color))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, gridcolor=chart_colors['grid'], tickfont=dict(color=chart_colors['text_highlight'], size=12)), angularaxis=dict(gridcolor=chart_colors['grid'])), showlegend=False)
    return fig

@app.callback(Output("bars", "figure"), [Input("companies-compare", "value"), Input("dimension-compare", "value"), Input("year", "value")])
def update_bars(companies, dimension, year):
    if not companies or not dimension or not year or wide.empty: return create_base_figure("请选择对比项")
    fig = create_base_figure(f"公司对比 - {dimension} ({year})")
    dff = wide[(wide["year"] == year) & (wide["company"].isin(companies))].sort_values(dimension, ascending=False)
    if dff.empty: return fig
    bar_colors = [color for _, color in zip(range(len(dff)), cycle(PRECISE_PALETTE))]
    fig.add_trace(go.Bar(x=dff["company"], y=dff[dimension], marker_color=bar_colors))
    fig.update_layout(xaxis_gridcolor=chart_colors['grid'], yaxis_gridcolor=chart_colors['grid'])
    return fig

@app.callback(Output("heatmap", "figure"), Input("year", "value"))
def update_heatmap(year):
    if not year or wide.empty: return create_base_figure("请选择年份")
    fig = create_base_figure(f"风险维度热力图 ({year}年)")
    try:
        dfy = wide[wide["year"] == year].copy()
        if dfy.empty:
            fig.update_layout(title_text=f"在 {year} 年无任何公司数据")
            return fig
        dfy_sorted = dfy.sort_values('综合', ascending=True)
        df_heatmap = dfy_sorted[CATS + ['company']].set_index('company').T
        fig.add_trace(go.Heatmap(z=df_heatmap.values, x=df_heatmap.columns, y=df_heatmap.index, colorscale=precise_heatmap_scale, colorbar=dict(title=dict(text='风险值'), tickfont=dict(color=chart_colors['text']), lenmode='fraction', len=0.75, yanchor='middle', y=0.5)))
        fig.update_xaxes(showticklabels=False, ticks="")
        return fig
    except Exception:
        traceback.print_exc()
        fig.update_layout(title_text=f"生成热力图时发生未知错误，请查看后台日志")
        return fig

# ===== 5) 启动入口 =====
if __name__ == '__main__':
    app.run(host="127.0.0.1", port=8050, debug=True)
