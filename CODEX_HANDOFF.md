# CODEX HANDOFF — MediaManager

## Purpose of This File

This project was previously being developed with another Codex account/user ("Account A").

Account A reached its Codex usage limit before a complete automated handoff could be generated.

A second Codex account/user ("Account B") will continue development using the exact same local repository on the same computer.

The previous Codex conversation history is NOT available to Account B.

Therefore:

**The repository, Git history, current working tree, tests, configuration, and this handoff file are the source of truth.**

Do NOT restart this project from scratch.

Do NOT assume that unfinished work needs to be reimplemented until the existing code has been inspected.

---

## Project

This is an existing MediaManager application that is being extended rather than replaced.

The objective is to preserve the existing application's working functionality and modern UI while adding substantially more media automation and recommendation functionality.

---

## Main Development Goals

The planned MediaManager development includes the following major features.

### Automatic TV Episode Acquisition

Add functionality that can automatically determine the newest/latest appropriate TV episode that should be acquired for a TV series added to MediaManager.

The intended flow is approximately:

**MediaManager**
→ determine missing/latest required episode
→ search through **Prowlarr**
→ evaluate/select an appropriate release
→ send the selected download to **qBittorrent**
→ monitor download state
→ detect completion
→ update MediaManager appropriately

The final implementation should avoid downloading episodes that already exist.

It should also avoid repeatedly submitting duplicate downloads.

Existing application architecture and media-state handling should be reused whenever possible instead of creating a completely separate duplicate system.

---

## Prowlarr Integration

MediaManager should be able to communicate with Prowlarr.

The implementation may eventually need to support:

* configurable Prowlarr URL,
* configurable API key,
* connection testing,
* media searching,
* episode searching,
* result parsing,
* release metadata,
* quality information,
* seeders/availability when exposed,
* download links,
* error handling,
* timeout handling,
* authentication failures,
* and clear UI/API errors.

Do NOT invent the Prowlarr API implementation.

Inspect any existing integration code first.

If no integration exists, use the actual documented/observed Prowlarr API behaviour rather than assumptions.

Never commit real API keys or secrets into the repository.

---

## qBittorrent Integration

MediaManager should eventually be able to send selected releases to qBittorrent.

The implementation may need to support:

* configurable qBittorrent URL,
* authentication,
* connection testing,
* submitting downloads,
* categories/tags when appropriate,
* download state,
* progress,
* completed state,
* failed state,
* duplicate detection,
* and error handling.

Do NOT create duplicate qBittorrent integration logic if the repository already contains an existing client or download abstraction that can be safely extended.

---

## TV Episode Monitoring

The intended long-term design should be able to understand which TV episodes are:

* already available,
* missing,
* future/unreleased,
* monitored,
* currently downloading,
* completed,
* failed,
* or waiting for acquisition.

Do not assume the current database already contains all of these states.

Inspect the actual database models/schema first.

Prefer extending existing models safely rather than replacing working data structures.

Any database migration must preserve existing user data.

---

## AI Recommendations

MediaManager is also intended to gain AI-powered recommendations.

Potential providers may include:

* OpenAI-compatible APIs,
* local Ollama models,
* or other configurable LLM providers if consistent with the existing architecture.

AI recommendations should ideally use information already available to MediaManager, such as:

* existing media library,
* watched media when available,
* genres,
* ratings,
* user preferences,
* previously accepted recommendations,
* previously rejected recommendations,
* and other relevant metadata.

AI functionality must not be tightly hard-coded to one provider if the existing architecture makes provider abstraction practical.

Do not expose API keys in source code, logs, or frontend responses.

---

## Discovery

A Discovery system is planned.

The goal is to allow the user to discover movies and TV series beyond the existing library.

Potential discovery inputs may include:

* genres,
* language,
* release date,
* popularity,
* ratings,
* trending media,
* upcoming media,
* AI recommendations,
* and user/library preference signals.

Discovery should integrate naturally with the existing MediaManager UI rather than feeling like an unrelated second application.

---

## UI Requirements

Preserve the existing MediaManager design language wherever practical.

The existing modern appearance is considered important.

Do NOT perform a broad visual redesign unless explicitly requested.

New functionality should visually fit into the existing interface.

Prefer:

**extend existing components and patterns**

over:

**replace the entire interface**

unless there is a strong architectural reason.

---

## IMPORTANT — Current Implementation State Is Not Fully Documented

Because Account A reached its Codex usage limit before generating an automated handoff, the exact last Codex conversation state is not contained in this file.

Therefore Account B MUST inspect the repository before changing anything.

Do NOT assume that a feature listed above has not already been partially or fully implemented.

Do NOT assume that existing uncommitted changes are disposable.

---

## Mandatory First Actions for Account B

Before modifying ANY code:

### 1. Read this entire file.

Read `CODEX_HANDOFF.md` completely.

