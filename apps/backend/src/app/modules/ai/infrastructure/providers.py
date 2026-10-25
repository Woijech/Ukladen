from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from langchain_core.language_models import BaseChatModel

from app.integrations.llm.openrouter import openrouter_model
from app.modules.ai.application.connections import ConnectionAccess
from app.modules.ai.application.lifecycle import AiTransactions
from app.modules.ai.application.recovery import RUN_TIMEOUT
from app.modules.ai.domain.connections import ConnectionUnavailable
from app.modules.ai.domain.state import Run


class OpenRouterModels:
    def __init__(
        self, transactions: AiTransactions, access: ConnectionAccess, *, background: bool = False
    ) -> None:
        self.transactions, self.access, self.background = transactions, access, background

    def credential(self, run: Run) -> str:
        with self.transactions(run.user_id, write=True) as repository:
            current = repository.get_run(run.user_id, run.id)
            now = datetime.now(UTC)
            if (
                current is None
                or current.status != "running"
                or (not self.background and now >= current.created_at + RUN_TIMEOUT)
            ):
                raise ConnectionUnavailable("Model execution is no longer active.")
            _, key = self.access.check(repository, run.user_id, current, now)
            return key

    def backoff(self, run: Run, seconds: int) -> None:
        with self.transactions(run.user_id, write=True) as repository:
            scope = (
                f"personal:{run.connection_id}"
                if run.connection_id
                else self.access.configuration.quota_scope(run.offering_id or "")
            )
            repository.block_connection(scope, datetime.now(UTC) + timedelta(seconds=seconds))

    @contextmanager
    def __call__(self, run: Run, *, before_dispatch=None) -> Iterator[BaseChatModel]:
        if run.offering_id is None:
            raise ConnectionUnavailable("No real model selected.")
        profile = self.access.configuration.offering(run.user_id, run.offering_id)

        def credential() -> str:
            if before_dispatch:
                before_dispatch()
            return self.credential(run)

        model, client = openrouter_model(
            profile, credential, lambda seconds: self.backoff(run, seconds)
        )
        with client:
            yield model
