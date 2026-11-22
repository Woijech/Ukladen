"""Backup validation and an opt-in isolated Docker restore drill."""

import importlib.util
import io
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
import uuid
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "workspace_backup", Path(__file__).with_name("workspace-backup.py")
)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class ArchiveChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        (self.directory / "postgres.dump").write_bytes(b"synthetic dump")
        for name in backup.ARCHIVES[1:]:
            with tarfile.open(self.directory / name, "w:gz") as archive:
                item = tarfile.TarInfo("owned.txt")
                item.size = 5
                archive.addfile(item, io.BytesIO(b"hello"))
        self.manifest()

    def manifest(self):
        (self.directory / "manifest.json").write_text(
            json.dumps(
                {
                    "format": 1,
                    "sha256": {
                        name: backup.digest(self.directory / name)
                        for name in backup.ARCHIVES
                    },
                }
            )
        )

    def test_complete_archive_and_tampering(self):
        backup.verify(self.directory)
        (self.directory / "postgres.dump").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "verification failed"):
            backup.verify(self.directory)

    def test_traversal_and_links_are_rejected_even_with_matching_checksum(self):
        for name, kind in [("../outside", tarfile.REGTYPE), ("link", tarfile.SYMTYPE)]:
            with self.subTest(name=name):
                with tarfile.open(self.directory / "objects.tar.gz", "w:gz") as archive:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    member.linkname = "/outside"
                    archive.addfile(member)
                self.manifest()
                with self.assertRaisesRegex(ValueError, "Unsafe archive"):
                    backup.verify(self.directory)


@unittest.skipUnless(
    os.environ.get("DOCKER_BACKUP_TEST") == "1", "Explicit isolated Docker drill"
)
class DockerRestoreDrill(unittest.TestCase):
    def test_database_and_objects_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            compose_file = root / "compose.yml"
            compose_file.write_text("""services:
  postgres:
    image: pgvector/pgvector:pg18
    environment:
      POSTGRES_USER: fixture
      POSTGRES_PASSWORD: synthetic-test-password
      POSTGRES_DB: fixture
    healthcheck:
      test: [CMD-SHELL, "pg_isready -U fixture -d fixture"]
      interval: 1s
      retries: 30
    volumes: [database:/var/lib/postgresql]
  seaweedfs:
    image: pgvector/pgvector:pg18
    entrypoint: [sleep, infinity]
    volumes: [objects:/data]
volumes:
  database:
  objects:
""")
            original_root, original_compose = backup.ROOT, backup.COMPOSE
            backup.ROOT = root
            (root / ".env.home").write_text("SYNTHETIC_SECRET=fixture\n")
            projects = [
                f"ukladen-backup-test-{uuid.uuid4().hex[:10]}" for _ in range(2)
            ]
            try:

                def select(project):
                    backup.COMPOSE = [
                        "docker",
                        "compose",
                        "-p",
                        project,
                        "-f",
                        str(compose_file),
                    ]

                select(projects[0])
                backup.compose("up", "-d", "--wait")
                backup.compose(
                    "exec",
                    "-T",
                    "postgres",
                    "psql",
                    "-U",
                    "fixture",
                    "-d",
                    "fixture",
                    "-c",
                    "CREATE TABLE proof (value text); INSERT INTO proof VALUES ('restored');",
                )
                backup.compose(
                    "exec",
                    "-T",
                    "seaweedfs",
                    "sh",
                    "-c",
                    "echo synthetic-object > /data/proof.txt",
                )
                backup.backup(root / "backups")
                snapshot = next((root / "backups").glob("workspace-*"))
                self.assertTrue(backup.verify(snapshot))
                self.assertEqual((snapshot.stat().st_mode & 0o777), 0o700)
                # A fresh database and a never-started object container are the restore target.
                select(projects[1])
                backup.compose("up", "-d", "--wait", "postgres")
                backup.compose("create", "seaweedfs")
                backup.restore(snapshot)
                result = (
                    backup.compose(
                        "exec",
                        "-T",
                        "postgres",
                        "psql",
                        "-U",
                        "fixture",
                        "-d",
                        "fixture",
                        "-Atc",
                        "SELECT value FROM proof",
                    )
                    .decode()
                    .strip()
                )
                self.assertEqual(result, "restored")
                volume, image = backup.storage()
                self.assertEqual(
                    backup.volume_command(
                        volume, image, "cat", "/snapshot/proof.txt", readonly=True
                    ).strip(),
                    b"synthetic-object",
                )
                with self.assertRaisesRegex(ValueError, "not empty"):
                    backup.restore(snapshot)
            finally:
                for project in projects:
                    select(project)
                    subprocess.run(
                        [*backup.COMPOSE, "down", "--volumes"],
                        check=False,
                        stdout=subprocess.DEVNULL,
                    )
                backup.ROOT, backup.COMPOSE = original_root, original_compose


if __name__ == "__main__":
    unittest.main()
