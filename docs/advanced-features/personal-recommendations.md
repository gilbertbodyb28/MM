---
description: Generate private, personalized recommendations with Plex or Tautulli history and a local Ollama model.
---

# Personal AI Recommendations

MediaManager can ingest viewing history from Tautulli or Plex and ask a local
Ollama model for personalized movie and TV recommendations. Recommendations are
resolved through MediaManager's metadata provider before they appear in
Discover, so a recommendation can be added with the normal library workflow.

The feature is opt-in and disabled by default.

## 1. Start Ollama

The development Compose file includes an optional Ollama service:

```bash
docker compose -f docker-compose.dev.yaml --profile ai up -d ollama
docker compose -f docker-compose.dev.yaml exec ollama ollama pull llama3.2
```

An existing Ollama installation works as well. Its `/api/chat` endpoint must be
reachable from the MediaManager container.

## 2. Find the MediaManager user ID

Sign in as the target user and request `GET /api/v1/users/me`, or inspect that
request in the browser developer tools. Copy the returned UUID into the user
mapping below.

## 3. Configure one history provider

Tautulli is the recommended polling source because it provides normalized
history and statistics. Create an API key under **Settings → Web Interface** in
Tautulli and note the Tautulli user ID.

```toml title="config.toml"
[recommendations]
enabled = true
history_provider = "tautulli"
refresh_interval_minutes = 360
refresh_lease_timeout_seconds = 3600
history_page_size = 100
max_history_items_per_sync = 1000
prompt_history_items = 150
metadata_enrichment_limit = 25
recommendation_count = 20
minimum_history_items = 3
recommendation_ttl_hours = 168
generate_on_webhook = false
max_webhook_payload_bytes = 1000000

[[recommendations.users]]
user_id = "8f4e4b84-9d14-4cb8-91dc-17ecb6c9a4f1"
tautulli_user_id = "1"
plex_username = "media-user"
enabled = true

[recommendations.tautulli]
enabled = true
url = "http://tautulli:8181"
api_key = "replace-with-your-tautulli-api-key"
verify_ssl = true
request_timeout_seconds = 20

[recommendations.plex]
enabled = false
url = "http://plex:32400"
token = ""
verify_ssl = true
request_timeout_seconds = 20
webhook_enabled = false
webhook_secret = ""
server_uuid = ""

[recommendations.ollama]
enabled = true
url = "http://ollama:11434"
model = "llama3.2"
api_key = ""
verify_ssl = true
request_timeout_seconds = 120
keep_alive = "5m"
max_response_bytes = 1000000
```

To poll Plex directly instead, set `history_provider = "plex"`, enable the Plex
block, provide a Plex token, and add `plex_account_id` to each user mapping.
Set `server_uuid` to the Plex server's machine identifier when several servers
can send events to the same Media Manager instance. Leaving it empty preserves
the single-server setup.

Secrets can be supplied outside TOML with nested environment variables:

```bash
MEDIAMANAGER_RECOMMENDATIONS__TAUTULLI__API_KEY=your-key
MEDIAMANAGER_RECOMMENDATIONS__PLEX__TOKEN=your-token
MEDIAMANAGER_RECOMMENDATIONS__PLEX__WEBHOOK_SECRET=a-long-random-secret
```

## Plex webhooks

For near-real-time `media.scrobble` and `media.rate` events, enable webhooks and
set a strong random secret:

```toml title="config.toml"
[recommendations]
generate_on_webhook = true

[recommendations.plex]
webhook_enabled = true
webhook_secret = "replace-with-a-long-random-secret"
```

Configure Plex to send events to:

```text
https://media.example.com/api/v1/recommendations/webhook/plex?secret=replace-with-a-long-random-secret
```

The query parameter is the Plex-compatible fallback. If your webhook sender can
set headers, prefer `X-MediaManager-Webhook-Secret` and use the URL without a
query string. Use HTTPS and configure the reverse proxy not to retain query
strings in access logs. Payload size is capped before JSON parsing, secrets are
compared in constant time, and unsupported event types are ignored.

## Scheduling and privacy

The scheduler checks every 15 minutes and refreshes only mappings whose
configured interval has elapsed. Discover also provides a manual **Refresh**
button for a mapped user. A database-backed refresh lease prevents duplicate
Ollama work across multiple API or scheduler workers; an abandoned lease expires
after `refresh_lease_timeout_seconds`.

Stored history is deliberately minimized to title, media type, year, genres,
rating, watch time, completion, and a provider event ID. IP addresses, client
devices, session identifiers, and Plex/Tautulli credentials are never stored in
the history tables or sent to the browser. Ollama responses are validated
against a strict JSON schema before anything is persisted.

API endpoints:

- `GET /api/v1/recommendations`
- `GET /api/v1/recommendations/status`
- `POST /api/v1/recommendations/refresh`
- `POST /api/v1/recommendations/webhook/plex`
