from __future__ import annotations

import html
import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(page_title="Торговый календарь", page_icon="📈", layout="centered")


@st.cache_resource
def load_notebook_core() -> dict:
    """Загружает утверждённые расчёты и HTML-шаблоны из notebook."""
    notebook_path = Path(__file__).with_name("Trading_Calendar.ipynb")
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    source = "\n".join(
        cell.get("source", "") if isinstance(cell.get("source", ""), str) else "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
    )
    source = source.split("def period_dashboard_app", 1)[0]
    source = source.replace("from IPython.display import HTML, clear_output, display", "")
    namespace: dict = {}
    exec(compile(source, str(notebook_path), "exec"), namespace)
    return namespace


core = load_notebook_core()


def _chart_grid(low: float, high: float, width: float, height: float, left: float, right: float, top: float, bottom: float):
    plot_height = height - top - bottom

    def y_for_value(value):
        return top + (high - float(value)) / max(1e-9, high - low) * plot_height

    parts = []
    for index in range(5):
        tick = high - (high - low) * index / 4
        y = y_for_value(tick)
        parts.append(f'<line class="tc-chart-grid-line" x1="{left:.1f}" y1="{y:.1f}" x2="{width-right:.1f}" y2="{y:.1f}"/>')
        parts.append(f'<text class="tc-chart-axis-text" x="{left-8:.1f}" y="{y+3.5:.1f}" text-anchor="end">{html.escape(core["format_money"](tick))}</text>')
    return y_for_value, parts


def _data_date_labels(parts, values, x_for_value, plot_bottom: float, height: float, label_for_value, rotate_labels: bool = True) -> None:
    label_y = min(height - 9.0, plot_bottom + 15.0)
    for value in values:
        x = x_for_value(value)
        label = html.escape(label_for_value(value))
        parts.append(f'<line class="tc-chart-zero-line" x1="{x:.1f}" y1="{plot_bottom:.1f}" x2="{x:.1f}" y2="{plot_bottom+4:.1f}"/>')
        if rotate_labels:
            parts.append(f'<text class="tc-chart-axis-text tc-chart-x-label" x="{x:.1f}" y="{label_y:.1f}" text-anchor="end" transform="rotate(-55 {x:.1f} {label_y:.1f})">{label}</text>')
        else:
            parts.append(f'<text class="tc-chart-axis-text tc-chart-x-label" x="{x:.1f}" y="{label_y:.1f}" text-anchor="middle">{label}</text>')


def _month_chart_geometry(low: float, high: float, days_in_month: int, data_days):
    width, height = 560.0, 330.0
    left, right, top, bottom = 62.0, 22.0, 20.0, 70.0
    plot_width = width - left - right

    def x_for_day(day):
        return left + (float(day) - 1.0) / max(1.0, days_in_month - 1.0) * plot_width

    y_for_value, parts = _chart_grid(low, high, width, height, left, right, top, bottom)
    plot_bottom = height - bottom
    _data_date_labels(parts, sorted(set(data_days)), x_for_day, plot_bottom, height, lambda day: str(int(day)), rotate_labels=False)
    zero_y = y_for_value(0.0)
    parts.append(f'<line class="tc-chart-zero-line" x1="{left:.1f}" y1="{zero_y:.1f}" x2="{width-right:.1f}" y2="{zero_y:.1f}"/>')
    return width, height, plot_width, x_for_day, y_for_value, zero_y, parts


def _equity_curve_svg_all_dates(rows, days_in_month: int) -> str:
    cumulative = 0.0
    curve = [(1, 0.0)]
    for trade_date, pnl in rows:
        cumulative += pnl
        curve.append((trade_date.day, cumulative))
    low, high = core["_chart_bounds"]([value for _, value in curve])
    data_days = [trade_date.day for trade_date, _ in rows]
    width, height, _, x_for_day, y_for_value, zero_y, parts = _month_chart_geometry(low, high, days_in_month, data_days)
    points = [(x_for_day(day), y_for_value(value)) for day, value in curve]
    path = " ".join(("M" if index == 0 else "L") + f" {x:.1f} {y:.1f}" for index, (x, y) in enumerate(points))
    if len(points) > 1:
        area = path + f" L {points[-1][0]:.1f} {zero_y:.1f} L {points[0][0]:.1f} {zero_y:.1f} Z"
        parts.append(f'<path d="{area}" fill="#54c98a" fill-opacity="0.16"/>')
    parts.append(f'<path d="{path}" fill="none" stroke="#60dfa0" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/>')
    for x, y in points[1:]:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="#60dfa0" stroke="#162b2a" stroke-width="1.2"/>')
    return f'<svg class="tc-chart-svg" style="min-width:{width:.0f}px" viewBox="0 0 {width:.0f} {height:.0f}" role="img" aria-label="Кривая доходности">' + "".join(parts) + "</svg>"


