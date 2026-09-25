<script lang="ts">
	import AddMediaCard from '$lib/components/add-media-card.svelte';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Button } from '$lib/components/ui/button';
	import { ChevronRight, DatabaseZap, Settings } from 'lucide-svelte';
	import type { MetaDataProviderSearchResult } from '$lib/api/api';
	import { resolve } from '$app/paths';

	let {
		media = [],
		isShow,
		isLoading,
		isUnavailable = false,
		canConfigure = false
	}: {
		media: MetaDataProviderSearchResult[];
		isShow: boolean;
		isLoading: boolean;
		isUnavailable?: boolean;
		canConfigure?: boolean;
	} = $props();

	let safeMedia = $derived(Array.isArray(media) ? media : []);
</script>

<div class="media-poster-grid">
	{#if isLoading}
		<Skeleton class="media-poster-skeleton" />
		<Skeleton class="media-poster-skeleton" />
		<Skeleton class="media-poster-skeleton" />
	{:else if isUnavailable}
		<div
			class="col-span-full flex min-h-48 flex-col items-center justify-center gap-3 rounded-xl border border-dashed p-6 text-center"
		>
			<DatabaseZap class="size-8 text-muted-foreground" />
			<div class="space-y-1">
				<h4 class="font-semibold">Metadata is not available yet</h4>
				<p class="max-w-xl text-sm text-muted-foreground">
					{canConfigure
						? 'Configure TMDB or TVDB in Settings to load trending titles and recommendations.'
						: 'Ask an administrator to configure the TMDB or TVDB metadata provider.'}
				</p>
			</div>
			{#if canConfigure}
				<Button href={resolve('/dashboard/settings', {}) + '#metadata'} variant="outline">
					<Settings />
					Open metadata settings
				</Button>
			{/if}
		</div>
	{:else if safeMedia.length === 0}
		<div
			class="col-span-full rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground"
		>
			No new {isShow ? 'shows' : 'movies'} are available right now.
		</div>
	{:else}
		{#each safeMedia.slice(0, 3) as mediaItem (mediaItem.external_id)}
			<AddMediaCard {isShow} result={mediaItem} />
		{/each}
	{/if}
</div>
{#if !isUnavailable}
	<div class="mt-4 flex justify-center">
		<Button
			variant="secondary"
			href={isShow
				? resolve('/dashboard/tv/add-show', {})
				: resolve('/dashboard/movies/add-movie', {})}
		>
			More recommendations
			<ChevronRight />
		</Button>
	</div>
{/if}
