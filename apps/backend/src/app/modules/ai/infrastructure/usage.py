from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.modules.ai.application.usage import (
    UsageReport,
    daily_series,
    summarize,
    usage_groups,
    usage_window,
)
from app.modules.ai.domain.state import AiPersistenceUnavailable
from app.modules.users.application.profile import ProfileService
from app.modules.users.infrastructure.repository import SqlAlchemyProfileRepository


class SqlAlchemyUsageReader:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    def read(
        self,
        user_id: UUID,
        date_from: date | None = None,
        date_to: date | None = None,
        days: int = 7,
        limit: int = 20,
        offset: int = 0,
    ) -> UsageReport:
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=30)
        try:
            with self.sessions() as database, database.begin():
                database.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
                database.execute(text("SET LOCAL statement_timeout = '5s'"))
                profile = ProfileService(SqlAlchemyProfileRepository(database)).get(user_id)
                start_date, end_date, start, end = usage_window(
                    profile.timezone, date_from, date_to, days, now
                )
                params = {
                    "owner": user_id,
                    "tz": profile.timezone,
                    "start": start,
                    "end": end,
                    "cutoff": cutoff,
                    "limit": limit + 1,
                    "offset": offset,
                }
                runs = (
                    database.execute(
                        text("""
                    SELECT (created_at AT TIME ZONE :tz)::date AS day, provider, model,
                      CASE WHEN connection_id IS NULL THEN 'operator'
                        ELSE 'personal' END AS credential_source,
                      count(*) AS runs
                    FROM ai_runs
                    WHERE user_id = :owner AND created_at >= :start AND created_at < :end
                      AND (finished_at IS NULL OR finished_at > :cutoff)
                    GROUP BY day, provider, model, credential_source
                """),
                        params,
                    )
                    .mappings()
                    .all()
                )
                attempts = (
                    database.execute(
                        text("""
                    SELECT (a.started_at AT TIME ZONE :tz)::date AS day, r.provider, r.model,
                      CASE WHEN r.connection_id IS NULL THEN 'operator'
                        ELSE 'personal' END AS credential_source,
                      count(*) AS attempts,
                      sum(a.input_tokens) AS known_input_tokens,
                      sum(a.output_tokens) AS known_output_tokens,
                      count(*) FILTER (WHERE a.input_tokens IS NULL) AS unknown_input_attempts,
                      count(*) FILTER (WHERE a.output_tokens IS NULL) AS unknown_output_attempts,
                      count(*) FILTER (WHERE r.price IS NULL OR a.input_tokens IS NULL
                        OR a.output_tokens IS NULL) AS unpriced_attempts,
                      r.price->>'currency' AS currency,
                      sum(CASE WHEN a.input_tokens IS NOT NULL AND a.output_tokens IS NOT NULL
                        THEN (a.input_tokens * (r.price->>'input_per_million')::numeric
                          + a.output_tokens * (r.price->>'output_per_million')::numeric) / 1000000
                        ELSE NULL END) AS cost
                    FROM ai_provider_attempts a JOIN ai_runs r
                      ON r.id = a.run_id AND r.user_id = a.user_id
                    WHERE a.user_id = :owner AND a.started_at >= :start AND a.started_at < :end
                      AND coalesce(a.finished_at, a.started_at) > :cutoff
                    GROUP BY day, r.provider, r.model, credential_source, currency
                """),
                        params,
                    )
                    .mappings()
                    .all()
                )
                recent = (
                    database.execute(
                        text("""
                    SELECT id, conversation_id, provider, model, status, created_at,
                      CASE WHEN connection_id IS NULL THEN 'operator'
                        ELSE 'personal' END AS credential_source
                    FROM ai_runs
                    WHERE user_id = :owner AND created_at >= :start AND created_at < :end
                      AND (finished_at IS NULL OR finished_at > :cutoff)
                    ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset
                """),
                        params,
                    )
                    .mappings()
                    .all()
                )
                searches = (
                    database.execute(
                        text("""
                    SELECT (t.started_at AT TIME ZONE :tz)::date AS day, r.provider, r.model,
                      CASE WHEN r.connection_id IS NULL THEN 'operator'
                        ELSE 'personal' END AS credential_source,
                      count(*) AS unpriced_web_searches
                    FROM ai_tool_executions t JOIN ai_runs r
                      ON r.id = t.run_id AND r.user_id = t.user_id
                    WHERE t.user_id = :owner AND t.tool_name = 'search_web'
                      AND t.started_at >= :start AND t.started_at < :end
                      AND coalesce(t.finished_at, t.started_at) > :cutoff
                    GROUP BY day, r.provider, r.model, credential_source
                """),
                        params,
                    )
                    .mappings()
                    .all()
                )
                rows = [dict(row) for row in (*runs, *attempts, *searches)]
                return UsageReport(
                    timezone=profile.timezone,
                    date_from=start_date,
                    date_to=end_date,
                    summary=summarize([row for row in rows if row["provider"] != "fake"]),
                    fake=summarize([row for row in rows if row["provider"] == "fake"]),
                    daily=daily_series(rows, start_date, end_date),
                    models=usage_groups(rows, "model"),
                    recent_runs=[dict(row) for row in recent[:limit]],
                    limit=limit,
                    offset=offset,
                    has_more=len(recent) > limit,
                    retained_from=cutoff,
                    retention_partial=start < cutoff,
                )
        except SQLAlchemyError:
            raise AiPersistenceUnavailable("AI usage storage is unavailable.") from None
