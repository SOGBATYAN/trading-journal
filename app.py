from __future__ import annotations

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(page_title="Торговый календарь", page_icon="📈", layout="wide")


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
    .block-container { max-width: 1500px; padding-top: 1.4rem; padding-bottom: 3rem; }
    [data-testid="stFileUploader"] { border: 1px solid #262d3f; border-radius: 14px; padding: .45rem .8rem; background: #101524; }
    div[data-testid="stButton"] > button { border-radius: 9px; font-weight: 750; min-height: 38px; }
    div[data-testid="stButton"] > button[kind="primary"] { background: #1e9f62; border-color: #58dc95; color: white; }
    div[data-testid="stDateInput"] input { color: #f3f5f8; }
    .site-section-gap { height: 12px; }
    .site-month-title { color:#f3f5f8; font: 780 clamp(20px,2vw,28px) Inter,system-ui,sans-serif; text-align:center; padding-top:5px; }
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
    st.markdown("## ✦ Dashboard")
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
show_svg_html(core["APP_WIDGET_CSS"] + core["render_period_equity_chart"](trades, start_date, end_date), height=370)

st.markdown('<div class="site-section-gap"></div>', unsafe_allow_html=True)

# Календарь и все утверждённые месячные блоки.
months = sorted(trades["month"].dropna().unique().tolist())
if "month_index" not in st.session_state or st.session_state.month_index >= len(months):
    st.session_state.month_index = len(months) - 1

left, month_title, right, month_stats = st.columns([0.55, 2.5, 0.55, 5.4])
with left:
    if st.button("‹", disabled=st.session_state.month_index == 0, use_container_width=True):
        st.session_state.month_index -= 1
        st.rerun()
with month_title:
    st.markdown(f'<div class="site-month-title">{core["month_label"](months[st.session_state.month_index])}</div>', unsafe_allow_html=True)
with right:
    if st.button("›", disabled=st.session_state.month_index == len(months) - 1, use_container_width=True):
        st.session_state.month_index += 1
        st.rerun()
with month_stats:
    show_html(core["APP_WIDGET_CSS"] + core["app_stats_html"](daily, months[st.session_state.month_index]))

selected_month = months[st.session_state.month_index]
show_html(core["CALENDAR_CSS"] + '<div class="tc-scroll">' + core["render_calendar_grid"](daily, selected_month) + "</div>")
show_html(core["APP_WIDGET_CSS"] + core["render_dashboard"](trades, daily, selected_month))
show_svg_html(core["APP_WIDGET_CSS"] + core["render_month_charts"](daily, selected_month), height=390)
