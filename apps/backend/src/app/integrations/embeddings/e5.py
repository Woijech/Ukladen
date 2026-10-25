from collections.abc import Sequence
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Literal

from app.integrations.embeddings.artifacts import FILES, MODEL, REVISION, verify
from app.modules.search.application.embeddings import (
    EmbeddingBusy,
    EmbeddingProfile,
    EmbeddingUnavailable,
    InvalidEmbeddingInput,
)

if TYPE_CHECKING:
    import onnxruntime as ort
    from tokenizers import Tokenizer


class E5EmbeddingProvider:
    profile = EmbeddingProfile("onnx-cpu", MODEL, REVISION, 384, 512, True)

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._lock = Lock()
        self._runtime: tuple[Tokenizer, ort.InferenceSession] | None = None

    def _load(self) -> tuple[Tokenizer, ort.InferenceSession]:
        if self._runtime is None:
            import onnxruntime as ort
            from tokenizers import Tokenizer

            ort.disable_telemetry_events()
            for remote, size, digest in FILES:
                verify(self.directory / Path(remote).name, size, digest)
            tokenizer = Tokenizer.from_file(str(self.directory / "tokenizer.json"))
            tokenizer.no_truncation()
            tokenizer.no_padding()
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            options.add_session_config_entry("session.intra_op.allow_spinning", "0")
            options.add_session_config_entry("session.inter_op.allow_spinning", "0")
            session = ort.InferenceSession(
                str(self.directory / "model.onnx"),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
            self._runtime = tokenizer, session
        return self._runtime

    def embed(
        self, texts: Sequence[str], *, purpose: Literal["query", "document"]
    ) -> list[tuple[float, ...]]:
        if (
            purpose not in ("query", "document")
            or not isinstance(texts, Sequence)
            or isinstance(texts, str | bytes)
            or not 1 <= len(texts) <= (1 if purpose == "query" else 4)
        ):
            raise InvalidEmbeddingInput("Expected one query or one to four documents.")
        for text in texts:
            try:
                valid = (
                    isinstance(text, str)
                    and bool(text.strip())
                    and "\x00" not in text
                    and len(text.encode("utf-8")) <= 16384
                )
            except UnicodeEncodeError:
                valid = False
            if not valid:
                raise InvalidEmbeddingInput("Expected nonempty text within 16 KiB UTF-8.")
        if not self._lock.acquire(blocking=False):
            raise EmbeddingBusy("Embedding instance is busy; no work was queued.")
        try:
            import numpy as np

            tokenizer, session = self._load()
            prefix = "query: " if purpose == "query" else "passage: "
            encoded = [tokenizer.encode(prefix + text) for text in texts]
            if any(len(item.ids) > self.profile.max_tokens for item in encoded):
                raise InvalidEmbeddingInput(
                    "Text exceeds 512 tokens including prefix and specials."
                )
            length = max(len(item.ids) for item in encoded)
            ids = np.asarray(
                [item.ids + [1] * (length - len(item.ids)) for item in encoded], dtype=np.int64
            )
            mask = np.asarray(
                [[1] * len(item.ids) + [0] * (length - len(item.ids)) for item in encoded],
                dtype=np.int64,
            )
            states = np.asarray(
                session.run(
                    ["last_hidden_state"],
                    {
                        "input_ids": ids,
                        "attention_mask": mask,
                        "token_type_ids": np.zeros_like(ids),
                    },
                )[0],
                dtype=np.float32,
            )
            if states.shape != (*ids.shape, self.profile.dimensions):
                raise ValueError("Invalid embedding shape.")
            pooled = (states * mask[..., None]).sum(axis=1) / mask.sum(axis=1, keepdims=True)
            norms = np.linalg.norm(pooled, axis=1, keepdims=True)
            if not np.isfinite(pooled).all() or not np.isfinite(norms).all() or (norms == 0).any():
                raise ValueError("Invalid embedding values.")
            vectors = (pooled / norms).astype(np.float32)
            return [tuple(float(value) for value in row) for row in vectors]
        except InvalidEmbeddingInput:
            raise
        except Exception:
            raise EmbeddingUnavailable("Local embedding runtime is unavailable.") from None
        finally:
            self._lock.release()
