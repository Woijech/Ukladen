import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def deployment(tmp_path):
    project = tmp_path / "project"
    (project / "infra").mkdir(parents=True)
    shutil.copy(ROOT / "infra/ai-home.sh", project / "infra/ai-home.sh")
    binary = tmp_path / "bin"
    binary.mkdir()
    docker = binary / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$@" >> "$AI_TEST_ARGUMENTS"\n'
        'if [[ " $* " == *" exec "* ]]; then\n'
        '  if [[ "${AI_TEST_DUMP_FAILURE:-}" == 1 ]]; then exit 1; fi\n'
        '  printf "synthetic dump"\n'
        "fi\n"
    )
    docker.chmod(0o755)
    arguments = tmp_path / "arguments"
    environment = os.environ | {
        "PATH": f"{binary}:{os.environ['PATH']}",
        "AI_CONSUMER_UID": "1200",
        "AI_CONSUMER_GID": "1200",
        "AI_TEST_ARGUMENTS": str(arguments),
    }

    def run(*args, **env):
        return subprocess.run(
            ["bash", str(project / "infra/ai-home.sh"), *args],
            env=environment | env,
            capture_output=True,
            text=True,
        )

    return project, arguments, run


def test_home_ai_defaults_to_quiet_config_and_keeps_non_root_consumers(deployment):
    _, arguments, run = deployment
    assert run().returncode == 0
    values = arguments.read_text().splitlines()
    assert values[-2:] == ["config", "--quiet"]
    assert "docker-compose.ai-runtime.yml" in values
    assert values.count("--profile") == 2
    arguments.unlink()
    assert run(AI_CONSUMER_UID="0").returncode == 1
    assert not arguments.exists()


@pytest.mark.parametrize("failed", [False, True])
def test_backup_has_private_permissions_and_discards_failed_dump(deployment, failed):
    project, arguments, run = deployment
    result = run("backup", AI_TEST_DUMP_FAILURE="1" if failed else "0")
    assert result.returncode == int(failed)
    dumps = list((project / "backups").glob("*.dump"))
    assert len(dumps) == int(not failed)
    if not failed:
        assert dumps[0].read_text() == "synthetic dump"
        assert dumps[0].stat().st_mode & 0o777 == 0o600
    values = arguments.read_text()
    assert values.index("up\n") < values.index("exec\n")
    assert "--format=custom" in values