def _daily_bars_svg_all_dates(rows, days_in_month: int) -> str:
    values = [pnl for _, pnl in rows]
    low, high = core["_chart_bounds"](values)
    data_days = [trade_date.day for trade_date, _ in rows]
    width, height, plot_width, x_for_day, y_for_value, zero_y, parts = _month_chart_geometry(low, high, days_in_month, data_days)
    bar_width = max(4.0, min(17.0, plot_width / max(1, days_in_month) * 0.72))
    for trade_date, pnl in rows:
        x = x_for_day(trade_date.day) - bar_width / 2
        value_y = y_for_value(pnl)
        y = min(value_y, zero_y)
        bar_height = max(1.5, abs(value_y - zero_y))
        color = "#68d99a" if pnl > 0 else "#ee6465" if pnl < 0 else "#7f899b"
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" rx="2.5" fill="{color}"/>')
    return f'<svg class="tc-chart-svg" style="min-width:{width:.0f}px" viewBox="0 0 {width:.0f} {height:.0f}" role="img" aria-label="Дневной P&amp;L">' + "".join(parts) + "</svg>"


def _period_equity_curve_svg_all_dates(trades: pd.DataFrame, start_date, end_date) -> str:
    selected = trades.loc[trades["trade_date"].between(start_date, end_date, inclusive="both")]
    daily_rows = list(selected.groupby("trade_date", sort=True)["trade_pnl"].sum().items()) if not selected.empty else []
    cumulative = 0.0
    curve = [(start_date, 0.0)]
    for trade_date, pnl in daily_rows:
        cumulative += float(pnl)
        curve.append((trade_date, cumulative))

    low, high = core["_chart_bounds"]([value for _, value in curve])
    total_days = max(1, (end_date - start_date).days)
    width = max(1120.0, 70.0 + 34.0 + total_days * 24.0)
    height = 330.0
    left, right, top, bottom = 70.0, 34.0, 20.0, 70.0
    plot_width = width - left - right

    def x_for_date(trade_date):
        return left + (trade_date - start_date).days / total_days * plot_width

    y_for_value, parts = _chart_grid(low, high, width, height, left, right, top, bottom)
    plot_bottom = height - bottom
    date_format = "%d.%m.%y" if start_date.year != end_date.year else "%d.%m"
    data_dates = [trade_date for trade_date, _ in daily_rows]
    _data_date_labels(parts, data_dates, x_for_date, plot_bottom, height, lambda trade_date: trade_date.strftime(date_format))

    zero_y = y_for_value(0.0)
    parts.append(f'<line class="tc-chart-zero-line" x1="{left:.1f}" y1="{zero_y:.1f}" x2="{width-right:.1f}" y2="{zero_y:.1f}"/>')
    points = [(x_for_date(trade_date), y_for_value(value)) for trade_date, value in curve]
    path = " ".join(("M" if index == 0 else "L") + f" {x:.1f} {y:.1f}" for index, (x, y) in enumerate(points))
    if len(points) > 1:
        area = path + f" L {points[-1][0]:.1f} {zero_y:.1f} L {points[0][0]:.1f} {zero_y:.1f} Z"
        parts.append(f'<path d="{area}" fill="#54c98a" fill-opacity="0.16"/>')
    parts.append(f'<path d="{path}" fill="none" stroke="#60dfa0" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/>')
    for x, y in points[1:]:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="#60dfa0" stroke="#162b2a" stroke-width="1.2"/>')
    return f'<svg class="tc-chart-svg tc-period-chart-svg" style="min-width:{width:.0f}px" viewBox="0 0 {width:.0f} {height:.0f}" role="img" aria-label="Кривая доходности выбранного периода">' + "".join(parts) + "</svg>"


core["_equity_curve_svg"] = _equity_curve_svg_all_dates
core["_daily_bars_svg"] = _daily_bars_svg_all_dates
core["_period_equity_curve_svg"] = _period_equity_curve_svg_all_dates