### 2. Read active AGENTS instructions.

Follow all active global and repository-specific `AGENTS.md` instructions.

### 3. Inspect Git status.

Run:

```bash
git status
```

Identify:

* modified files,
* staged files,
* untracked files,
* deleted files,
* and the current branch.

### 4. Inspect existing uncommitted changes.

Run:

```bash
git diff
```

and, when relevant:

```bash
git diff --staged
```

Treat these changes as potentially important work from Account A.

Do NOT discard them.

### 5. Inspect recent history.

Run:

```bash
git log --oneline -10
```

Use the history to understand recent development.

### 6. Inspect repository architecture.

Determine:

* programming languages,
* backend framework,
* frontend framework,
* database/storage system,
* API structure,
* configuration system,
* dependency management,
* test framework,
* Docker configuration if present,
* media-management abstractions,
* existing integrations,
* existing download logic,
* and existing recommendation/discovery functionality.

### 7. Search for partially implemented work.

Search for relevant terms such as:

* prowlarr
* qbittorrent
* torrent
* download
* episode
* season
* monitor
* recommendation
* discovery
* AI
* OpenAI
* Ollama
* TODO
* FIXME

The exact names may differ.

Inspect the implementation rather than assuming that absence of one exact term means the feature does not exist.

### 8. Establish a baseline.

Before making major changes, run the existing:

* build,
* tests,
* type checker,
* and linting

when available.

Determine which failures already existed before new changes are made.

### 9. Report the reconstructed state.

Before beginning substantial new implementation, provide a concise report containing:

* what the application currently does,
* what relevant functionality already exists,
* what Account A appears to have changed,
* what is currently unfinished,
* existing test/build failures,
* likely next development step,
* and any uncertainties that cannot be determined from the repository.

Do not modify unrelated code while performing this reconstruction.

---

## Critical Safety Rules

### Do Not Restart the Project

This is an existing application.

Do not create a replacement application merely because the previous Codex chat is unavailable.

### Do Not Revert Unknown Work

Existing modified/uncommitted files may contain valuable Account A work.

Do not run destructive commands such as:

```bash
git reset --hard
git clean -fd
```

or equivalent destructive operations unless the creator explicitly requests it.

### Do Not Guess

If something can be determined by reading:

* source code,
* configuration,
* database schema,
* tests,
* Git history,
* logs,
* or actual API responses,

inspect that evidence instead of guessing.

### Preserve Working Functionality

Existing verified functionality should continue to work after new features are added.

### Build Incrementally

Prefer:

**small implementation**
→ **build**
→ **test**
→ **verify**
→ **next implementation**

instead of making one enormous unverified change.

---

## Recommended Development Order

Unless the existing repository indicates a better architecture, a reasonable implementation sequence is:

### Phase 1 — Repository Reconstruction

Understand exactly what currently exists.

No speculative rewrites.

### Phase 2 — Prowlarr Connectivity

Establish a reliable Prowlarr client/connection.

Verify authentication and API behaviour.

### Phase 3 — Search

Implement and verify media/episode search through Prowlarr.

### Phase 4 — qBittorrent Connectivity

Establish reliable qBittorrent communication.

### Phase 5 — Download Submission

Connect selected Prowlarr results to qBittorrent.

### Phase 6 — Download State

Monitor active downloads and completion.

### Phase 7 — Episode State

Determine missing/available/future/downloading/completed episodes.

### Phase 8 — Automatic Acquisition

Automate the complete episode acquisition workflow with safeguards against duplicate downloads.

### Phase 9 — Discovery

Build/extend Discovery using existing application architecture.

### Phase 10 — AI Recommendations

Integrate configurable AI recommendation functionality.

### Phase 11 — UI Integration

Expose the features through the existing MediaManager design system.

### Phase 12 — Regression Testing

Verify existing MediaManager functionality and all newly added functionality together.

This order is guidance, not permission to ignore a better architecture already present in the repository.

---

## Secrets and Credentials

Never place real credentials directly into this file.

Do not commit:

* Prowlarr API keys,
* qBittorrent passwords,
* OpenAI API keys,
* Ollama credentials if applicable,
* TMDB keys,
* Plex tokens,
* or other secrets.

Use the project's existing environment/configuration mechanism.

If credentials already exist locally, do not expose their values in chat unnecessarily.

---

## Account Handoff Information

Previous development account:

**Account A**

Continuation account:

**Account B**

Both accounts may use the same local repository on the same Mac.

Chat history should NOT be treated as shared between the accounts.

The local repository and Git state ARE shared because Account B is opening the same filesystem/project.

---

## Reasoning Policy

Global Codex reasoning instructions are maintained separately in:

```text
~/.codex/AGENTS.md
```

The global default reasoning configuration is expected to be managed through:

```text
~/.codex/config.toml
```

Follow the active global instructions.

