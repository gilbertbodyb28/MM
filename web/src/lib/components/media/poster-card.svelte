<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { cn } from '$lib/utils';
	import ImageOff from '@lucide/svelte/icons/image-off';
	import type { Snippet } from 'svelte';

	let {
		title,
		year = null,
		posterPath = null,
		mediaId = null,
		href = null,
		class: className,
		badge,
		status,
		actions
	}: {
		title: string;
		year?: number | string | null;
		posterPath?: string | null;
		mediaId?: string | null;
		href?: string | null;
		class?: string;
		badge?: Snippet;
		status?: Snippet;
		actions?: Snippet;
	} = $props();

	let imageFailed = $state(false);
	const apiUrl = $derived((env.PUBLIC_API_URL ?? '').replace(/\/$/, ''));
	const resolvedPosterUrl = $derived(resolvePosterUrl(posterPath));
	const displayYear = $derived(year == null || year === '' ? '—' : String(year));

	function resolvePosterUrl(path: string | null): string | null {
		if (!path) return null;
		if (/^(?:https?:|data:|blob:)/.test(path)) return path;
		if (path.startsWith('/api/')) return `${apiUrl}${path}`;
		return `https://image.tmdb.org/t/p/w500${path.startsWith('/') ? path : `/${path}`}`;
	}
</script>

<article class={cn('media-poster-card group', className)} aria-label={title}>
	<div class="media-poster-artwork">
		{#if mediaId && !imageFailed}
			<picture>
				<source srcset={`${apiUrl}/api/v1/static/image/${mediaId}.avif`} type="image/avif" />
				<source srcset={`${apiUrl}/api/v1/static/image/${mediaId}.webp`} type="image/webp" />
				<img
					alt={`${title} poster`}
					class="media-poster-image"
					decoding="async"
					loading="lazy"
					onerror={() => (imageFailed = true)}
					src={`${apiUrl}/api/v1/static/image/${mediaId}.jpg`}
				/>
			</picture>
		{:else if resolvedPosterUrl && !imageFailed}
			<img
				alt={`${title} poster`}
				class="media-poster-image"
				decoding="async"
				loading="lazy"
				onerror={() => (imageFailed = true)}
				src={resolvedPosterUrl}
			/>
		{:else}
			<div class="media-poster-placeholder">
				<ImageOff aria-hidden="true" />
				<span>Artwork unavailable</span>
			</div>
		{/if}

		{#if href}
			<!-- href is produced by SvelteKit's resolve() at the caller. -->
			<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
			<a class="media-poster-open" {href} aria-label={`Open ${title}`}></a>
		{/if}

		{#if badge}
			<div class="media-poster-badge">{@render badge()}</div>
		{/if}
		{#if status}
			<div class="media-poster-status">{@render status()}</div>
		{/if}
		{#if actions}
			<div class="media-poster-actions">{@render actions()}</div>
		{/if}
	</div>

	<div class="media-poster-meta">
		{#if href}
			<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
			<a class="media-poster-title" {href}>{title}</a>
		{:else}
			<h3 class="media-poster-title">{title}</h3>
		{/if}
		<p class="media-poster-year">{displayYear}</p>
	</div>
</article>
