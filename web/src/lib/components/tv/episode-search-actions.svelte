<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import client from '$lib/api';
	import type { AutomationJob, IndexerQueryResult } from '$lib/api/api';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as Table from '$lib/components/ui/table';
	import { formatSecondsToOptimalUnit, getTorrentQualityString } from '$lib/utils';
	import { Download, LoaderCircle, RefreshCw, Search, SearchCheck } from 'lucide-svelte';
	import { toast } from 'svelte-sonner';

	type EpisodeTarget = {
		id: string;
		number: number;
		title: string;
		downloaded?: boolean;
	};

	let {
		showId,
		showName,
		seasonNumber,
		episode,
		job = null,
		onJobChange
	}: {
		showId: string;
		showName: string;
		seasonNumber: number;
		episode: EpisodeTarget;
		job?: AutomationJob | null;
		onJobChange?: (job: AutomationJob) => void;
	} = $props();

	let dialogOpen = $state(false);
	let releases = $state<IndexerQueryResult[] | null>(null);
	let searchError = $state<string | null>(null);
	let isSearching = $state(false);
	let isQueuing = $state(false);
	let grabbingResultId = $state<string | null>(null);

	let episodeLabel = $derived(
		`S${String(seasonNumber).padStart(2, '0')}E${String(episode.number).padStart(2, '0')}`
	);
	let activeJob = $derived(
		job?.status === 'queued' ||
			job?.status === 'searching' ||
			job?.status === 'downloading' ||
			job?.status === 'retry_wait'
	);
	let automaticSearchTitle = $derived(
		job?.status_message
			? `Automatic Search — ${job.status_message}`
			: 'Automatic Search — let MediaManager choose the best release in the background'
	);

	function errorMessage(error: unknown, fallback: string): string {
		if (typeof error === 'object' && error !== null && 'detail' in error) {
			const detail = (error as { detail?: unknown }).detail;
			if (typeof detail === 'string') return detail;
		}
		return fallback;
	}

	function formatSize(bytes: number): string {
		if (!Number.isFinite(bytes) || bytes <= 0) return 'Unknown';
		const gibibytes = bytes / 1024 / 1024 / 1024;
		return gibibytes >= 0.1
			? `${gibibytes.toFixed(2)} GB`
			: `${(bytes / 1024 / 1024).toFixed(0)} MB`;
	}

	async function interactiveSearch() {
		dialogOpen = true;
		isSearching = true;
		searchError = null;
		releases = null;
		try {
			const { data, error, response } = await client.GET(
				'/api/v1/tv/shows/{show_id}/episodes/{episode_id}/releases',
				{
					params: { path: { show_id: showId, episode_id: episode.id } }
				}
			);
			if (!response.ok || error) {
				throw new Error(errorMessage(error, `Interactive search failed (${response.status}).`));
			}
			releases = data ?? [];
			if (releases.length === 0) toast.info(`No exact releases found for ${episodeLabel}.`);
		} catch (error) {
			searchError = error instanceof Error ? error.message : 'Interactive search failed.';
			toast.error(searchError);
		} finally {
			isSearching = false;
		}
	}

	async function grabRelease(result: IndexerQueryResult) {
		if (!result.id) return;
		grabbingResultId = result.id;
		searchError = null;
		try {
			const { error, response } = await client.POST(
				'/api/v1/tv/shows/{show_id}/episodes/{episode_id}/releases/{result_id}/grab',
				{
					params: {
						path: { show_id: showId, episode_id: episode.id, result_id: result.id }
					}
				}
			);
			if (!response.ok || error) {
				throw new Error(
					errorMessage(error, `The release could not be grabbed (${response.status}).`)
				);
			}
			dialogOpen = false;
			toast.success(`${episodeLabel} was sent to the download client.`);
			await invalidateAll();
		} catch (error) {
			searchError = error instanceof Error ? error.message : 'The release could not be grabbed.';
			toast.error(searchError);
		} finally {
			grabbingResultId = null;
		}
	}

	async function automaticSearch() {
		isQueuing = true;
		try {
			const { data, error, response } = await client.POST(
				'/api/v1/tv/shows/{show_id}/episodes/{episode_id}/automatic-search',
				{
					params: { path: { show_id: showId, episode_id: episode.id } }
				}
			);
			if (!response.ok || error || !data) {
				throw new Error(
					errorMessage(error, `Automatic search could not be queued (${response.status}).`)
				);
			}
			onJobChange?.(data);
			toast.success(`Automatic search queued for ${episodeLabel}.`);
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Automatic search could not be queued.');
		} finally {
			isQueuing = false;
		}
	}
</script>

