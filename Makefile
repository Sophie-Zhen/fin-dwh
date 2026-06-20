# One-command entry points for each piece of the pipeline.
# dbt needs the Snowflake creds in the environment, so the dbt targets source
# .env into the shell first. The Python scripts read .env themselves via
# python-dotenv, so they don't need that.

SHELL := /bin/bash
.PHONY: help install gen-data load dbt-deps dbt-build dashboard nl2sql all

help:
	@echo "fin_dwh — make targets:"
	@echo "  make install     Install Python dependencies (run inside your conda/virtual env)"
	@echo "  make gen-data    Generate the synthetic Sparkov-schema CSV into data/"
	@echo "  make load        Load the CSV into the Snowflake RAW schema (Bullet 1)"
	@echo "  make dbt-build   Run dbt: staging + star-schema marts + tests (Bullet 2)"
	@echo "  make dashboard   Launch the Streamlit BI dashboard (Bullet 3)"
	@echo "  make nl2sql      Ask Gemini one example question over the marts (Bullet 4)"
	@echo "  make all         install + gen-data + load + dbt-build (then run 'make dashboard')"

install:
	pip install -r requirements.txt

gen-data:
	python etl/generate_sample.py

load:
	python etl/load_raw.py

dbt-deps:
	cd dbt_project && DBT_PROFILES_DIR=. dbt deps

dbt-build: dbt-deps
	set -a && source .env && set +a && cd dbt_project && DBT_PROFILES_DIR=. dbt build

dashboard:
	streamlit run dashboard/app.py

nl2sql:
	python ai/nl2sql.py "What are the top 5 merchant categories by total spend?"

all: install gen-data load dbt-build
	@echo "Done. Now run: make dashboard"
