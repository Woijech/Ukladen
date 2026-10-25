"""Explicit local-only AI-06 retrieval check on a disposable synthetic index."""

import json
import os
import statistics
import sys
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from alembic import command
from app.integrations.embeddings.e5 import E5EmbeddingProvider
from app.modules.ai.application.source_queries import SearchRead
from app.modules.notes.domain.blocks import document_value, markdown_document
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.search.application.indexing import IndexingService
from app.modules.search.infrastructure.hybrid import HybridSearch
from app.modules.search.infrastructure.indexing import SqlAlchemyIndexStore
from app.modules.users.infrastructure.orm import UserModel

CASES = [
    (
        "database",
        "Нормализация баз данных. Functional dependencies, first, second and third normal forms. "
        "Устранение транзитивной зависимости и аномалий обновления.",
        [
            "Как устранить транзитивные зависимости в таблицах?",
            "How do normal forms prevent update anomalies?",
        ],
    ),
    (
        "network",
        "Компьютерные сети. TCP обеспечивает надёжную доставку, подтверждение и повторную "
        "передачу сегментов. UDP не гарантирует доставку. Network transport protocols.",
        [
            "Какой протокол повторяет потерянные сегменты?",
            "Which transport protocol guarantees reliable delivery?",
        ],
    ),
    (
        "calculus",
        "Математический анализ. Производная показывает скорость изменения функции. Интеграл "
        "вычисляет площадь под кривой. Calculus derivatives and definite integrals.",
        [
            "Как вычислить площадь под графиком функции?",
            "What measures the instantaneous rate of change of a function?",
        ],
    ),
    (
        "physics",
        "Физика электричества. Закон Ома связывает силу тока, напряжение и сопротивление: I=U/R. "
        "Ohm's law for electrical circuits.",
        [
            "Как связаны ток и сопротивление электрической цепи?",
            "How does voltage determine current through a resistor?",
        ],
    ),
    (
        "systems",
        "Операционные системы. Взаимная блокировка возникает при циклическом ожидании ресурсов. "
        "Deadlock prevention, locks, resource allocation and process scheduling.",
        [
            "Как предотвратить взаимную блокировку процессов?",
            "Why can processes wait forever for each other's locks?",
        ],
    ),
    (
        "biology",
        "Биология. Фотосинтез преобразует световую энергию в химическую. Хлоропласты, хлорофилл "
        "и фиксация углекислого газа. Photosynthesis in plants.",
        [
            "Как растения превращают солнечный свет в энергию?",
            "What do chloroplasts and chlorophyll do?",
        ],
    ),
]


def main(directory: Path) -> None:
    url = os.environ["AI_TEST_DATABASE_URL"]
    schema = f"ai06_quality_{uuid4().hex}"
    control = create_engine(url)
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        with control.begin() as database:
            database.execute(CreateSchema(schema))
        with engine.begin() as database:
            config = Config("alembic.ini")
            config.attributes["connection"] = database
            command.upgrade(config, "head")
        sessions = sessionmaker(engine, expire_on_commit=False)
        user = uuid4()
        identifiers = {name: uuid4() for name, _, _ in CASES}
        with sessions.begin() as database:
            database.add(UserModel(id=user, email="quality@example.com"))
            database.flush()
            for name, text, _ in CASES:
                # A source crosses multiple real-tokenizer windows.
                body = (text + "\n") * 30
                database.add(
                    PageModel(
                        id=identifiers[name],
                        user_id=user,
                        title=name,
                        document=document_value(markdown_document(body)),
                    )
                )
        index_provider, query_provider = (
            E5EmbeddingProvider(directory),
            E5EmbeddingProvider(directory),
        )
        store = SqlAlchemyIndexStore(sessions, index_provider.profile)
        store.register()
        start = perf_counter()
        for source_id in identifiers.values():
            IndexingService(store, index_provider, index_provider.count_tokens).process(
                user, "page", source_id
            )
        indexing_seconds = perf_counter() - start
        hybrid = HybridSearch(sessions, query_provider)
        results, timings = [], []
        for name, _, queries in CASES:
            for language, query in zip(("ru", "en"), queries, strict=True):
                start = perf_counter()
                evidence = hybrid.read(user, SearchRead(query=query, limit=8))
                timings.append(perf_counter() - start)
                ranked = list(dict.fromkeys(source.id for source in evidence.sources))
                rank = (
                    ranked.index(str(identifiers[name])) + 1
                    if str(identifiers[name]) in ranked
                    else None
                )
                results.append({"topic": name, "language": language, "rank": rank})
        hits = sum(row["rank"] is not None and row["rank"] <= 3 for row in results)
        print(
            json.dumps(
                {
                    "cases": results,
                    "top3": hits,
                    "total": len(results),
                    "indexing_seconds": round(indexing_seconds, 3),
                    "query_p50_seconds": round(statistics.median(timings), 3),
                    "query_max_seconds": round(max(timings), 3),
                },
                ensure_ascii=False,
            )
        )
        assert hits >= 11, "Synthetic bilingual top-3 retrieval gate failed."
    finally:
        engine.dispose()
        with control.begin() as database:
            database.execute(DropSchema(schema, cascade=True, if_exists=True))
        control.dispose()


if __name__ == "__main__":
    main(Path(sys.argv[1]))
