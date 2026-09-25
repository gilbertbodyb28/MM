<script lang="ts">
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import MediaRow from '$lib/components/discover/media-row.svelte';
	import type { DiscoverMediaItem } from '$lib/components/discover/types';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import * as Breadcrumb from '$lib/components/ui/breadcrumb';
	import * as Sidebar from '$lib/components/ui/sidebar';
	import { AlertTriangle, BrainCircuit, LoaderCircle, RefreshCw, Settings2 } from 'lucide-svelte';
	import { toast } from 'svelte-sonner';

	interface RecommendationSectionItem {
		recommendation_id: string;
		name: string;
		media_type: 'movie' | 'show';
		year: number | null;
		external_id: number;
		metadata_provider: 'tmdb';
		poster_path: string | null;
		added: boolean;
		media_id: string | null;
		score: number;
		rank: number;
	}

	interface RecommendationSection {
		section_id: string;
		source_title: string;
		source_media_type: 'movie' | 'show';
		source_year: number | null;
		reason: string;
		rank: number;
		candidates_considered: number;
		generated_at: string;
		items: RecommendationSectionItem[];
	}

	interface SectionCollection {
		sections: RecommendationSection[];
		section_count: number;
		item_count: number;
		generated_at: string | null;
	}

	interface RecommendationStatus {
		enabled: boolean;
		mapped: boolean;
		tautulli_configured: boolean;
		plex_configured: boolean;
		history_item_count: number;
	}

	let collection = $state<SectionCollection | null>(null);
	let recommendationStatus = $state<RecommendationStatus | null>(null);
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state<string | null>(null);
	let unauthorized = $state(false);

	onMount(() => void loadPage());

	function apiError(status: number, payload: unknown, fallback: string): string {
		if (payload && typeof payload === 'object' && 'detail' in payload) {
			const detail = (payload as { detail?: unknown }).detail;
			if (typeof detail === 'string') return detail;
		}
		if (status === 429) return 'The recommendation provider is rate limited. Try again shortly.';
		if (status >= 500) return 'The recommendation service is temporarily unavailable.';
		return fallback;
	}

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
			// A status-specific message below is more useful than a JSON parse error.
		}
		if (response.status === 401 || response.status === 403) unauthorized = true;
		if (!response.ok) {
			throw new Error(apiError(response.status, payload, 'AI Recommendations could not be loaded.'));
		}
		return payload as T;
	}

	async function loadPage() {
		loading = true;
		error = null;
		unauthorized = false;
		try {
			const [status, sections] = await Promise.all([
				requestJson<RecommendationStatus>('/api/v1/recommendations/status'),
				requestJson<SectionCollection>('/api/v1/recommendations/sections?limit=20')
			]);
			recommendationStatus = status;
			collection = sections;
		} catch (caught) {
			error = caught instanceof Error ? caught.message : 'AI Recommendations could not be loaded.';
		} finally {
			loading = false;
		}
	}

	async function refreshRecommendations() {
		refreshing = true;
		error = null;
		try {
			collection = await requestJson<SectionCollection>(
				'/api/v1/recommendations/sections/refresh',
				{ method: 'POST' }
			);
			toast.success(
				`Generated ${collection.item_count} new recommendations in ${collection.section_count} sections.`
			);
		} catch (caught) {
			error = caught instanceof Error ? caught.message : 'Recommendations could not be refreshed.';
			toast.error(error);
		} finally {
			refreshing = false;
		}
	}

	function toMediaItem(item: RecommendationSectionItem): DiscoverMediaItem {
		return {
			id: item.media_id,
			external_id: item.external_id,
			media_type: item.media_type === 'show' ? 'tv' : 'movie',
			name: item.name,
			original_name: null,
			overview: null,
			poster_path: item.poster_path,
			backdrop_path: null,
			year: item.year,
			release_date: item.year ? `${item.year}-01-01` : null,
			vote_average: null,
			vote_count: 0,
			popularity: null,
			genre_ids: [],
			original_language: null,
			metadata_provider: item.metadata_provider,
			adult: false,
			added: item.added
		};
	}

	function markAdded(sectionId: string, updated: DiscoverMediaItem) {
		if (!collection) return;
		collection = {
			...collection,
			sections: collection.sections.map((section) =>
				section.section_id !== sectionId
					? section
					: {
							...section,
							items: section.items.map((item) =>
								item.external_id === updated.external_id &&
								item.media_type === (updated.media_type === 'tv' ? 'show' : 'movie')
									? { ...item, added: true, media_id: updated.id }
									: item
							)
						}
			)
		};
	}
</script>

