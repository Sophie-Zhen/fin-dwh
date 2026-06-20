# fin_dwh — Financial Transactions Data Warehouse & AI Query Layer

An end-to-end, junior-level data project: a Python ETL pipeline loads a public
credit-card-transactions dataset into a **Snowflake** data warehouse, **dbt**
builds a Kimball star schema with data-quality tests, a **Streamlit** dashboard
surfaces the metrics, and a **Google Gemini** natural-language-to-SQL layer
(with **Claude** as an automatic fallback) lets non-technical users query the
warehouse in plain English.

```
 CSV (Sparkov schema)
      │   etl/load_raw.py  (Python, snowflake-connector)
      ▼
 ┌─────────────┐     ┌──────────────────┐     ┌──────────────────────────────┐
 │  RAW        │ dbt │  STAGING         │ dbt │  MARTS  (star schema)        │
 │ raw_        │ ──▶ │  stg_            │ ──▶ │  fact_transactions           │
 │ transactions│     │  transactions    │     │  dim_customer / dim_merchant │
 └─────────────┘     └──────────────────┘     │  dim_account  / dim_date     │
   Snowflake            (views)                └──────────────┬───────────────┘
                                                              │
                          ┌───────────────────────────────────┴───────────┐
                          ▼                                                ▼
                 dashboard/app.py                                   ai/nl2sql.py
                 Streamlit BI (KPIs,                   English question ─▶ Gemini (Claude fallback)
                 charts, filters)                             ─▶ validated SELECT ─▶ result
```

## Dataset

The pipeline expects the public **"Credit Card Transactions" (Sparkov / Kaggle
`kartik2112/fraud-detection`)** schema — per transaction: timestamp, `cc_num`,
merchant, category, amount, customer name/gender/address/job/dob, and lat/long.

Because the Kaggle download needs a Kaggle account, this repo also ships
`etl/generate_sample.py`, which produces a **synthetic dataset in the exact same
schema**. That makes the project runnable end-to-end with zero external
downloads — ideal for a demo. To use the real public data instead, download
`fraudTrain.csv` from Kaggle into `data/` and point the loader at it:

```bash
python etl/load_raw.py --csv data/fraudTrain.csv --sample 50000
```

Everything downstream (dbt, dashboard, AI layer) is identical either way.

## Prerequisites

