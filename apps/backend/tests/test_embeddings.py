import hashlib
import io
import math
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.integrations.embeddings import artifacts
from app.integrations.embeddings.e5 import E5EmbeddingProvider
from app.modules.search.application.embeddings import (
    EmbeddingBusy,
    EmbeddingUnavailable,
    InvalidEmbeddingInput,
)


@pytest.mark.parametrize(
    "texts,purpose",
    [
        ([], "query"),
        (["x", "y"], "query"),
        (["x"] * 5, "document"),
        ("x", "query"),
        ([""], "query"),
        ([" \n"], "query"),
        (["a\x00b"], "query"),
        (["\ud800"], "query"),
        (["я" * 8193], "document"),
        (["x"], "unknown"),
    ],
)
def test_invalid_inputs_never_load_model(tmp_path: Path, texts, purpose) -> None:
    provider = E5EmbeddingProvider(tmp_path)
    with pytest.raises(InvalidEmbeddingInput):
        provider.embed(texts, purpose=purpose)
    assert provider._runtime is None


def test_lazy_import_does_not_load_optional_runtime_or_model() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; import sys; "
            "from app.integrations.embeddings.e5 import E5EmbeddingProvider; "
            "p=E5EmbeddingProvider(Path('/does-not-exist')); "
            "assert p._runtime is None; "
            "assert not {'numpy', 'onnxruntime', 'tokenizers'} & sys.modules.keys()",
        ],
        check=True,
    )


def test_unavailable_artifacts_are_sanitized_without_download(tmp_path: Path, monkeypatch) -> None:
    network = Mock(side_effect=AssertionError("Network must never be called"))
    monkeypatch.setattr(artifacts, "urlopen", network)
    provider = E5EmbeddingProvider(tmp_path / "private-path")
    with pytest.raises(EmbeddingUnavailable, match="^Local embedding runtime is unavailable.$"):
        provider.embed(["hello"], purpose="query")
    network.assert_not_called()
    assert provider._lock.acquire(blocking=False)
    provider._lock.release()


def test_busy_instance_rejects_without_queueing(tmp_path: Path) -> None:
    provider = E5EmbeddingProvider(tmp_path)
    with provider._lock, pytest.raises(EmbeddingBusy):
        provider.embed(["hello"], purpose="query")
    assert provider._runtime is None


def fake_runtime(provider, monkeypatch, *, output="valid"):
    np = pytest.importorskip("numpy")
    seen = []

    def encode(text):
        seen.append(text)
        return SimpleNamespace(ids=[2] * len(text.split()))

    def run(names, inputs):
        assert names == ["last_hidden_state"]
        ids, mask = inputs["input_ids"], inputs["attention_mask"]
        assert ids.dtype == np.int64 and mask.dtype == np.int64
        assert not inputs["token_type_ids"].any()
        result = np.ones((*ids.shape, 384), dtype=np.float32)
        result[:, :, 0] = 2
        result[mask == 0] = 10000
        if output == "nan":
            result[:] = np.nan
        if output == "zero":
            result[:] = 0
        if output == "shape":
            result = result[:, :, :3]
        return [result]

    session = Mock(run=Mock(side_effect=run))
    monkeypatch.setattr(provider, "_load", lambda: (SimpleNamespace(encode=encode), session))
    return seen, session


def test_prefix_mask_pooling_normalization_and_real_token_budget(tmp_path, monkeypatch) -> None:
    provider = E5EmbeddingProvider(tmp_path)
    seen, session = fake_runtime(provider, monkeypatch)
    vectors = provider.embed(["короткий текст", "longer English document text"], purpose="document")
    assert seen == ["passage: короткий текст", "passage: longer English document text"]
    assert len(vectors) == 2 and vectors[0] == vectors[1]
    assert all(
        len(row) == 384 and math.isclose(math.hypot(*row), 1, abs_tol=1e-6) for row in vectors
    )
    provider.embed(["find my lecture"], purpose="query")
    assert seen[-1] == "query: find my lecture"
    provider.embed(["word " * 511], purpose="query")
    calls = session.run.call_count
    with pytest.raises(InvalidEmbeddingInput, match="512 tokens"):
        provider.embed(["word " * 512], purpose="query")
    assert session.run.call_count == calls


@pytest.mark.parametrize("output", ["nan", "zero", "shape"])
def test_invalid_model_output_is_not_returned(tmp_path, monkeypatch, output) -> None:
    provider = E5EmbeddingProvider(tmp_path)
    fake_runtime(provider, monkeypatch, output=output)
    with pytest.raises(EmbeddingUnavailable):
        provider.embed(["hello"], purpose="query")


def test_download_checks_hash_and_never_publishes_partial_file(tmp_path, monkeypatch) -> None:
    data = b"synthetic artifact"
    digest = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(artifacts, "FILES", (("nested/model.onnx", len(data), digest),))
    request = Mock(return_value=io.BytesIO(data))
    monkeypatch.setattr(artifacts, "urlopen", request)
    artifacts.download(tmp_path)
    assert (tmp_path / "model.onnx").read_bytes() == data
    artifacts.download(tmp_path)
    assert request.call_count == 1
    (tmp_path / "model.onnx").unlink()
    request.return_value = io.BytesIO(b"corrupted")
    with pytest.raises(ValueError):
        artifacts.download(tmp_path)
    assert list(tmp_path.iterdir()) == []
