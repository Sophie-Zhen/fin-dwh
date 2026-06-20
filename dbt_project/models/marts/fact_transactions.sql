-- Transaction fact (the centre of the star). Grain: one row per transaction.
-- Foreign keys are recomputed with the SAME surrogate-key logic as the
-- dimensions, so the relationships tests in _marts.yml hold.

with stg as (
    select * from {{ ref('stg_transactions') }}
)

select
    transaction_id,
    cast(to_char(transaction_ts, 'YYYYMMDD') as integer)  as date_key,
    {{ dbt_utils.generate_surrogate_key([
        'first_name', 'last_name', 'date_of_birth', 'street', 'city', 'state', 'postal_code'
    ]) }}                                                  as customer_key,
    {{ dbt_utils.generate_surrogate_key(['card_number']) }} as account_key,
    {{ dbt_utils.generate_surrogate_key(['merchant_name', 'merchant_category']) }} as merchant_key,
    transaction_ts,
    amount,
    is_fraud,
    merch_lat,
    merch_long
from stg
