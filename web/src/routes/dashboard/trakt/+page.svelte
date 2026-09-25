<script lang="ts">
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { getContext, onMount } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import type { UserRead } from '$lib/api/api';
	import { emitMediaAddedSuccess } from '$lib/celebration';
	import PosterCard from '$lib/components/media/poster-card.svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { Separator } from '$lib/components/ui/separator';
	import * as Breadcrumb from '$lib/components/ui/breadcrumb';
	import * as Sidebar from '$lib/components/ui/sidebar';
	import {
		AlertTriangle,
		Check,
		CircleUserRound,
		Film,
		ListChecks,
		LoaderCircle,
		LogIn,
		LogOut,
		RefreshCw,
		Settings2,
		Tv
	} from 'lucide-svelte';
	import { toast } from 'svelte-sonner';

	type Source = 'watchlist' | 'collection' | 'history' | 'lists';
	type MediaFilter = 'all' | 'movie' | 'show';

	interface TraktStatus {
		configured: boolean;
		connected: boolean;
		username: string | null;
		slug: string | null;
		expires_at: string | null;
	}

	interface TraktItem {
		key: string;
		media_type: 'movie' | 'show';
		title: string;
		year: number | null;
		poster_path: string | null;
		ids: { trakt: number | null; imdb: string | null; tmdb: number | null; tvdb: number | null };
		sources: string[];
	}

	interface TraktCollection {
		source: Source;
		items: TraktItem[];
		total: number;
	}

	interface ImportResult {
		imported: number;
		failed: number;
		results: Array<{
			media_type: 'movie' | 'show';
			tmdb_id: number;
			title: string;
			success: boolean;
			already_added: boolean;
			media_id: string | null;
			error: string | null;
		}>;
	}

	const currentUser: () => UserRead = getContext('user');
	const sourceOptions: Array<{ value: Source; label: string; description: string }> = [
		{ value: 'watchlist', label: 'Watchlist', description: 'Titles saved for later' },
		{ value: 'collection', label: 'Collection', description: 'Your Trakt collection' },
		{ value: 'history', label: 'History', description: 'Watched titles' },
		{ value: 'lists', label: 'Lists', description: 'Items from your personal lists' }
	];

	let status = $state<TraktStatus | null>(null);
	let items = $state<TraktItem[]>([]);
	let source = $state<Source>('watchlist');
	let mediaFilter = $state<MediaFilter>('all');
	let selected = $state(new SvelteSet<string>());
	let loadingStatus = $state(true);
	let loadingItems = $state(false);
	let connecting = $state(false);
	let disconnecting = $state(false);
	let importing = $state(false);
	let error = $state<string | null>(null);
	let importErrors = $state<string[]>([]);

	const selectableItems = $derived(items.filter((item) => item.ids.tmdb != null));
	const selectedItems = $derived(items.filter((item) => selected.has(item.key)));

	onMount(() => {
		const outcome = page.url.searchParams.get('trakt');
		if (outcome === 'connected') toast.success('Trakt account connected.');
		if (outcome === 'error') toast.error('Trakt authorization did not complete. Try again.');
		void loadStatus();
	});

	async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
		const response = await fetch(path, {
			credentials: 'include',
			...init,
			headers: { Accept: 'application/json', ...init?.headers }
		});
		let payload: unknown = null;
		try {
			payload = await response.json();
		} catch {
			// Use the safe status-based fallback below.
		}
		if (!response.ok) {
			if (payload && typeof payload === 'object' && 'detail' in payload) {
				const detail = (payload as { detail?: unknown }).detail;
				if (typeof detail === 'string') throw new Error(detail);
			}
			if (response.status === 429) throw new Error('Trakt is rate limited. Try again shortly.');
			if (response.status === 401) throw new Error('Your Trakt session is not authorized.');
			throw new Error('Trakt is temporarily unavailable.');
		}
		return payload as T;
	}

	async function loadStatus() {
		loadingStatus = true;
		error = null;
		try {
			status = await requestJson<TraktStatus>('/api/v1/trakt/status');
			if (status.connected) await loadItems();
		} catch (caught) {
			error = caught instanceof Error ? caught.message : 'Trakt status could not be loaded.';
		} finally {
			loadingStatus = false;
		}
	}

	async function connect() {
		connecting = true;
		try {
			const data = await requestJson<{ authorization_url: string }>('/api/v1/trakt/authorize');
			window.location.assign(data.authorization_url);
		} catch (caught) {
			toast.error(caught instanceof Error ? caught.message : 'Could not start Trakt connection.');
			connecting = false;
		}
	}

	async function disconnect() {
		disconnecting = true;
		try {
			await fetch('/api/v1/trakt/connection', { method: 'DELETE', credentials: 'include' });
			status = status ? { ...status, connected: false, username: null, slug: null } : null;
			items = [];
			selected = new SvelteSet();
			toast.success('Trakt account disconnected.');
		} catch {
			toast.error('Trakt could not be disconnected.');
		} finally {
			disconnecting = false;
		}
	}

	async function loadItems(nextSource = source, nextFilter = mediaFilter) {
		source = nextSource;
		mediaFilter = nextFilter;
		loadingItems = true;
		error = null;
		selected = new SvelteSet();
		importErrors = [];
		try {
			const query = new URLSearchParams({ source, media_type: mediaFilter });
			const collection = await requestJson<TraktCollection>(`/api/v1/trakt/items?${query}`);
			items = collection.items;
		} catch (caught) {
			items = [];
			error = caught instanceof Error ? caught.message : 'Trakt items could not be loaded.';
		} finally {
			loadingItems = false;
		}
	}

	function toggle(item: TraktItem, checked: boolean) {
		const next = new SvelteSet(selected);
		if (checked) next.add(item.key);
		else next.delete(item.key);
		selected = next;
	}

	function selectAll() {
		selected = new SvelteSet(selectableItems.map((item) => item.key));
	}

	function deselectAll() {
		selected = new SvelteSet();
	}

	async function importSelected() {
		if (!currentUser().is_superuser) {
			toast.error('Only administrators can import titles into MediaManager.');
			return;
		}
		const payloadItems = selectedItems.flatMap((item) =>
			item.ids.tmdb == null
				? []
				: [{ media_type: item.media_type, tmdb_id: item.ids.tmdb, title: item.title }]
		);
		if (payloadItems.length === 0) return;
		importing = true;
		importErrors = [];
		try {
			const result = await requestJson<ImportResult>('/api/v1/trakt/import', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ items: payloadItems })
			});
			importErrors = result.results
				.filter((item) => !item.success)
				.map((item) => `${item.title}: ${item.error ?? 'Import failed.'}`);
			selected = new SvelteSet(
				selectedItems
					.filter((item) =>
						result.results.some(
							(resultItem) => !resultItem.success && resultItem.tmdb_id === item.ids.tmdb
						)
					)
					.map((item) => item.key)
			);
			if (result.imported)
				toast.success(
					`${result.imported} Trakt title${result.imported === 1 ? '' : 's'} imported.`
				);
			const createdIds = result.results
				.filter((item) => item.success && !item.already_added && item.media_id)
				.map((item) => item.media_id!)
				.toSorted();
			if (createdIds.length > 0) {
				emitMediaAddedSuccess({
					operationId: `trakt:${createdIds.join(',')}`,
					count: createdIds.length,
					source: 'trakt'
				});
			}
			if (result.failed)
				toast.error(
					`${result.failed} title${result.failed === 1 ? '' : 's'} could not be imported.`
				);
		} catch (caught) {
			toast.error(
				caught instanceof Error ? caught.message : 'Selected titles could not be imported.'
			);
		} finally {
			importing = false;
		}
	}
