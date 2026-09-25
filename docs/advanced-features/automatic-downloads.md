---
description: Configure automatic release searches and downloads with Prowlarr or Jackett and qBittorrent.
---

# Automatic Downloads

MediaManager can automatically search for a movie when it is added and keep an
opted-in TV show supplied with missing episodes. Searches use the existing
quality-scoring rules, submit the highest-ranked approved result to the active
download client, and keep a durable job record in PostgreSQL.

Adding media can allocate download bandwidth and disk space, so the Add routes
and manual automation controls require a MediaManager administrator.

## Prerequisites

Configure at least one indexer and one download client before enabling the
pipeline. Prowlarr is preferred when both Prowlarr and Jackett are available.

```toml title="config.toml"
[indexers.prowlarr]
enabled = true
url = "http://prowlarr:9696"
api_key = "replace-with-your-prowlarr-api-key"
timeout_seconds = 60
max_results = 1000

[torrents.qbittorrent]
enabled = true
host = "http://qbittorrent"
port = 8080
username = "admin"
password = "replace-with-your-qbittorrent-password"
category_name = "MediaManager"
category_save_path = "/data/torrents"

[misc]
torrent_directory = "/data/torrents"
```

!!! important
    `category_save_path` is interpreted by qBittorrent, while
    `torrent_directory` is interpreted by MediaManager. In Docker, both
    containers must mount the same host directory at `/data/torrents`.

Configure scoring rules before turning automation on. Results with a negative
score or without a matching active download client are rejected; remaining
results are ordered by detected quality, score, age or seeders, and size.

## Enable the pipeline

```toml title="config.toml"
[automation]
enabled = true
auto_download_movies = true
auto_download_shows = true
continuous_download_enabled = true
include_specials = false
process_batch_size = 5
max_releases_per_show_cycle = 50
max_attempts = 6
base_backoff_seconds = 300
max_backoff_seconds = 21600
exhausted_retry_seconds = 86400
lease_timeout_seconds = 1800
```

Restart MediaManager after changing `config.toml`. Database migrations run
automatically in the official container startup script.

## Runtime behavior

The scheduler runs an automation cycle every five minutes. Each cycle:

1. Adds unmanaged movies and opted-in shows to the durable queue.
2. Atomically claims and finishes one job at a time, up to
   `process_batch_size`, so multiple workers cannot process the same job and a
   queued batch cannot consume worker leases before processing starts.
3. Searches the configured indexers and applies the existing scoring rules.
4. Submits one movie release, or the smallest set of episode/season packs that
   covers the missing TV episodes.
5. Records the selected release and download-client torrent ID.

An automation job marked `succeeded` means that the download client accepted
the selected release. Download progress and final library import continue to
be tracked by MediaManager's existing torrent/import services.

Failed searches use exponential backoff. Exhausted jobs remain visible and can
be retried by an administrator. A worker lease allows another worker to recover
a job after an interrupted process.

For TV shows, enable **continuous download** when adding or editing the show.
The metadata refresh runs every six hours and creates newly released episode
records. Episodes with a known future air date are ignored until that date; the
next automation cycle then searches for any aired, unmanaged episodes.

## Administration API

Authenticated users can inspect jobs:

- `GET /api/v1/automation/jobs`
- `GET /api/v1/automation/jobs/{job_id}`

Administrators can manually queue or retry work:

- `POST /api/v1/automation/movies/{movie_id}`
- `POST /api/v1/automation/shows/{show_id}`
- `POST /api/v1/automation/jobs/{job_id}/retry`

Automation is disabled by default so an upgraded installation never starts a
download until its owner explicitly opts in.
