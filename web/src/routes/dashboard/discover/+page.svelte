<script lang="ts">
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import client from '$lib/api';
	import FilterSheet from '$lib/components/discover/filter-sheet.svelte';
	import MediaCard from '$lib/components/discover/media-card.svelte';
	import MediaRow from '$lib/components/discover/media-row.svelte';
	import {
		cloneDiscoverFilters,
		DEFAULT_DISCOVER_FILTERS,
		DISCOVER_CATEGORY_LABELS,
		hasAdvancedCatalogFilters,
		type DiscoverCategory,
		type DiscoverFilters,
		type DiscoverGenre,
		type DiscoverMediaItem,
		type DiscoverMediaType,
		type DiscoverPage
	} from '$lib/components/discover/types';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Separator } from '$lib/components/ui/separator';
	import * as Breadcrumb from '$lib/components/ui/breadcrumb';
	import * as Sidebar from '$lib/components/ui/sidebar';
	import {
		ChevronLeft,
		ChevronRight,
		Filter,
		LoaderCircle,
		RefreshCw,
		Search,
		Sparkles,
		X
	} from 'lucide-svelte';
	import { toast } from 'svelte-sonner';

	type CategoryEndpoint = Exclude<DiscoverCategory, 'discover'>;

	interface BrowseSnapshot {
		query: string;
		filters: DiscoverFilters;
	}

	let landingLoading = $state(true);
	let landingError = $state<string | null>(null);
	let trending = $state<DiscoverMediaItem[]>([]);
	let upcoming = $state<DiscoverMediaItem[]>([]);
	let popularMovies = $state<DiscoverMediaItem[]>([]);
	let popularShows = $state<DiscoverMediaItem[]>([]);
	let topRated = $state<DiscoverMediaItem[]>([]);

	let movieGenres = $state<DiscoverGenre[]>([]);
	let tvGenres = $state<DiscoverGenre[]>([]);
	let filters = $state<DiscoverFilters>(cloneDiscoverFilters(DEFAULT_DISCOVER_FILTERS));
	let filterSheetOpen = $state(false);
	let searchQuery = $state('');
	let browsing = $state(false);
	let results = $state<DiscoverMediaItem[]>([]);
	let resultsLoading = $state(false);
	let resultsError = $state<string | null>(null);
	let resultPage = $state(1);
	let resultTotalPages = $state(0);
	let resultTotalResults = $state(0);
	let appliedBrowse = $state<BrowseSnapshot | null>(null);

	let browseRequestId = 0;

	const activeFilterCount = $derived(
		(filters.year_from == null ? 0 : 1) +
			(filters.year_to == null ? 0 : 1) +
			filters.genres.length +
			(filters.rating_min === DEFAULT_DISCOVER_FILTERS.rating_min ? 0 : 1) +
			(filters.rating_max === DEFAULT_DISCOVER_FILTERS.rating_max ? 0 : 1) +
			(filters.category === DEFAULT_DISCOVER_FILTERS.category ? 0 : 1) +
			(filters.sort_by === DEFAULT_DISCOVER_FILTERS.sort_by ? 0 : 1) +
			(filters.include_adult ? 1 : 0)
	);
	const appliedQuery = $derived(appliedBrowse?.query ?? '');
	const appliedCategory = $derived(appliedBrowse?.filters.category ?? filters.category);
	const resultHeading = $derived(
		appliedQuery ? `Results for “${appliedQuery}”` : DISCOVER_CATEGORY_LABELS[appliedCategory]
	);
	const resultSourceDescription = $derived(describeBrowseSource(appliedBrowse));

	onMount(() => {
		void Promise.all([loadLanding(), loadGenres()]);
	});

	function errorMessage(error: unknown, fallback: string): string {
		if (error instanceof Error) return error.message;
		if (typeof error === 'string') return error;
		if (error && typeof error === 'object' && 'detail' in error) {
			const detail = (error as { detail?: unknown }).detail;
			if (typeof detail === 'string') return detail;
		}
		return fallback;
	}

	function describeBrowseSource(snapshot: BrowseSnapshot | null): string {
		if (!snapshot) return 'Preparing your results.';
		if (snapshot.query) {
			return hasAdvancedCatalogFilters(snapshot.filters)
				? 'Search filters are applied to the titles returned on each results page.'
				: 'TMDB title search.';
		}
		if (snapshot.filters.category === 'discover') {
			return 'Full catalog with provider-side filters.';
		}
		return `${DISCOVER_CATEGORY_LABELS[snapshot.filters.category]} curated feed.`;
	}

	function unwrapPage(
		response: { data?: unknown; error?: unknown },
		fallback: string
	): DiscoverPage {
		if (response.error || !response.data) {
			throw new Error(errorMessage(response.error, fallback));
		}
		return response.data as DiscoverPage;
	}

	async function getCategory(
		category: CategoryEndpoint,
		mediaType: 'movie' | 'tv',
		page = 1
	): Promise<DiscoverPage> {
		const query = { media_type: mediaType, page } as const;
		switch (category) {
			case 'trending':
				return unwrapPage(
					await client.GET('/api/v1/discover/trending', { params: { query } }),
					'Could not load trending titles.'
				);
			case 'upcoming':
				return unwrapPage(
					await client.GET('/api/v1/discover/upcoming', { params: { query } }),
					'Could not load upcoming titles.'
				);
			case 'top_rated':
				return unwrapPage(
					await client.GET('/api/v1/discover/top-rated', { params: { query } }),
					'Could not load top-rated titles.'
				);
			case 'popular':
				return unwrapPage(
					await client.GET('/api/v1/discover/popular', { params: { query } }),
					'Could not load popular titles.'
				);
		}
	}

	function mergePages(...pages: DiscoverPage[]): DiscoverMediaItem[] {
		const merged: DiscoverMediaItem[] = [];
		const seen = new SvelteSet<string>();
		const longest = Math.max(0, ...pages.map((page) => page.results.length));

		for (let index = 0; index < longest; index += 1) {
			for (const page of pages) {
				const item = page.results[index];
				if (!item) continue;
				const key = `${item.metadata_provider}-${item.media_type}-${item.external_id}`;
				if (!seen.has(key)) {
					seen.add(key);
					merged.push(item);
				}
			}
		}
		return merged;
	}

	async function loadLanding() {
		landingLoading = true;
		landingError = null;
		try {
			const [
				trendingMovies,
				trendingShows,
				upcomingMovies,
				upcomingShows,
				movies,
				shows,
				topMovies,
				topShows
			] = await Promise.all([
				getCategory('trending', 'movie'),
				getCategory('trending', 'tv'),
				getCategory('upcoming', 'movie'),
				getCategory('upcoming', 'tv'),
				getCategory('popular', 'movie'),
				getCategory('popular', 'tv'),
				getCategory('top_rated', 'movie'),
				getCategory('top_rated', 'tv')
			]);

			trending = mergePages(trendingMovies, trendingShows);
			upcoming = mergePages(upcomingMovies, upcomingShows);
			popularMovies = movies.results;
			popularShows = shows.results;
			topRated = mergePages(topMovies, topShows);
		} catch (error) {
			landingError = errorMessage(error, 'Discover could not be loaded.');
		} finally {
			landingLoading = false;
		}
	}

	async function loadGenres() {
		try {
			const [movieResponse, tvResponse] = await Promise.all([
				client.GET('/api/v1/discover/genres', {
					params: { query: { media_type: 'movie' } }
				}),
				client.GET('/api/v1/discover/genres', {
					params: { query: { media_type: 'tv' } }
				})
			]);

			if (!movieResponse.error && movieResponse.data) movieGenres = movieResponse.data;
			if (!tvResponse.error && tvResponse.data) tvGenres = tvResponse.data;
		} catch (error) {
			console.warn('Discover genres could not be loaded', error);
			movieGenres = [];
			tvGenres = [];
		}
	}

	function filteredQuery(
		mediaType: 'movie' | 'tv',
		page: number,
		selectedFilters: DiscoverFilters
	) {
		return {
			media_type: mediaType,
			page,
			year_from: selectedFilters.year_from ?? undefined,
			year_to: selectedFilters.year_to ?? undefined,
			genres: selectedFilters.genres.length > 0 ? selectedFilters.genres : undefined,
			rating_min:
				selectedFilters.rating_min === DEFAULT_DISCOVER_FILTERS.rating_min
					? undefined
					: selectedFilters.rating_min,
			rating_max:
				selectedFilters.rating_max === DEFAULT_DISCOVER_FILTERS.rating_max
					? undefined
					: selectedFilters.rating_max,
			sort_by: selectedFilters.sort_by,
			include_adult: selectedFilters.include_adult
		};
	}

	async function getFilteredPage(
		mediaType: 'movie' | 'tv',
		page: number,
		snapshot: BrowseSnapshot
	): Promise<DiscoverPage> {
		if (snapshot.query) {
			return unwrapPage(
				await client.GET('/api/v1/discover/search', {
					params: {
						query: {
							...filteredQuery(mediaType, page, snapshot.filters),
							query: snapshot.query
						}
					}
				}),
				'Could not search Discover.'
			);
		}

		if (snapshot.filters.category !== 'discover') {
			return getCategory(snapshot.filters.category, mediaType, page);
		}

		return unwrapPage(
			await client.GET('/api/v1/discover', {
				params: {
					query: {
						...filteredQuery(mediaType, page, snapshot.filters),
						category: 'discover'
					}
				}
			}),
			'Could not browse Discover.'
		);
	}

	function createBrowseSnapshot(query = searchQuery, selectedFilters = filters): BrowseSnapshot {
		return {
			query: query.trim(),
			filters: cloneDiscoverFilters(selectedFilters)
		};
	}

	async function runBrowse(page = 1, requestedSnapshot?: BrowseSnapshot) {
		const requestId = ++browseRequestId;
		const snapshot = requestedSnapshot
			? createBrowseSnapshot(requestedSnapshot.query, requestedSnapshot.filters)
			: createBrowseSnapshot();
		browsing = true;
		resultsLoading = true;
		resultsError = null;
		resultPage = page;
		appliedBrowse = snapshot;
		try {
			const mediaTypes: ('movie' | 'tv')[] =
				snapshot.filters.media_type === 'all' ? ['movie', 'tv'] : [snapshot.filters.media_type];
			const pages = await Promise.all(
				mediaTypes.map((mediaType) => getFilteredPage(mediaType, page, snapshot))
			);
			if (requestId !== browseRequestId) return;
			results = mergePages(...pages);
			resultTotalPages = Math.max(0, ...pages.map((result) => result.total_pages));
			resultTotalResults = snapshot.query
				? results.length
				: pages.reduce((total, result) => total + result.total_results, 0);
		} catch (error) {
			if (requestId !== browseRequestId) return;
			results = [];
			resultTotalPages = 0;
			resultTotalResults = 0;
			resultsError = errorMessage(error, 'Discover search failed.');
		} finally {
			if (requestId === browseRequestId) resultsLoading = false;
		}
	}

	function normalizeFiltersForBrowse(
		selectedFilters: DiscoverFilters,
		query: string
	): DiscoverFilters {
		const normalizedFilters = cloneDiscoverFilters(selectedFilters);
		if (normalizedFilters.category === 'discover') return normalizedFilters;

		const categoryLabel = DISCOVER_CATEGORY_LABELS[normalizedFilters.category];
		if (query.trim()) {
			normalizedFilters.category = 'discover';
			toast.info(
				`${categoryLabel} is a curated feed and does not change title search. Search will use All catalog.`
			);
		} else if (hasAdvancedCatalogFilters(normalizedFilters)) {
			normalizedFilters.category = 'discover';
			toast.info(
				`${categoryLabel} is a curated feed. Switched to All catalog so every advanced filter is applied accurately.`
			);
		}
		return normalizedFilters;
	}

	function submitSearch(event: SubmitEvent) {
		event.preventDefault();
		filters = normalizeFiltersForBrowse(filters, searchQuery);
		void runBrowse(1);
	}

	function setMediaType(mediaType: DiscoverMediaType) {
		filters = { ...cloneDiscoverFilters(filters), media_type: mediaType, genres: [] };
		if (browsing) void runBrowse(1);
	}

	function applyFilters(nextFilters: DiscoverFilters) {
		filters = normalizeFiltersForBrowse(nextFilters, searchQuery);
		void runBrowse(1);
	}

	function showCategory(category: CategoryEndpoint, mediaType: DiscoverMediaType = 'all') {
		searchQuery = '';
		filters = {
			...cloneDiscoverFilters(DEFAULT_DISCOVER_FILTERS),
			category,
			media_type: mediaType
		};
		void runBrowse(1);
	}

	function closeResults() {
		browseRequestId += 1;
		browsing = false;
		resultsLoading = false;
		searchQuery = '';
		results = [];
		resultsError = null;
		appliedBrowse = null;
	}

	function changeResultPage(page: number) {
		void runBrowse(page, appliedBrowse ?? undefined);
	}

	function markAdded(item: DiscoverMediaItem) {
		const update = (items: DiscoverMediaItem[]) =>
			items.map((candidate) =>
				candidate.external_id === item.external_id &&
				candidate.media_type === item.media_type &&
				candidate.metadata_provider === item.metadata_provider
					? { ...candidate, id: item.id, added: true }
					: candidate
			);
		trending = update(trending);
		upcoming = update(upcoming);
		popularMovies = update(popularMovies);
		popularShows = update(popularShows);
		topRated = update(topRated);
		results = update(results);
	}
