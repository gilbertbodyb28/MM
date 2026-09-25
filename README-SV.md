# MediaManager Enhanced – svensk startguide

Det här paketet är en komplett vidareutveckling av MediaManager med fyra integrerade områden:

- automatisk sökning och nedladdning via Prowlarr eller Jackett och qBittorrent, Transmission eller SABnzbd;
- en Seerr-inspirerad Discover-sida med Trending, Coming soon, Popular, Top rated, sökning och avancerade filter;
- privata Ollama-rekommendationer baserade på Plex- eller Tautulli-historik;
- ett sparat Light/Dark-temaval med både snabbknapp och tydlig av/på-switch.

Backend följer originalappens Python 3.13/FastAPI/SQLAlchemy/Alembic-struktur. Frontend följer Svelte 5/SvelteKit, Tailwind och shadcn-svelte. Inga parallella ramverk har lagts till.

## 1. Packa upp och skapa konfiguration

```bash
unzip MediaManager-enhanced.zip
cd MediaManager
mkdir -p config data/tv data/movies data/torrents images
cp config.example.toml config/config.toml
openssl rand -hex 32
```

Öppna `config/config.toml` och gör minst följande:

1. Ersätt `auth.token_secret` med värdet från `openssl`.
2. Ange din e-postadress i `auth.admin_emails`.
3. Kontrollera sökvägarna under `[misc]`. Standardvägarna `/data/tv`, `/data/movies` och `/data/torrents` matchar den medföljande Compose-filen.
4. Anpassa biblioteksposterna under `misc.tv_libraries` och `misc.movie_libraries`.

Första installationen skapar en administratör med den första adressen i `admin_emails` och lösenordet `admin`. Logga in på `http://localhost:8000` och byt lösenordet omedelbart.

## 2. Automatisk nedladdning

För den medföljande Prowlarr- och qBittorrent-profilen ska relevanta delar av `config.toml` använda Compose-namnen:

```toml
[indexers.prowlarr]
enabled = true
url = "http://prowlarr:9696"
api_key = "your-api-key"
timeout_seconds = 60
max_results = 1000

[torrents.qbittorrent]
enabled = true
host = "http://qbittorrent"
port = 8080
username = "admin"
password = "your-password"
category_name = "MediaManager"
category_save_path = "/data/torrents"

[automation]
enabled = true
auto_download_movies = true
auto_download_shows = true
continuous_download_enabled = true
```

Starta Prowlarr-varianten:

```bash
docker compose --profile downloads up -d --build
```

För Jackett använder du i stället `[indexers.jackett]`, URL `http://jackett:9117`, din API-nyckel och:

```bash
docker compose --profile jackett up -d --build
```

Aktivera inte `[automation]` förrän indexeraren och nedladdningsklienten svarar korrekt. qBittorrents `category_save_path` och MediaManagers `misc.torrent_directory` ska båda vara `/data/torrents` i standardinstallationen.

## 3. Discover och lokal metadata-relay

Den utökade Discover-funktionen behöver de nya TMDB-reläendpoints som ingår i paketet. Lägg din TMDB-nyckel i en `.env`-fil bredvid `docker-compose.yaml`:

```dotenv
TMDB_API_KEY=DIN_TMDB_API_NYCKEL
```

Ändra sedan:

```toml
[metadata.tmdb]
tmdb_relay_url = "http://metadata-relay:8000/tmdb"
primary_languages = [""]
default_language = "en"
```

Starta reläet tillsammans med appen:

```bash
docker compose --profile discover-relay up -d --build
```

TMDB-nyckeln stannar i reläcontainern och skickas aldrig till webbläsaren.

## 4. Ollama, Tautulli och Plex

Starta AI-profilen och hämta standardmodellen:

```bash
docker compose --profile ai up -d --build
docker compose exec ollama ollama pull llama3.2
```

Logga först in i MediaManager och hämta användarens UUID från svaret på `GET /api/v1/users/me` i webbläsarens utvecklarverktyg. Aktivera därefter rekommendationerna i `config.toml`:

```toml
[recommendations]
enabled = true
history_provider = "tautulli"
refresh_interval_minutes = 360
refresh_lease_timeout_seconds = 3600

[[recommendations.users]]
user_id = "DITT-MEDIAMANAGER-UUID"
tautulli_user_id = "DITT-TAUTULLI-USER-ID"
plex_username = "DITT-PLEX-NAMN"
enabled = true

[recommendations.tautulli]
enabled = true
url = "http://tautulli:8181"
api_key = "your-api-key"

[recommendations.ollama]
enabled = true
url = "http://ollama:11434"
model = "llama3.2"
```

