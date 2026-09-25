<script lang="ts">
	import { Separator } from '$lib/components/ui/separator/index.js';
	import * as Sidebar from '$lib/components/ui/sidebar/index.js';
	import * as Breadcrumb from '$lib/components/ui/breadcrumb/index.js';
	import PosterCard from '$lib/components/media/poster-card.svelte';
	import { resolve } from '$app/paths';
	import type { MediaImportSuggestion } from '$lib/api/api';
	import ImportCandidatesDialog from '$lib/components/import-media/import-candidates-dialog.svelte';
	import DetectedMediaCard from '$lib/components/import-media/detected-media-card.svelte';
	import { getContext } from 'svelte';
	import type { PageProps } from './$types';
	import LoadingBar from '$lib/components/loading-bar.svelte';

	let { data }: PageProps = $props();
	let importableMovies: () => MediaImportSuggestion[] = getContext('importableMovies');
</script>

<svelte:head>
	<title>Movies - MediaManager</title>
	<meta content="Browse and manage your movie collection in MediaManager" name="description" />
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
					<Breadcrumb.Page>Movies</Breadcrumb.Page>
				</Breadcrumb.Item>
			</Breadcrumb.List>
		</Breadcrumb.Root>
	</div>
</header>
<main class="flex w-full flex-1 flex-col gap-4 p-4 pt-0">
	<h1 class="scroll-m-20 text-center text-4xl font-extrabold tracking-tight lg:text-5xl">Movies</h1>
	{#if importableMovies().length > 0}
		<div
			class="grid w-full auto-rows-min gap-4 sm:grid-cols-1 lg:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-4"
		>
			{#each importableMovies() as importable (importable.directory)}
				<DetectedMediaCard isTv={false} directory={importable.directory}>
					<ImportCandidatesDialog
						isTv={false}
						name={importable.directory}
						candidates={importable.candidates}
					>
						Import movie
					</ImportCandidatesDialog>
				</DetectedMediaCard>
			{/each}
		</div>
	{/if}
	{#await data.movies}
		<LoadingBar />
	{:then movies}
		<div class="media-poster-grid">
			{#each movies as movie (movie.id)}
				<PosterCard
					title={movie.name}
					year={movie.year}
					mediaId={movie.id}
					href={resolve('/dashboard/movies/[movieId]', { movieId: movie.id! })}
				/>
			{:else}
				<div class="col-span-full text-center text-muted-foreground">No movies added yet.</div>
			{/each}
		</div>
	{/await}
</main>
