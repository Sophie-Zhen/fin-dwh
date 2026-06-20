-- Account dimension (the credit card / financial instrument). One row per card
-- number. Modelled separately from the customer following Kimball: the card is
-- the account, the person is the customer.

with stg as (
    select * from {{ ref('stg_transactions') }}
),

deduped as (
    select
        *,
        row_number() over (partition by card_number order by transaction_ts) as rn
    from stg
)

select
    {{ dbt_utils.generate_surrogate_key(['card_number']) }} as account_key,
    card_number,
    'XXXX-XXXX-XXXX-' || right(card_number, 4)              as card_masked,
    case left(card_number, 1)
        when '4' then 'Visa'
        when '5' then 'Mastercard'
        when '3' then 'American Express'
        when '6' then 'Discover'
        else 'Other'
    end                                                    as card_brand
from deduped
where rn = 1
