"""Bullet 1 — ETL: load a transactions CSV into the Snowflake RAW schema.

Reads a Sparkov-schema CSV (the synthetic one from generate_sample.py, or the
real Kaggle fraudTrain.csv / fraudTest.csv) and bulk-loads it into
FIN_DWH.RAW.RAW_TRANSACTIONS. Idempotent: the table is replaced on every run,
so re-running never duplicates rows. dbt then cleans and reshapes it.

Usage:
    python etl/load_raw.py                                  # loads data/transactions.csv
    python etl/load_raw.py --csv data/fraudTrain.csv        # the real Kaggle file
    python etl/load_raw.py --csv data/fraudTrain.csv --sample 50000   # random sample
"""
from __future__ import annotations

import argparse
import os

import pandas as pd
from dotenv import load_dotenv
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas

RAW_SCHEMA = "RAW"
RAW_TABLE = "RAW_TRANSACTIONS"

# Columns we deliberately read as strings (preserve precision / leading zeros,
# and let dbt do the date/timestamp parsing in the staging layer).
STRING_COLUMNS = {
    "cc_num": str,
    "zip": str,
    "trans_date_trans_time": str,
    "dob": str,
    "trans_num": str,
}


def get_connection():
    load_dotenv()
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "FIN_WH"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "FIN_DWH"),
    )


def read_csv(path: str, sample: int | None) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=STRING_COLUMNS)

    # The Kaggle file has an unnamed integer index as its first column; the
    # synthetic file names it trans_index. Normalise both to trans_index.
    if "Unnamed: 0" in df.columns:
        df = df.rename(columns={"Unnamed: 0": "trans_index"})
    if "trans_index" not in df.columns:
        df.insert(0, "trans_index", range(len(df)))

    if sample is not None and sample < len(df):
        df = df.sample(n=sample, random_state=42).reset_index(drop=True)

    # write_pandas quotes identifiers by their exact case; quote_identifiers=False
    # (below) uppercases them, so keep df columns lower_snake and let Snowflake
    # store them as UPPERCASE unquoted identifiers.
    df.columns = [c.lower() for c in df.columns]

    # Rename a few columns whose source names collide with SQL keywords, so the
    # RAW table needs no quoting downstream. (dbt's staging model expects these.)
    df = df.rename(columns={"first": "cust_first", "last": "cust_last", "long": "home_lon"})
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="data/transactions.csv")
    parser.add_argument("--sample", type=int, default=None,
                        help="Randomly sample N rows (useful for the large Kaggle file).")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        raise SystemExit(
            f"CSV not found: {args.csv}\n"
            "Run 'python etl/generate_sample.py' first, or pass --csv path/to/fraudTrain.csv"
        )

    df = read_csv(args.csv, args.sample)
    database = os.environ.get("SNOWFLAKE_DATABASE", "FIN_DWH")

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {database}")
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {database}.{RAW_SCHEMA}")

        # auto_create_table=True infers a sensible table from the dataframe;
        # overwrite=True replaces it, which is what makes this re-runnable.
        success, n_chunks, n_rows, _ = write_pandas(
            conn,
            df,
            table_name=RAW_TABLE,
            database=database,
            schema=RAW_SCHEMA,
            auto_create_table=True,
            overwrite=True,
            quote_identifiers=False,
        )
        if not success:
            raise SystemExit("write_pandas reported failure.")

        cur.execute(f"SELECT COUNT(*) FROM {database}.{RAW_SCHEMA}.{RAW_TABLE}")
        count = cur.fetchone()[0]
        print(f"Loaded {n_rows:,} rows into {database}.{RAW_SCHEMA}.{RAW_TABLE} "
              f"(table now holds {count:,} rows).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