- Python 3.11 (a conda env is recommended: `conda create -n fin_dwh python=3.11`)
- A free Snowflake 30-day trial account
- A Google Gemini API key (free tier at https://aistudio.google.com/apikey)
- Optionally, an Anthropic API key (used automatically as a fallback if Gemini fails)

## Setup

1. **Install dependencies** (inside your env):
   ```bash
   make install          # or: pip install -r requirements.txt
   ```

2. **Create your Snowflake objects.** Sign up for the trial, open a Snowsight
   worksheet as `ACCOUNTADMIN`, and run [`snowflake/setup.sql`](snowflake/setup.sql).
   It creates the `FIN_WH` (XSMALL) warehouse, the `FIN_DWH` database, and the
   `RAW` / `STAGING` / `MARTS` schemas.

3. **Configure secrets.** Copy the template and fill in real values:
   ```bash
   cp .env.example .env
   ```
   `.env` is gitignored — only `.env.example` (placeholders) is committed.

## Run it (the demo path)

```bash
make gen-data     # 1. create data/transactions.csv (synthetic, Sparkov schema)
make load         # 2. load it into FIN_DWH.RAW.RAW_TRANSACTIONS
make dbt-build    # 3. build staging + star-schema marts and run all dbt tests
make dashboard    # 4. open the Streamlit dashboard
make nl2sql       # 5. ask Gemini one example question from the CLI
```

`make load` prints the row count it loaded. `make dbt-build` ends with `PASS`
for every model and test. The dashboard opens at http://localhost:8501.

## How each component works

- **ETL (`etl/`)** — `load_raw.py` reads the CSV with pandas (keeping `cc_num`,
  `zip`, and the date columns as strings to avoid precision loss), then bulk-loads
  it with `write_pandas` into `RAW.RAW_TRANSACTIONS`. It uses
  `overwrite=True`, so re-running it never duplicates rows (idempotent).

- **Dimensional model (`dbt_project/`)** — one staging view
  (`stg_transactions`) cleans, casts and renames the raw columns. The marts then
  build a **star schema**: a `fact_transactions` fact joined to four dimensions
  (`dim_customer`, `dim_merchant`, `dim_account`, `dim_date`). Dimension
  surrogate keys are hashes of their natural keys (`dbt_utils.generate_surrogate_key`),
  and the fact recomputes the same hashes so the joins line up. `dim_date` is a
  proper calendar spine (`dbt_utils.date_spine`). Data-quality tests live in the
  `_*.yml` files: `unique` + `not_null` on every dimension key, and
  `relationships` tests proving every fact foreign key resolves to its dimension.

- **BI dashboard (`dashboard/app.py`)** — Streamlit queries the marts and shows a
  total-spend KPI row, spend by merchant category (bar), spend over time (line),
  and a top-merchants table — all driven by a parameterized **date-range** and
  **merchant-category** filter in the sidebar.

- **AI NL→SQL (`ai/nl2sql.py`)** — the marts schema is given to the model in the
  system prompt; an English question comes back as a single `SELECT`. Gemini is
  the primary provider and Claude is an automatic fallback (if the Gemini call
  errors or returns nothing, it retries with Claude). A guard (`validate_sql`)
  rejects anything that isn't one read-only statement starting with `SELECT`/
  `WITH`, blocking all DDL/DML before it reaches Snowflake — regardless of which
  provider produced it. The same function powers the dashboard's "Ask in plain
  English" box.

## CV bullet → code checklist

| CV bullet | Where it lives | How to run / verify |
|---|---|---|
| **1.** End-to-end Python ETL ingesting a public transactions dataset into Snowflake (RAW → curated layers) | `etl/load_raw.py`, `etl/generate_sample.py` | `make gen-data && make load` — prints rows loaded into `FIN_DWH.RAW.RAW_TRANSACTIONS` |
| **2.** Star schema (transaction fact + customer/merchant/account/date dims) in dbt, with data-quality tests (Kimball) | `dbt_project/models/staging/*`, `dbt_project/models/marts/*`, `_*.yml` tests | `make dbt-build` — builds the marts and runs `unique`/`not_null`/`relationships` tests |
| **3.** Interactive Streamlit BI dashboard over Snowflake (spend, merchant-category, time-series, parameterized filters) | `dashboard/app.py` | `make dashboard` |
| **4.** LLM natural-language-to-SQL layer (Google Gemini, Claude fallback) for non-technical users | `ai/nl2sql.py` (+ the box in `dashboard/app.py`) | `make nl2sql`, or use the dashboard box. Try: "Top 5 merchant categories by spend", "Spend by card brand", "Which 5 states have the highest total spend?" |

## Example NL→SQL questions to demo

- *What are the top 5 merchant categories by total spend?*
- *Show total spend by card brand.*
- *Which 5 states have the highest average transaction amount?*
- *How many transactions happened on weekends vs weekdays?*

## Screenshots

Add these after your first run (they intentionally aren't committed empty):

- `docs/dashboard.png` — the dashboard with KPIs and charts
- `docs/nl2sql.png` — an English question, the generated SQL, and its result

## Notes on scope / choices

- **Dataset:** I used a synthetic generator that matches the Sparkov schema so
  the project runs offline, while keeping full support for the real Kaggle file.
- **Driver:** queries use `snowflake-connector-python` (with the `pandas` extra)
  for both loading and reading; I left `snowflake-sqlalchemy` out to keep the
  dependency set minimal, since the connector covers everything here.
- This is deliberately junior-scoped: no orchestrator, CI/CD, or cloud deploy.
