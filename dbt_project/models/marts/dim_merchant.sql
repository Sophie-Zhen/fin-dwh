-- Merchant dimension. One row per (merchant, category) pair. The Sparkov data
-- prefixes every merchant name with "fraud_"; we keep the raw name and also
-- expose a cleaned version for display.

with stg as (
    select * from {{ ref('stg_transactions') }}
),

deduped as (
    select
        *,
        row_number() over (
            partition by merchant_name, merchant_category
            order by transaction_ts
        ) as rn
    from stg
)

select
    {{ dbt_utils.generate_surrogate_key(['merchant_name', 'merchant_category']) }} as merchant_key,
    merchant_name,
    merchant_category,
    replace(merchant_name, 'fraud_', '')                                          as merchant_name_clean
from deduped
where rn = 1
