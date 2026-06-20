-- One-time Snowflake bootstrap.
-- Run this in a Snowsight worksheet (role ACCOUNTADMIN) after creating your
-- free 30-day trial account. It creates the warehouse, database, and the three
-- schemas the pipeline writes to: RAW (Python ETL) -> STAGING (dbt) -> MARTS (dbt).

-- XSMALL warehouse, auto-suspends after 60s idle to conserve trial credits.
create warehouse if not exists FIN_WH
  warehouse_size = 'XSMALL'
  auto_suspend = 60
  auto_resume = true
  initially_suspended = true;

create database if not exists FIN_DWH;

create schema if not exists FIN_DWH.RAW;
create schema if not exists FIN_DWH.STAGING;
create schema if not exists FIN_DWH.MARTS;

-- The natural-language-to-SQL layer is read-only by validation in Python
-- (ai/nl2sql.py rejects anything that isn't a single SELECT). If you want
-- defence-in-depth at the database level too, you can create a read-only role
-- and point the AI layer at it instead of ACCOUNTADMIN. Example (optional):
--
--   create role if not exists FIN_READONLY;
--   grant usage on warehouse FIN_WH to role FIN_READONLY;
--   grant usage on database FIN_DWH to role FIN_READONLY;
--   grant usage on schema FIN_DWH.MARTS to role FIN_READONLY;
--   grant select on all tables in schema FIN_DWH.MARTS to role FIN_READONLY;
--   grant select on future tables in schema FIN_DWH.MARTS to role FIN_READONLY;
--   grant role FIN_READONLY to user <your_user>;