<div class="flex items-center justify-center gap-1">
	<Button
		aria-label={`Interactive search for ${episodeLabel} ${episode.title}`}
		title="Interactive Search — inspect Prowlarr results and choose a release"
		class="size-8"
		disabled={episode.downloaded || isSearching || grabbingResultId !== null}
		onclick={interactiveSearch}
		size="icon"
		type="button"
		variant="ghost"
	>
		{#if isSearching}
			<LoaderCircle class="animate-spin" />
		{:else}
			<SearchCheck />
		{/if}
	</Button>
	<Button
		aria-label={`Automatic search for ${episodeLabel} ${episode.title}`}
		title={automaticSearchTitle}
		class={`size-8 ${
			job?.status === 'succeeded'
				? 'text-emerald-500'
				: job?.status === 'failed'
					? 'text-destructive'
					: ''
		}`}
		disabled={episode.downloaded || isQueuing || activeJob}
		onclick={automaticSearch}
		size="icon"
		type="button"
		variant="ghost"
	>
		{#if isQueuing || activeJob}
			<LoaderCircle class="animate-spin" />
		{:else}
			<Search />
		{/if}
	</Button>
	<span aria-live="polite" class="sr-only">
		{#if job?.status === 'failed'}
			Automatic search failed: {job.last_error ?? job.status_message}
		{:else if job?.status === 'succeeded'}
			Automatic search succeeded: {job.status_message}
		{:else if activeJob}
			Automatic search in progress: {job?.status_message ?? job?.status}
		{/if}
	</span>
</div>

<Dialog.Root bind:open={dialogOpen}>
	<Dialog.Content
		class="max-h-[min(90svh,58rem)] max-w-[min(96vw,90rem)] overflow-y-auto rounded-3xl p-0"
	>
		<div class="border-b bg-gradient-to-br from-primary/12 via-background to-background p-6">
			<Dialog.Header>
				<div
					class="mb-2 flex size-11 items-center justify-center rounded-2xl border bg-card shadow-sm"
				>
					<SearchCheck class="size-5" />
				</div>
				<Dialog.Title>Interactive Search · {episodeLabel}</Dialog.Title>
				<Dialog.Description>
					Inspect exact Prowlarr matches for {showName} — {episode.title}. Nothing downloads until
					you choose Grab.
				</Dialog.Description>
			</Dialog.Header>
		</div>

		<div class="space-y-4 p-6">
			<div class="flex flex-wrap items-center justify-between gap-3">
				<p class="text-sm text-muted-foreground">
					Only releases that explicitly match {episodeLabel} are shown; season packs are excluded.
				</p>
				<Button
					disabled={isSearching}
					onclick={interactiveSearch}
					size="sm"
					type="button"
					variant="outline"
				>
					{#if isSearching}<LoaderCircle class="animate-spin" />{:else}<RefreshCw />{/if}
					Search again
				</Button>
			</div>

			{#if searchError}
				<div
					class="rounded-xl border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive"
					role="alert"
				>
					{searchError}
				</div>
			{/if}

			{#if isSearching}
				<div class="flex min-h-48 items-center justify-center gap-2 text-sm text-muted-foreground">
					<LoaderCircle class="animate-spin" /> Searching Prowlarr…
				</div>
			{:else if releases}
				<div class="overflow-x-auto rounded-2xl border">
					<Table.Root>
						<Table.Header>
							<Table.Row>
								<Table.Head class="min-w-[24rem]">Release</Table.Head>
								<Table.Head>Quality</Table.Head>
								<Table.Head>Indexer</Table.Head>
								<Table.Head>Protocol</Table.Head>
								<Table.Head>Size</Table.Head>
								<Table.Head>Availability</Table.Head>
								<Table.Head>Score</Table.Head>
								<Table.Head>Flags</Table.Head>
								<Table.Head class="text-right">Action</Table.Head>
							</Table.Row>
						</Table.Header>
						<Table.Body>
							{#each releases as release (release.id)}
								<Table.Row>
									<Table.Cell class="font-medium">{release.title}</Table.Cell>
									<Table.Cell>{getTorrentQualityString(release.quality)}</Table.Cell>
									<Table.Cell>{release.indexer ?? 'Unknown'}</Table.Cell>
									<Table.Cell>{release.usenet ? 'Usenet' : 'Torrent'}</Table.Cell>
									<Table.Cell>{formatSize(release.size)}</Table.Cell>
									<Table.Cell>
										{release.usenet
											? release.age > 0
												? formatSecondsToOptimalUnit(release.age)
												: 'Unknown age'
											: `${release.seeders} seeders`}
									</Table.Cell>
									<Table.Cell>{release.score}</Table.Cell>
									<Table.Cell>
										<div class="flex max-w-56 flex-wrap gap-1">
											{#each release.flags as flag (flag)}
												<Badge variant="outline">{flag}</Badge>
											{/each}
											{#if release.flags.length === 0}<span class="text-muted-foreground">—</span
												>{/if}
										</div>
									</Table.Cell>
									<Table.Cell class="text-right">
										<Button
											disabled={!release.id || grabbingResultId !== null}
											onclick={() => grabRelease(release)}
											size="sm"
											type="button"
										>
											{#if grabbingResultId === release.id}<LoaderCircle
													class="animate-spin"
												/>{:else}<Download />{/if}
											Grab
										</Button>
									</Table.Cell>
								</Table.Row>
							{:else}
								<Table.Row>
									<Table.Cell class="h-32 text-center text-muted-foreground" colspan={9}>
										No exact releases were found. Try Search again after your indexers refresh.
									</Table.Cell>
								</Table.Row>
							{/each}
						</Table.Body>
					</Table.Root>
				</div>
			{/if}
		</div>
	</Dialog.Content>
</Dialog.Root>