Do not override the creator's reasoning escalation policy from this project.

---

## First Message Account B Should Effectively Follow

When Account B starts working on this repository, behave as though the following instruction was provided:

> This MediaManager repository was previously developed by another Codex account whose conversation history is unavailable.
>
> Read `CODEX_HANDOFF.md` completely before making any changes.
>
> Then inspect `git status`, `git diff`, staged changes, recent Git history, the repository architecture, relevant source files, tests, configuration, and any partially implemented Prowlarr, qBittorrent, episode automation, Discovery, or AI recommendation functionality.
>
> Treat existing uncommitted changes as important and do not discard them.
>
> Reconstruct the current project state from the repository itself.
>
> Do not restart or reimplement functionality that already exists.
>
> Establish the current build/test baseline.
>
> Before making substantial changes, tell me:
>
> 1. what is already implemented,
> 2. what appears unfinished,
> 3. what Account A was most likely working on,
> 4. what currently fails,
> 5. and what you recommend doing next.
>
> Preserve all verified working functionality and follow all active `AGENTS.md` instructions.

---

## Final Handoff Rule

The absence of Account A's conversation history is NOT permission to start over.

**Inspect first.**

**Preserve existing work.**

**Reconstruct state from evidence.**

**Continue from the repository's actual current state.**

**Verify every substantial change before proceeding.**

---

# Recovered Account A State — Verified Handoff

## Git Recovery

The previous Account A working tree was successfully reconstructed onto the upstream Git repository.

Recovery information:

- Upstream base commit: `98f2532`
- Recovery checkpoint commit: `3ac2965`
- Recovery branch: `recovered-account-a-work`
- Recovery checkpoint contained 114 changed files
- Recovery checkpoint contained 13,464 insertions and 639 deletions

The recovered source tree is preserved in Git and is the authoritative continuation point for Account B.

Do not reset this branch to `master`.
Do not discard commit `3ac2965`.

## Recovered Feature Areas

The recovered Account A work includes substantial implementation in:

- automatic download automation
- episode air-date tracking
- Prowlarr and indexer integration
- qBittorrent integration
- TV acquisition and episode handling
- Discover backend
- Discover frontend
- personal recommendations
- Ollama / LLM recommendation infrastructure
- Plex / Tautulli recommendation inputs
- database migrations
- scheduler changes
- API and schema changes
- frontend navigation and settings integration
- automated tests
- QA screenshots and documentation

Presence of these implementations does not by itself mean every feature is production-complete.

Account B must inspect and preserve existing working functionality before replacing or redesigning code.

## Verified Baseline — 2026-08-15

### Backend tests

Command:

`uv run pytest`

Result:

- PASS
- 69 tests passed
- Exit code: 0

### Python lint

Command:

`uv run ruff check .`

Result:

- PASS
- Exit code: 0

### Python type checking

Command:

`uv run ty check`

Result:

- EXISTING FAILING BASELINE
- Exit code: 1
- 100 diagnostics reported

These type diagnostics existed at handoff time and must not automatically be attributed to future Account B changes.

### Frontend validation

Command:

`npm run check`

Result:

- PASS
- 0 errors
- 7 warnings
- Exit code: 0

### Frontend production build

Initial command:

`npm run build`

Initial result:

- Failed because `PUBLIC_VERSION` was not available through `$env/static/public`.

Verification command:

`PUBLIC_VERSION="recovery-baseline" npm run build`

Verified result:

- PASS
- Exit code: 0
- SvelteKit/Vite client build completed
- SvelteKit/Vite server build completed
- Static adapter completed successfully

Therefore the initial frontend build failure was caused by the missing build-time `PUBLIC_VERSION` environment variable rather than a verified source-code build failure.

### npm dependency baseline

`npm ci` completed successfully.

npm reported:

- 19 audit findings total
- 2 low
- 5 moderate
- 12 high

Do not blindly run `npm audit fix --force`.
Dependency upgrades must be evaluated separately because forced upgrades may introduce breaking changes.

## Baseline Rules for Account B

At handoff:

- pytest: GREEN
- Ruff: GREEN
- Svelte check: GREEN with 7 warnings
- frontend production build: GREEN when `PUBLIC_VERSION` is supplied
- `ty`: RED with an existing baseline of 100 diagnostics

Account B must distinguish these pre-existing baseline conditions from regressions introduced by future changes.

Before substantial development:

1. Read this entire `CODEX_HANDOFF.md`.
2. Read the applicable Codex `AGENTS.md`.
3. Confirm branch `recovered-account-a-work`.
4. Inspect recovery commit `3ac2965`.
5. Check `git status`.
6. Inspect relevant existing implementation before editing.
7. Preserve working behavior.
8. Run appropriate tests after changes.

The Account A recovery is complete and Git commit `3ac2965` is the protected recovery checkpoint.

