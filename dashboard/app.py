"""Bullet 3 — Streamlit BI dashboard over the Snowflake marts.

Shows a total-spend KPI row, spend by merchant category (bar), spend over time
(line) and top merchants, all driven by a parameterized date-range + category
filter. Also embeds the Bullet 4 "Ask in plain English" Gemini NL->SQL box.

Run with:  streamlit run dashboard/app.py
"""
from __future__ import annotations

import os
import sys

import streamlit as st

# Make the sibling `ai` package importable however Streamlit is launched.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai.nl2sql import get_connection, question_to_sql, run_select  # noqa: E402

st.set_page_config(page_title="fin_dwh — Transactions BI", layout="wide")


@st.cache_resource
def get_conn():
    return get_connection()


@st.cache_data(ttl=600)
def run_query(sql: str):
    cur = get_conn().cursor()
    cur.execute(sql)
    df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    return df


def build_where(start, end, categories: list[str]) -> str:
    clauses = [
        f"f.transaction_ts >= '{start}'",
        f"f.transaction_ts < dateadd(day, 1, '{end}')",
    ]
    if categories:
        quoted = ", ".join("'" + c.replace("'", "''") + "'" for c in categories)
        clauses.append(f"m.merchant_category in ({quoted})")
    return " and ".join(clauses)


FROM_JOIN = "fact_transactions f join dim_merchant m on f.merchant_key = m.merchant_key"

# --- Filters -----------------------------------------------------------------
st.title("Financial Transactions — BI Dashboard")
st.caption("Snowflake star schema (fact_transactions + customer / merchant / account / date dims)")

bounds = run_query(
    "select min(transaction_ts)::date as min_d, max(transaction_ts)::date as max_d "
    "from fact_transactions"
)
min_date, max_date = bounds.loc[0, "min_d"], bounds.loc[0, "max_d"]
all_categories = run_query(
    "select distinct merchant_category from dim_merchant order by 1"
)["merchant_category"].tolist()

with st.sidebar:
    st.header("Filters")
    date_range = st.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    categories = st.multiselect("Merchant category", options=all_categories, default=[])

# st.date_input returns a single date until both ends are picked.
if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
else:
    start, end = min_date, max_date

where = build_where(start, end, categories)

# --- KPIs --------------------------------------------------------------------
kpis = run_query(
    f"select coalesce(sum(f.amount), 0) as total_spend, count(*) as txns, "
    f"coalesce(avg(f.amount), 0) as avg_txn, count(distinct f.customer_key) as customers "
    f"from {FROM_JOIN} where {where}"
)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total spend", f"${kpis.loc[0, 'total_spend']:,.0f}")
c2.metric("Transactions", f"{int(kpis.loc[0, 'txns']):,}")
c3.metric("Avg transaction", f"${kpis.loc[0, 'avg_txn']:,.2f}")
c4.metric("Distinct customers", f"{int(kpis.loc[0, 'customers']):,}")

# --- Charts ------------------------------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("Spend by merchant category")
    by_cat = run_query(
        f"select m.merchant_category as category, sum(f.amount) as spend "
        f"from {FROM_JOIN} where {where} group by 1 order by spend desc"
    )
    if not by_cat.empty:
        st.bar_chart(by_cat.set_index("category")["spend"])
    else:
        st.info("No data for the selected filters.")

with right:
    st.subheader("Spend over time (monthly)")
    over_time = run_query(
        f"select date_trunc('month', f.transaction_ts) as month, sum(f.amount) as spend "
        f"from {FROM_JOIN} where {where} group by 1 order by 1"
    )
    if not over_time.empty:
        st.line_chart(over_time.set_index("month")["spend"])
    else:
        st.info("No data for the selected filters.")

st.subheader("Top merchants")
top_merchants = run_query(
    f"select m.merchant_name_clean as merchant, sum(f.amount) as spend, count(*) as txns "
    f"from {FROM_JOIN} where {where} group by 1 order by spend desc limit 10"
)
st.dataframe(top_merchants, use_container_width=True, hide_index=True)

# --- Bullet 4: Ask in plain English -----------------------------------------
st.divider()
st.subheader("Ask in plain English")
st.caption("Gemini (Claude fallback) turns your question into a read-only SQL query over the marts.")

question = st.text_input(
    "Question",
    placeholder="e.g. Which 5 states have the highest total spend?",
)
if st.button("Ask") and question:
    with st.spinner("Asking Gemini..."):
        try:
            sql = question_to_sql(question)
            st.code(sql, language="sql")
            result = run_select(sql, conn=get_conn())
            st.dataframe(result, use_container_width=True, hide_index=True)
        except ValueError as exc:
            st.error(f"Query rejected by the safety guard: {exc}")
        except Exception as exc:  # surface Snowflake/Gemini errors to the user
            st.error(f"Something went wrong: {exc}")