<svelte:head>
	<title>AI Recommendations - MediaManager</title>
	<meta
		name="description"
		content="Personalized movie and TV recommendations based on verified Plex viewing history"
	/>
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
				<Breadcrumb.Item><Breadcrumb.Page>AI Recommendations</Breadcrumb.Page></Breadcrumb.Item>
			</Breadcrumb.List>
		</Breadcrumb.Root>
		<Button
			class="ml-auto"
			disabled={loading || refreshing || !recommendationStatus?.enabled || !recommendationStatus?.mapped}
			onclick={refreshRecommendations}
		>
			{#if refreshing}<LoaderCircle class="animate-spin" /> Generating{:else}<RefreshCw /> Refresh{/if}
		</Button>
	</div>
</header>

<main class="mx-auto flex w-full max-w-[100rem] flex-1 flex-col gap-8 p-4 pb-16 md:p-6">
	<section class="ai-recommendations-hero overflow-hidden rounded-3xl border p-6 md:p-9">
		<div class="relative z-10 max-w-3xl">
			<div class="mb-3 flex items-center gap-2 text-sm font-semibold text-primary">
				<BrainCircuit class="size-5" /> Personal to your history
			</div>
			<h1 class="text-3xl font-bold tracking-tight md:text-5xl">AI Recommendations</h1>
			<p class="mt-3 max-w-2xl text-muted-foreground md:text-lg">
				Every rail starts with something you actually watched. Existing Plex titles and previous
				recommendations are filtered on the server before anything reaches this page.
			</p>
			{#if collection?.generated_at}
				<p class="mt-4 text-xs text-muted-foreground">
					Last generated {new Date(collection.generated_at).toLocaleString()}
				</p>
			{/if}
		</div>
	</section>

	{#if loading}
		<div class="space-y-10" aria-live="polite" aria-label="Loading recommendations">
			{#each Array.from({ length: 3 }) as _, index (index)}
				<MediaRow title="Loading personalized section" items={[]} loading />
			{/each}
		</div>
	{:else if unauthorized}
		<div class="state-panel">
			<AlertTriangle />
			<h2>Sign in required</h2>
			<p>Your session cannot access personalized recommendations. Sign in again and retry.</p>
		</div>
	{:else if !recommendationStatus?.enabled || !recommendationStatus?.mapped}
		<div class="state-panel">
			<Settings2 />
			<h2>Connect your viewing history</h2>
			<p>
				Enable recommendations and map your Plex or Tautulli identity in Settings. Credentials
				stay on the backend.
			</p>
			<Button href={resolve('/dashboard/settings', {})}><Settings2 /> Open Settings</Button>
		</div>
	{:else if error && !collection?.sections.length}
		<div class="state-panel border-destructive/35 bg-destructive/5">
			<AlertTriangle class="text-destructive" />
			<h2>Recommendations unavailable</h2>
			<p>{error}</p>
			<div class="flex flex-wrap justify-center gap-2">
				<Button onclick={loadPage} variant="outline">Try again</Button>
				<Button href={resolve('/dashboard/settings', {})}>Check Settings</Button>
			</div>
		</div>
	{:else if !collection?.sections.length}
		<div class="state-panel">
			<BrainCircuit />
			<h2>Ready to learn your taste</h2>
			<p>
				Your history connection is ready. Generate the first set of verified recommendations.
			</p>
			<Button disabled={refreshing} onclick={refreshRecommendations}>
				{#if refreshing}<LoaderCircle class="animate-spin" />{:else}<RefreshCw />{/if}
				Generate recommendations
			</Button>
		</div>
	{:else}
		{#if error}
			<div class="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
				{error} The last successful recommendations remain visible.
			</div>
		{/if}
		<div class="space-y-11">
			{#each collection.sections as section (section.section_id)}
				<MediaRow
					title={`Because you watched ${section.source_title}`}
					subtitle={`${section.reason} ${section.items.length} verified titles from ${section.candidates_considered} candidates.`}
					items={section.items.map(toMediaItem)}
					onAdded={(item) => markAdded(section.section_id, item)}
				/>
			{/each}
		</div>
	{/if}
</main>

<style>
	.ai-recommendations-hero {
		position: relative;
		background:
			radial-gradient(circle at 82% 22%, color-mix(in oklab, var(--primary) 26%, transparent), transparent 34%),
			linear-gradient(135deg, color-mix(in oklab, var(--card) 93%, transparent), color-mix(in oklab, var(--primary) 8%, var(--card)));
	}

	.ai-recommendations-hero::after {
		position: absolute;
		inset: auto -4rem -7rem auto;
		width: 20rem;
		aspect-ratio: 1;
		border: 1px solid color-mix(in oklab, var(--primary) 24%, transparent);
		border-radius: 999px;
		box-shadow: 0 0 6rem color-mix(in oklab, var(--primary) 16%, transparent);
		content: '';
	}

	.state-panel {
		display: flex;
		min-height: 21rem;
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