CHART_DISPLAY_CSS = """
<style>
.tc-chart-card {
  overflow-x: auto !important;
  scrollbar-color: #465269 #121829;
  scrollbar-width: thin;
}
.tc-chart-title {
  font-size: clamp(19px, 1.55vw, 24px) !important;
  line-height: 1.2 !important;
}
.tc-chart-subtitle {
  margin-top: 4px !important;
  font-size: clamp(11px, .95vw, 14px) !important;
  line-height: 1.25 !important;
}
.tc-chart-axis-text {
  fill: #b8c3d5 !important;
  font-size: 11px !important;
  opacity: 1 !important;
}
.tc-chart-x-label {
  font-size: 10px !important;
}
.tc-period-equity-card .tc-chart-svg {
  max-height: none !important;
}
</style>
"""


MONTH_STATS_ALIGN_CSS = """
<style>
.tc-app-stats {
  width: 100% !important;
  justify-content: flex-end !important;
}
</style>
"""


CALENDAR_COMPACT_CSS = """
<style>
.tc-calendar-layout {
  --tc-row-gap: clamp(2px, .4vw, 5px) !important;
  --tc-head-height: clamp(26px, 3.2vw, 42px) !important;
  --tc-day-height: clamp(54px, 6.8vw, 88px) !important;
}
.tc-week-card {
  padding: 7px 4px !important;
}
.tc-week-title { line-height: 1.15 !important; }
.tc-week-pnl,
.tc-week-badge { line-height: 1.1 !important; }
.tc-week-pnl,
.tc-week-badge {
  margin-top: 9px !important;
}
.tc-week-badge {
  padding: 2px 4px !important;
}
</style>
"""


def show_html(markup: str) -> None:
    st.html(markup)


def show_svg_html(markup: str, height: int) -> None:
    """Показывает SVG без очистки тегов со стороны st.html()."""
    document = '<style>html,body{margin:0;background:#090d17;overflow:hidden}</style>' + markup
    components.html(document, height=height, scrolling=False)


def load_uploaded_report(uploaded_file):
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as temporary:
        temporary.write(uploaded_file.getvalue())
        temporary_path = Path(temporary.name)
    return core["prepare_trades"](temporary_path)


def activate_period(period: str, first_date: date, last_date: date) -> None:
    days = {"7d": 7, "30d": 30, "90d": 90}.get(period)
    st.session_state.period = period
    st.session_state.start_date = first_date if days is None else max(first_date, last_date - timedelta(days=days - 1))
    st.session_state.end_date = last_date


def manual_dates_changed() -> None:
    st.session_state.period = "custom"


