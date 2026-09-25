<script lang="ts">
	import { Separator } from '$lib/components/ui/separator/index.js';
	import * as Sidebar from '$lib/components/ui/sidebar/index.js';
	import * as Breadcrumb from '$lib/components/ui/breadcrumb/index.js';
	import StatCard from '$lib/components/stats/stat-cards.svelte';
	import RecommendedMediaCarousel from '$lib/components/recommended-media-carousel.svelte';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import client from '$lib/api';
	import type { MetaDataProviderSearchResult } from '$lib/api/api.d.ts';
	import type { PageProps } from './$types';
	let { data }: PageProps = $props();
	let recommendedShows: MetaDataProviderSearchResult[] = $state([]);
	let showsLoading = $state(true);
	let showsUnavailable = $state(false);

	let recommendedMovies: MetaDataProviderSearchResult[] = $state([]);
	let moviesLoading = $state(true);
	let moviesUnavailable = $state(false);

	async function loadRecommendedShows(): Promise<void> {
		try {
			const { data, error } = await client.GET('/api/v1/tv/recommended');
			recommendedShows = Array.isArray(data) ? data : [];
			showsUnavailable = Boolean(error) || !Array.isArray(data);
		} catch {
			recommendedShows = [];
			showsUnavailable = true;
		} finally {
			showsLoading = false;
		}
	}

	async function loadRecommendedMovies(): Promise<void> {
		try {
			const { data, error } = await client.GET('/api/v1/movies/recommended');
			recommendedMovies = Array.isArray(data) ? data : [];
			moviesUnavailable = Boolean(error) || !Array.isArray(data);
		} catch {
			recommendedMovies = [];
			moviesUnavailable = true;
		} finally {
			moviesLoading = false;
		}
	}

	onMount(() => {
		void Promise.allSettled([loadRecommendedShows(), loadRecommendedMovies()]);
	});
</script>

<svelte:head>
	<title>Dashboard - MediaManager</title>
	<meta
		content="MediaManager Dashboard - View your recommended movies and TV shows"
		name="description"
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
					<Breadcrumb.Page>Home</Breadcrumb.Page>
				</Breadcrumb.Item>
			</Breadcrumb.List>
		</Breadcrumb.Root>
	</div>
</header>
<div class="flex flex-1 flex-col gap-4 p-4 pt-0">
	<h1 class="scroll-m-20 text-center text-4xl font-extrabold tracking-tight lg:text-5xl">
		Dashboard
	</h1>
	<main class="min-h-screen flex-1 items-center justify-center rounded-xl p-4 md:min-h-min">
		<div class="mx-auto">
			<div class="my-8 block text-2xl">Welcome to MediaManager!</div>
			<StatCard showCount={data.tvShows?.length ?? 0} moviesCount={data.movies?.length ?? 0}
			></StatCard>
		</div>
		<div class="mx-auto">
			<h3 class="my-4 text-center text-2xl font-semibold">Trending Shows</h3>
			<RecommendedMediaCarousel
				canConfigure={Boolean(data.user?.is_superuser)}
				isLoading={showsLoading}
				isShow={true}
				isUnavailable={showsUnavailable}
				media={recommendedShows}
			/>

			<h3 class="my-4 text-center text-2xl font-semibold">Trending Movies</h3>
			<RecommendedMediaCarousel
				canConfigure={Boolean(data.user?.is_superuser)}
				isLoading={moviesLoading}
				isShow={false}
				isUnavailable={moviesUnavailable}
				media={recommendedMovies}
			/>
		</div>
	</main>
</div>
