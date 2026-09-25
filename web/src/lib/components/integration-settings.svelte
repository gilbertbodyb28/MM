<script lang="ts">
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Checkbox } from '$lib/components/ui/checkbox/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import * as Select from '$lib/components/ui/select/index.js';
	import { Separator } from '$lib/components/ui/separator/index.js';
	import { Switch } from '$lib/components/ui/switch/index.js';
	import {
		BrainCircuit,
		Database,
		KeyRound,
		Link2,
		LoaderCircle,
		PlugZap,
		Save,
		Send,
		Server,
		UserRoundCog
	} from 'lucide-svelte';
	import { untrack } from 'svelte';
	import { toast } from 'svelte-sonner';

	type HistoryProvider = 'auto' | 'tautulli' | 'plex';
	type ServiceName =
		| 'prowlarr'
		| 'qbittorrent'
		| 'tmdb'
		| 'tvdb'
		| 'tautulli'
		| 'plex'
		| 'ollama'
		| 'trakt'
		| 'seerr';

	type IntegrationSettings = {
		prowlarr: {
			enabled: boolean;
			url: string;
			api_key_configured: boolean;
			timeout_seconds: number;
			max_results: number;
		};
		qbittorrent: {
			enabled: boolean;
			host: string;
			port: number;
			username: string;
			password_configured: boolean;
			category_name: string;
			category_save_path: string;
		};
		tmdb: {
			api_key_configured: boolean;
			access_token_configured: boolean;
			direct_configured: boolean;
			tmdb_relay_url: string;
			default_language: string;
			primary_languages: string[];
		};
		tvdb: {
			api_key_configured: boolean;
			pin_configured: boolean;
			direct_configured: boolean;
			tvdb_relay_url: string;
		};
		recommendations: {
			enabled: boolean;
			history_provider: HistoryProvider;
			refresh_interval_minutes: number;
			recommendation_count: number;
			minimum_history_items: number;
			tautulli: {
				enabled: boolean;
				url: string;
				api_key_configured: boolean;
				verify_ssl: boolean;
				request_timeout_seconds: number;
			};
			plex: {
				enabled: boolean;
				url: string;
				token_configured: boolean;
				verify_ssl: boolean;
				request_timeout_seconds: number;
				webhook_enabled: boolean;
				webhook_secret_configured: boolean;
				server_uuid: string;
			};
			ollama: {
				enabled: boolean;
				url: string;
				model: string;
				api_key_configured: boolean;
				verify_ssl: boolean;
				request_timeout_seconds: number;
				keep_alive: string;
			};
		};
		trakt: {
			enabled: boolean;
			client_id_configured: boolean;
			client_secret_configured: boolean;
			redirect_uri: string;
			frontend_return_url: string;
			verify_ssl: boolean;
			request_timeout_seconds: number;
		};
		seerr: {
			enabled: boolean;
			url: string;
			api_key_configured: boolean;
			verify_ssl: boolean;
			request_timeout_seconds: number;
		};
	};

	type RecommendationMapping = {
		tautulli_user_id: string;
		plex_account_id: string;
		plex_username: string;
		enabled: boolean;
		configured: boolean;
	};

	type ConnectionTest = {
		service: ServiceName;
		ok: boolean;
		message: string;
	};

	let {
		initialSettings,
		initialMapping,
		integrationError = null,
		mappingError = null
	}: {
		initialSettings: IntegrationSettings | null;
		initialMapping: RecommendationMapping | null;
		integrationError?: string | null;
		mappingError?: string | null;
	} = $props();

	function editableSettings(value: IntegrationSettings): IntegrationSettings {
		const editable = structuredClone(value);
		editable.recommendations.plex.server_uuid ??= '';
		return editable;
	}

	function editableMapping(value: RecommendationMapping | null): RecommendationMapping {
		return {
			tautulli_user_id: value?.tautulli_user_id ?? '',
			plex_account_id: value?.plex_account_id ?? '',
			plex_username: value?.plex_username ?? '',
			enabled: value?.enabled ?? false,
			configured: value?.configured ?? false
		};
	}

	let settings = $state<IntegrationSettings | null>(
		untrack(() => (initialSettings ? editableSettings(initialSettings) : null))
	);
	let mapping = $state<RecommendationMapping>(untrack(() => editableMapping(initialMapping)));

	let primaryLanguages = $state(
		untrack(() => initialSettings?.tmdb.primary_languages.join(', ') ?? '')
	);
	let historyProvider = $state<string>(
		untrack(() => initialSettings?.recommendations.history_provider ?? 'auto')
	);
	let saving = $state(false);
	let savingMapping = $state(false);
	let testing = $state<Partial<Record<ServiceName, boolean>>>({});
	let testResults = $state<Partial<Record<ServiceName, ConnectionTest>>>({});

	let prowlarrApiKey = $state('');
	let clearProwlarrApiKey = $state(false);
	let qbittorrentPassword = $state('');
	let clearQbittorrentPassword = $state(false);
	let tmdbApiKey = $state('');
	let tmdbAccessToken = $state('');
	let clearTmdbApiKey = $state(false);
	let clearTmdbAccessToken = $state(false);
	let tvdbApiKey = $state('');
	let tvdbPin = $state('');
	let clearTvdbApiKey = $state(false);
	let clearTvdbPin = $state(false);
	let tautulliApiKey = $state('');
	let clearTautulliApiKey = $state(false);
	let plexToken = $state('');
	let plexWebhookSecret = $state('');
	let clearPlexToken = $state(false);
	let clearPlexWebhookSecret = $state(false);
	let ollamaApiKey = $state('');
	let clearOllamaApiKey = $state(false);
	let traktClientId = $state('');
	let traktClientSecret = $state('');
	let clearTraktClientId = $state(false);
	let clearTraktClientSecret = $state(false);
	let seerrApiKey = $state('');
	let clearSeerrApiKey = $state(false);

	function secretPlaceholder(configured: boolean, name: string): string {
		return configured
			? `${name} configured — leave blank to keep it`
			: `Enter ${name.toLowerCase()}`;
	}

	function normalizeOptional(value: string | null): string | null {
		const normalized = value?.trim() ?? '';
		return normalized || null;
	}

	function optionalSecret(value: string): string | undefined {
		const normalized = value.trim();
		return normalized || undefined;
	}

	async function responseError(response: Response, fallback: string): Promise<string> {
		try {
			const payload = await response.json();
			if (typeof payload?.detail === 'string') return payload.detail;
		} catch {
			// The fallback is intentionally generic; integration responses may contain secrets.
		}
		return fallback;
	}

	function resetSecretEditors(): void {
		prowlarrApiKey = '';
		clearProwlarrApiKey = false;
		qbittorrentPassword = '';
		clearQbittorrentPassword = false;
		tmdbApiKey = '';
		tmdbAccessToken = '';
		clearTmdbApiKey = false;
		clearTmdbAccessToken = false;
		tvdbApiKey = '';
		tvdbPin = '';
		clearTvdbApiKey = false;
		clearTvdbPin = false;
		tautulliApiKey = '';
		clearTautulliApiKey = false;
		plexToken = '';
		plexWebhookSecret = '';
		clearPlexToken = false;
		clearPlexWebhookSecret = false;
		ollamaApiKey = '';
		clearOllamaApiKey = false;
		traktClientId = '';
		traktClientSecret = '';
		clearTraktClientId = false;
		clearTraktClientSecret = false;
		seerrApiKey = '';
		clearSeerrApiKey = false;
	}

	function updatePayload() {
		if (!settings) return null;

		return {
			prowlarr: {
				enabled: settings.prowlarr.enabled,
				url: settings.prowlarr.url,
				api_key: optionalSecret(prowlarrApiKey),
				clear_api_key: clearProwlarrApiKey,
				timeout_seconds: settings.prowlarr.timeout_seconds,
				max_results: settings.prowlarr.max_results
			},
			qbittorrent: {
				enabled: settings.qbittorrent.enabled,
				host: settings.qbittorrent.host,
				port: settings.qbittorrent.port,
				username: settings.qbittorrent.username,
				password: optionalSecret(qbittorrentPassword),
				clear_password: clearQbittorrentPassword,
				category_name: settings.qbittorrent.category_name,
				category_save_path: settings.qbittorrent.category_save_path
			},
			tmdb: {
				api_key: optionalSecret(tmdbApiKey),
				access_token: optionalSecret(tmdbAccessToken),
				clear_api_key: clearTmdbApiKey,
				clear_access_token: clearTmdbAccessToken,
				tmdb_relay_url: settings.tmdb.tmdb_relay_url,
				default_language: settings.tmdb.default_language,
				primary_languages: primaryLanguages
					.split(',')
					.map((language) => language.trim())
					.filter(Boolean)
			},
			tvdb: {
				api_key: optionalSecret(tvdbApiKey),
				pin: optionalSecret(tvdbPin),
				clear_api_key: clearTvdbApiKey,
				clear_pin: clearTvdbPin,
				tvdb_relay_url: settings.tvdb.tvdb_relay_url
			},
			recommendations: {
				enabled: settings.recommendations.enabled,
				history_provider: historyProvider as HistoryProvider,
				refresh_interval_minutes: settings.recommendations.refresh_interval_minutes,
				recommendation_count: settings.recommendations.recommendation_count,
				minimum_history_items: settings.recommendations.minimum_history_items,
				tautulli: {
					enabled: settings.recommendations.tautulli.enabled,
					url: settings.recommendations.tautulli.url,
					api_key: optionalSecret(tautulliApiKey),
					clear_api_key: clearTautulliApiKey,
					verify_ssl: settings.recommendations.tautulli.verify_ssl,
					request_timeout_seconds: settings.recommendations.tautulli.request_timeout_seconds
				},
				plex: {
					enabled: settings.recommendations.plex.enabled,
					url: settings.recommendations.plex.url,
					token: optionalSecret(plexToken),
					clear_token: clearPlexToken,
					verify_ssl: settings.recommendations.plex.verify_ssl,
					request_timeout_seconds: settings.recommendations.plex.request_timeout_seconds,
					webhook_enabled: settings.recommendations.plex.webhook_enabled,
					webhook_secret: optionalSecret(plexWebhookSecret),
					clear_webhook_secret: clearPlexWebhookSecret,
					server_uuid: normalizeOptional(settings.recommendations.plex.server_uuid)
				},
				ollama: {
					enabled: settings.recommendations.ollama.enabled,
					url: settings.recommendations.ollama.url,
					model: settings.recommendations.ollama.model,
					api_key: optionalSecret(ollamaApiKey),
					clear_api_key: clearOllamaApiKey,
					verify_ssl: settings.recommendations.ollama.verify_ssl,
					request_timeout_seconds: settings.recommendations.ollama.request_timeout_seconds,
					keep_alive: settings.recommendations.ollama.keep_alive
				}
			},
			trakt: {
				enabled: settings.trakt.enabled,
				client_id: optionalSecret(traktClientId),
				client_secret: optionalSecret(traktClientSecret),
				clear_client_id: clearTraktClientId,
				clear_client_secret: clearTraktClientSecret,
				redirect_uri: settings.trakt.redirect_uri,
				frontend_return_url: settings.trakt.frontend_return_url,
				verify_ssl: settings.trakt.verify_ssl,
				request_timeout_seconds: settings.trakt.request_timeout_seconds
			},
			seerr: {
				enabled: settings.seerr.enabled,
				url: settings.seerr.url,
				api_key: optionalSecret(seerrApiKey),
				clear_api_key: clearSeerrApiKey,
				verify_ssl: settings.seerr.verify_ssl,
				request_timeout_seconds: settings.seerr.request_timeout_seconds
			}
		};
	}

	async function saveSettings(showToast = true): Promise<boolean> {
		const payload = updatePayload();
		if (!payload) return false;
		saving = true;
		try {
			const response = await fetch('/api/v1/settings/integrations', {
				method: 'PATCH',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify(payload)
			});
			if (!response.ok) {
				toast.error(await responseError(response, 'Integration settings could not be saved.'));
				return false;
			}
			settings = editableSettings((await response.json()) as IntegrationSettings);
			primaryLanguages = settings.tmdb.primary_languages.join(', ');
			historyProvider = settings.recommendations.history_provider;
			resetSecretEditors();
			if (showToast) toast.success('Integration settings saved.');
			return true;
		} catch {
			toast.error('Could not reach MediaManager to save the integration settings.');
			return false;
		} finally {
			saving = false;
		}
	}

	async function testService(service: ServiceName): Promise<void> {
		if (!(await saveSettings(false))) return;
		testing[service] = true;
		delete testResults[service];
		try {
			const response = await fetch(`/api/v1/settings/integrations/${service}/test`, {
				method: 'POST'
			});
			if (!response.ok) {
				toast.error(await responseError(response, `Could not test ${service}.`));
				return;
			}
			const result = (await response.json()) as ConnectionTest;
			testResults[service] = result;
			if (result.ok) toast.success(`${service}: ${result.message}`);
			else toast.error(`${service}: ${result.message}`);
		} catch {
			toast.error(`Could not reach MediaManager to test ${service}.`);
		} finally {
			testing[service] = false;
		}
	}

	async function saveMapping(): Promise<void> {
		const tautulliUserId = normalizeOptional(mapping.tautulli_user_id);
		const plexAccountId = normalizeOptional(mapping.plex_account_id);
		const plexUsername = normalizeOptional(mapping.plex_username);
		if (mapping.enabled && !tautulliUserId && !plexAccountId && !plexUsername) {
			toast.error('Enter at least one Plex or Tautulli identity before enabling mapping.');
			return;
		}

		savingMapping = true;
		try {
			const response = await fetch('/api/v1/settings/recommendation-mapping/me', {
				method: 'PUT',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({
					tautulli_user_id: tautulliUserId,
					plex_account_id: plexAccountId,
					plex_username: plexUsername,
					enabled: mapping.enabled
				})
			});
			if (!response.ok) {
				toast.error(await responseError(response, 'Recommendation profile could not be saved.'));
				return;
			}
			mapping = editableMapping((await response.json()) as RecommendationMapping);
			toast.success('Recommendation profile saved.');
		} catch {
			toast.error('Could not reach MediaManager to save your recommendation profile.');
		} finally {
			savingMapping = false;
		}
	}
