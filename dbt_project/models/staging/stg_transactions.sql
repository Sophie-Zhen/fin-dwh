-- Staging: one row per transaction, cleaned, typed and renamed to snake_case
-- analytics names. This is the single source the marts build from.

with source as (
    select * from {{ source('raw', 'raw_transactions') }}
)

select
    trans_num                                          as transaction_id,
    to_timestamp_ntz(trans_date_trans_time)            as transaction_ts,
    cast(cc_num as string)                             as card_number,
    merchant                                           as merchant_name,
    category                                           as merchant_category,
    cast(amt as number(12, 2))                         as amount,
    cust_first                                         as first_name,
    cust_last                                          as last_name,
    gender,
    street,
    city,
    state,
    cast(zip as string)                                as postal_code,
    cast(lat as float)                                 as home_lat,
    cast(home_lon as float)                            as home_long,
    cast(city_pop as number)                           as city_population,
    job,
    to_date(dob)                                       as date_of_birth,
    cast(unix_time as number)                          as unix_time,
    cast(merch_lat as float)                           as merch_lat,
    cast(merch_long as float)                          as merch_long,
    cast(is_fraud as boolean)                          as is_fraud
from source
