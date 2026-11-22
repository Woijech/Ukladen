#!/usr/bin/env python3
"""Cold, checksummed PostgreSQL + SeaweedFS backups for the home Compose stack."""

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import signal
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = [str(ROOT / "infra/ai-home.sh")]
ARCHIVES = ("postgres.dump", "objects.tar.gz", "configuration.tar.gz")
WRITERS = {
    "api",
    "worker",
    "material-worker",
    "ai-document-worker",
    "embedding-worker",
    "beat",
}


def run(*args, output=None, source=None):
    return subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        stdin=source,
        stdout=output if output is not None else subprocess.PIPE,
    ).stdout


def compose(*args, **kwargs):
    return run(*COMPOSE, *args, **kwargs)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(directory):
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Select a regular backup directory")
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("format") != 1 or set(manifest.get("sha256", {})) != set(ARCHIVES):
        raise ValueError("Unsupported or incomplete backup manifest")
    for name in ARCHIVES:
        path = directory / name
        if (
            path.is_symlink()
            or not path.is_file()
            or digest(path) != manifest["sha256"][name]
        ):
            raise ValueError(f"Backup verification failed: {name}")
    for name in ARCHIVES[1:]:
        with tarfile.open(directory / name, "r:gz") as archive:
            for member in archive:
                path = Path(member.name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or not (member.isfile() or member.isdir())
                ):
                    raise ValueError(f"Unsafe archive entry in {name}")
    return manifest


def storage():
    identifier = compose("ps", "--all", "--quiet", "seaweedfs").decode().strip()
    if not identifier:
        raise ValueError("Create the SeaweedFS container before backup or restore")
    data = json.loads(run("docker", "inspect", identifier))[0]
    mounts = [
        m
        for m in data["Mounts"]
        if m["Destination"] == "/data" and m["Type"] == "volume"
    ]
    if len(mounts) != 1:
        raise ValueError("Expected one named SeaweedFS data volume")
    image = compose("images", "--quiet", "postgres").decode().strip().splitlines()[0]
    return mounts[0]["Name"], image


def volume_command(volume, image, *command, readonly=False, **kwargs):
    mount = f"type=volume,source={volume},target=/snapshot" + (
        ",readonly" if readonly else ""
    )
    return run(
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        "none",
        "--mount",
        mount,
        "--entrypoint",
        command[0],
        image,
        *command[1:],
        **kwargs,
    )


def suspended_services():
    running = set(
        compose("ps", "--services", "--status", "running").decode().splitlines()
    )
    # Stop ingress/beat before workers, so no new writes can race the two snapshots.
    stopped = [
        name
        for name in (
            "api",
            "beat",
            "worker",
            "material-worker",
            "ai-document-worker",
            "embedding-worker",
            "seaweedfs",
        )
        if name in running
    ]
    if stopped:
        compose("stop", "--timeout", "120", *stopped)
    return stopped


def resume(stopped):
    if stopped:
        compose("start", *stopped)


def backup(destination):
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError("Backup destination must not be a symlink")
    target = destination / datetime.now(timezone.utc).strftime(
        "workspace-%Y%m%dT%H%M%SZ"
    )
    if target.exists():
        raise ValueError("A backup with this timestamp already exists")
    volume, image = storage()
    temporary = Path(tempfile.mkdtemp(prefix=".incomplete-", dir=destination))
    stopped = []
    try:
        # Record running services first: a failed stop must still restart the originals.
        running = set(
            compose("ps", "--services", "--status", "running").decode().splitlines()
        )
        stopped = sorted(running & (WRITERS | {"seaweedfs"}))
        suspended_services()
        with (temporary / "postgres.dump").open("wb") as out:
            compose(
                "exec",
                "-T",
                "postgres",
                "sh",
                "-c",
                'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom',
                output=out,
            )
        with (temporary / "objects.tar.gz").open("wb") as out:
            volume_command(
                volume,
                image,
                "tar",
                "--numeric-owner",
                "-C",
                "/snapshot",
                "-czf",
                "-",
                ".",
                readonly=True,
                output=out,
            )
        with tarfile.open(
            temporary / "configuration.tar.gz", "w:gz", dereference=False
        ) as archive:
            for name in (".env.home", ".secrets/ai"):
                path = ROOT / name
                if path.exists():
                    archive.add(path, arcname=name)
        manifest = {
            "format": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "storage_image": image,
            "sha256": {name: digest(temporary / name) for name in ARCHIVES},
        }
        (temporary / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        verify(temporary)
        for path in temporary.iterdir():
            path.chmod(0o600)
        temporary.rename(target)
        print(f"Complete backup: {target}")
    finally:
        try:
            resume(stopped)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)


def restore(directory):
    verify(directory)
    running = set(
        compose("ps", "--services", "--status", "running").decode().splitlines()
    )
    if running & (WRITERS | {"seaweedfs"}):
        raise ValueError(
            "Stop application writers and SeaweedFS before restoring an empty target"
        )
    volume, image = storage()
    tables = (
        compose(
            "exec",
            "-T",
            "postgres",
            "sh",
            "-c",
            '''psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')"''',
        )
        .decode()
        .strip()
    )
    if tables != "0":
        raise ValueError("Restore refused: the target database is not empty")
    if volume_command(
        volume,
        image,
        "find",
        "/snapshot",
        "-mindepth",
        "1",
        "-print",
        "-quit",
        readonly=True,
    ).strip():
        raise ValueError("Restore refused: the target object volume is not empty")
    with (directory / "objects.tar.gz").open("rb") as source:
        volume_command(
            volume,
            image,
            "tar",
            "--numeric-owner",
            "-C",
            "/snapshot",
            "-xzf",
            "-",
            source=source,
        )
    with (directory / "postgres.dump").open("rb") as source:
        compose(
            "exec",
            "-T",
            "postgres",
            "sh",
            "-c",
            'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --single-transaction --exit-on-error',
            source=source,
        )
    print(
        "Restored database and objects. Configuration is archived separately; review it before starting services."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("backup", "verify", "restore"))
    parser.add_argument("directory", nargs="?", type=Path)
    parser.add_argument("--confirm-empty-target", action="store_true")
    args = parser.parse_args()

    def interrupted(signum, frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, interrupted)
    os.umask(0o077)
    os.chdir(ROOT)
    with (ROOT / ".local" / "backup.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "backup":
            backup(args.directory or ROOT / "backups")
        elif args.directory is None:
            parser.error("Select a backup directory")
        elif args.action == "verify":
            verify(args.directory)
            print("Backup checksums and archive paths verified")
        elif not args.confirm_empty_target:
            parser.error(
                "Restore requires --confirm-empty-target and a separate empty stack"
            )
        else:
            restore(args.directory)


if __name__ == "__main__":
    (ROOT / ".local").mkdir(exist_ok=True)
    main()
