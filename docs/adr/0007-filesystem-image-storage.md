# ADR-0007: Images on the filesystem, metadata in the database

Status: Proposed
Date: 2026-10-06
Deciders: James Tack, Maria de los Angeles Agudelo

## Context

The node uploads only relevant images: tens to a few hundred per day, a few hundred kilobytes each. They need metadata, retention and links to detections. S3-compatible object storage is the usual answer, and MinIO was the usual self-hosted choice, but its community edition stopped shipping binaries and images in 2025 and its repository was archived in February 2026.

## Decision

Store image files on a Docker volume under `images/{node_id}/{yyyy}/{mm}/{dd}/{image_id}.jpg`, with metadata, hash and retention date in the `images` table. The API serves files and thumbnails. Backups use `rsync`.

## Alternatives considered

| Option | Why not |
|---|---|
| MinIO | No longer maintained as open source |
| SeaweedFS (Apache-2.0) or Garage (AGPL-3.0) | Good S3-compatible options, but an extra service for a volume a folder handles easily. First choices if we ever need S3 |
| Images inside PostgreSQL (`bytea`) | Bloats the database and its backups |

## Consequences

- Simple to run and inspect.
- Moving to object storage later only touches the storage module in the API, behind a small interface (`put`, `get`, `delete`, `url`).
