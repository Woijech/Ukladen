# ADR 0001: Use SeaweedFS for Local Object Storage

Date: 2026-10-01
Status: accepted by the repository owner.

## Context

The foundation originally used MinIO as required by the architecture. MinIO's
[community repository](https://github.com/minio/minio) is archived and no longer
maintained. Upstream container pulls failed, requiring a local source build.
The repository owner explicitly approved replacing MinIO with SeaweedFS.

## Decision

Use the upstream `chrislusf/seaweedfs:4.48` image in single-process `weed mini` mode
for local development. Retain the S3-compatible storage boundary and `S3_*`
application settings. PostgreSQL continues to hold metadata only; application
upload and download functionality is not implemented by this change.

Configure S3 credentials and the initial bucket through environment variables.
Use the S3 gateway's `/readyz` probe instead of the MinIO-specific readiness URL.
Disable the unused WebDAV, Iceberg and Lance endpoints. Run as the image's non-root
`seaweed` user. Publish only S3 and the password-protected Admin UI on localhost.
No Python or JavaScript dependency is added.

The primary architecture and agent rules are updated to reflect this decision.
The backend remains a modular monolith.

## Consequences

The MinIO source-build Dockerfile and separate bucket initializer are removed.
SeaweedFS manages its own local data and bucket initialization in a named volume.
It has internal master, volume, filer and S3 components; `mini` runs them together
rather than adding separately deployed processes to this foundation.

Existing MinIO volumes are retained and are not compatible with SeaweedFS's
on-disk format. This change does not migrate objects. Any existing user-uploaded
objects must be transferred through S3 clients before deleting the old volume.

Single-node local storage has no redundancy. Production storage, backups,
service-account permissions and high availability require a separate deployment
decision. No production provider is selected by this ADR.

References: [SeaweedFS 4.48](https://github.com/seaweedfs/seaweedfs/releases/tag/4.48),
[mini setup](https://github.com/seaweedfs/seaweedfs/wiki/Quick-Start-with-weed-mini),
[S3 health routes](https://github.com/seaweedfs/seaweedfs/blob/4.48/weed/s3api/s3api_server.go).
