<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import * as Sheet from '$lib/components/ui/sheet';
	import { Slider } from '$lib/components/ui/slider';
	import { RotateCcw } from 'lucide-svelte';
	import {
		cloneDiscoverFilters,
		DEFAULT_DISCOVER_FILTERS,
		DISCOVER_CATEGORY_LABELS,
		type DiscoverCategory,
		type DiscoverFilters,
		type DiscoverGenre,
		type DiscoverMediaType
	} from './types';

	let {
		open = $bindable(false),
		filters,
		movieGenres = [],
		tvGenres = [],
		onApply
	}: {
		open: boolean;
		filters: DiscoverFilters;
		movieGenres?: DiscoverGenre[];
		tvGenres?: DiscoverGenre[];
		onApply: (filters: DiscoverFilters) => void;
	} = $props();

	let draft = $state<DiscoverFilters>(cloneDiscoverFilters(DEFAULT_DISCOVER_FILTERS));
	let ratingRange = $state<number[]>([
		DEFAULT_DISCOVER_FILTERS.rating_min,
		DEFAULT_DISCOVER_FILTERS.rating_max
	]);
	let wasOpen = false;

	const availableGenres = $derived(
		draft.media_type === 'movie'
			? movieGenres
			: draft.media_type === 'tv'
				? tvGenres
				: [...movieGenres, ...tvGenres].filter(
						(genre, index, all) => all.findIndex((entry) => entry.id === genre.id) === index
					)
	);

	$effect(() => {
		if (open && !wasOpen) {
			draft = cloneDiscoverFilters(filters);
			ratingRange = [filters.rating_min, filters.rating_max];
		}
		wasOpen = open;
	});

	function selectMediaType(mediaType: DiscoverMediaType) {
		draft.media_type = mediaType;
		draft.genres = [];
	}

	function toggleGenre(id: number, checked: boolean) {
		draft.genres = checked
			? [...draft.genres, id]
			: draft.genres.filter((genreId) => genreId !== id);
	}

	function selectCategory(category: DiscoverCategory) {
		draft.category = category;
		if (category !== 'discover') {
			draft.sort_by = DEFAULT_DISCOVER_FILTERS.sort_by;
		}
	}

	function clearAll() {
		draft = cloneDiscoverFilters(DEFAULT_DISCOVER_FILTERS);
		ratingRange = [DEFAULT_DISCOVER_FILTERS.rating_min, DEFAULT_DISCOVER_FILTERS.rating_max];
	}

	function apply() {
		onApply({
			...cloneDiscoverFilters(draft),
			rating_min: ratingRange[0] ?? 1,
			rating_max: ratingRange[1] ?? 10
		});
		open = false;
	}
</script>