</script>

{#if settings}
	<form
		class="space-y-4"
		onsubmit={(event) => {
			event.preventDefault();
			void saveSettings();
		}}
	>
		<Card.Root id="integrations">
			<Card.Header class="gap-3">
				<div class="flex flex-wrap items-start justify-between gap-3">
					<div class="space-y-1.5">
						<Card.Title class="flex items-center gap-2">
							<PlugZap class="size-5" />
							Downloads and indexers
						</Card.Title>
						<Card.Description>
							Configure Prowlarr and qBittorrent without editing TOML or Docker Compose files.
						</Card.Description>
					</div>
					<Badge variant="outline">Administrator only</Badge>
				</div>
				<Alert.Root>
					<KeyRound class="size-4" />
					<Alert.Title>Secrets stay hidden</Alert.Title>
					<Alert.Description>
						Saved credentials are never returned to the browser. Leave a secret blank to keep it.
						Connection tests save this form first and run from inside MediaManager.
					</Alert.Description>
				</Alert.Root>
			</Card.Header>
			<Card.Content class="grid gap-6 lg:grid-cols-2">
				<section class="space-y-4 rounded-xl border p-4">
					<div class="flex items-center justify-between gap-3">
						<div>
							<h3 class="font-semibold">Prowlarr</h3>
							<p class="text-sm text-muted-foreground">Search configured indexers for releases.</p>
						</div>
						<div class="flex items-center gap-2">
							<Badge variant={settings.prowlarr.api_key_configured ? 'secondary' : 'outline'}>
								{settings.prowlarr.api_key_configured ? 'Key configured' : 'No key'}
							</Badge>
							<Switch bind:checked={settings.prowlarr.enabled} id="prowlarr-enabled" />
						</div>
					</div>
					<div class="space-y-2">
						<Label for="prowlarr-url">Server URL</Label>
						<Input
							bind:value={settings.prowlarr.url}
							id="prowlarr-url"
							placeholder="http://host:9696"
						/>
					</div>
					<div class="space-y-2">
						<Label for="prowlarr-key">API key</Label>
						<Input
							bind:value={prowlarrApiKey}
							disabled={clearProwlarrApiKey}
							id="prowlarr-key"
							placeholder={secretPlaceholder(settings.prowlarr.api_key_configured, 'API key')}
							type="password"
						/>
					</div>
					<div class="grid grid-cols-2 gap-3">
						<div class="space-y-2">
							<Label for="prowlarr-timeout">Timeout (seconds)</Label>
							<Input
								bind:value={settings.prowlarr.timeout_seconds}
								id="prowlarr-timeout"
								max="300"
								min="1"
								type="number"
							/>
						</div>
						<div class="space-y-2">
							<Label for="prowlarr-results">Maximum results</Label>
							<Input
								bind:value={settings.prowlarr.max_results}
								id="prowlarr-results"
								max="1000"
								min="1"
								type="number"
							/>
						</div>
					</div>
					<div class="flex flex-wrap items-center justify-between gap-3">
						<label
							class="flex items-center gap-2 text-sm text-muted-foreground"
							for="clear-prowlarr-key"
						>
							<Checkbox bind:checked={clearProwlarrApiKey} id="clear-prowlarr-key" />
							Clear saved API key
						</label>
						<Button
							disabled={saving || testing.prowlarr}
							onclick={() => void testService('prowlarr')}
							type="button"
							variant="outline"
						>
							{#if testing.prowlarr}<LoaderCircle class="animate-spin" />{:else}<PlugZap />{/if}
							Test Prowlarr
						</Button>
					</div>
					{#if testResults.prowlarr}
						<p class:text-destructive={!testResults.prowlarr.ok} class="text-sm" aria-live="polite">
							{testResults.prowlarr.message}
						</p>
					{/if}
				</section>

				<section class="space-y-4 rounded-xl border p-4">
					<div class="flex items-center justify-between gap-3">
						<div>
							<h3 class="font-semibold">qBittorrent</h3>
							<p class="text-sm text-muted-foreground">
								Send selected releases to your download client.
							</p>
						</div>
						<div class="flex items-center gap-2">
							<Badge variant={settings.qbittorrent.password_configured ? 'secondary' : 'outline'}>
								{settings.qbittorrent.password_configured ? 'Password configured' : 'No password'}
							</Badge>
							<Switch bind:checked={settings.qbittorrent.enabled} id="qbittorrent-enabled" />
						</div>
					</div>
					<div class="grid gap-3 sm:grid-cols-[1fr_8rem]">
						<div class="space-y-2">
							<Label for="qbittorrent-host">Host or IP address</Label>
							<Input
								bind:value={settings.qbittorrent.host}
								id="qbittorrent-host"
								placeholder="192.168.1.20"
							/>
						</div>
						<div class="space-y-2">
							<Label for="qbittorrent-port">Port</Label>
							<Input
								bind:value={settings.qbittorrent.port}
								id="qbittorrent-port"
								max="65535"
								min="1"
								type="number"
							/>
						</div>
					</div>
					<div class="grid gap-3 sm:grid-cols-2">
						<div class="space-y-2">
							<Label for="qbittorrent-username">Username</Label>
							<Input
								bind:value={settings.qbittorrent.username}
								autocomplete="username"
								id="qbittorrent-username"
							/>
						</div>
						<div class="space-y-2">
							<Label for="qbittorrent-password">Password</Label>
							<Input
								bind:value={qbittorrentPassword}
								autocomplete="new-password"
								disabled={clearQbittorrentPassword}
								id="qbittorrent-password"
								placeholder={secretPlaceholder(
									settings.qbittorrent.password_configured,
									'Password'
								)}
								type="password"
							/>
						</div>
					</div>
					<div class="grid gap-3 sm:grid-cols-2">
						<div class="space-y-2">
							<Label for="qbittorrent-category">Category</Label>
							<Input bind:value={settings.qbittorrent.category_name} id="qbittorrent-category" />
						</div>
						<div class="space-y-2">
							<Label for="qbittorrent-save-path">Category save path</Label>
							<Input
								bind:value={settings.qbittorrent.category_save_path}
								id="qbittorrent-save-path"
							/>
						</div>
					</div>
					<div class="flex flex-wrap items-center justify-between gap-3">
						<label
							class="flex items-center gap-2 text-sm text-muted-foreground"
							for="clear-qbittorrent-password"
						>
							<Checkbox bind:checked={clearQbittorrentPassword} id="clear-qbittorrent-password" />
							Clear saved password
						</label>
						<Button
							disabled={saving || testing.qbittorrent}
							onclick={() => void testService('qbittorrent')}
							type="button"
							variant="outline"
						>
							{#if testing.qbittorrent}<LoaderCircle class="animate-spin" />{:else}<PlugZap />{/if}
							Test qBittorrent
						</Button>
					</div>
					{#if testResults.qbittorrent}
						<p
							class:text-destructive={!testResults.qbittorrent.ok}
							class="text-sm"
							aria-live="polite"
						>
							{testResults.qbittorrent.message}
						</p>
					{/if}
				</section>
			</Card.Content>
		</Card.Root>

		<Card.Root id="metadata">
			<Card.Header>
				<Card.Title class="flex items-center gap-2"
					><Database class="size-5" />Metadata providers</Card.Title
				>
				<Card.Description>
					Add TMDB and TVDB credentials here to restore Discover metadata and artwork. Direct
					credentials take precedence over relay URLs.
				</Card.Description>
			</Card.Header>
			<Card.Content class="grid gap-6 lg:grid-cols-2">
				<section class="space-y-4 rounded-xl border p-4">
					<div class="flex items-center justify-between gap-3">
						<h3 class="font-semibold">TMDB</h3>
						<Badge variant={settings.tmdb.direct_configured ? 'secondary' : 'outline'}>
							{settings.tmdb.direct_configured ? 'Direct access configured' : 'Using relay'}
						</Badge>
					</div>
					<div class="space-y-2">
						<Label for="tmdb-api-key">API key</Label>
						<Input
							bind:value={tmdbApiKey}
							disabled={clearTmdbApiKey}
							id="tmdb-api-key"
							placeholder={secretPlaceholder(settings.tmdb.api_key_configured, 'API key')}
							type="password"
						/>
					</div>
					<label
						class="flex items-center gap-2 text-sm text-muted-foreground"
						for="clear-tmdb-api-key"
					>
						<Checkbox bind:checked={clearTmdbApiKey} id="clear-tmdb-api-key" /> Clear saved API key
					</label>
					<div class="space-y-2">
						<Label for="tmdb-token">Read access token</Label>
						<Input
							bind:value={tmdbAccessToken}
							disabled={clearTmdbAccessToken}
							id="tmdb-token"
							placeholder={secretPlaceholder(settings.tmdb.access_token_configured, 'Access token')}
							type="password"
						/>
					</div>
					<label
						class="flex items-center gap-2 text-sm text-muted-foreground"
						for="clear-tmdb-token"
					>
						<Checkbox bind:checked={clearTmdbAccessToken} id="clear-tmdb-token" /> Clear saved access
						token
					</label>
					<div class="space-y-2">
						<Label for="tmdb-relay">Relay URL</Label>
						<Input bind:value={settings.tmdb.tmdb_relay_url} id="tmdb-relay" type="url" />
					</div>
					<div class="grid gap-3 sm:grid-cols-2">
						<div class="space-y-2">
							<Label for="tmdb-language">Default language</Label>
							<Input
								bind:value={settings.tmdb.default_language}
								id="tmdb-language"
								placeholder="en-US"
							/>
						</div>
						<div class="space-y-2">
							<Label for="tmdb-primary-languages">Primary languages</Label>
							<Input
								bind:value={primaryLanguages}
								id="tmdb-primary-languages"
								placeholder="en, sv, ja"
							/>
						</div>
					</div>
					<div class="flex justify-end">
						<Button
							disabled={saving || testing.tmdb}
							onclick={() => void testService('tmdb')}
							type="button"
							variant="outline"
						>
							{#if testing.tmdb}<LoaderCircle class="animate-spin" />{:else}<PlugZap />{/if} Test TMDB
						</Button>
					</div>
					{#if testResults.tmdb}<p class:text-destructive={!testResults.tmdb.ok} class="text-sm">
							{testResults.tmdb.message}
						</p>{/if}
				</section>

				<section class="space-y-4 rounded-xl border p-4">
					<div class="flex items-center justify-between gap-3">
						<h3 class="font-semibold">TVDB</h3>
						<Badge variant={settings.tvdb.direct_configured ? 'secondary' : 'outline'}>
							{settings.tvdb.direct_configured ? 'Direct access configured' : 'Using relay'}
						</Badge>
					</div>
					<div class="space-y-2">
						<Label for="tvdb-api-key">API key</Label>
						<Input
							bind:value={tvdbApiKey}
							disabled={clearTvdbApiKey}
							id="tvdb-api-key"
							placeholder={secretPlaceholder(settings.tvdb.api_key_configured, 'API key')}
							type="password"
						/>
					</div>
					<label
						class="flex items-center gap-2 text-sm text-muted-foreground"
						for="clear-tvdb-api-key"
					>
						<Checkbox bind:checked={clearTvdbApiKey} id="clear-tvdb-api-key" /> Clear saved API key
					</label>
					<div class="space-y-2">
						<Label for="tvdb-pin">Subscriber PIN (optional)</Label>
						<Input
							bind:value={tvdbPin}
							disabled={clearTvdbPin}
							id="tvdb-pin"
							placeholder={secretPlaceholder(settings.tvdb.pin_configured, 'PIN')}
							type="password"
						/>
					</div>
					<label class="flex items-center gap-2 text-sm text-muted-foreground" for="clear-tvdb-pin">
						<Checkbox bind:checked={clearTvdbPin} id="clear-tvdb-pin" /> Clear saved PIN
					</label>
					<div class="space-y-2">
						<Label for="tvdb-relay">Relay URL</Label>
						<Input bind:value={settings.tvdb.tvdb_relay_url} id="tvdb-relay" type="url" />
					</div>
					<div class="flex justify-end">
						<Button
							disabled={saving || testing.tvdb}
							onclick={() => void testService('tvdb')}
							type="button"
							variant="outline"
						>
							{#if testing.tvdb}<LoaderCircle class="animate-spin" />{:else}<PlugZap />{/if} Test TVDB
						</Button>
					</div>
					{#if testResults.tvdb}<p class:text-destructive={!testResults.tvdb.ok} class="text-sm">
							{testResults.tvdb.message}
						</p>{/if}
				</section>
			</Card.Content>
		</Card.Root>

		<Card.Root id="trakt">
			<Card.Header>
				<Card.Title class="flex items-center gap-2"><Link2 class="size-5" />Trakt and Seerr</Card.Title>
				<Card.Description>
					Connect Trakt through per-user OAuth and send media requests to Seerr through the
					MediaManager backend. Saved secrets are never returned to this page.
				</Card.Description>
			</Card.Header>
			<Card.Content class="grid gap-6 xl:grid-cols-2">
				<section class="space-y-4 rounded-xl border p-4">
					<div class="flex items-center justify-between gap-3">
						<div>
							<h3 class="font-semibold">Trakt OAuth</h3>
							<p class="text-sm text-muted-foreground">
								Watchlist, Collection, History, and personal Lists.
							</p>
						</div>
						<div class="flex items-center gap-2">
							<Badge
								variant={settings.trakt.client_id_configured && settings.trakt.client_secret_configured
									? 'secondary'
									: 'outline'}
							>
								{settings.trakt.client_id_configured && settings.trakt.client_secret_configured
									? 'OAuth configured'
									: 'Credentials missing'}
							</Badge>
							<Switch bind:checked={settings.trakt.enabled} id="trakt-enabled" />
						</div>
					</div>
					<div class="grid gap-3 sm:grid-cols-2">
						<div class="space-y-2">
							<Label for="trakt-client-id">Client ID</Label>
							<Input
								bind:value={traktClientId}
								disabled={clearTraktClientId}
								id="trakt-client-id"
								placeholder={secretPlaceholder(settings.trakt.client_id_configured, 'Client ID')}
								type="password"
							/>
						</div>
						<div class="space-y-2">
							<Label for="trakt-client-secret">Client secret</Label>
							<Input
								bind:value={traktClientSecret}
								disabled={clearTraktClientSecret}
								id="trakt-client-secret"
								placeholder={secretPlaceholder(
									settings.trakt.client_secret_configured,
									'Client secret'
								)}
								type="password"
							/>
						</div>
					</div>
					<div class="space-y-2">
						<Label for="trakt-redirect-uri">OAuth redirect URI</Label>
						<Input bind:value={settings.trakt.redirect_uri} id="trakt-redirect-uri" type="url" />
						<p class="text-xs text-muted-foreground">
							Register this exact URL as the Redirect URI in the Trakt API application.
						</p>
					</div>
					<div class="space-y-2">
						<Label for="trakt-return-url">Frontend return URL</Label>
						<Input
							bind:value={settings.trakt.frontend_return_url}
							id="trakt-return-url"
							type="url"
						/>
					</div>
					<div class="grid grid-cols-2 gap-3">
						<div class="space-y-2">
							<Label for="trakt-timeout">Timeout (seconds)</Label>
							<Input
								bind:value={settings.trakt.request_timeout_seconds}
								id="trakt-timeout"
								max="300"
								min="1"
								type="number"
							/>
						</div>
						<div class="flex items-end justify-between gap-3 pb-2">
							<Label for="trakt-ssl">Verify TLS</Label>
							<Switch bind:checked={settings.trakt.verify_ssl} id="trakt-ssl" />
						</div>
					</div>
					<div class="grid gap-2 sm:grid-cols-2">
						<label class="flex items-center gap-2 text-sm text-muted-foreground" for="clear-trakt-id">
							<Checkbox bind:checked={clearTraktClientId} id="clear-trakt-id" /> Clear client ID
						</label>
						<label class="flex items-center gap-2 text-sm text-muted-foreground" for="clear-trakt-secret">
							<Checkbox bind:checked={clearTraktClientSecret} id="clear-trakt-secret" /> Clear client secret
						</label>
					</div>
					<Button
						class="w-full"
						disabled={saving || testing.trakt}
						onclick={() => void testService('trakt')}
						type="button"
						variant="outline"
					>
						{#if testing.trakt}<LoaderCircle class="animate-spin" />{:else}<PlugZap />{/if}
						Test Trakt
					</Button>
					{#if testResults.trakt}
						<p class:text-destructive={!testResults.trakt.ok} class="text-sm">
							{testResults.trakt.message}
						</p>
					{/if}
				</section>

				<section class="space-y-4 rounded-xl border p-4">
					<div class="flex items-center justify-between gap-3">
						<div>
							<h3 class="font-semibold">Seerr</h3>
							<p class="text-sm text-muted-foreground">
								Request missing recommendations and Discovery results.
							</p>
						</div>
						<div class="flex items-center gap-2">
							<Badge variant={settings.seerr.api_key_configured ? 'secondary' : 'outline'}>
								{settings.seerr.api_key_configured ? 'Key configured' : 'No key'}
							</Badge>
							<Switch bind:checked={settings.seerr.enabled} id="seerr-enabled" />
						</div>
					</div>
					<div class="space-y-2">
						<Label for="seerr-url">Seerr URL</Label>
						<Input
							bind:value={settings.seerr.url}
							id="seerr-url"
							placeholder="http://host:5055"
							type="url"
						/>
					</div>
					<div class="space-y-2">
						<Label for="seerr-api-key">API key</Label>
						<Input
							bind:value={seerrApiKey}
							disabled={clearSeerrApiKey}
							id="seerr-api-key"
							placeholder={secretPlaceholder(settings.seerr.api_key_configured, 'API key')}
							type="password"
						/>
					</div>
					<div class="grid grid-cols-2 gap-3">
						<div class="space-y-2">
							<Label for="seerr-timeout">Timeout (seconds)</Label>
							<Input
								bind:value={settings.seerr.request_timeout_seconds}
								id="seerr-timeout"
								max="300"
								min="1"
								type="number"
							/>
						</div>
						<div class="flex items-end justify-between gap-3 pb-2">
							<Label for="seerr-ssl">Verify TLS</Label>
							<Switch bind:checked={settings.seerr.verify_ssl} id="seerr-ssl" />
						</div>
					</div>
					<label class="flex items-center gap-2 text-sm text-muted-foreground" for="clear-seerr-key">
						<Checkbox bind:checked={clearSeerrApiKey} id="clear-seerr-key" /> Clear saved API key
					</label>
					<Alert.Root>
						<Send class="size-4" />
						<Alert.Title>Backend proxy</Alert.Title>
						<Alert.Description>
							The API key is attached only by MediaManager; it is never placed in frontend code.
						</Alert.Description>
					</Alert.Root>
					<Button
						class="w-full"
						disabled={saving || testing.seerr}
						onclick={() => void testService('seerr')}
						type="button"
						variant="outline"
					>
						{#if testing.seerr}<LoaderCircle class="animate-spin" />{:else}<PlugZap />{/if}
						Test Seerr
					</Button>
					{#if testResults.seerr}
						<p class:text-destructive={!testResults.seerr.ok} class="text-sm">
							{testResults.seerr.message}
						</p>
					{/if}
				</section>
			</Card.Content>
		</Card.Root>

		<Card.Root id="recommendations">
			<Card.Header>
				<div class="flex flex-wrap items-center justify-between gap-3">
					<div>
						<Card.Title class="flex items-center gap-2"
							><BrainCircuit class="size-5" />Personal recommendations</Card.Title
						>
						<Card.Description>
							Use local Plex or Tautulli history with Ollama. Viewing history remains in your
							environment.
						</Card.Description>
					</div>
					<div class="flex items-center gap-2">
						<Label for="recommendations-enabled">Enabled</Label>
						<Switch bind:checked={settings.recommendations.enabled} id="recommendations-enabled" />
					</div>
				</div>
			</Card.Header>
			<Card.Content class="space-y-6">
				<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
					<div class="space-y-2">
						<Label for="history-provider">History provider</Label>
						<Select.Root bind:value={historyProvider} type="single">
							<Select.Trigger class="w-full" id="history-provider">
								{historyProvider === 'auto'
									? 'Automatic'
									: historyProvider === 'plex'
										? 'Plex'
										: 'Tautulli'}
							</Select.Trigger>
							<Select.Content>
								<Select.Item value="auto">Automatic</Select.Item>
								<Select.Item value="tautulli">Tautulli</Select.Item>
								<Select.Item value="plex">Plex</Select.Item>
							</Select.Content>
						</Select.Root>
					</div>
					<div class="space-y-2">
						<Label for="recommendation-refresh">Refresh (minutes)</Label>
						<Input
							bind:value={settings.recommendations.refresh_interval_minutes}
							id="recommendation-refresh"
							max="43200"
							min="15"
							type="number"
						/>
					</div>
					<div class="space-y-2">
						<Label for="recommendation-count">Number of recommendations</Label>
						<Input
							bind:value={settings.recommendations.recommendation_count}
							id="recommendation-count"
							max="50"
							min="1"
							type="number"
						/>
					</div>
					<div class="space-y-2">
						<Label for="recommendation-history">Minimum history items</Label>
						<Input
							bind:value={settings.recommendations.minimum_history_items}
							id="recommendation-history"
							max="100"
							min="1"
							type="number"
						/>
					</div>
				</div>

				<Separator />
				<div class="grid gap-6 xl:grid-cols-3">
					<section class="space-y-4 rounded-xl border p-4">
						<div class="flex items-center justify-between gap-2">
							<div>
								<h3 class="font-semibold">Tautulli</h3>
								<p class="text-sm text-muted-foreground">Detailed Plex watch history.</p>
							</div>
							<Switch
								bind:checked={settings.recommendations.tautulli.enabled}
								id="tautulli-enabled"
							/>
						</div>
						<Badge
							variant={settings.recommendations.tautulli.api_key_configured
								? 'secondary'
								: 'outline'}
							>{settings.recommendations.tautulli.api_key_configured
								? 'Key configured'
								: 'No key'}</Badge
						>
						<div class="space-y-2">
							<Label for="tautulli-url">Server URL</Label><Input
								bind:value={settings.recommendations.tautulli.url}
								id="tautulli-url"
								type="url"
							/>
						</div>
						<div class="space-y-2">
							<Label for="tautulli-key">API key</Label><Input
								bind:value={tautulliApiKey}
								disabled={clearTautulliApiKey}
								id="tautulli-key"
								placeholder={secretPlaceholder(
									settings.recommendations.tautulli.api_key_configured,
									'API key'
								)}
								type="password"
							/>
						</div>
						<div class="space-y-2">
							<Label for="tautulli-timeout">Timeout (seconds)</Label><Input
								bind:value={settings.recommendations.tautulli.request_timeout_seconds}
								id="tautulli-timeout"
								max="300"
								min="1"
								type="number"
							/>
						</div>
						<div class="flex items-center justify-between gap-3">
							<Label for="tautulli-ssl">Verify TLS certificate</Label><Switch
								bind:checked={settings.recommendations.tautulli.verify_ssl}
								id="tautulli-ssl"
							/>
						</div>
						<label
							class="flex items-center gap-2 text-sm text-muted-foreground"
							for="clear-tautulli-key"
							><Checkbox bind:checked={clearTautulliApiKey} id="clear-tautulli-key" /> Clear saved API
							key</label
						>
						<Button
							class="w-full"
							disabled={saving || testing.tautulli}
							onclick={() => void testService('tautulli')}
							type="button"
							variant="outline"
							>{#if testing.tautulli}<LoaderCircle class="animate-spin" />{:else}<PlugZap />{/if} Test
							Tautulli</Button
						>
						{#if testResults.tautulli}<p
								class:text-destructive={!testResults.tautulli.ok}
								class="text-sm"
							>
								{testResults.tautulli.message}
							</p>{/if}
					</section>

					<section class="space-y-4 rounded-xl border p-4">
						<div class="flex items-center justify-between gap-2">
							<div>
								<h3 class="font-semibold">Plex</h3>
								<p class="text-sm text-muted-foreground">Direct Plex viewing history.</p>
							</div>
							<Switch bind:checked={settings.recommendations.plex.enabled} id="plex-enabled" />
						</div>
						<Badge
							variant={settings.recommendations.plex.token_configured ? 'secondary' : 'outline'}
							>{settings.recommendations.plex.token_configured
								? 'Token configured'
								: 'No token'}</Badge
						>
						<div class="space-y-2">
							<Label for="plex-url">Server URL</Label><Input
								bind:value={settings.recommendations.plex.url}
								id="plex-url"
								type="url"
							/>
						</div>
						<div class="space-y-2">
							<Label for="plex-token">Access token</Label><Input
								bind:value={plexToken}
								disabled={clearPlexToken}
								id="plex-token"
								placeholder={secretPlaceholder(
									settings.recommendations.plex.token_configured,
									'Token'
								)}
								type="password"
							/>
						</div>
						<div class="space-y-2">
							<Label for="plex-server-uuid">Server UUID (optional)</Label><Input
								bind:value={settings.recommendations.plex.server_uuid}
								id="plex-server-uuid"
							/>
						</div>
						<div class="space-y-2">
							<Label for="plex-timeout">Timeout (seconds)</Label><Input
								bind:value={settings.recommendations.plex.request_timeout_seconds}
								id="plex-timeout"
								max="300"
								min="1"
								type="number"
							/>
						</div>
						<div class="flex items-center justify-between gap-3">
							<Label for="plex-ssl">Verify TLS certificate</Label><Switch
								bind:checked={settings.recommendations.plex.verify_ssl}
								id="plex-ssl"
							/>
						</div>
						<label
							class="flex items-center gap-2 text-sm text-muted-foreground"
							for="clear-plex-token"
							><Checkbox bind:checked={clearPlexToken} id="clear-plex-token" /> Clear saved token</label
						>
						<Separator />
						<div class="flex items-center justify-between gap-3">
							<div>
								<Label for="plex-webhook">Plex webhook</Label>
								<p class="text-xs text-muted-foreground">Accept real-time history events.</p>
							</div>
							<Switch
								bind:checked={settings.recommendations.plex.webhook_enabled}
								id="plex-webhook"
							/>
						</div>
						<div class="space-y-2">
							<Label for="plex-webhook-secret">Webhook secret</Label><Input
								bind:value={plexWebhookSecret}
								disabled={clearPlexWebhookSecret}
								id="plex-webhook-secret"
								placeholder={secretPlaceholder(
									settings.recommendations.plex.webhook_secret_configured,
									'Webhook secret'
								)}
								type="password"
							/>
						</div>
						<label
							class="flex items-center gap-2 text-sm text-muted-foreground"
							for="clear-plex-webhook"
							><Checkbox bind:checked={clearPlexWebhookSecret} id="clear-plex-webhook" /> Clear webhook
							secret</label
						>
						<Button
							class="w-full"
							disabled={saving || testing.plex}
							onclick={() => void testService('plex')}
							type="button"
							variant="outline"
							>{#if testing.plex}<LoaderCircle class="animate-spin" />{:else}<PlugZap />{/if} Test Plex</Button
						>
						{#if testResults.plex}<p class:text-destructive={!testResults.plex.ok} class="text-sm">
								{testResults.plex.message}
							</p>{/if}
					</section>

					<section class="space-y-4 rounded-xl border p-4">
						<div class="flex items-center justify-between gap-2">
							<div>
								<h3 class="font-semibold">Ollama</h3>
								<p class="text-sm text-muted-foreground">Local recommendation model.</p>
							</div>
							<Switch bind:checked={settings.recommendations.ollama.enabled} id="ollama-enabled" />
						</div>
						<Badge
							variant={settings.recommendations.ollama.api_key_configured ? 'secondary' : 'outline'}
							>{settings.recommendations.ollama.api_key_configured
								? 'Key configured'
								: 'No key required'}</Badge
						>
						<div class="space-y-2">
							<Label for="ollama-url">Server URL</Label><Input
								bind:value={settings.recommendations.ollama.url}
								id="ollama-url"
								type="url"
							/>
						</div>
						<div class="space-y-2">
							<Label for="ollama-model">Model</Label><Input
								bind:value={settings.recommendations.ollama.model}
								id="ollama-model"
								placeholder="llama3.2"
							/>
						</div>
						<div class="space-y-2">
							<Label for="ollama-key">API key (optional)</Label><Input
								bind:value={ollamaApiKey}
								disabled={clearOllamaApiKey}
								id="ollama-key"
								placeholder={secretPlaceholder(
									settings.recommendations.ollama.api_key_configured,
									'API key'
								)}
								type="password"
							/>
						</div>
						<div class="grid grid-cols-2 gap-3">
							<div class="space-y-2">
								<Label for="ollama-timeout">Timeout</Label><Input
									bind:value={settings.recommendations.ollama.request_timeout_seconds}
									id="ollama-timeout"
									max="900"
									min="1"
									type="number"
								/>
							</div>
							<div class="space-y-2">
								<Label for="ollama-keepalive">Keep alive</Label><Input
									bind:value={settings.recommendations.ollama.keep_alive}
									id="ollama-keepalive"
									placeholder="5m"
								/>
							</div>
						</div>
						<div class="flex items-center justify-between gap-3">
							<Label for="ollama-ssl">Verify TLS certificate</Label><Switch
								bind:checked={settings.recommendations.ollama.verify_ssl}
								id="ollama-ssl"
							/>
						</div>
						<label
							class="flex items-center gap-2 text-sm text-muted-foreground"
							for="clear-ollama-key"
							><Checkbox bind:checked={clearOllamaApiKey} id="clear-ollama-key" /> Clear saved API key</label
						>
						<Button
							class="w-full"
							disabled={saving || testing.ollama}
							onclick={() => void testService('ollama')}
							type="button"
							variant="outline"
							>{#if testing.ollama}<LoaderCircle class="animate-spin" />{:else}<PlugZap />{/if} Test Ollama</Button
						>
						{#if testResults.ollama}<p
								class:text-destructive={!testResults.ollama.ok}
								class="text-sm"
							>
								{testResults.ollama.message}
							</p>{/if}
					</section>
				</div>
			</Card.Content>
			<Card.Footer class="flex justify-end border-t pt-6">
				<Button disabled={saving} type="submit">
					{#if saving}<LoaderCircle class="animate-spin" />{:else}<Save />{/if}
					Save all integrations
				</Button>
			</Card.Footer>
		</Card.Root>
	</form>
{:else if integrationError}
	<Alert.Root variant="destructive">
		<Server class="size-4" />
		<Alert.Title>Integration settings are unavailable</Alert.Title>
		<Alert.Description>{integrationError}</Alert.Description>
	</Alert.Root>
{/if}

<Card.Root id="recommendation-profile">
	<Card.Header>
		<div class="flex flex-wrap items-center justify-between gap-3">
			<div>
				<Card.Title class="flex items-center gap-2"
					><UserRoundCog class="size-5" />My recommendation profile</Card.Title
				>
				<Card.Description>
					Map this MediaManager account to your Plex or Tautulli identity. This controls whose watch
					history is used for personal picks.
				</Card.Description>
			</div>
			<Badge variant={mapping.configured ? 'secondary' : 'outline'}
				>{mapping.configured ? 'Mapped' : 'Not mapped'}</Badge
			>
		</div>
	</Card.Header>
	<Card.Content>
		{#if mappingError}
			<Alert.Root class="mb-4" variant="destructive">
				<Alert.Title>Profile could not be loaded</Alert.Title>
				<Alert.Description>{mappingError}</Alert.Description>
			</Alert.Root>
		{/if}
		<form
			class="space-y-4"
			onsubmit={(event) => {
				event.preventDefault();
				void saveMapping();
			}}
		>
			<div class="flex items-center justify-between gap-3 rounded-lg border p-3">
				<div>
					<Label for="mapping-enabled">Use personal viewing history</Label>
					<p class="text-sm text-muted-foreground">
						Disable this to pause personalized recommendations for your account.
					</p>
				</div>
				<Switch bind:checked={mapping.enabled} id="mapping-enabled" />
			</div>
			<div class="grid gap-4 md:grid-cols-3">
				<div class="space-y-2">
					<Label for="mapping-tautulli">Tautulli user ID</Label>
					<Input
						bind:value={mapping.tautulli_user_id}
						id="mapping-tautulli"
						placeholder="For example: 1"
					/>
				</div>
				<div class="space-y-2">
					<Label for="mapping-plex-id">Plex account ID</Label>
					<Input
						bind:value={mapping.plex_account_id}
						id="mapping-plex-id"
						placeholder="Plex account ID"
					/>
				</div>
				<div class="space-y-2">
					<Label for="mapping-plex-name">Plex username</Label>
					<Input
						bind:value={mapping.plex_username}
						id="mapping-plex-name"
						placeholder="Plex username or email"
					/>
				</div>
			</div>
			<div class="flex justify-end">
				<Button disabled={savingMapping} type="submit">
					{#if savingMapping}<LoaderCircle class="animate-spin" />{:else}<Save />{/if}
					Save recommendation profile
				</Button>
			</div>
		</form>
	</Card.Content>
</Card.Root>
