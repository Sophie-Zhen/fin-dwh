-- Date dimension built as a contiguous calendar spine covering the data range
-- (2019-2021). date_key is a YYYYMMDD integer the fact table joins on.

with spine as (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="to_date('2019-01-01')",
        end_date="to_date('2022-01-01')"
    ) }}
)

select
    cast(to_char(date_day, 'YYYYMMDD') as integer)        as date_key,
    cast(date_day as date)                                as full_date,
    year(date_day)                                        as year,
    quarter(date_day)                                     as quarter,
    month(date_day)                                       as month,
    monthname(date_day)                                   as month_name,
    day(date_day)                                         as day_of_month,
    dayofweekiso(date_day)                                as day_of_week,
    dayname(date_day)                                     as day_name,
    iff(dayofweekiso(date_day) in (6, 7), true, false)    as is_weekend
from spine