</script>

<svelte:head>
	<title>Trakt - MediaManager</title>
	<meta name="description" content="Connect Trakt and selectively import movies and TV shows" />
</svelte:head>

<header class="flex h-16 shrink-0 items-center gap-2">
	<div class="flex w-full items-center gap-2 px-4">
		<Sidebar.Trigger class="-ml-1" />
		<Separator class="mr-2 h-4" orientation="vertical" />
		<Breadcrumb.Root>
			<Breadcrumb.List>
				<Breadcrumb.Item class="hidden md:block">
					<Breadcrumb.Link href={resolve('/dashboard', {})}>MediaManager</Breadcrumb.Link>
				</Breadcrumb.Item>
				<Breadcrumb.Separator class="hidden md:block" />
				<Breadcrumb.Item><Breadcrumb.Page>Trakt</Breadcrumb.Page></Breadcrumb.Item>
			</Breadcrumb.List>
		</Breadcrumb.Root>
	</div>
</header>

<main class="mx-auto flex w-full max-w-[100rem] flex-1 flex-col gap-6 p-4 pb-16 md:p-6">
	<section class="trakt-hero rounded-3xl border p-6 md:p-9">
		<div class="flex flex-wrap items-start justify-between gap-6">
			<div class="max-w-3xl">
				<div class="mb-3 flex items-center gap-2 text-sm font-semibold text-primary">
					<ListChecks class="size-5" /> Selective library import
				</div>
				<h1 class="text-3xl font-bold tracking-tight md:text-5xl">Trakt</h1>
				<p class="mt-3 text-muted-foreground md:text-lg">
					Review Watchlist, Collection, History, and personal Lists. Nothing is imported until you
					select it.
				</p>
			</div>
			{#if status?.connected}
				<div class="flex items-center gap-3 rounded-2xl border bg-card/65 px-4 py-3">
					<CircleUserRound class="size-9 text-primary" />
					<div>
						<p class="font-semibold">{status.username ?? status.slug ?? 'Connected account'}</p>
						<p class="text-xs text-muted-foreground">Trakt connected</p>
					</div>
					<Button disabled={disconnecting} onclick={disconnect} size="sm" variant="outline">
						{#if disconnecting}<LoaderCircle class="animate-spin" />{:else}<LogOut />{/if}
						Disconnect
					</Button>
				</div>
			{/if}
		</div>
	</section>

	{#if loadingStatus}
		<div class="state-panel">
			<LoaderCircle class="animate-spin" />
			<p>Checking Trakt connection…</p>
		</div>
	{:else if !status?.configured}
		<div class="state-panel">
			<Settings2 />
			<h2>Trakt OAuth needs configuration</h2>
			<p>Add the Trakt client ID, client secret, and callback URL in Settings first.</p>
			<Button href={resolve('/dashboard/settings', {}) + '#trakt'}
				><Settings2 /> Open Settings</Button
			>
		</div>
	{:else if !status.connected}
		<div class="state-panel">
			<LogIn />
			<h2>Connect your Trakt account</h2>
			<p>
				Authorization happens on Trakt. MediaManager never sends your OAuth tokens to the browser.
			</p>
			<Button disabled={connecting} onclick={connect}>
				{#if connecting}<LoaderCircle class="animate-spin" /> Connecting{:else}<LogIn /> Connect Trakt
					account{/if}
			</Button>
		</div>
	{:else}
		<section class="space-y-4 rounded-2xl border bg-card/55 p-4 md:p-5">
			<div class="flex flex-wrap items-center justify-between gap-4">
				<div class="flex flex-wrap gap-2" role="tablist" aria-label="Trakt source">
					{#each sourceOptions as option (option.value)}
						<Button
							aria-selected={source === option.value}
							onclick={() => loadItems(option.value, mediaFilter)}
							role="tab"
							variant={source === option.value ? 'default' : 'outline'}
						>
							{option.label}
						</Button>
					{/each}
				</div>
				<div class="flex gap-2" role="radiogroup" aria-label="Media type">
					{#each [['all', 'All'], ['movie', 'Movies'], ['show', 'TV Shows']] as option (option[0])}
						<Button
							aria-checked={mediaFilter === option[0]}
							onclick={() => loadItems(source, option[0] as MediaFilter)}
							role="radio"
							size="sm"
							variant={mediaFilter === option[0] ? 'secondary' : 'ghost'}>{option[1]}</Button
						>
					{/each}
				</div>
			</div>
			<p class="text-sm text-muted-foreground">
				{sourceOptions.find((option) => option.value === source)?.description}. Titles without a
				TMDB ID stay visible but cannot be imported automatically.
			</p>
		</section>

		<div
			class="sticky top-3 z-20 flex flex-wrap items-center gap-2 rounded-2xl border bg-background/85 p-3 shadow-lg backdrop-blur-xl"
		>
			<Button
				disabled={selectableItems.length === 0 || loadingItems}
				onclick={selectAll}
				size="sm"
				variant="outline">Select All</Button
			>
			<Button disabled={selected.size === 0} onclick={deselectAll} size="sm" variant="ghost"
				>Deselect All</Button
			>
			<span class="mr-auto text-sm text-muted-foreground"
				>{selected.size} of {selectableItems.length} selected</span
			>
			<Button
				disabled={selected.size === 0 || importing || !currentUser().is_superuser}
				onclick={importSelected}
			>
				{#if importing}<LoaderCircle class="animate-spin" /> Importing{:else}<Check /> Import Selected{/if}
			</Button>
		</div>

		{#if !currentUser().is_superuser}
			<div class="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm">
				You can browse and select Trakt items, but an administrator must perform the import.
			</div>
		{/if}
		{#if error}
			<div class="state-panel border-destructive/35 bg-destructive/5">
				<AlertTriangle class="text-destructive" />
				<h2>Unable to load Trakt</h2>
				<p>{error}</p>
				<Button onclick={() => loadItems()} variant="outline"><RefreshCw /> Try again</Button>
			</div>
		{:else if loadingItems}
			<div class="state-panel">
				<LoaderCircle class="animate-spin" />
				<p>Loading {source}…</p>
			</div>
		{:else if items.length === 0}
			<div class="state-panel">
				<ListChecks />
				<h2>No titles here</h2>
				<p>This Trakt source is empty for the selected media type.</p>
			</div>
		{:else}
			<div class="media-poster-grid">
				{#each items as item (item.key)}
					<PosterCard title={item.title} year={item.year ?? '—'} posterPath={item.poster_path}>
						{#snippet badge()}
							<Badge class="gap-1 bg-black/70 text-white" variant="secondary">
								{#if item.media_type === 'movie'}<Film class="size-3" /> Movie{:else}<Tv
										class="size-3"
									/> TV{/if}
							</Badge>
						{/snippet}
						{#snippet actions()}
							<label
								class="flex h-10 w-full cursor-pointer items-center justify-center gap-2 rounded-md bg-primary px-3 text-sm font-semibold text-primary-foreground"
							>
								<Checkbox
									checked={selected.has(item.key)}
									disabled={item.ids.tmdb == null}
									onCheckedChange={(checked) => toggle(item, checked === true)}
								/>
								{item.ids.tmdb == null
									? 'No TMDB ID'
									: selected.has(item.key)
										? 'Selected'
										: 'Select'}
							</label>
						{/snippet}
					</PosterCard>
				{/each}
			</div>
		{/if}

		{#if importErrors.length}
			<div class="rounded-xl border border-destructive/30 bg-destructive/5 p-4">
				<h2 class="font-semibold text-destructive">Some titles were not imported</h2>
				<ul class="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
					{#each importErrors as message (message)}<li>{message}</li>{/each}
				</ul>
			</div>
		{/if}
	{/if}
</main>

<style>
	.trakt-hero {
		background:
			radial-gradient(
				circle at 85% 20%,
				color-mix(in oklab, #ed1c24 25%, transparent),
				transparent 34%
			),
			linear-gradient(
				135deg,
				color-mix(in oklab, var(--card) 92%, transparent),
				color-mix(in oklab, #ed1c24 7%, var(--card))
			);
	}

	.state-panel {
		display: flex;
		min-height: 20rem;
		align-items: center;
		justify-content: center;
		flex-direction: column;
		gap: 0.8rem;
		border: 1px dashed var(--border);
		border-radius: 1.5rem;
		padding: 2rem;
		text-align: center;
		background: color-mix(in oklab, var(--card) 82%, transparent);
	}

	.state-panel :global(svg) {
		width: 2rem;
		height: 2rem;
	}
	.state-panel h2 {
		font-size: 1.3rem;
		font-weight: 700;
	}
	.state-panel p {
		max-width: 38rem;
		color: var(--muted-foreground);
	}
</style>
