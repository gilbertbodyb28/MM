---
description: Hourly background scan of every TV show that sends newly aired episodes to the download client.
---

# Episode Scanner

The episode scanner checks every TV show in the library for newly aired
episodes once an hour and sends each one it can find on the configured
indexers (Prowlarr or Jackett) to the configured download client
(qBittorrent, Transmission or SABnzbd). It runs inside the MediaManager
backend, so it keeps working when no browser has the page open.

Open **Avsnittsscanner** in the sidebar (`/dashboard/episode-scanner`) to see:

- when the last scan ran, how long it took and whether it had errors;
- when the next scheduled scan starts;
- every episode the last scan found, what it did with it and why;
- the episodes most recently sent for download, and a short run history;
- a **Scanna nu** button that starts a scan immediately;
- an **Automatisk scanning** switch that turns the hourly scan on or off.

The status page is visible to every user; only administrators can start a
scan or change the switch. Manual scans work while automatic scanning is off.

## What counts as a new episode

An episode is a candidate when it aired within the look-back window (the last
14 days by default) and its air date is known. Specials are ignored unless
`include_specials` is enabled. Older gaps are deliberately left to the
[continuous-download automation](automatic-downloads.md), so turning the
scanner on never bulk-downloads a show's back catalogue.

Every candidate is then checked in this order and skipped when:

1. it is already in the library;
2. it is already downloading or waiting to be imported;
3. the show is unmonitored, or its season is not monitored;
4. the automation queue already owns it (a queued or retrying episode job, or
   a show job that is running right now);
5. qBittorrent already holds a torrent for it that was added outside
   MediaManager.

Remaining episodes are searched with the existing quality-scoring rules. The
best release the configured client can accept is submitted through the same
code path as a manual episode download, which refuses episodes that became
managed in the meantime. Episodes without a release are searched again on the
next scan.

Shows that the metadata provider has just marked as ended still get their
most recent episodes, as long as their seasons are monitored, so a finale that
airs while the show is being marked as ended is not missed.

The episode list itself comes from the metadata refresh that already runs
every six hours (`POST /api/v1/tv/shows/{show_id}/metadata` refreshes one show
immediately).

## Errors

A failure never stops the scan. Problems are recorded per episode (a failed
indexer search or a rejected download) or per show (an unexpected error while
checking it), shown in red on the status page, and retried on the next scan.
Missing or unreachable indexers and download clients are reported once at the
top of the page. Messages are stored with URL queries, credentials and API
keys removed.

## Configuration

Automatic scanning is switched on and off from the page and stored in the
database. The scan itself can be tuned in `config.toml`:

```toml title="config.toml"
[episode_scanner]
interval_minutes = 60        # time between automatic scans (5–1440)
lookback_days = 14           # how recently an episode must have aired
include_specials = false     # also consider season 0
history_days = 30            # how long scan results are kept
lease_timeout_seconds = 600  # a silent running scan is treated as interrupted
```

Every option can also be set with an environment variable such as
`MEDIAMANAGER_EPISODE_SCANNER__INTERVAL_MINUTES=30`.

## How it is scheduled

A lightweight task checks every five minutes whether a scan is due (enabled
and at least one interval since the previous scan started) and, if so, queues
the scan itself. Only one scan can run at a time; a scan whose worker died is
marked as interrupted after `lease_timeout_seconds`. The check also runs at
startup, so a scan missed while MediaManager was stopped starts shortly after
it comes back.

## API

- `GET /api/v1/episode-scanner/status` – settings, latest run, next scan and results.
- `PUT /api/v1/episode-scanner/settings` – `{"enabled": true | false}` (administrators).
- `POST /api/v1/episode-scanner/scan` – start a scan now (administrators);
  returns `409` while a scan is running.
