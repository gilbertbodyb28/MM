<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { invalidateAll } from '$app/navigation';
	import { resolve } from '$app/paths';
	import * as Breadcrumb from '$lib/components/ui/breadcrumb/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Separator } from '$lib/components/ui/separator/index.js';
	import * as Sidebar from '$lib/components/ui/sidebar/index.js';
	import { CalendarDays, Check, Film, ImageOff, RotateCw, Tv } from 'lucide-svelte';
	import { SvelteMap } from 'svelte/reactivity';
	import type { PageProps } from './$types';
	import type { CalendarItem } from './+page';

	type CalendarFilter = 'upcoming' | 'released' | 'available';
	type CalendarGroup = { key: string; label: string; items: CalendarItem[] };

	let { data }: PageProps = $props();
	let activeFilter = $state<CalendarFilter>('upcoming');
	let refreshing = $state(false);

	const filters: { value: CalendarFilter; label: string }[] = [
		{ value: 'upcoming', label: 'Upcoming' },
		{ value: 'released', label: 'Released' },
		{ value: 'available', label: 'Available' }
	];

	const today = $derived(startOfDay(new Date()));
	const validItems = $derived(
		(data.items as CalendarItem[]).filter(
			(item) => item.release_date && !Number.isNaN(itemDate(item).getTime())
		)
	);
	const filteredItems = $derived(
		validItems
			.filter((item) => {
				const difference = dayDifference(itemDate(item), today);
				if (activeFilter === 'available') return item.available;
				if (activeFilter === 'released') return difference < 0;
				return difference >= 0;
			})
			.toSorted((left, right) => {
				const direction = activeFilter === 'released' ? -1 : 1;
				return (itemDate(left).getTime() - itemDate(right).getTime()) * direction;
			})
	);
	const groups = $derived(groupByDate(filteredItems));

	function parseDate(value: string): Date {
		return /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value);
	}

	function itemDate(item: CalendarItem): Date {
		return parseDate(item.release_date);
	}

	function startOfDay(value: Date): Date {
		return new Date(value.getFullYear(), value.getMonth(), value.getDate());
	}

	function dayDifference(value: Date, comparison: Date): number {
		return Math.round((startOfDay(value).getTime() - comparison.getTime()) / 86_400_000);
	}

	function localDateKey(value: Date): string {
		const year = value.getFullYear();
		const month = String(value.getMonth() + 1).padStart(2, '0');
		const day = String(value.getDate()).padStart(2, '0');
		return `${year}-${month}-${day}`;
	}

	function groupByDate(items: CalendarItem[]): CalendarGroup[] {
		const grouped = new SvelteMap<string, CalendarItem[]>();
		for (const item of items) {
			const key = localDateKey(itemDate(item));
			grouped.set(key, [...(grouped.get(key) ?? []), item]);
		}

		return Array.from(grouped, ([key, groupItems]) => ({
			key,
			label: dateHeading(groupItems[0]!),
			items: groupItems
		}));
	}

	function dateHeading(item: CalendarItem): string {
		const date = itemDate(item);
		const difference = dayDifference(date, today);
		const prefix = difference === 0 ? 'Today' : difference === 1 ? 'Tomorrow' : null;
		const formatted = new Intl.DateTimeFormat(undefined, {
			weekday: 'long',
			month: 'long',
			day: 'numeric',
			year: date.getFullYear() === today.getFullYear() ? undefined : 'numeric'
		}).format(date);
		return prefix ? `${prefix} · ${formatted}` : formatted;
	}

	function countdown(item: CalendarItem): { value: string; unit: string } {
		const difference = dayDifference(itemDate(item), today);
		if (difference === 0) return { value: 'Today', unit: 'releases' };
		if (difference > 0)
			return { value: String(difference), unit: difference === 1 ? 'day' : 'days' };
		const elapsed = Math.abs(difference);
		return { value: String(elapsed), unit: elapsed === 1 ? 'day ago' : 'days ago' };
	}

	function episodeLabel(item: CalendarItem): string | null {
		if (item.media_type === 'movie') return null;
		if (item.season_number == null || item.episode_number == null) return 'TV episode';
		return `S${String(item.season_number).padStart(2, '0')}E${String(item.episode_number).padStart(2, '0')}`;
	}

	function posterUrl(id: string, extension: 'avif' | 'webp' | 'jpg'): string {
		const baseUrl = env.PUBLIC_API_URL?.replace(/\/$/, '') ?? '';
		return `${baseUrl}/api/v1/static/image/${id}.${extension}`;
	}

	async function refreshCalendar() {
		refreshing = true;
		try {
			await invalidateAll();
		} finally {
			refreshing = false;
		}
	}
