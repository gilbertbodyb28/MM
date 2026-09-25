<script lang="ts" module>
	let configuredRequest: Promise<boolean> | null = null;

	async function seerrConfigured(): Promise<boolean> {
		configuredRequest ??= fetch('/api/v1/seerr/configured', { credentials: 'include' })
			.then(async (response) => {
				if (!response.ok) return false;
				const payload = (await response.json()) as { configured?: boolean };
				return payload.configured === true;
			})
			.catch(() => false);
		return configuredRequest;
	}
</script>

<script lang="ts">
	import { onMount } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import { Check, CircleEllipsis, LoaderCircle, Send, ShieldCheck } from 'lucide-svelte';
	import { toast } from 'svelte-sonner';

	type SeerrState =
		| 'not_requested'
		| 'requested'
		| 'pending'
		| 'approved'
		| 'declined'
		| 'processing'
		| 'partially_available'
		| 'available'
		| 'unknown';

	let {
		mediaType,
		tmdbId,
		class: className = ''
	}: { mediaType: 'movie' | 'tv'; tmdbId: number; class?: string } = $props();

	let configured = $state(false);
	let loading = $state(false);
	let requestState = $state<SeerrState>('not_requested');

	const terminal = $derived(
		['requested', 'pending', 'approved', 'processing', 'partially_available', 'available'].includes(
			requestState
		)
	);
	const label = $derived(
		requestState === 'available'
			? 'Available'
			: requestState === 'approved'
				? 'Approved'
				: requestState === 'processing'
					? 'Processing'
					: requestState === 'partially_available'
						? 'Partially available'
						: requestState === 'pending'
							? 'Pending'
							: requestState === 'requested'
								? 'Requested'
								: requestState === 'declined'
									? 'Declined'
									: 'Request'
	);

	onMount(async () => {
		configured = await seerrConfigured();
	});

	async function requestMedia(event: MouseEvent) {
		event.preventDefault();
		event.stopPropagation();
		if (terminal || loading) return;
		loading = true;
		try {
			const response = await fetch('/api/v1/seerr/request', {
				method: 'POST',
				credentials: 'include',
				headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
				body: JSON.stringify({
					media_type: mediaType,
					tmdb_id: tmdbId,
					seasons: mediaType === 'tv' ? 'all' : null
				})
			});
			const payload = (await response.json().catch(() => null)) as
				| { status?: SeerrState; message?: string; detail?: string }
				| null;
			if (!response.ok) throw new Error(payload?.detail ?? 'Seerr could not complete the request.');
			requestState = payload?.status ?? 'requested';
			toast.success(payload?.message ?? 'Request sent to Seerr.');
		} catch (caught) {
			toast.error(caught instanceof Error ? caught.message : 'Seerr could not complete the request.');
		} finally {
			loading = false;
		}
	}
</script>

{#if configured}
	<Button
		class={className}
		disabled={loading || terminal}
		onclick={requestMedia}
		size="sm"
		type="button"
		variant={terminal ? 'secondary' : 'outline'}
	>
		{#if loading}
			<LoaderCircle class="animate-spin" />
		{:else if requestState === 'available'}
			<ShieldCheck />
		{:else if terminal}
			<Check />
		{:else if requestState === 'declined'}
			<CircleEllipsis />
		{:else}
			<Send />
		{/if}
		{label}
	</Button>
{/if}
