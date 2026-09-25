# Recommendations domain

The recommendations domain keeps provider credentials in configuration, maps each
Media Manager user to a Plex or Tautulli identity, stores only the viewing fields
needed for recommendations, and validates every Ollama response against a strict
JSON schema.

## Configuration additions

The full configuration is owned by `RecommendationConfig`. These optional values
can be added without changing existing installations:

```toml
[recommendations]
refresh_lease_timeout_seconds = 3600

[recommendations.plex]
# Restrict signed webhooks to one Plex Media Server. Empty remains backwards
# compatible and accepts any server after webhook-secret validation.
server_uuid = ""
```

User mappings are authoritative configuration. In particular, an entry with
`enabled = false` disables and updates an older enabled database mapping:

```toml
[[recommendations.users]]
user_id = "00000000-0000-0000-0000-000000000000"
tautulli_user_id = "1"
plex_account_id = "1"
plex_username = "Plex user"
enabled = false
```

## Webhook authentication

The preferred secret transport is the `X-MediaManager-Webhook-Secret` header.
Plex webhook URLs that cannot add headers can continue to use `?secret=...`.
Authentication happens before the request body is consumed. JSON is read as a
bounded stream; multipart requests accept at most one field, one file, and one
configured-size part.

## Recommendation API fallback

Metadata resolution is title- and year-aware. A valid Ollama recommendation is
not discarded when no metadata result matches: the API still returns `name`,
`year`, `reason`, `genres`, `confidence`, and rank, while `external_id`,
`poster_path`, `overview`, and other provider fields remain `null`. Discover UIs
must render this fallback instead of dropping the card.

## Single-flight behavior

An in-process per-user lock gives manual refresh calls an immediate conflict
response. A conditional PostgreSQL lease in `recommendation_sync_state` provides
the same protection across API and Taskiq worker processes. Leases expire after
`refresh_lease_timeout_seconds` so a terminated worker cannot block refreshes
indefinitely.
