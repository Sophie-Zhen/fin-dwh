-- Customer dimension (the person who holds the card). One row per distinct
-- person, identified by name + date of birth + address. Surrogate key is a
-- hash of that natural key so the fact table can join to it deterministically.

with stg as (
    select * from {{ ref('stg_transactions') }}
),

deduped as (
    select
        *,
        row_number() over (
            partition by first_name, last_name, date_of_birth, street, city, state, postal_code
            order by transaction_ts
        ) as rn
    from stg
)

select
    {{ dbt_utils.generate_surrogate_key([
        'first_name', 'last_name', 'date_of_birth', 'street', 'city', 'state', 'postal_code'
    ]) }}                                                  as customer_key,
    first_name,
    last_name,
    first_name || ' ' || last_name                        as full_name,
    gender,
    date_of_birth,
    datediff('year', date_of_birth, current_date())       as age,
    street,
    city,
    state,
    postal_code,
    home_lat,
    home_long,
    city_population,
    job
from deduped
where rn = 1