<Sheet.Root bind:open>
	<Sheet.Content class="flex w-full flex-col gap-0 p-0 sm:max-w-md" side="right">
		<Sheet.Header class="border-b px-6 py-5 text-left">
			<Sheet.Title class="text-2xl">Filters</Sheet.Title>
			<Sheet.Description>Refine your discovery results.</Sheet.Description>
		</Sheet.Header>

		<div class="flex-1 space-y-6 overflow-y-auto px-6 py-5">
			<fieldset class="space-y-2">
				<legend class="text-sm font-semibold">Media type</legend>
				<div class="grid grid-cols-3 overflow-hidden rounded-md border">
					{#each [['all', 'All'], ['movie', 'Movies'], ['tv', 'TV Shows']] as option (option[0])}
						<button
							type="button"
							class="h-10 border-r text-sm font-medium transition last:border-r-0 {draft.media_type ===
							option[0]
								? 'bg-primary text-primary-foreground'
								: 'bg-background hover:bg-accent'}"
							onclick={() => selectMediaType(option[0] as DiscoverMediaType)}
						>
							{option[1]}
						</button>
					{/each}
				</div>
			</fieldset>

			<fieldset class="space-y-2">
				<legend class="text-sm font-semibold">Release year</legend>
				<div class="grid grid-cols-2 gap-3">
					<div class="space-y-1.5">
						<Label for="discover-year-from">From</Label><Input
							id="discover-year-from"
							type="number"
							min="1870"
							max="2100"
							placeholder="From"
							bind:value={draft.year_from}
						/>
					</div>
					<div class="space-y-1.5">
						<Label for="discover-year-to">To</Label><Input
							id="discover-year-to"
							type="number"
							min="1870"
							max="2100"
							placeholder="To"
							bind:value={draft.year_to}
						/>
					</div>
				</div>
			</fieldset>

			<fieldset class="space-y-2">
				<legend class="text-sm font-semibold">Genres</legend>
				<div
					class="grid max-h-44 grid-cols-2 gap-x-3 gap-y-2 overflow-y-auto rounded-md border p-3"
				>
					{#each availableGenres as genre (genre.id)}
						<label class="flex cursor-pointer items-center gap-2 text-sm">
							<input
								type="checkbox"
								class="size-4 rounded border-input accent-primary"
								checked={draft.genres.includes(genre.id)}
								onchange={(event) => toggleGenre(genre.id, event.currentTarget.checked)}
							/>
							<span>{genre.name}</span>
						</label>
					{/each}
				</div>
			</fieldset>

			<fieldset class="space-y-3">
				<div class="flex items-center justify-between">
					<legend class="text-sm font-semibold">TMDB rating</legend>
					<span class="text-sm text-muted-foreground"
						>{ratingRange[0] ?? 1}–{ratingRange[1] ?? 10}</span
					>
				</div>
				<Slider type="multiple" bind:value={ratingRange} min={1} max={10} step={0.5} />
				<div class="flex justify-between text-xs text-muted-foreground">
					<span>1</span><span>10</span>
				</div>
			</fieldset>

			<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
				<div class="space-y-2">
					<Label for="discover-category">Category</Label>
					<select
						id="discover-category"
						class="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus:ring-1 focus:ring-ring focus:outline-none"
						value={draft.category}
						onchange={(event) => selectCategory(event.currentTarget.value as DiscoverCategory)}
					>
						<option value="discover">All catalog</option>
						<option value="popular">Popular</option>
						<option value="upcoming">Upcoming</option>
						<option value="top_rated">Top rated</option>
						<option value="trending">Trending</option>
					</select>
				</div>
				<div class="space-y-2">
					{#if draft.category === 'discover'}
						<Label for="discover-sort">Order</Label>
						<select
							id="discover-sort"
							class="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus:ring-1 focus:ring-ring focus:outline-none"
							bind:value={draft.sort_by}
						>
							<option value="popularity.desc">Popularity</option>
							<option value="vote_average.desc">Rating</option>
							<option value="release_date.desc">Newest</option>
							<option value="release_date.asc">Oldest</option>
						</select>
					{:else}
						<Label>Order</Label>
						<div
							class="flex h-9 w-full items-center rounded-md border border-input bg-muted/40 px-3 text-sm text-muted-foreground shadow-sm"
						>
							Curated feed order
						</div>
					{/if}
				</div>
			</div>

			{#if draft.category !== 'discover'}
				<p
					class="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs leading-relaxed"
				>
					<strong>{DISCOVER_CATEGORY_LABELS[draft.category]}</strong> is a curated feed. If you also select
					year, genre, rating, or adult-content filters, Media Manager will switch to All catalog when
					you apply them so the result stays accurate.
				</p>
			{/if}

			<label class="flex cursor-pointer items-center gap-2 text-sm">
				<input
					type="checkbox"
					class="size-4 rounded border-input accent-primary"
					bind:checked={draft.include_adult}
				/>
				<span>Include adult content</span>
			</label>
		</div>

		<Sheet.Footer class="grid grid-cols-2 gap-3 border-t px-6 py-5 sm:grid-cols-2">
			<Button variant="outline" onclick={clearAll}><RotateCcw /> Clear all</Button>
			<Button onclick={apply}>Apply filters</Button>
		</Sheet.Footer>
	</Sheet.Content>
</Sheet.Root>