st.markdown(
    """
    <style>
    .stApp { background: #090d17; color: #f3f5f8; }
    [data-testid="stMainBlockContainer"],
    .stMainBlockContainer,
    .main .block-container {
      width: 100% !important;
      max-width: 1000px !important;
      margin-left: auto !important;
      margin-right: auto !important;
      padding-top: 1.4rem !important;
      padding-bottom: 3rem !important;
    }
    [data-testid="stFileUploader"] { border: 1px solid #262d3f; border-radius: 14px; padding: .45rem .8rem; background: #101524; }
    div[data-testid="stButton"] > button { border-radius: 9px; font-weight: 750; min-height: 38px; }
    div[data-testid="stButton"] > button[kind="primary"] { background: #1e9f62; border-color: #58dc95; color: white; }
    div[data-testid="stDateInput"] input { color: #f3f5f8; }
    .site-section-gap { height: 12px; }
    .site-month-title { color:#f3f5f8; font: 780 clamp(20px,2vw,28px) Inter,system-ui,sans-serif; text-align:center; padding:0; line-height:50px; white-space:nowrap; }
    .st-key-calendar_prev div[data-testid="stButton"] > button,
    .st-key-calendar_next div[data-testid="stButton"] > button {
      width:50px !important; min-width:50px !important; height:50px !important; min-height:50px !important;
      padding:0 !important; border:1px solid #285e50 !important; border-radius:11px !important;
      background:#101724 !important; color:#62dea0 !important; box-shadow:none !important;
      font-size:30px !important; font-weight:450 !important; line-height:1 !important;
      transition:background .16s ease,border-color .16s ease,color .16s ease !important;
    }
    .st-key-calendar_next { transform: translateX(-14px); }
    .st-key-calendar_prev div[data-testid="stButton"] > button:hover,
    .st-key-calendar_next div[data-testid="stButton"] > button:hover {
      border-color:#65e5a5 !important; background:#1c3a35 !important; color:#f3f5f8 !important;
    }
    .st-key-calendar_prev div[data-testid="stButton"] > button:disabled,
    .st-key-calendar_next div[data-testid="stButton"] > button:disabled {
      border-color:#285e50 !important; background:#101724 !important; color:#62dea0 !important; opacity:.32 !important;
    }
    .site-dashboard-heading { display:flex; align-items:center; gap:10px; color:#f3f5f8; font:820 clamp(30px,2.4vw,42px) Inter,system-ui,sans-serif; line-height:1.2; letter-spacing:-.025em; padding:.15rem 0 .55rem; }
    .site-dashboard-sparkle { color:#69dda0; font-size:1.12em; line-height:1; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Торговый календарь")
uploaded = st.file_uploader("Загрузите Closed Trades Report.csv", type=["csv"])

if uploaded is None:
    st.info("Загрузите CSV-отчёт, чтобы открыть Dashboard и календарь.")
    st.stop()

try:
    trades, daily = load_uploaded_report(uploaded)
except Exception as error:
    st.error(f"Не удалось прочитать отчёт: {error}")
    st.stop()

first_date = min(trades["trade_date"])
last_date = max(trades["trade_date"])

if "period" not in st.session_state:
    st.session_state.period = "all"
    st.session_state.start_date = first_date
    st.session_state.end_date = last_date

st.session_state.start_date = max(first_date, min(st.session_state.start_date, last_date))
st.session_state.end_date = max(first_date, min(st.session_state.end_date, last_date))

# Верхний Dashboard и независимый выбор периода.
title_col, *button_cols = st.columns([5.4, 1, 1, 1, 1])
with title_col:
    st.markdown('<div class="site-dashboard-heading"><span class="site-dashboard-sparkle">✦</span>Dashboard</div>', unsafe_allow_html=True)
for column, key, label in zip(button_cols, ["7d", "30d", "90d", "all"], ["7D", "30D", "90D", "All"]):
    with column:
        st.button(
            label,
            key=f"period_{key}",
            type="primary" if st.session_state.period == key else "secondary",
            use_container_width=True,
            on_click=activate_period,
            args=(key, first_date, last_date),
        )

date_col_1, date_col_2, spacer = st.columns([1.2, 1.2, 5])
with date_col_1:
    st.date_input(
        "С",
        min_value=first_date,
        max_value=last_date,
        key="start_date",
        on_change=manual_dates_changed,
    )
with date_col_2:
    st.date_input(
        "По",
        min_value=first_date,
        max_value=last_date,
        key="end_date",
        on_change=manual_dates_changed,
    )

start_date = st.session_state.start_date
end_date = st.session_state.end_date
if start_date > end_date:
    st.error("Начальная дата должна быть раньше конечной.")
    st.stop()

show_html(core["APP_WIDGET_CSS"] + '<div class="tc-app-shell tc-period-shell">' + core["render_period_dashboard"](trades, start_date, end_date) + "</div>")
show_svg_html(core["APP_WIDGET_CSS"] + CHART_DISPLAY_CSS + core["render_period_equity_chart"](trades, start_date, end_date), height=450)

st.markdown('<div class="site-section-gap"></div>', unsafe_allow_html=True)

# Календарь и все утверждённые месячные блоки.
months = sorted(trades["month"].dropna().unique().tolist())
if "month_index" not in st.session_state or st.session_state.month_index >= len(months):
    st.session_state.month_index = len(months) - 1

left, month_title, right, month_stats = st.columns([0.62, 2.0, 0.7, 6.68], gap="medium", vertical_alignment="center")
with left:
    if st.button("‹", key="calendar_prev", disabled=st.session_state.month_index == 0, use_container_width=True):
        st.session_state.month_index -= 1
        st.rerun()
with month_title:
    st.markdown(f'<div class="site-month-title">{core["month_label"](months[st.session_state.month_index])}</div>', unsafe_allow_html=True)
with right:
    if st.button("›", key="calendar_next", disabled=st.session_state.month_index == len(months) - 1, use_container_width=True):
        st.session_state.month_index += 1
        st.rerun()
with month_stats:
    show_html(core["APP_WIDGET_CSS"] + MONTH_STATS_ALIGN_CSS + core["app_stats_html"](daily, months[st.session_state.month_index]))

selected_month = months[st.session_state.month_index]
show_html(core["CALENDAR_CSS"] + CALENDAR_COMPACT_CSS + '<div class="tc-scroll">' + core["render_calendar_grid"](daily, selected_month) + "</div>")
show_html(core["APP_WIDGET_CSS"] + core["render_dashboard"](trades, daily, selected_month))
show_svg_html(core["APP_WIDGET_CSS"] + CHART_DISPLAY_CSS + core["render_month_charts"](daily, selected_month), height=590)
