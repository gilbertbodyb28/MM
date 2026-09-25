<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { ChevronLeft, ChevronRight, Sparkles } from 'lucide-svelte';
	import MediaCard from './media-card.svelte';
	import type { DiscoverMediaItem } from './types';

	const SKELETON_KEYS = Array.from({ length: 8 }, (_, index) => index);

	let {
		title,
		items,
		loading = false,
		error = null,
		subtitle = null,
		onSeeAll,
		onAdded
	}: {
		title: string;
		items: DiscoverMediaItem[];
		loading?: boolean;
		error?: string | null;
		subtitle?: string | null;
		onSeeAll?: () => void;
		onAdded?: (item: DiscoverMediaItem) => void;
	} = $props();

	let scroller: HTMLDivElement | null = $state(null);

	function scroll(direction: -1 | 1) {
		scroller?.scrollBy({
			left: direction * Math.max(520, scroller.clientWidth * 0.8),
			behavior: 'smooth'
		});
	}
</script>

<section class="min-w-0" aria-labelledby={`row-${title.toLowerCase().replaceAll(' ', '-')}`}>
	<div class="mb-3 flex items-end justify-between gap-3">
		<div class="min-w-0">
			<div class="flex items-center gap-2">
				{#if subtitle}<Sparkles class="size-4 text-primary" aria-hidden="true" />{/if}
				<h2
					id={`row-${title.toLowerCase().replaceAll(' ', '-')}`}
					class="truncate text-xl font-semibold tracking-tight"
				>
					{title}
				</h2>
			</div>
			{#if subtitle}<p class="mt-0.5 text-sm text-muted-foreground">{subtitle}</p>{/if}
		</div>
		<div class="flex shrink-0 items-center gap-1">
			{#if onSeeAll}
				<Button variant="ghost" size="sm" onclick={onSeeAll}>See all <ChevronRight /></Button>
			{/if}
			<Button
				variant="outline"
				size="icon"
				class="size-8 rounded-full"
				onclick={() => scroll(-1)}
				aria-label={`Scroll ${title} left`}
			>
				<ChevronLeft />
			</Button>
			<Button
				variant="outline"
				size="icon"
				class="size-8 rounded-full"
				onclick={() => scroll(1)}
				aria-label={`Scroll ${title} right`}
			>
				<ChevronRight />
			</Button>
		</div>
	</div>

	{#if error}
		<div
			class="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-6 text-sm text-destructive"
		>
			{error}
		</div>
	{:else}
		<div
			bind:this={scroller}
			class="media-poster-rail scrollbar-none -mx-1 px-1 pb-3"
		>
			{#if loading}
				{#each SKELETON_KEYS as key (key)}
					<div class="media-poster-rail-item">
						<Skeleton class="media-poster-skeleton" />
					</div>
				{/each}
			{:else if items.length === 0}
				<div
					class="flex min-h-44 w-full items-center justify-center rounded-lg border border-dashed text-sm text-muted-foreground"
				>
					No titles are available for this section yet.
				</div>
			{:else}
				{#each items as item (`${item.metadata_provider}-${item.media_type}-${item.external_id}`)}
					<div class="media-poster-rail-item">
						<MediaCard {item} {onAdded} />
					</div>
				{/each}
			{/if}
		</div>
	{/if}
</section>

<style>
	.scrollbar-none {
		scrollbar-width: none;
	}

	.scrollbar-none::-webkit-scrollbar {
		display: none;
	}
</style>