Plex kan användas direkt genom att välja `history_provider = "plex"`, aktivera `[recommendations.plex]`, ange token och lägga `plex_account_id` i användarmappningen. För webhooks rekommenderas headern `X-MediaManager-Webhook-Secret`; Plex-kompatibel `?secret=...` stöds också. Den fullständiga konfigurationen finns i `docs/advanced-features/personal-recommendations.md`.

## 5. Starta allt

Prowlarr + qBittorrent + Discover-relay + Ollama/Tautulli:

```bash
docker compose \
  --profile downloads \
  --profile discover-relay \
  --profile ai \
  up -d --build
```

Kontrollera status:

```bash
docker compose ps
docker compose logs -f mediamanager
curl -f http://localhost:8000/api/v1/health
```

Databasmigreringar körs automatiskt vid containerstart. Discover syns i huvudmenyn. Automationsjobb kan granskas via `/api/v1/automation/jobs`, och rekommendationer kan uppdateras från Discover när användaren är mappad.

## 6. Light och Dark mode

Öppna **Settings → Appearance** och slå av eller på **Dark mode**. Samma val kan ändras med snabbknappen längst ned i sidomenyn. Valet sparas automatiskt på enheten och används igen efter omladdning; ingen omstart av MediaManager behövs.

## 7. Avsnittsscanner (nya avsnitt varje timme)

Scannern kontrollerar alla TV-serier i biblioteket varje timme och skickar nya avsnitt till nedladdningstjänsten (qBittorrent, Transmission eller SABnzbd) via de anslutna indexerarna (Prowlarr eller Jackett). Den körs i MediaManager-servern, så den fungerar även när webbsidan är stängd.

Öppna **TV Shows → Avsnittsscanner** i sidomenyn. Där finns:

- **Automatisk scanning** – reglaget som slår på eller av den timvisa scanningen (på från början);
- **Scanna nu** – startar en scanning direkt, även när automatisk scanning är avstängd;
- senaste scanning, nästa planerade scanning och resultatet (kontrollerade serier, skickade avsnitt, avsnitt som väntar på release och fel);
- vilka avsnitt som hittades och vad som hände med dem, de senast skickade avsnitten och en kort historik.

Ett avsnitt räknas som nytt om det har sänts de senaste 14 dagarna. Avsnitt som redan finns i biblioteket, laddas ned, ligger i nedladdningskön eller redan finns i qBittorrent hoppas över för att undvika dubbletter. Serier som lagts till som **Unmonitored** och säsonger som inte övervakas kontrolleras men laddas aldrig ned automatiskt. Om något går fel för en serie eller ett avsnitt visas felet i rött på sidan, övriga serier kontrolleras som vanligt och avsnittet försöks igen vid nästa scanning.

Intervall och tidsfönster kan ändras i `config.toml` (standardvärden visas):

```toml
[episode_scanner]
interval_minutes = 60
lookback_days = 14
include_specials = false
```

Mer detaljer finns i `docs/advanced-features/episode-scanner.md`.

## 8. Uppdatera MediaManager på din NAS

Uppdateringen innehåller en databasmigrering som körs automatiskt när containern startar. Dina inställningar och ditt bibliotek ligger kvar i mapparna `config/`, `data/`, `images/` och `postgres/`, så de ska inte tas bort.

1. Logga in på NAS:en med SSH och gå till mappen där MediaManager ligger (där `docker-compose.yaml` finns).
2. Ta gärna en säkerhetskopia av databasen först:

   ```bash
   docker compose exec db pg_dump -U MediaManager MediaManager > mediamanager-backup.sql
   ```

3. Hämta den nya koden. Om mappen är en Git-klon:

   ```bash
   git fetch https://github.com/gilbertbodyb28/MM.git claude/nice-bohr-cgv1ib
   git checkout -B episode-scanner FETCH_HEAD
   ```

   Annars: ladda ned grenen som ZIP från GitHub och kopiera in filerna över de gamla, men behåll mapparna `config/`, `data/`, `images/` och `postgres/`. Har du ändrat `docker-compose.yaml` på NAS:en (till exempel sökvägar eller portar) sparar du en kopia först och för över dina ändringar efteråt.

4. Bygg om och starta om appen med samma profiler som du brukar använda, till exempel:

   ```bash
   docker compose --profile downloads up -d --build
   ```

   Använder du NAS:ens Docker-/Compose-app i webbläsaren i stället för SSH väljer du projektet och kör **bygg om / uppdatera**.

5. Kontrollera att scannern har startat:

   ```bash
   docker compose logs -f mediamanager | grep -i "episode scan"
   ```

   Den första scanningen startar inom några minuter efter omstarten. Öppna sedan **TV Shows → Avsnittsscanner** för att se resultatet.

## Dokumentation

- `docs/advanced-features/episode-scanner.md`
- `docs/advanced-features/automatic-downloads.md`
- `docs/advanced-features/discover.md`
- `docs/advanced-features/personal-recommendations.md`
- `QA-RAPPORT.md`
