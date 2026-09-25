<script lang="ts">
	import { Button, buttonVariants } from '$lib/components/ui/button/index.js';
	import * as Dialog from '$lib/components/ui/dialog/index.js';
	import { toast } from 'svelte-sonner';
	import client from '$lib/api';
	import type { MetaDataProviderSearchResult } from '$lib/api/api';
	import { Spinner } from '$lib/components/ui/spinner';
	import SuggestedMediaCard from '$lib/components/import-media/suggested-media-card.svelte';
	import { invalidateAll } from '$app/navigation';
	import { emitMediaAddedSuccess } from '$lib/celebration';

	let {
		isTv,
		name,
		candidates,
		children
	}: {
		isTv: boolean;
		name: string;
		candidates: MetaDataProviderSearchResult[];
		children: any;
	} = $props();
	let dialogOpen = $state(false);
	let submitRequestError = $state<string | null>(null);
	let isImporting = $state<boolean>(false);

	async function handleImportMedia(media: MetaDataProviderSearchResult) {
		isImporting = true;
		submitRequestError = null;
		try {
			let created = false;
			let mediaId: string;
			if (isTv) {
				const addResponse = await client.POST('/api/v1/tv/shows', {
					params: {
						query: {
							metadata_provider: media.metadata_provider as 'tmdb' | 'tvdb',
							show_id: media.external_id
						}
					}
				});
				if (addResponse.error || !addResponse.data?.id) throw new Error('Failed to add show.');
				created = addResponse.response.status === 201;
				mediaId = addResponse.data.id;
				const importResponse = await client.POST('/api/v1/tv/importable/{show_id}', {
					params: {
						path: { show_id: mediaId },
						query: { directory: name }
					}
				});
				if (importResponse.error) throw new Error('Failed to import show.');
			} else {
				const addResponse = await client.POST('/api/v1/movies', {
					params: {
						query: {
							metadata_provider: media.metadata_provider as 'tmdb' | 'tvdb',
							movie_id: media.external_id
						}
					}
				});
				if (addResponse.error || !addResponse.data?.id) throw new Error('Failed to add movie.');
				created = addResponse.response.status === 201;
				mediaId = addResponse.data.id;
				const importResponse = await client.POST('/api/v1/movies/importable/{movie_id}', {
					params: {
						path: { movie_id: mediaId },
						query: { directory: name }
					}
				});
				if (importResponse.error) throw new Error('Failed to import movie.');
			}

			if (created) {
				emitMediaAddedSuccess({
					operationId: `${isTv ? 'show' : 'movie'}:${mediaId}`,
					count: 1,
					source: 'library-import'
				});
			}
			toast.success('Imported successfully!');
			await invalidateAll();
			dialogOpen = false;
		} catch (error) {
			submitRequestError = error instanceof Error ? error.message : 'Failed to import.';
			toast.error(submitRequestError);
		} finally {
			isImporting = false;
		}
	}
</script>

<Dialog.Root bind:open={dialogOpen}>
	<Dialog.Trigger
		class={buttonVariants({ variant: 'default' })}
		onclick={() => {
			dialogOpen = true;
		}}
	>
		{@render children?.()}
	</Dialog.Trigger>
	<Dialog.Content class="max-h-[90vh] w-fit min-w-[80vw] overflow-y-auto">
		<Dialog.Header>
			<Dialog.Title>Import unknown {isTv ? 'show' : 'movie'} "{name}"</Dialog.Title>
			<Dialog.Description
				>Select the {isTv ? 'show' : 'movie'} that is in this directory to import it!
			</Dialog.Description>
		</Dialog.Header>
		<div
			class="grid w-full auto-rows-min gap-4 sm:grid-cols-1 lg:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-4"
		>
			{#if !isImporting}
				{#each candidates as candidate (candidate.external_id)}
					<SuggestedMediaCard result={candidate} action={() => handleImportMedia(candidate)}
					></SuggestedMediaCard>
				{:else}
					No {isTv ? 'shows' : 'movies'} were found, change the directory's name for better search results!
				{/each}
			{:else}
				<Spinner class="size-8"></Spinner>
			{/if}
			{#if submitRequestError}
				<p class="col-span-full text-center text-sm text-red-500">{submitRequestError}</p>
			{/if}
		</div>
		<Dialog.Footer>
			<Button disabled={isImporting} onclick={() => (dialogOpen = false)} variant="outline"
				>Cancel
			</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
