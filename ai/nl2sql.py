"""Bullet 4 — natural-language-to-SQL over the marts.

Primary provider is Google Gemini; if that call fails (no key, API error, empty
result) it transparently falls back to Anthropic Claude. A plain-English
question goes in; the model returns a single Snowflake SELECT over the star
schema; we validate it is read-only, run it, and return a DataFrame.

Used two ways:
  * imported by the Streamlit dashboard (the "Ask in plain English" box)
  * as a CLI:  python ai/nl2sql.py "Which 5 states have the highest spend?"

Guardrails: the generated SQL must be a single statement that starts with
SELECT or WITH, and must contain no DDL/DML keywords. Anything else is rejected
before it ever reaches Snowflake.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import pandas as pd
from dotenv import load_dotenv
import snowflake.connector
from google import genai
from google.genai import types
import anthropic

# The marts schema, described for the model. Keep this in sync with dbt/models/marts.
SCHEMA_DESCRIPTION = """
Star schema in FIN_DWH.MARTS (Snowflake). Query is run with FIN_DWH as the
database and MARTS as the active schema, so reference tables by their bare name.

fact_transactions (one row per transaction)
    transaction_id   string   degenerate natural key
    date_key         integer  -> dim_date.date_key (YYYYMMDD)
    customer_key     string   -> dim_customer.customer_key
    account_key      string   -> dim_account.account_key
    merchant_key     string   -> dim_merchant.merchant_key
    transaction_ts   timestamp
    amount           number   transaction amount in dollars
    is_fraud         boolean
    merch_lat        float
    merch_long       float

dim_customer
    customer_key   string (PK)
    first_name, last_name, full_name, gender
    date_of_birth  date
    age            integer
    street, city, state, postal_code
    home_lat, home_long  float
    city_population integer
    job            string

dim_account
    account_key  string (PK)
    card_number  string
    card_masked  string   (e.g. XXXX-XXXX-XXXX-1234)
    card_brand   string   (Visa / Mastercard / American Express / Discover / Other)

dim_merchant
    merchant_key        string (PK)
    merchant_name       string   (raw, prefixed with "fraud_")
    merchant_category   string   (e.g. grocery_pos, travel, shopping_net)
    merchant_name_clean string   (display name without the prefix)

dim_date
    date_key      integer (PK, YYYYMMDD)
    full_date     date
    year, quarter, month  integer
    month_name, day_name  string
    day_of_month, day_of_week  integer
    is_weekend    boolean
""".strip()

SYSTEM_PROMPT = f"""You are a careful data analyst that writes Snowflake SQL.
Given a question, reply with ONE read-only SELECT query over the schema below.

Rules:
- Output ONLY the SQL. No explanation, no markdown code fences.
- Use a single SELECT statement (a leading WITH/CTE is allowed). Never write
  INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, MERGE or any other statement.
- Reference tables by their bare name (fact_transactions, dim_customer, ...).
- Spend means SUM(amount). Always alias aggregated columns clearly.
- Add a sensible LIMIT (e.g. 100) when the question implies a list of rows.

Schema:
{SCHEMA_DESCRIPTION}
"""

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|merge|grant|revoke|"
    r"call|copy|put|remove|use|comment|begin|commit|rollback)\b",
    re.IGNORECASE,
)


def get_connection():
    load_dotenv()
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "FIN_WH"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "FIN_DWH"),
        schema=os.environ.get("SNOWFLAKE_SCHEMA", "MARTS"),
    )


def question_to_sql(question: str) -> str:
    """Translate a question to a single Snowflake SELECT.

    Tries Gemini first, then falls back to Claude if Gemini errors out.
    """
    load_dotenv()
    try:
        return _gemini_sql(question)
    except Exception as gemini_error:
        print(f"Gemini failed ({gemini_error}); trying Claude fallback.", file=sys.stderr)
        try:
            return _claude_sql(question)
        except Exception as claude_error:
            raise RuntimeError(
                f"NL->SQL failed on both providers. "
                f"Gemini: {gemini_error} | Claude: {claude_error}"
            )


def _gemini_sql(question: str) -> str:
    """Primary provider: Google Gemini."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    client = genai.Client(api_key=api_key)
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")
    response = client.models.generate_content(
        model=model,
        contents=question,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0,
        ),
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned no SQL.")
    return _strip_fences(text)


def _claude_sql(question: str) -> str:
    """Fallback provider: Anthropic Claude."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}],
    )
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise RuntimeError("Claude returned no SQL.")
    return _strip_fences(text)


def _strip_fences(text: str) -> str:
    text = text.strip()
    # Remove ```sql ... ``` fencing if the model added it despite instructions.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def validate_sql(sql: str) -> str:
    """Raise ValueError unless `sql` is a single read-only SELECT statement."""
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise ValueError("Empty query.")
    if ";" in cleaned:
        raise ValueError("Only a single statement is allowed.")
    lowered = cleaned.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise ValueError("Query must start with SELECT or WITH.")
    if FORBIDDEN.search(cleaned):
        raise ValueError("Query contains a forbidden (non-read-only) keyword.")
    return cleaned


def run_select(sql: str, conn=None) -> pd.DataFrame:
    """Validate and run a SELECT, returning the result as a DataFrame.

    A LIMIT is enforced by wrapping the (validated) query in a subquery, so even
    an unbounded SELECT can't pull the whole warehouse into the dashboard.
    """
    safe_sql = validate_sql(sql)
    wrapped = safe_sql if re.search(r"\blimit\b", safe_sql, re.IGNORECASE) \
        else f"select * from (\n{safe_sql}\n) limit 1000"

    own_conn = conn is None
    conn = conn or get_connection()
    try:
        cur = conn.cursor()
        cur.execute(wrapped)
        return cur.fetch_pandas_all()
    finally:
        if own_conn:
            conn.close()


def answer(question: str) -> tuple[str, pd.DataFrame]:
    """Convenience: question -> (generated_sql, result_dataframe)."""
    sql = question_to_sql(question)
    return sql, run_select(sql)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", help="A plain-English question about the data.")
    args = parser.parse_args()

    try:
        sql = question_to_sql(args.question)
    except RuntimeError as exc:
        print(f"\nCould not generate SQL: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print("\n--- Generated SQL ---")
    print(sql)
    try:
        df = run_select(sql)
    except ValueError as exc:
        print(f"\nRejected by safety guard: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print("\n--- Result ---")
    print(df.to_string(index=False) if not df.empty else "(no rows)")


if __name__ == "__main__":
    main()
