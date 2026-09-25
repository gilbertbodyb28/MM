<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { getContext } from 'svelte';
	import client from '$lib/api';
	import { emitMediaAddedSuccess } from '$lib/celebration';
	import type { UserRead } from '$lib/api/api';
	import AddSeriesDialog from '$lib/components/add-series-dialog.svelte';
	import PosterCard from '$lib/components/media/poster-card.svelte';
	import SeerrRequestButton from '$lib/components/seerr-request-button.svelte';
	import { Button } from '$lib/components/ui/button';
	import { Check, Film, LoaderCircle, LockKeyhole, Plus, Tv } from 'lucide-svelte';
	import { toast } from 'svelte-sonner';
	import type { DiscoverMediaItem } from './types';

	let {
		item,
		onAdded
	}: {
		item: DiscoverMediaItem;
		onAdded?: (item: DiscoverMediaItem) => void;
	} = $props();

	let loading = $state(false);
	let addedOverride = $state<boolean | null>(null);
	let internalIdOverride = $state<string | null>(null);
	const currentUser: (() => UserRead) | undefined = getContext('user');

	const isShow = $derived(item.media_type === 'tv');
	const added = $derived(addedOverride ?? item.added);
	const internalId = $derived(internalIdOverride ?? item.id);
	const canAdd = $derived(currentUser ? currentUser().is_superuser : false);
	const year = $derived(item.year ?? item.release_date?.slice(0, 4) ?? '—');
	const mediaHref = $derived(
		internalId
			? resolve(
					isShow ? '/dashboard/tv/[showId]' : '/dashboard/movies/[movieId]',
					isShow ? { showId: internalId } : { movieId: internalId }
				)
			: null
	);

	async function openMedia(id: string) {
		await goto(
			resolve(
				isShow ? '/dashboard/tv/[showId]' : '/dashboard/movies/[movieId]',
				isShow ? { showId: id } : { movieId: id }
			)
		);
	}

	async function addMovie() {
		if (!canAdd) {
			toast.info('Only administrators can add new titles.');
			return;
		}

		loading = true;
		try {
			const response = await client.POST('/api/v1/movies', {
				params: {
					query: {
						movie_id: item.external_id,
						metadata_provider: item.metadata_provider,
						language: item.original_language ?? undefined
					}
				}
			});

			if (response.error || !response.data?.id) {
				throw new Error('Media Manager could not add this title.');
			}

			internalIdOverride = response.data.id;
			addedOverride = true;
			onAdded?.({ ...item, id: internalIdOverride, added: true });
			toast.success(`${item.name} was added to your library.`);
			if (response.response.status === 201) {
				emitMediaAddedSuccess({
					operationId: `movie:${response.data.id}`,
					count: 1,
					source: 'discover'
				});
			}
		} catch (error) {
			console.error('Failed to add media from Discover', error);
			toast.error(error instanceof Error ? error.message : 'Failed to add media.');
		} finally {
			loading = false;
		}
	}

	function seriesAdded(show: { id: string }) {
		internalIdOverride = show.id;
		addedOverride = true;
		onAdded?.({ ...item, id: show.id, added: true });
	}
</script>

<PosterCard title={item.name} {year} posterPath={item.poster_path} href={mediaHref}>
	{#snippet badge()}
		<span
			class="flex items-center gap-1 rounded-full border border-white/30 bg-black/65 px-2 py-1 text-[10px] font-semibold tracking-wide text-white uppercase backdrop-blur-sm"
		>
			{#if isShow}<Tv class="size-3" /> TV{:else}<Film class="size-3" /> Movie{/if}
		</span>
	{/snippet}
	{#snippet status()}
		{#if added}
			<span
				class="grid size-8 place-items-center rounded-full border border-white/30 bg-emerald-600/90 text-white shadow"
				title="Already in your library"
			>
				<Check class="size-4" aria-hidden="true" />
			</span>
		{/if}
	{/snippet}
	{#snippet actions()}
		{#if internalId}
			<Button class="h-9 w-full" size="sm" onclick={() => openMedia(internalId)}>
				<Check /> Open
			</Button>
		{:else if canAdd && isShow}
			<AddSeriesDialog
				class="h-9 w-full"
				compact
				candidate={item}
				label="Add"
				onAdded={seriesAdded}
			/>
		{:else if canAdd}
			<Button class="h-9 w-full" size="sm" disabled={loading} onclick={addMovie}>
				{#if loading}<LoaderCircle class="animate-spin" /> Loading{:else}<Plus /> Add{/if}
			</Button>
		{:else}
			<div
				class="flex h-9 w-full items-center justify-center gap-2 rounded-md border border-white/25 bg-black/55 text-xs font-medium text-white/80"
				title="Only administrators can add new titles"
			>
				<LockKeyhole class="size-3.5" aria-hidden="true" /> Admin only
			</div>
		{/if}
		{#if !added}
			<SeerrRequestButton
				class="h-9 w-full border-white/25 bg-black/55 text-white hover:bg-black/75 hover:text-white"
				mediaType={isShow ? 'tv' : 'movie'}
				tmdbId={item.external_id}
			/>
		{/if}
	{/snippet}
</PosterCard>
