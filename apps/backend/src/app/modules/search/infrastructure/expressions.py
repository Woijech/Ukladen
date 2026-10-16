from sqlalchemy import Text, cast, func, literal, type_coerce
from sqlalchemy.dialects.postgresql import REGCONFIG, TSQUERY, TSVECTOR


def search_vector(title, body):
    return type_coerce(func.ukladen_search_vector(title, body), TSVECTOR)


def search_query(text: str):
    queries = [
        type_coerce(func.plainto_tsquery(cast(literal(config), REGCONFIG), text), TSQUERY)
        for config in ("pg_catalog.simple", "pg_catalog.russian", "pg_catalog.english")
    ]
    return queries[0].op("||")(queries[1]).op("||")(queries[2])


def search_snippet(body, query):
    return func.left(
        func.ts_headline(
            cast(literal("pg_catalog.russian"), REGCONFIG),
            type_coerce(body, Text),
            query,
            "StartSel=,StopSel=,MinWords=10,MaxWords=35,MaxFragments=1",
        ),
        600,
    )
