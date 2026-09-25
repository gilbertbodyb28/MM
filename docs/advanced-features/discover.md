---
description: Browse and search TMDB from MediaManager's Seerr-inspired Discover page.
---

# Discover

The **Discover** item in the main navigation opens a catalog experience built
with MediaManager's existing Svelte and shadcn-svelte components. It uses the
configured TMDB metadata relay; no TMDB credentials are sent to the browser.

The enhanced source tree includes the matching relay endpoints. If the public
relay configured by default has not yet deployed those endpoints, run the
bundled relay locally:

```bash
TMDB_API_KEY=replace-with-your-tmdb-api-key \
  docker compose --profile discover-relay up -d --build
```

Then set `metadata.tmdb.tmdb_relay_url` to
`http://metadata-relay:8000/tmdb` in `config.toml`. The TMDB key stays in the
relay container and is never exposed to the browser.

The landing page contains:

- trending movies and TV;
- upcoming releases;
- popular movies and TV;
- top-rated titles;
- personal Ollama recommendations, when configured.

Every card shows whether the title is already in the MediaManager library.
Administrators can use **Add** to call the existing movie or TV endpoint, so
automatic downloading starts immediately when that feature is enabled. Other
users can browse the catalog and open titles that are already present.

## Search and filters

The search controls support movies, TV, or a combined view. The filter sheet
supports:

- release-year ranges;
- one or more genres;
- minimum and maximum TMDB rating;
- popular, upcoming, top-rated, and full-catalog categories;
- popularity, rating, newest, and oldest sorting;
- optional adult content.

Category browsing uses TMDB Discover whenever an advanced filter is active, so
year, genre, rating, sorting, and pagination are applied by TMDB across the
catalog rather than only to the currently visible page. Trending remains its
own curated feed; applying an advanced filter switches the UI explicitly to
the full catalog instead of silently changing the meaning of “trending”. Text
search uses TMDB's search endpoint; genre and rating filters are applied to
each returned search page because TMDB does not expose those filters on
text-search requests. The result count is therefore labelled per page.

## API

All endpoints require an active MediaManager user:

- `GET /api/v1/discover/trending`
- `GET /api/v1/discover/popular`
- `GET /api/v1/discover/upcoming`
- `GET /api/v1/discover/top-rated`
- `GET /api/v1/discover/genres`
- `GET /api/v1/discover`
- `GET /api/v1/discover/search`

The response includes the TMDB ID, media type, artwork, release information,
ratings, genres, and MediaManager's internal `id`/`added` state.
