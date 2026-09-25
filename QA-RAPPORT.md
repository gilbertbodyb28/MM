# QA-rapport – MediaManager Enhanced

Verifierad den 14 augusti 2026 mot MediaManagers befintliga arkitektur.

## Automatiska kontroller

- Backend: 69 tester godkända.
- Ruff lint: godkänd utan fel.
- Typkontroll av alla nya och direkt berörda domäner: godkänd.
- Säkerhetsregression: indexerarens API-nycklar, URL-frågor och fragment redigeras bort ur torrent- och redirect-loggar.
- Alembic: en sammanhängande head, `c7f1e6a24b90`; komplett offline-upgrade-SQL genererades utan fel.
- Svelte check: 0 fel. Sju äldre varningar finns kvar i originalets carousel, toggle-group och dashboard-layout.
- ESLint: 0 fel. Sexton äldre `any`-varningar finns kvar i originalets download/import-komponenter.
- Prettier: godkänd för hela `web/src`.
- Produktionsbygge av SvelteKit: godkänt.
- Båda Compose-filerna: validerade.
- Docker: `mediamanager-enhanced:local` och `mediamanager-metadata-relay:local` byggdes framgångsrikt från levererad källkod.

Originalprojektets fulla generiska typkontroll innehåller fortfarande äldre diagnostik i bland annat auth/common/importer-kod. De nya domänerna och den ändrade qBittorrent/indexer-koden är typgröna, och runtime-, test- och produktionsbyggena passerar.

## Renderad webbläsar-QA

Följande kördes mot riktig FastAPI/PostgreSQL-backend och Svelte-utvecklingsserver med deterministiska, lokala metadata-fixtures:

- administratörsinloggning;
- Discover-landing med alla fem katalograder;
- titel­sökning;
- kombinerat år- och genrefilter;
- Add-flöde från kort till skapad bibliotekspost;
- markerat `Open`/redan tillagt tillstånd;
- personliga Ollama-kort med motivering;
- olöst Ollama-rekommendation som ligger kvar med `Metadata match pending`;
- Light/Dark-switchen under Settings och snabbknappen i sidomenyn i båda riktningarna;
- synkroniserad status mellan båda temakontrollerna samt bevarat val efter omladdning;
- desktoplayout;
- 375 × 812 mobilviewport utan horisontell sid­overflow;
- en avslutande ren sidladdning utan konsolfel.

Skärmbilderna använder fiktiva QA-titlar och skickar ingen privat historik externt:

- `qa/discover-desktop.png`
- `qa/discover-mobile.png`
- `qa/discover-recommendations-mobile.png`

## Designjämförelse

1. Sidnavigation, breadcrumb och typografi återanvänder MediaManagers befintliga komponenter.
2. Sökfält, mediatypväxel och filter ligger i samma visuella hierarki som konceptet.
3. Horisontella Seerr-liknande rader, `See all` och navigeringspilar följer konceptets interaktion.
4. Kort behåller titel, år, mediatyp och betyg i posteröverlägget samt lägger till säkra Add/Open-tillstånd.
5. Light och Dark mode använder samma originaltokens och kan växlas utan omladdning eller visuell avvikelse.
6. Rekommendationsdelen följer katalogkortens designspråk och har ett separat, tydligt vänteläge för osäkra metadata­matchningar.
7. Mobilversionen staplar sökkontrollerna och behåller två användbara kortkolumner utan att klippa sidinnehållet.

Konceptets rubriker `Trending`, `Coming Soon` och `Recommended for You` återges som `Trending now`, `Coming soon` och `Recommended for you`. Den extra hero-texten förklarar katalogens funktion men ändrar inte flödet.

## Externa beroenden

Live-verifiering mot ägarens egna Prowlarr/Jackett-, qBittorrent-, Plex/Tautulli- och Ollama-instanser kräver deras privata URL:er och nycklar. Klienterna, felhanteringen, säkerhetsgränserna och orkestreringen täcks av testsviten. Paketet innehåller en lokal Discover-relay eftersom det offentliga standardreläet ännu inte exponerar samtliga nya Discover-endpoints.
