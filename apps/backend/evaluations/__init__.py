"""Local evaluations; never import this test dependency into the application runtime."""

import os

# Configure privacy before DeepEval imports its settings or tracing modules.
os.environ.update(
    DEEPEVAL_TELEMETRY_OPT_OUT="1",
    DEEPEVAL_UPDATE_WARNING_OPT_IN="0",
    DEEPEVAL_DISABLE_DOTENV="1",
    DEEPEVAL_DISABLE_LEGACY_KEYFILE="1",
    CONFIDENT_API_KEY="",
)
