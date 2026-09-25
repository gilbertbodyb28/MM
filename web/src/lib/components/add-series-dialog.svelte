<script lang="ts">
	import client from '$lib/api';
	import type { Show } from '$lib/api/api';
	import * as Dialog from '$lib/components/ui/dialog';
	import { Button } from '$lib/components/ui/button';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { emitMediaAddedSuccess } from '$lib/celebration';
	import { Check, LoaderCircle, Plus, RefreshCw, Tv } from 'lucide-svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import { toast } from 'svelte-sonner';

	interface SeriesCandidate {
		external_id: number;
		metadata_provider: string;
		original_language?: string | null;
		name: string;
	}

	interface AddedSeries {
		id: string;
		name: string;
		external_id: number;
		metadata_provider: string;
	}

	let {
		candidate,
		compact = false,
		class: className = '',
		label = 'Add Series',
		onAdded
	}: {
		candidate: SeriesCandidate;
		compact?: boolean;
		class?: string;
		label?: string;
		onAdded?: (show: AddedSeries) => void | Promise<void>;
	} = $props();

	let open = $state(false);
	let preview = $state<Show | null>(null);
	let previewLoading = $state(false);
	let previewError = $state<string | null>(null);
	let submitting = $state(false);
	let submitError = $state<string | null>(null);
	let monitoring = $state<'monitored' | 'unmonitored'>('monitored');
	let monitorScope = $state<'entire' | 'specific'>('entire');
	let selectedSeasons = new SvelteSet<number>();

	const seasons = $derived(
		(preview?.seasons ?? []).toSorted((left, right) => left.number - right.number)
	);
	const canSubmit = $derived(
		!submitting &&
			(monitoring === 'unmonitored' ||
				monitorScope === 'entire' ||
				(preview !== null && selectedSeasons.size > 0))
	);

	function responseError(error: unknown, fallback: string): string {
		if (error && typeof error === 'object' && 'detail' in error) {
			const detail = (error as { detail?: unknown }).detail;
			if (typeof detail === 'string') return detail;
		}
		return fallback;
	}

	async function loadPreview(): Promise<void> {
		if (previewLoading) return;
		previewLoading = true;
		previewError = null;
		try {
			const response = await client.GET('/api/v1/tv/shows/preview', {
				params: {
					query: {
						show_id: candidate.external_id,
						metadata_provider: candidate.metadata_provider as 'tmdb' | 'tvdb',
						language: candidate.original_language ?? undefined
					}
				}
			});
			if (response.error || !response.data) {
				throw new Error(responseError(response.error, 'Season information could not be loaded.'));
			}
			preview = response.data;
		} catch (error) {
			previewError =
				error instanceof Error ? error.message : 'Season information could not be loaded.';
		} finally {
			previewLoading = false;
		}
	}

	function openDialog(): void {
		open = true;
		submitError = null;
		if (!preview) void loadPreview();
	}

	function setSeason(number: number, checked: boolean): void {
		if (checked) selectedSeasons.add(number);
		else selectedSeasons.delete(number);
	}

	function selectAllSeasons(): void {
		selectedSeasons.clear();
		for (const season of seasons) selectedSeasons.add(season.number);
	}

	async function addSeries(): Promise<void> {
		if (!canSubmit) return;
		submitting = true;
		submitError = null;
		try {
			const response = await client.POST('/api/v1/tv/shows', {
				params: {
					query: {
						show_id: candidate.external_id,
						metadata_provider: candidate.metadata_provider as 'tmdb' | 'tvdb',
						language: candidate.original_language ?? undefined,
						monitoring,
						monitor_scope: monitorScope,
						monitor_season:
							monitoring === 'monitored' && monitorScope === 'specific'
								? [...selectedSeasons].sort((left, right) => left - right)
								: undefined
					}
				}
			});
			if (response.error || !response.data?.id) {
				throw new Error(responseError(response.error, 'MediaManager could not add this series.'));
			}
			const added: AddedSeries = { ...response.data, id: response.data.id };
			open = false;
			toast.success(`${candidate.name} was added to your library.`);
			if (response.response.status === 201) {
				emitMediaAddedSuccess({
					operationId: `show:${added.id}`,
					count: 1,
					source: 'series'
				});
			}
			await onAdded?.(added);
		} catch (error) {
			submitError =
				error instanceof Error ? error.message : 'MediaManager could not add this series.';
		} finally {
			submitting = false;
		}
	}
</script>

<Button class={className} size={compact ? 'sm' : 'default'} type="button" onclick={openDialog}>
	<Plus />
	{label}
</Button>