</script>

<svelte:head>
	<title>Discover - MediaManager</title>
	<meta
		name="description"
		content="Discover trending, upcoming, popular and top-rated movies and TV shows."
	/>
</svelte:head>

<header class="flex h-16 shrink-0 items-center gap-2">
	<div class="flex items-center gap-2 px-4">
		<Sidebar.Trigger class="-ml-1" />
		<Separator class="mr-2 h-4" orientation="vertical" />
		<Breadcrumb.Root>
			<Breadcrumb.List>
				<Breadcrumb.Item class="hidden md:block">
					<Breadcrumb.Link href={resolve('/dashboard', {})}>MediaManager</Breadcrumb.Link>
				</Breadcrumb.Item>
				<Breadcrumb.Separator class="hidden md:block" />
				<Breadcrumb.Item>
					<Breadcrumb.Page>Discover</Breadcrumb.Page>
				</Breadcrumb.Item>
			</Breadcrumb.List>
		</Breadcrumb.Root>
	</div>
</header>

<main
	class="glass-discover flex min-w-0 flex-1 flex-col gap-8 overflow-hidden p-4 pt-0 md:p-6 md:pt-0"
	data-theme-region="discover"
>
	<section class="rounded-2xl border bg-card px-4 py-6 shadow-sm md:px-8 md:py-8">
		<div class="mx-auto max-w-5xl">
			<div
				class="mb-3 inline-flex items-center gap-1.5 rounded-full border bg-muted/50 px-3 py-1 text-xs font-medium text-muted-foreground"
			>
				<Sparkles class="size-3.5 text-primary" /> Movies, shows and recommendations
			</div>
			<h1 class="text-3xl font-bold tracking-tight md:text-4xl">Discover something great</h1>
			<p class="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground md:text-base">
				Explore what is trending, find upcoming releases, or search the complete catalog with
				advanced filters.
			</p>

			<form class="mt-6 flex flex-col gap-3 lg:flex-row" onsubmit={submitSearch}>
				<div class="relative min-w-0 flex-1">
					<Search
						class="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
					/>
					<Input
						class="h-11 pr-10 pl-9"
						placeholder="Search movies and TV shows..."
						aria-label="Search movies and TV shows"
						bind:value={searchQuery}
					/>
					{#if searchQuery}
						<button
							type="button"
							class="absolute top-1/2 right-3 -translate-y-1/2 text-muted-foreground hover:text-foreground"
							onclick={() => (searchQuery = '')}
							aria-label="Clear search"
						>
							<X class="size-4" />
						</button>
					{/if}
				</div>

				<div class="grid h-11 grid-cols-3 overflow-hidden rounded-md border bg-background">
					{#each [['all', 'All'], ['movie', 'Movies'], ['tv', 'TV']] as option (option[0])}
						<button
							type="button"
							class="min-w-20 border-r px-3 text-sm font-medium transition last:border-r-0 {filters.media_type ===
							option[0]
								? 'bg-primary text-primary-foreground'
								: 'hover:bg-accent'}"
							onclick={() => setMediaType(option[0] as DiscoverMediaType)}
						>
							{option[1]}
						</button>
					{/each}
				</div>

				<Button
					type="button"
					variant="outline"
					class="h-11"
					onclick={() => (filterSheetOpen = true)}
				>
					<Filter /> Filters
					{#if activeFilterCount > 0}
						<span class="rounded-full bg-primary px-1.5 py-0.5 text-[10px] text-primary-foreground"
							>{activeFilterCount}</span
						>
					{/if}
				</Button>
				<Button type="submit" class="h-11" disabled={resultsLoading}>
					{#if resultsLoading}<LoaderCircle class="animate-spin" />{:else}<Search />{/if}
					Search
				</Button>
			</form>
		</div>
	</section>

	{#if browsing}
		<section class="min-w-0">
			<div class="mb-5 flex flex-wrap items-end justify-between gap-3">
				<div class="min-w-0">
					<div class="flex min-w-0 flex-wrap items-center gap-2">
						<h2 class="min-w-0 text-2xl font-semibold tracking-tight break-words">
							{resultHeading}
						</h2>
						{#if !resultsLoading}
							<span class="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">
								{resultTotalResults.toLocaleString()}
								{appliedQuery ? 'on this page' : 'titles'}
							</span>
						{/if}
					</div>
					<p class="mt-1 text-sm text-muted-foreground">
						{resultSourceDescription} Page {resultPage}{resultTotalPages > 0
							? ` of ${resultTotalPages}`
							: ''}.
					</p>
				</div>
				<Button variant="ghost" onclick={closeResults}><X /> Back to Discover</Button>
			</div>

			{#if resultsError}
				<div class="rounded-xl border border-destructive/30 bg-destructive/5 p-6 text-destructive">
					<p class="font-medium">{resultsError}</p>
					<Button class="mt-4" variant="outline" onclick={() => changeResultPage(resultPage)}>
						<RefreshCw /> Try again
					</Button>
				</div>
			{:else if resultsLoading}
				<div class="flex min-h-80 items-center justify-center text-muted-foreground">
					<LoaderCircle class="mr-2 size-5 animate-spin" /> Loading titles...
				</div>
			{:else if results.length === 0}
				<div
					class="flex min-h-80 flex-col items-center justify-center rounded-xl border border-dashed"
				>
					<Search class="mb-3 size-8 text-muted-foreground" />
					<p class="font-medium">No matching titles</p>
					<p class="mt-1 text-sm text-muted-foreground">Try a wider year range or fewer filters.</p>
				</div>
			{:else}
				<div
					class="media-poster-grid"
				>
					{#each results as item (`${item.metadata_provider}-${item.media_type}-${item.external_id}`)}
						<MediaCard {item} onAdded={markAdded} />
					{/each}
				</div>

				<div class="mt-8 flex items-center justify-center gap-2">
					<Button
						variant="outline"
						disabled={resultPage <= 1 || resultsLoading}
						onclick={() => changeResultPage(resultPage - 1)}
					>
						<ChevronLeft /> Previous
					</Button>
					<span class="min-w-24 text-center text-sm text-muted-foreground">
						{resultPage} / {Math.max(1, resultTotalPages)}
					</span>
					<Button
						variant="outline"
						disabled={resultPage >= resultTotalPages || resultsLoading}
						onclick={() => changeResultPage(resultPage + 1)}
					>
						Next <ChevronRight />
					</Button>
				</div>
			{/if}
		</section>
	{:else}
		<section class="space-y-8 pb-8">
			{#if landingError}
				<div class="rounded-xl border border-destructive/30 bg-destructive/5 p-5 text-destructive">
					<div class="flex flex-wrap items-center justify-between gap-3">
						<p>{landingError}</p>
						<div class="flex flex-wrap gap-2">
							<Button href={resolve('/dashboard/settings', {}) + '#metadata'} variant="outline">
								Configure metadata
							</Button>
							<Button variant="outline" onclick={loadLanding}><RefreshCw /> Try again</Button>
						</div>
					</div>
				</div>
			{/if}

			<MediaRow
				title="Trending now"
				items={trending}
				loading={landingLoading}
				onSeeAll={() => showCategory('trending')}
				onAdded={markAdded}
			/>
			<MediaRow
				title="Coming soon"
				items={upcoming}
				loading={landingLoading}
				onSeeAll={() => showCategory('upcoming')}
				onAdded={markAdded}
			/>
			<MediaRow
				title="Popular movies"
				items={popularMovies}
				loading={landingLoading}
				onSeeAll={() => showCategory('popular', 'movie')}
				onAdded={markAdded}
			/>
			<MediaRow
				title="Popular TV"
				items={popularShows}
				loading={landingLoading}
				onSeeAll={() => showCategory('popular', 'tv')}
				onAdded={markAdded}
			/>
			<MediaRow
				title="Top rated"
				items={topRated}
				loading={landingLoading}
				onSeeAll={() => showCategory('top_rated')}
				onAdded={markAdded}
			/>
		</section>
	{/if}
</main>

<FilterSheet
	bind:open={filterSheetOpen}
	{filters}
	{movieGenres}
	{tvGenres}
	onApply={applyFilters}
/>