</script>

<svelte:head>
	<title>Release Calendar - MediaManager</title>
	<meta
		content="See when movies and TV episodes in your MediaManager library are released"
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
					<Breadcrumb.Page>Release Calendar</Breadcrumb.Page>
				</Breadcrumb.Item>
			</Breadcrumb.List>
		</Breadcrumb.Root>
	</div>
</header>

<main class="mx-auto flex w-full max-w-[110rem] flex-1 flex-col gap-8 p-4 pt-2 sm:p-6 lg:p-8">
	<section class="flex flex-col gap-5 text-center">
		<div
			class="mx-auto flex size-12 items-center justify-center rounded-2xl border bg-card shadow-sm"
		>
			<CalendarDays class="size-6" aria-hidden="true" />
		</div>
		<div>
			<h1 class="text-3xl font-extrabold tracking-tight sm:text-4xl lg:text-5xl">
				Release calendar
			</h1>
			<p class="mx-auto mt-3 max-w-2xl text-sm text-muted-foreground sm:text-base">
				Upcoming movies and episodes from the titles you have added to MediaManager.
			</p>
		</div>

		<div
			class="mx-auto inline-flex max-w-full gap-1 overflow-x-auto rounded-2xl border bg-card p-1.5 shadow-sm"
			aria-label="Calendar filters"
		>
			{#each filters as filter (filter.value)}
				<button
					type="button"
					class="rounded-xl px-4 py-2 text-sm font-semibold transition-colors sm:px-6 {activeFilter ===
					filter.value
						? 'bg-primary text-primary-foreground shadow-sm'
						: 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'}"
					aria-pressed={activeFilter === filter.value}
					onclick={() => (activeFilter = filter.value)}
				>
					{filter.label}
				</button>
			{/each}
		</div>
	</section>

	{#if data.loadError}
		<section class="rounded-2xl border border-destructive/40 bg-destructive/10 p-6 text-center">
			<p class="font-semibold text-destructive">{data.loadError}</p>
			<Button class="mt-4" variant="outline" onclick={refreshCalendar} disabled={refreshing}>
				<RotateCw class={refreshing ? 'animate-spin' : ''} />
				Try again
			</Button>
		</section>
	{:else if groups.length === 0}
		<section
			class="flex min-h-72 flex-col items-center justify-center rounded-3xl border border-dashed bg-card/50 p-8 text-center"
		>
			<CalendarDays class="size-10 text-muted-foreground" aria-hidden="true" />
			<h2 class="mt-4 text-xl font-bold">Nothing to show here yet</h2>
			<p class="mt-2 max-w-lg text-sm text-muted-foreground">
				{activeFilter === 'upcoming'
					? 'Upcoming movie and episode dates will appear here as soon as metadata is available.'
					: activeFilter === 'available'
						? 'No releases are marked as available yet.'
						: 'No previous releases were found for your added titles.'}
			</p>
		</section>
	{:else}
		{#each groups as group (group.key)}
			<section aria-labelledby={`release-date-${group.key}`}>
				<div class="mb-4 flex items-center gap-3">
					<h2 id={`release-date-${group.key}`} class="text-lg font-bold capitalize sm:text-xl">
						{group.label}
					</h2>
					<div class="h-px flex-1 bg-border"></div>
					<span class="text-xs font-medium text-muted-foreground">
						{group.items.length}
						{group.items.length === 1 ? 'release' : 'releases'}
					</span>
				</div>

				<div class="release-calendar-grid">
					{#each group.items as item (item.id)}
						{@const remaining = countdown(item)}
						{@const episode = episodeLabel(item)}
						<a
							href={resolve(
								item.media_type === 'movie'
									? '/dashboard/movies/[movieId]'
									: '/dashboard/tv/[showId]',
								item.media_type === 'movie' ? { movieId: item.media_id } : { showId: item.media_id }
							)}
							class="release-card group relative isolate grid overflow-hidden rounded-3xl border bg-card shadow-sm ring-ring transition duration-300 hover:-translate-y-0.5 hover:shadow-xl focus-visible:ring-2 focus-visible:outline-none"
							aria-label={`Open ${item.name}`}
						>
							{#if item.poster_id}
								<picture class="absolute inset-0 -z-20">
									<source srcset={posterUrl(item.poster_id, 'avif')} type="image/avif" />
									<source srcset={posterUrl(item.poster_id, 'webp')} type="image/webp" />
									<img
										src={posterUrl(item.poster_id, 'jpg')}
										alt=""
										class="size-full object-cover object-top transition duration-500 group-hover:scale-[1.025]"
										loading="lazy"
									/>
								</picture>
							{:else}
								<div class="absolute inset-0 -z-20 flex items-center justify-center bg-muted">
									<ImageOff class="size-14 text-muted-foreground/50" aria-hidden="true" />
								</div>
							{/if}
							<div
								class="absolute inset-0 -z-10 bg-gradient-to-t from-black via-black/40 to-black/5"
							></div>

							<div
								class="grid min-w-20 place-content-start border-r border-white/15 bg-black/55 p-4 text-white backdrop-blur-sm sm:min-w-24"
							>
								<span class="text-3xl leading-none font-black tracking-tight sm:text-4xl">
									{remaining.value}
								</span>
								<span class="mt-1 text-xs font-bold text-white/70 sm:text-sm">{remaining.unit}</span
								>
							</div>

							<div class="flex min-w-0 flex-col justify-between p-4 text-white sm:p-6">
								<div class="flex flex-wrap items-center justify-end gap-2">
									<span
										class="inline-flex items-center gap-1 rounded-full border border-white/25 bg-black/60 px-2.5 py-1 text-[11px] font-bold uppercase backdrop-blur-sm"
									>
										{#if item.media_type === 'movie'}
											<Film class="size-3.5" aria-hidden="true" /> Movie
										{:else}
											<Tv class="size-3.5" aria-hidden="true" /> Episode
										{/if}
									</span>
									{#if item.available}
										<span
											class="inline-flex items-center gap-1 rounded-full bg-emerald-500 px-2.5 py-1 text-[11px] font-bold text-emerald-950 uppercase shadow-sm"
										>
											<Check class="size-3.5" aria-hidden="true" /> Available
										</span>
									{/if}
								</div>

								<div class="min-w-0 drop-shadow-lg">
									<h3
										class="line-clamp-2 text-2xl leading-tight font-black tracking-tight sm:text-3xl"
									>
										{item.name}
									</h3>
									{#if episode}
										<p class="mt-2 line-clamp-2 text-sm font-semibold text-white/80 sm:text-base">
											{episode}{item.episode_title ? ` · ${item.episode_title}` : ''}
										</p>
									{:else if item.overview}
										<p class="mt-2 line-clamp-2 text-sm text-white/75">{item.overview}</p>
									{/if}
									<time
										class="mt-3 block text-xs font-semibold text-white/65"
										datetime={item.release_date}
									>
										{new Intl.DateTimeFormat(undefined, {
											dateStyle: 'long'
										}).format(itemDate(item))}
									</time>
								</div>
							</div>
						</a>
					{/each}
				</div>
			</section>
		{/each}
	{/if}
</main>
