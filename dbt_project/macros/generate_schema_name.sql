{#
  Use the model's custom +schema value as the literal schema name (uppercased),
  instead of dbt's default of <target_schema>_<custom_schema>. This gives us
  clean STAGING and MARTS schemas in Snowflake.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim | upper }}
    {%- endif -%}
{%- endmacro %}