<Dialog.Root bind:open>
	<Dialog.Content class="max-h-[min(88svh,52rem)] max-w-2xl overflow-y-auto rounded-3xl p-0">
		<div class="border-b bg-gradient-to-br from-primary/12 via-background to-background p-6 sm:p-7">
			<Dialog.Header>
				<div
					class="mb-2 flex size-11 items-center justify-center rounded-2xl border bg-card shadow-sm"
				>
					<Tv class="size-5" />
				</div>
				<Dialog.Title>Add {candidate.name}</Dialog.Title>
				<Dialog.Description>
					Choose how MediaManager should monitor this series before it is added.
				</Dialog.Description>
			</Dialog.Header>
		</div>

		<div class="space-y-6 p-6 sm:p-7">
			<section aria-labelledby="monitoring-heading">
				<h3 class="mb-3 text-sm font-semibold" id="monitoring-heading">Monitoring</h3>
				<div class="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Monitoring">
					{#each [{ value: 'monitored', label: 'Monitored', description: 'Automatically manage selected releases.' }, { value: 'unmonitored', label: 'Unmonitored', description: 'Add it without automatic downloads.' }] as option (option.value)}
						<button
							class="monitor-choice {monitoring === option.value ? 'is-selected' : ''}"
							aria-checked={monitoring === option.value}
							role="radio"
							type="button"
							onclick={() => (monitoring = option.value as typeof monitoring)}
						>
							<span class="monitor-radio"
								>{#if monitoring === option.value}<Check />{/if}</span
							>
							<span><strong>{option.label}</strong><small>{option.description}</small></span>
						</button>
					{/each}
				</div>
			</section>

			{#if monitoring === 'monitored'}
				<section aria-labelledby="monitor-scope-heading">
					<h3 class="mb-3 text-sm font-semibold" id="monitor-scope-heading">Monitor scope</h3>
					<div class="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Monitor scope">
						{#each [{ value: 'entire', label: 'Entire Series', description: 'All current and future seasons and episodes.' }, { value: 'specific', label: 'Specific Seasons', description: 'Only the seasons you select below.' }] as option (option.value)}
							<button
								class="monitor-choice {monitorScope === option.value ? 'is-selected' : ''}"
								aria-checked={monitorScope === option.value}
								role="radio"
								type="button"
								onclick={() => (monitorScope = option.value as typeof monitorScope)}
							>
								<span class="monitor-radio"
									>{#if monitorScope === option.value}<Check />{/if}</span
								>
								<span><strong>{option.label}</strong><small>{option.description}</small></span>
							</button>
						{/each}
					</div>
				</section>

				{#if monitorScope === 'specific'}
					<section
						class="rounded-2xl border bg-muted/20 p-4"
						aria-labelledby="season-selection-heading"
					>
						<div class="mb-3 flex items-center justify-between gap-3">
							<div>
								<h3 class="text-sm font-semibold" id="season-selection-heading">Seasons</h3>
								<p class="text-xs text-muted-foreground">Choose at least one season.</p>
							</div>
							{#if seasons.length > 0}
								<Button size="sm" variant="ghost" type="button" onclick={selectAllSeasons}
									>Select all</Button
								>
							{/if}
						</div>
						{#if previewLoading}
							<div
								class="flex min-h-28 items-center justify-center gap-2 text-sm text-muted-foreground"
							>
								<LoaderCircle class="animate-spin" /> Loading seasons…
							</div>
						{:else if previewError}
							<div
								class="rounded-xl border border-destructive/35 bg-destructive/5 p-4 text-sm text-destructive"
							>
								<p>{previewError}</p>
								<Button
									class="mt-3"
									size="sm"
									variant="outline"
									type="button"
									onclick={loadPreview}
								>
									<RefreshCw /> Try again
								</Button>
							</div>
						{:else}
							<div class="grid max-h-56 gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
								{#each seasons as season (season.number)}
									<label
										class="flex cursor-pointer items-center gap-3 rounded-xl border bg-card/70 p-3 text-sm hover:bg-accent/60"
									>
										<Checkbox
											checked={selectedSeasons.has(season.number)}
											onCheckedChange={(checked) => setSeason(season.number, checked === true)}
										/>
										<span class="min-w-0"
											><strong class="block truncate"
												>{season.number === 0 ? 'Specials' : `Season ${season.number}`}</strong
											><small class="text-muted-foreground">{season.episodes.length} episodes</small
											></span
										>
									</label>
								{/each}
							</div>
						{/if}
					</section>
				{/if}
			{/if}

			{#if submitError}
				<div
					class="rounded-xl border border-destructive/35 bg-destructive/5 p-4 text-sm text-destructive"
					role="alert"
				>
					{submitError}
				</div>
			{/if}
		</div>

		<Dialog.Footer class="border-t bg-muted/20 p-5 sm:px-7">
			<Button variant="outline" type="button" disabled={submitting} onclick={() => (open = false)}
				>Cancel</Button
			>
			<Button type="button" disabled={!canSubmit} onclick={addSeries}>
				{#if submitting}<LoaderCircle class="animate-spin" /> Adding…{:else}<Plus /> Add Series{/if}
			</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>

<style>
	.monitor-choice {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
		border: 1px solid var(--border);
		border-radius: 1rem;
		padding: 0.9rem;
		text-align: left;
		background: color-mix(in oklab, var(--card) 75%, transparent);
		transition:
			border-color 160ms ease,
			background 160ms ease,
			box-shadow 160ms ease;
	}

	.monitor-choice:hover,
	.monitor-choice.is-selected {
		border-color: color-mix(in oklab, var(--primary) 62%, var(--border));
	}

	.monitor-choice.is-selected {
		background: color-mix(in oklab, var(--primary) 8%, var(--card));
		box-shadow: 0 0 0 2px color-mix(in oklab, var(--primary) 12%, transparent);
	}

	.monitor-choice > span:last-child {
		min-width: 0;
	}
	.monitor-choice strong {
		display: block;
		font-size: 0.875rem;
	}
	.monitor-choice small {
		display: block;
		margin-top: 0.25rem;
		color: var(--muted-foreground);
		font-size: 0.75rem;
		line-height: 1.35;
	}
	.monitor-radio {
		display: grid;
		width: 1.15rem;
		height: 1.15rem;
		flex: none;
		place-items: center;
		border: 1.5px solid color-mix(in oklab, var(--foreground) 45%, transparent);
		border-radius: 999px;
		margin-top: 0.08rem;
	}
	.monitor-choice.is-selected .monitor-radio {
		border-color: var(--primary);
		background: var(--primary);
		color: var(--primary-foreground);
	}
	.monitor-radio :global(svg) {
		width: 0.72rem;
		height: 0.72rem;
		stroke-width: 3.5;
	}
</style>
