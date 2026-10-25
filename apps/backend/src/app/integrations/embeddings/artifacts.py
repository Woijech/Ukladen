import argparse
import hashlib
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

MODEL = "intfloat/multilingual-e5-small"
REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
FILES = (
    (
        "tokenizer.json",
        17082730,
        "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39",
    ),
    (
        "onnx/model.onnx",
        470268510,
        "ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665",
    ),
)


def verify(path: Path, size: int, digest: str) -> None:
    if path.stat().st_size != size:
        raise ValueError("Embedding artifact size mismatch.")
    with path.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != digest:
            raise ValueError("Embedding artifact checksum mismatch.")


def download(directory: Path) -> None:
    """Explicit operator download only; inference never calls this function."""
    directory.mkdir(parents=True, exist_ok=True)
    for remote, size, digest in FILES:
        target = directory / Path(remote).name
        if target.exists():
            verify(target, size, digest)
            continue
        temporary: Path | None = None
        try:
            with (
                urlopen(
                    f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{remote}?download=true",
                    timeout=60,
                ) as response,
                NamedTemporaryFile(dir=directory, delete=False) as output,
            ):
                temporary = Path(output.name)
                count = 0
                while chunk := response.read(1024 * 1024):
                    count += len(chunk)
                    if count > size:
                        raise ValueError("Embedding artifact exceeds expected size.")
                    output.write(chunk)
            verify(temporary, size, digest)
            temporary.chmod(0o644)
            temporary.replace(target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download the pinned E5 CPU proof artifacts.")
    parser.add_argument("directory", type=Path)
    download(parser.parse_args().directory)
