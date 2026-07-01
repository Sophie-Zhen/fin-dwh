# Databricks notebook source
# MAGIC %md
# MAGIC # fin_dwh — PySpark ETL variant (Databricks)
# MAGIC
# MAGIC A **PySpark variant** of the Python ETL (`etl/load_raw.py` + the dbt staging model
# MAGIC `stg_transactions.sql`). It ingests the same Sparkov-schema transactions dataset and
# MAGIC produces the **same staged/curated columns** the core pipeline produces — just via
# MAGIC Spark instead of pandas + dbt. This demonstrates the "same pipeline, Databricks /
# MAGIC PySpark variant" path; the production path stays Snowflake + dbt.
# MAGIC
# MAGIC **Runs on free Databricks** (Free Edition / Community Edition — browser-based, works
# MAGIC on macOS). No cluster config needed beyond the default.
# MAGIC
# MAGIC ### How to get the data into Databricks
# MAGIC 1. Locally, generate the CSV: `python etl/generate_sample.py` (creates
# MAGIC    `data/transactions.csv`). Or use the real Kaggle `fraudTrain.csv`.
# MAGIC 2. In Databricks: **+ New → Add data → Upload** the CSV. It lands at
# MAGIC    `/FileStore/tables/transactions.csv` (the default `DATA_PATH` below).
# MAGIC 3. Run all cells.

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql import types as T

# Path to the uploaded CSV. Change if you uploaded under a different name.
DATA_PATH = "/FileStore/tables/transactions.csv"

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Read raw CSV
# MAGIC Read every column as a string (`inferSchema=False`) so `cc_num`, `zip` and the date
# MAGIC columns keep their exact text — the same precision-preserving choice the pandas
# MAGIC loader makes. Casting happens later, in the staging step.

# COMMAND ----------

raw = (
    spark.read
    .option("header", True)
    .option("inferSchema", False)
    .csv(DATA_PATH)
)

print(f"Raw rows: {raw.count():,}")
display(raw.limit(5))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Normalise raw columns
# MAGIC Mirrors `etl/load_raw.py::read_csv`:
# MAGIC - the Kaggle file's unnamed index column (Spark names it `_c0`) → `trans_index`;
# MAGIC - lowercase every column name;
# MAGIC - rename the three columns whose source names collide with SQL keywords
# MAGIC   (`first` / `last` / `long`) so nothing downstream needs quoting.

# COMMAND ----------

df = raw
if "_c0" in df.columns:
    df = df.withColumnRenamed("_c0", "trans_index")

# lowercase all column names
df = df.toDF(*[c.lower() for c in df.columns])

# the synthetic file already has trans_index; only add one if it's missing
if "trans_index" not in df.columns:
    df = df.withColumn("trans_index", F.monotonically_increasing_id())

df = (
    df.withColumnRenamed("first", "cust_first")
      .withColumnRenamed("last", "cust_last")
      .withColumnRenamed("long", "home_lon")
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Staging transform (cast + rename to analytics names)
# MAGIC One row per transaction, cleaned and typed. The output columns and types match
# MAGIC `dbt_project/models/staging/stg_transactions.sql` exactly, so this is genuinely the
# MAGIC same curated dataset the dbt path builds.

# COMMAND ----------

staged = df.select(
    F.col("trans_num").alias("transaction_id"),
    F.to_timestamp("trans_date_trans_time").alias("transaction_ts"),
    F.col("cc_num").cast("string").alias("card_number"),
    F.col("merchant").alias("merchant_name"),
    F.col("category").alias("merchant_category"),
    F.col("amt").cast(T.DecimalType(12, 2)).alias("amount"),
    F.col("cust_first").alias("first_name"),
    F.col("cust_last").alias("last_name"),
    F.col("gender"),
    F.col("street"),
    F.col("city"),
    F.col("state"),
    F.col("zip").cast("string").alias("postal_code"),
    F.col("lat").cast("double").alias("home_lat"),
    F.col("home_lon").cast("double").alias("home_long"),
    F.col("city_pop").cast("long").alias("city_population"),
    F.col("job"),
    F.to_date("dob").alias("date_of_birth"),
    F.col("unix_time").cast("long").alias("unix_time"),
    F.col("merch_lat").cast("double").alias("merch_lat"),
    F.col("merch_long").cast("double").alias("merch_long"),
    # is_fraud arrives as "0"/"1" text; Spark only parses "true"/"false" to boolean,
    # so go via int. (Snowflake's cast(is_fraud as boolean) handles the numeric directly.)
    (F.col("is_fraud").cast("int") == 1).alias("is_fraud"),
)

staged.printSchema()
print(f"Staged rows: {staged.count():,}")
display(staged.limit(10))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Write the curated table (Delta)
# MAGIC Persist the staged data as a managed Delta table — the PySpark equivalent of the
# MAGIC dbt staging model's output. Idempotent: `overwrite` replaces it on every run.

# COMMAND ----------

(
    staged.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable("stg_transactions_spark")
)

print("Wrote table: stg_transactions_spark")
display(spark.sql("select merchant_category, round(sum(amount), 2) as spend "
                  "from stg_transactions_spark group by 1 order by spend desc limit 10"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. (Optional) Land the same data in Snowflake via the Spark connector
# MAGIC Demonstrates the PySpark path writing **into the Snowflake warehouse** (the same
# MAGIC sink the Python ETL targets), using the Snowflake Spark connector that ships with the
# MAGIC Databricks runtime. Off by default — fill `sfOptions` and flip the flag to run it.
# MAGIC `sfURL` is `<your_account_identifier>.snowflakecomputing.com`.

# COMMAND ----------

WRITE_TO_SNOWFLAKE = False  # set True after filling sfOptions below

sfOptions = {
    "sfURL": "<account_identifier>.snowflakecomputing.com",
    "sfUser": "<user>",
    "sfPassword": "<password>",
    "sfDatabase": "FIN_DWH",
    "sfSchema": "STAGING",
    "sfWarehouse": "FIN_WH",
    "sfRole": "ACCOUNTADMIN",
}

if WRITE_TO_SNOWFLAKE:
    (
        staged.write
        .format("snowflake")
        .options(**sfOptions)
        .option("dbtable", "STG_TRANSACTIONS_SPARK")
        .mode("overwrite")
        .save()
    )
    print("Wrote FIN_DWH.STAGING.STG_TRANSACTIONS_SPARK in Snowflake.")
else:
    print("Snowflake write skipped (WRITE_TO_SNOWFLAKE = False).")
