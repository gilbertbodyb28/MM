<script lang="ts">
	import { Separator } from '$lib/components/ui/separator/index.js';
	import * as Sidebar from '$lib/components/ui/sidebar/index.js';
	import * as Breadcrumb from '$lib/components/ui/breadcrumb/index.js';
	import PosterCard from '$lib/components/media/poster-card.svelte';
	import { resolve } from '$app/paths';
	import ImportCandidatesDialog from '$lib/components/import-media/import-candidates-dialog.svelte';
	import DetectedMediaCard from '$lib/components/import-media/detected-media-card.svelte';
	import type { MediaImportSuggestion } from '$lib/api/api';
	import { getContext } from 'svelte';
	import type { PageProps } from './$types';
	import LoadingBar from '$lib/components/loading-bar.svelte';

	let { data }: PageProps = $props();
	let importableShows: () => MediaImportSuggestion[] = getContext('importableShows');
</script>

<svelte:head>
	<title>TV Shows - MediaManager</title>
	<meta content="Browse and manage your TV show collection in MediaManager" name="description" />
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
					<Breadcrumb.Link href={resolve('/dashboard', {})}>Home</Breadcrumb.Link>
				</Breadcrumb.Item>
				<Breadcrumb.Separator class="hidden md:block" />
				<Breadcrumb.Item>
					<Breadcrumb.Page>Shows</Breadcrumb.Page>
				</Breadcrumb.Item>
			</Breadcrumb.List>
		</Breadcrumb.Root>
	</div>
</header>
<main class="flex w-full flex-col gap-4 p-4 pt-0">
	<h1 class="scroll-m-20 text-center text-4xl font-extrabold tracking-tight lg:text-5xl">
		TV Shows
	</h1>
	{#if importableShows().length > 0}
		<div
			class="grid w-full auto-rows-min gap-4 sm:grid-cols-1 lg:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-4"
		>
			{#each importableShows() as importable (importable.directory)}
				<DetectedMediaCard isTv={true} directory={importable.directory}>
					<ImportCandidatesDialog
						isTv={true}
						name={importable.directory}
						candidates={importable.candidates}
					>
						Import TV show
					</ImportCandidatesDialog>
				</DetectedMediaCard>
			{/each}
		</div>
	{/if}
	{#await data.tvShows}
		<LoadingBar />
	{:then tvShows}
		<div class="media-poster-grid">
			{#each tvShows as show (show.id)}
				<PosterCard
					title={show.name}
					year={show.year}
					mediaId={show.id}
					href={resolve('/dashboard/tv/[showId]', { showId: show.id! })}
				/>
			{:else}
				<div class="col-span-full text-center text-muted-foreground">No TV shows added yet.</div>
			{/each}
		</div>
	{/await}
</main>
