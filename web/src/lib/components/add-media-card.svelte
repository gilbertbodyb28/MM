<script lang="ts">
	import { Button } from '$lib/components/ui/button/index.js';
	import AddSeriesDialog from '$lib/components/add-series-dialog.svelte';
	import PosterCard from '$lib/components/media/poster-card.svelte';
	import { Check, LoaderCircle } from 'lucide-svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import type { MetaDataProviderSearchResult } from '$lib/api/api';
	import client from '$lib/api';
	import { emitMediaAddedSuccess } from '$lib/celebration';
	import { toast } from 'svelte-sonner';

	let loading = $state(false);
	let { result, isShow = true }: { result: MetaDataProviderSearchResult; isShow: boolean } =
		$props();
	const mediaHref = $derived(
		result.added && result.id
			? resolve(
					isShow ? '/dashboard/tv/[showId]' : '/dashboard/movies/[movieId]',
					isShow ? { showId: result.id } : { movieId: result.id }
				)
			: null
	);

	async function openAddedSeries(show: { id: string }) {
		await goto(resolve('/dashboard/tv/[showId]', { showId: show.id }), { invalidateAll: true });
	}

	async function addMovie() {
		loading = true;
		try {
			const response = await client.POST('/api/v1/movies', {
				params: {
					query: {
						movie_id: result.external_id,
						metadata_provider: result.metadata_provider as 'tmdb' | 'tvdb',
						language: result.original_language ?? undefined
					}
				}
			});
			if (response.error || !response.data?.id) {
				throw new Error('MediaManager could not add this movie.');
			}
			if (response.response.status === 201) {
				emitMediaAddedSuccess({
					operationId: `movie:${response.data.id}`,
					count: 1,
					source: 'movies'
				});
			}
			await goto(resolve('/dashboard/movies/[movieId]', { movieId: response.data.id }), {
				invalidateAll: true
			});
		} catch (error) {
			toast.error(
				error instanceof Error ? error.message : 'MediaManager could not add this movie.'
			);
		} finally {
			loading = false;
		}
	}
</script>

<PosterCard title={result.name} year={result.year} posterPath={result.poster_path} href={mediaHref}>
	{#snippet status()}
		{#if result.added}
			<span class="grid size-8 place-items-center rounded-full bg-emerald-600 text-white shadow">
				<Check class="size-4" aria-hidden="true" />
			</span>
		{/if}
	{/snippet}
	{#snippet actions()}
		{#if result.added}
			<Button
				class="w-full font-semibold"
				variant="secondary"
				href={resolve(
					isShow ? '/dashboard/tv/[showId]' : '/dashboard/movies/[movieId]',
					isShow ? { showId: result.id ?? '' } : { movieId: result.id ?? '' }
				)}
			>
				{isShow ? 'Show already exists' : 'Movie already exists'}
			</Button>
		{:else if isShow}
			<AddSeriesDialog
				class="w-full font-semibold"
				candidate={result}
				label="Add Show"
				onAdded={openAddedSeries}
			/>
		{:else}
			<Button class="w-full font-semibold" disabled={loading} onclick={addMovie}>
				{#if loading}
					<LoaderCircle class="mr-2 h-4 w-4 animate-spin" />
					<span class="animate-pulse">Loading...</span>
				{:else}
					Add Movie
				{/if}
			</Button>
		{/if}
	{/snippet}
</PosterCard>
