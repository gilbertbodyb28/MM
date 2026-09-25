<script lang="ts">
	import { Clock3, Film, Sparkles, Tv } from 'lucide-svelte';
	import type { RecommendationItem } from './types';

	let { item }: { item: RecommendationItem } = $props();

	const mediaLabel = $derived(item.media_type === 'show' ? 'TV show' : 'Movie');
</script>

<article
	class="flex min-w-0 flex-col rounded-xl border bg-background p-4 shadow-sm"
	aria-label={`${item.name}, metadata match pending`}
>
	<div class="flex items-start justify-between gap-3">
		<div class="flex min-w-0 items-center gap-2 text-xs font-medium text-muted-foreground">
			{#if item.media_type === 'show'}
				<Tv class="size-3.5 shrink-0" aria-hidden="true" />
			{:else}
				<Film class="size-3.5 shrink-0" aria-hidden="true" />
			{/if}
			<span>{mediaLabel}{item.year ? ` · ${item.year}` : ''}</span>
		</div>
		<span
			class="inline-flex shrink-0 items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[10px] font-semibold text-amber-700 dark:text-amber-300"
		>
			<Clock3 class="size-3" aria-hidden="true" /> Pending
		</span>
	</div>

	<div class="mt-3 flex items-start gap-2">
		<Sparkles class="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
		<div class="min-w-0">
			<h3 class="text-base leading-tight font-semibold break-words">{item.name}</h3>
			<p class="mt-2 text-sm leading-relaxed text-muted-foreground">{item.reason}</p>
		</div>
	</div>

	{#if item.genres?.length}
		<div class="mt-3 flex flex-wrap gap-1.5" aria-label="Genres">
			{#each item.genres.slice(0, 5) as genre (genre)}
				<span class="rounded-full bg-muted px-2 py-1 text-[10px] text-muted-foreground">
					{genre}
				</span>
			{/each}
		</div>
	{/if}

	<p class="mt-auto pt-4 text-xs text-muted-foreground">
		Metadata match pending — this recommendation cannot be added yet.
	</p>
</article>
