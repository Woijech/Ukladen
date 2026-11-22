# Local workspace backups

The home stack can create a consistent PostgreSQL + SeaweedFS snapshot in the ignored
`backups/` directory. Run as the non-root owner of `.env.home` and `.secrets/ai`,
with Docker access and Python 3.11 or later. No new Python packages are required.

```bash
python3 infra/workspace-backup.py backup
python3 infra/workspace-backup.py verify backups/workspace-YYYYMMDDTHHMMSSZ
```

The command temporarily stops running API/worker/scheduler services and SeaweedFS,
creates a custom-format database dump, archives the complete object volume and
`.env.home`/`.secrets/ai`, verifies SHA-256 checksums and archive paths, then restarts
exactly the services that were running. A signal or ordinary failure also attempts
to restart them. A host power failure can still require a manual service start.
PostgreSQL must already be running; the script does not start or migrate it.
Backup directories use mode 700 and files mode 600. Configuration archives contain
credentials. Keep them private. Local copies do not protect against losing this disk.
No automatic deletion/retention policy is applied.

Redis is transient and is not restored. Provider-side state, external IIS data and
embedding model weights are not included. Keep the corresponding source checkout
and download the configured embedding model again when recovering on another host.
After recovery, inspect interrupted jobs and reindex sources when necessary.

## Restore into a separate empty installation

Never point the restore command at the working installation. Use a separate checkout,
Compose project/host and fresh Docker volumes. Restore the matching `.env.home` and
AI configuration privately from `configuration.tar.gz` before starting application
services; do not print credentials in the terminal. `verify` rejects traversal paths,
links and mismatched checksums before any data restoration.

Create/start only PostgreSQL and create the unstarted object storage container:

```bash
bash infra/ai-home.sh up --detach --wait postgres
bash infra/ai-home.sh create seaweedfs
python3 infra/workspace-backup.py restore /absolute/path/to/backup --confirm-empty-target
```

The script refuses a running writer/object service, nonempty database or nonempty
object volume. It preserves object ownership and restores PostgreSQL in one
transaction. On a restore failure, discard only this disposable target's volumes
before retrying. It never erases a populated target. Start the same application
revision after restoration, then upgrade through normal migrations if needed.

## Optional daily timer

Use a user systemd service to run the backup command with `WorkingDirectory` set to
this checkout and an absolute `ExecStart=/usr/bin/python3 /path/to/Ukladen/infra/workspace-backup.py backup`.
Pair it with `OnCalendar=*-*-* 03:15:00`, `Persistent=true` and `WantedBy=timers.target`.
The machine must be awake and Docker available. Scheduling is opt-in; this change
does not install a timer or alter system configuration.

## Verification

```bash
python3 -m unittest discover -s infra -p test_workspace_backup.py -v
DOCKER_BACKUP_TEST=1 python3 -m unittest discover -s infra -p test_workspace_backup.py -v
```

The Docker drill uses two disposable projects with synthetic database rows and
object files, restores into the second project, checks both, and verifies that
another restore is refused. It does not use the working stack or its credentials.
