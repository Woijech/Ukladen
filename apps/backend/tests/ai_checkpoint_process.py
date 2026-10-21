"""Fresh-process driver for the native owned-checkpoint tests; synthetic data only."""

import json
import os
import sys
from typing import cast
from unittest.mock import patch
from uuid import UUID

from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from psycopg import Connection
from psycopg.pq import TransactionStatus
from psycopg.rows import DictRow, dict_row

from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.application.agent import AgentInput, AgentReview, InvalidAgentReview
from app.modules.ai.domain.state import AiNotFound
from app.modules.ai.infrastructure.checkpoints import owned_offline_runner
from app.modules.ai.infrastructure.fake_tools import fake_reviewed_double


def main() -> None:
    request = json.load(sys.stdin)
    with Connection[DictRow].connect(
        os.environ["AI_CHECKPOINT_PROCESS_DSN"],
        options=f"-csearch_path={request['schema']}",
        autocommit=True,
        row_factory=dict_row,
        connect_timeout=3,
    ) as connection:
        tool = cast(StructuredTool, fake_reviewed_double)

        def fail(logger, event, error):
            raise error

        with (
            patch.object(tool, "func", wraps=tool.func) as operation,
            patch("app.modules.ai.infrastructure.agent.log_failure", side_effect=fail),
        ):
            try:
                runner = owned_offline_runner(
                    connection,
                    UUID(request["user_id"]),
                    UUID(request["conversation_id"]),
                    FakeChatModel(
                        responses=(
                            AIMessage(
                                content="",
                                tool_calls=[
                                    {
                                        "name": "fake_reviewed_double",
                                        "args": {"value": 7},
                                        "id": "native-call-1",
                                        "type": "tool_call",
                                    }
                                ],
                            ),
                            AIMessage(content="Finished"),
                        )
                    ),
                    [fake_reviewed_double],
                    review_tools=frozenset({"fake_reviewed_double"}),
                )
                conversation_id = UUID(request["conversation_id"])
                result = (
                    runner.run(AgentInput(conversation_id=conversation_id, message="Synthetic"))
                    if request["phase"] == "start"
                    else runner.resume(
                        conversation_id, AgentReview.model_validate(request["review"])
                    )
                )
                output = {"result": result.model_dump(mode="json")}
            except AiNotFound:
                output = {"denied": True}
            except InvalidAgentReview:
                output = {"stale": True}
            assert connection.info.transaction_status == TransactionStatus.IDLE
            print(json.dumps(output | {"tool_calls": operation.call_count}))


if __name__ == "__main__":
    main()
