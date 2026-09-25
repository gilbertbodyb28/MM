<script lang="ts">
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import client from '$lib/api';
	import type {
		EpisodeScanItem,
		EpisodeScanReason,
		EpisodeScanRun,
		EpisodeScanRunStatus,
		EpisodeScanStatus
	} from '$lib/api/api';
	import { Button } from '$lib/components/ui/button';
	import { Switch } from '$lib/components/ui/switch';
	import { Separator } from '$lib/components/ui/separator';
	import * as Breadcrumb from '$lib/components/ui/breadcrumb';
	import * as Sidebar from '$lib/components/ui/sidebar';
	import {
		CalendarClock,
		CircleCheck,
		Download,
		History,
		Hourglass,
		LoaderCircle,
		Radar,
		ScanSearch,
		SkipForward,
		TriangleAlert
	} from 'lucide-svelte';
	import { toast } from 'svelte-sonner';

	const RUNNING_POLL_MS = 3_000;
	const IDLE_POLL_MS = 30_000;

	let status = $state<EpisodeScanStatus | null>(page.data.status ?? null);
	let statusError = $state<string | null>(page.data.statusError ?? null);
	let savingToggle = $state(false);
	let startingScan = $state(false);
	let clockOffset = $state(
		page.data.status ? Date.parse(page.data.status.server_time) - Date.now() : 0
	);
	let now = $state(Date.now());

	const isAdmin = $derived(Boolean(page.data.user?.is_superuser));
	const latestRun = $derived(status?.latest_run ?? null);
	const latestItems = $derived(status?.latest_items ?? []);
	const recentSent = $derived(status?.recent_sent ?? []);
	const recentRuns = $derived(status?.recent_runs ?? []);
	const errorItems = $derived(latestItems.filter((item) => item.outcome === 'error'));
	const episodeItems = $derived(
		latestItems
			.filter((item) => item.outcome !== 'skipped' && item.episode_id != null)
			.toSorted(compareItems)
	);
	const skippedItems = $derived(
		latestItems.filter((item) => item.outcome === 'skipped').toSorted(compareItems)
	);
	const running = $derived(Boolean(status?.running));
	const intervalText = $derived(describeInterval(status?.interval_minutes ?? 60));
	const busy = $derived(running || startingScan);

	const dateTimeFormat = new Intl.DateTimeFormat('sv-SE', {
		dateStyle: 'medium',
		timeStyle: 'short'
	});
	const relativeFormat = new Intl.RelativeTimeFormat('sv', { numeric: 'auto' });

	const runStatusLabels: Record<EpisodeScanRunStatus, string> = {
		running: 'Pågår',
		succeeded: 'Klar',
		completed_with_errors: 'Klar med fel',
		failed: 'Misslyckades',
		interrupted: 'Avbruten'
	};

	const reasonLabels: Record<EpisodeScanReason, string> = {
		in_library: 'Finns redan i biblioteket',
		downloading: 'Laddas redan ned eller väntar på import',
		queued: 'Ligger redan i nedladdningskön',
		in_download_client: 'Finns redan i qBittorrent',
		not_monitored: 'Serien övervakas inte (Unmonitored)',
		season_not_monitored: 'Säsongen övervakas inte',
		configuration: 'Inställningar saknas eller är fel',
		search: 'Sökningen hos indexeraren misslyckades',
		download: 'Nedladdningstjänsten tog inte emot avsnittet',
		unexpected: 'Oväntat fel när serien kontrollerades'
	};

	const outcomeOrder: Record<EpisodeScanItem['outcome'], number> = {
		error: 0,
		sent: 1,
		not_found: 2,
		skipped: 3
	};

	function compareItems(left: EpisodeScanItem, right: EpisodeScanItem): number {
		return (
			outcomeOrder[left.outcome] - outcomeOrder[right.outcome] ||
			(left.show_name ?? '').localeCompare(right.show_name ?? '', 'sv') ||
			(left.season_number ?? 0) - (right.season_number ?? 0) ||
			(left.episode_number ?? 0) - (right.episode_number ?? 0)
		);
	}

	function episodeCode(item: EpisodeScanItem): string {
		if (item.season_number == null || item.episode_number == null) return '';
		const pad = (value: number) => String(value).padStart(2, '0');
		return `S${pad(item.season_number)}E${pad(item.episode_number)}`;
	}

	function itemLabel(item: EpisodeScanItem): string {
		switch (item.outcome) {
			case 'sent':
				return 'Skickat för nedladdning';
			case 'not_found':
				return 'Ingen release hittades ännu – nytt försök vid nästa scanning';
			case 'skipped':
				return item.reason ? reasonLabels[item.reason] : 'Hoppades över';
			case 'error':
				return item.reason ? reasonLabels[item.reason] : 'Fel';
		}
	}

	function describeInterval(minutes: number): string {
		if (minutes === 60) return 'varje timme';
		if (minutes % 60 === 0) return `var ${minutes / 60}:e timme`;
		return `var ${minutes}:e minut`;
	}

	function formatDateTime(value: string | null | undefined): string {
		return value ? dateTimeFormat.format(new Date(value)) : '–';
	}

	function formatRelative(value: string | null | undefined): string {
		if (!value) return '';
		const seconds = (Date.parse(value) - (now + clockOffset)) / 1000;
		if (Math.abs(seconds) < 45) return seconds >= 0 ? 'om en liten stund' : 'nyss';
		const minutes = Math.round(seconds / 60);
		if (Math.abs(minutes) < 60) return relativeFormat.format(minutes, 'minute');
		const hours = Math.round(seconds / 3_600);
		if (Math.abs(hours) < 24) return relativeFormat.format(hours, 'hour');
		return relativeFormat.format(Math.round(seconds / 86_400), 'day');
	}

	function formatDuration(run: EpisodeScanRun): string {
		const end = run.finished_at ? Date.parse(run.finished_at) : now + clockOffset;
		const seconds = Math.max(0, Math.round((end - Date.parse(run.started_at)) / 1000));
		if (seconds < 60) return `${seconds} s`;
		return `${Math.floor(seconds / 60)} min ${seconds % 60} s`;
	}

	function errorDetail(error: unknown, fallback: string): string {
		if (error && typeof error === 'object' && 'detail' in error) {
			const detail = (error as { detail?: unknown }).detail;
			if (typeof detail === 'string') return detail;
		}
		return fallback;
	}

	function applyStatus(next: EpisodeScanStatus): void {
		const previous = status;
		status = next;
		statusError = null;
		clockOffset = Date.parse(next.server_time) - Date.now();
		const finishedRun = next.latest_run;
		if (
			previous?.running &&
			!next.running &&
			finishedRun &&
			finishedRun.id === previous.latest_run?.id
		) {
			announceFinished(finishedRun);
		}
	}

	function announceFinished(run: EpisodeScanRun): void {
		const sent = `${run.episodes_sent} avsnitt skickades för nedladdning`;
		if (run.status === 'succeeded') toast.success(`Scanningen är klar: ${sent}.`);
		else if (run.status === 'completed_with_errors')
			toast.warning(`Scanningen är klar men ${run.errors} fel uppstod: ${sent}.`);
		else toast.error('Scanningen misslyckades. Se felet på sidan.');
	}

	async function refresh(): Promise<void> {
		try {
			const { data } = await client.GET('/api/v1/episode-scanner/status');
			if (data) applyStatus(data);
			else statusError = 'Scannerns status kunde inte hämtas.';
		} catch {
			statusError = 'Scannerns status kunde inte hämtas.';
		}
	}

	async function setEnabled(enabled: boolean): Promise<void> {
		if (!status || savingToggle) return;
		const previous = status.enabled;
		status = { ...status, enabled };
		savingToggle = true;
		try {
			const { data, error } = await client.PUT('/api/v1/episode-scanner/settings', {
				body: { enabled }
			});
			if (!data) throw new Error(errorDetail(error, 'Inställningen kunde inte sparas.'));
			applyStatus(data);
			toast.success(
				enabled
					? 'Automatisk scanning är på. Nästa scanning startar enligt schemat.'
					: 'Automatisk scanning är avstängd.'
			);
		} catch (error) {
			if (status) status = { ...status, enabled: previous };
			toast.error(error instanceof Error ? error.message : 'Inställningen kunde inte sparas.');
		} finally {
			savingToggle = false;
		}
	}

	async function scanNow(): Promise<void> {
		if (busy) return;
		startingScan = true;
		try {
			const { data, error, response } = await client.POST('/api/v1/episode-scanner/scan');
			if (!data) {
				throw new Error(
					errorDetail(
						error,
						response.status === 409 ? 'En scanning pågår redan.' : 'Scanningen kunde inte startas.'
					)
				);
			}
			applyStatus(data);
			toast.info('Scanningen har startat. Resultatet visas här när den är klar.');
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Scanningen kunde inte startas.');
			await refresh();
		} finally {
			startingScan = false;
		}
	}

	onMount(() => {
		const clock = setInterval(() => (now = Date.now()), 15_000);
		return () => clearInterval(clock);
	});

	// Poll quickly while a scan runs so results appear live, slowly otherwise.
	$effect(() => {
		const timer = setInterval(() => void refresh(), running ? RUNNING_POLL_MS : IDLE_POLL_MS);
		return () => clearInterval(timer);
	});
</script>

<svelte:head>
	<title>Avsnittsscanner - MediaManager</title>
	<meta
		content="Automatisk scanning av alla TV-serier efter nya avsnitt i MediaManager"
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
					<Breadcrumb.Page>Avsnittsscanner</Breadcrumb.Page>
				</Breadcrumb.Item>
			</Breadcrumb.List>
		</Breadcrumb.Root>
	</div>
</header>

<main class="mx-auto flex w-full max-w-[80em] flex-1 flex-col gap-6 p-4 pb-16 md:p-6">
	<section class="scanner-hero rounded-3xl border p-6 md:p-9">
		<div class="flex flex-wrap items-start justify-between gap-6">
			<div class="max-w-3xl">
				<div class="mb-3 flex items-center gap-2 text-sm font-semibold text-primary">
					<Radar class="size-5" /> Automatisk avsnittsscanner
				</div>
				<h1 class="text-3xl font-bold tracking-tight md:text-5xl">Avsnittsscanner</h1>
				<p class="mt-3 text-muted-foreground md:text-lg">
					Kontrollerar alla dina TV-serier efter nya avsnitt {intervalText} och skickar dem automatiskt
					till nedladdningstjänsten. Scannern körs på servern – även när den här sidan är stängd.
				</p>
			</div>
			<div class="flex w-full flex-col gap-3 sm:w-auto sm:min-w-72">
				<label
					class="flex items-center justify-between gap-4 rounded-2xl border bg-card/65 px-4 py-3"
					for="automatic-scanning"
				>
					<span>
						<span class="block font-semibold">Automatisk scanning</span>
						<span class="text-xs text-muted-foreground">
							{status?.enabled ? 'På – körs i bakgrunden' : 'Av – endast manuell scanning'}
						</span>
					</span>
					<Switch
						aria-label="Automatisk scanning"
						checked={status?.enabled ?? false}
						disabled={!status || !isAdmin || savingToggle}
						id="automatic-scanning"
						onCheckedChange={(enabled) => setEnabled(enabled)}
					/>
				</label>
				<Button disabled={!status || !isAdmin || busy} onclick={scanNow} size="lg" type="button">
					{#if busy}
						<LoaderCircle class="animate-spin" /> Scannar…
					{:else}
						<ScanSearch /> Scanna nu
					{/if}
				</Button>
				{#if !isAdmin}
					<p class="text-xs text-muted-foreground">
						Endast administratörer kan starta scanningen eller ändra inställningen.
					</p>
				{/if}
			</div>
		</div>
	</section>

	{#if statusError}
		<div
			class="flex items-start gap-3 rounded-2xl border border-destructive/40 bg-destructive/5 p-4 text-sm"
			role="alert"
		>
			<TriangleAlert class="mt-0.5 size-5 shrink-0 text-destructive" />
			<div>
				<p class="font-semibold text-destructive">{statusError}</p>
				<Button class="mt-3" onclick={refresh} size="sm" type="button" variant="outline">
					Försök igen
				</Button>
			</div>
		</div>
	{/if}

	{#if status}
		<section class="grid gap-4 md:grid-cols-3" aria-label="Scannerstatus">
			<div class="stat-card">
				<div class="stat-label"><History class="size-4" /> Senaste scanning</div>
				{#if latestRun}
					<p class="stat-value">{formatDateTime(latestRun.started_at)}</p>
					<p class="text-sm text-muted-foreground">
						{formatRelative(latestRun.started_at)} ·
						{latestRun.trigger === 'manual' ? 'Manuell' : 'Schemalagd'}
						{#if latestRun.status !== 'running'}· tog {formatDuration(latestRun)}{/if}
					</p>
					<span class="run-status mt-3" data-status={latestRun.status}>
						{#if latestRun.status === 'running'}<LoaderCircle class="size-3.5 animate-spin" />{/if}
						{runStatusLabels[latestRun.status]}
					</span>
				{:else}
					<p class="stat-value">Ingen ännu</p>
					<p class="text-sm text-muted-foreground">Ingen scanning har körts än.</p>
				{/if}
			</div>

			<div class="stat-card">
				<div class="stat-label"><CalendarClock class="size-4" /> Nästa planerade scanning</div>
				{#if !status.enabled}
					<p class="stat-value">Avstängd</p>
					<p class="text-sm text-muted-foreground">
						Slå på automatisk scanning för att kontrollera serierna {intervalText}.
					</p>
				{:else if status.running}
					<p class="stat-value">{formatDateTime(status.next_scan_at)}</p>
					<p class="text-sm text-muted-foreground">Efter den pågående scanningen.</p>
				{:else}
					<p class="stat-value">{formatDateTime(status.next_scan_at)}</p>
					<p class="text-sm text-muted-foreground">{formatRelative(status.next_scan_at)}</p>
				{/if}
			</div>

			<div class="stat-card">
				<div class="stat-label"><Radar class="size-4" /> Resultat</div>
				{#if latestRun}
					<dl class="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
						<dt class="text-muted-foreground">Serier kontrollerade</dt>
						<dd class="text-right font-semibold">
							{latestRun.shows_checked} av {latestRun.shows_total}
						</dd>
						<dt class="text-muted-foreground">Nya avsnitt</dt>
						<dd class="text-right font-semibold">{latestRun.episodes_found}</dd>
						<dt class="text-muted-foreground">Skickade</dt>
						<dd class="text-right font-semibold text-emerald-600 dark:text-emerald-400">
							{latestRun.episodes_sent}
						</dd>
						<dt class="text-muted-foreground">Väntar på release</dt>
						<dd class="text-right font-semibold">{latestRun.episodes_not_found}</dd>
						<dt class="text-muted-foreground">Hoppades över</dt>
						<dd class="text-right font-semibold">{latestRun.episodes_skipped}</dd>
						<dt class="text-muted-foreground">Fel</dt>
						<dd class="text-right font-semibold" class:text-destructive={latestRun.errors > 0}>
							{latestRun.errors}
						</dd>
					</dl>
				{:else}
					<p class="text-sm text-muted-foreground">Resultatet visas efter första scanningen.</p>
				{/if}
			</div>
		</section>

		{#if latestRun?.message}
			<div
				class="flex items-start gap-3 rounded-2xl border p-4 text-sm {latestRun.status ===
					'failed' ||
				latestRun.status === 'interrupted' ||
				latestRun.errors > 0
					? 'border-destructive/40 bg-destructive/5'
					: 'border-amber-500/40 bg-amber-500/5'}"
				role="alert"
			>
				<TriangleAlert
					class="mt-0.5 size-5 shrink-0 {latestRun.status === 'failed' ||
					latestRun.status === 'interrupted' ||
					latestRun.errors > 0
						? 'text-destructive'
						: 'text-amber-600 dark:text-amber-300'}"
				/>
				<div class="space-y-1">
					{#each latestRun.message.split('\n') as line, index (index)}
						<p>{line}</p>
					{/each}
				</div>
			</div>
		{/if}

		{#if errorItems.length > 0}
			<section
				class="rounded-2xl border border-destructive/40 bg-destructive/5 p-4 md:p-5"
				aria-labelledby="scan-errors-heading"
				role="alert"
			>
				<h2 class="flex items-center gap-2 font-semibold text-destructive" id="scan-errors-heading">
					<TriangleAlert class="size-5" />
					{errorItems.length === 1
						? '1 fel under senaste scanningen'
						: `${errorItems.length} fel under senaste scanningen`}
				</h2>
				<p class="mt-1 text-sm text-muted-foreground">
					Övriga serier kontrollerades som vanligt. Avsnitt med fel försöks igen vid nästa scanning.
				</p>
				<ul class="mt-3 space-y-2">
					{#each errorItems as item (item.id)}
						<li class="rounded-xl border border-destructive/25 bg-card/70 p-3 text-sm">
							<p class="font-semibold">
								{item.show_name ?? 'Okänd serie'}
								{#if episodeCode(item)}<span class="text-muted-foreground"
										>· {episodeCode(item)}</span
									>{/if}
								– {itemLabel(item)}
							</p>
							{#if item.message}
								<p class="mt-1 font-mono text-xs break-words text-muted-foreground">
									{item.message}
								</p>
							{/if}
						</li>
					{/each}
				</ul>
			</section>
		{/if}

		<section class="rounded-2xl border bg-card/55 p-4 md:p-5" aria-labelledby="latest-heading">
			<div class="mb-4">
				<h2 class="text-lg font-semibold" id="latest-heading">Avsnitt i senaste scanningen</h2>
				<p class="text-sm text-muted-foreground">
					Avsnitt som sänts de senaste {status.lookback_days} dagarna räknas som nya. Avsnitt som redan
					finns i biblioteket, ligger i kön eller laddas ned hoppas över.
				</p>
			</div>
			{#if episodeItems.length === 0 && skippedItems.length === 0}
				<div class="empty-panel">
					<CircleCheck class="size-7 text-muted-foreground" />
					<p>
						{latestRun
							? 'Inga nya avsnitt hittades vid senaste scanningen.'
							: 'Starta en scanning för att se resultatet här.'}
					</p>
				</div>
			{:else}
				<ul class="divide-y rounded-xl border bg-card/70">
					{#each episodeItems as item (item.id)}
						<li class="flex flex-wrap items-start justify-between gap-3 p-3 text-sm">
							<div class="min-w-0">
								<p class="font-semibold">
									{item.show_name}
									<span class="text-muted-foreground">· {episodeCode(item)}</span>
								</p>
								{#if item.episode_title}<p class="text-muted-foreground">
										{item.episode_title}
									</p>{/if}
								{#if item.release_title}
									<p class="mt-1 font-mono text-xs break-all text-muted-foreground">
										{item.release_title}{#if item.indexer}
											· {item.indexer}{/if}
									</p>
								{/if}
								{#if item.outcome === 'sent' && item.message}
									<p class="mt-1 text-xs text-amber-600 dark:text-amber-300">
										Obs: {item.message}
									</p>
								{/if}
							</div>
							<span class="outcome-pill" data-outcome={item.outcome}>
								{#if item.outcome === 'sent'}<Download
										class="size-3.5"
									/>{:else if item.outcome === 'not_found'}<Hourglass
										class="size-3.5"
									/>{:else}<TriangleAlert class="size-3.5" />{/if}
								{itemLabel(item)}
							</span>
						</li>
					{/each}
				</ul>
				{#if skippedItems.length > 0}
					<details class="mt-3 rounded-xl border bg-card/40 p-3 text-sm">
						<summary class="cursor-pointer font-semibold">
							{skippedItems.length === 1
								? '1 avsnitt hoppades över'
								: `${skippedItems.length} avsnitt hoppades över`} för att undvika dubbletter
						</summary>
						<ul class="mt-3 space-y-2">
							{#each skippedItems as item (item.id)}
								<li class="flex flex-wrap items-center justify-between gap-2">
									<span>
										<span class="font-medium">{item.show_name}</span>
										<span class="text-muted-foreground">· {episodeCode(item)}</span>
									</span>
									<span class="outcome-pill" data-outcome="skipped">
										<SkipForward class="size-3.5" />
										{itemLabel(item)}
									</span>
								</li>
							{/each}
						</ul>
					</details>
				{/if}
			{/if}
		</section>

		<section class="rounded-2xl border bg-card/55 p-4 md:p-5" aria-labelledby="sent-heading">
			<h2 class="mb-4 text-lg font-semibold" id="sent-heading">Senast skickade för nedladdning</h2>
			{#if recentSent.length === 0}
				<p class="text-sm text-muted-foreground">Scannern har inte skickat några avsnitt ännu.</p>
			{:else}
				<ul class="divide-y rounded-xl border bg-card/70">
					{#each recentSent as item (item.id)}
						<li class="flex flex-wrap items-center justify-between gap-3 p-3 text-sm">
							<div class="min-w-0">
								<p class="font-semibold">
									{item.show_name}
									<span class="text-muted-foreground">· {episodeCode(item)}</span>
								</p>
								{#if item.release_title}
									<p class="font-mono text-xs break-all text-muted-foreground">
										{item.release_title}
									</p>
								{/if}
							</div>
							<span class="text-xs text-muted-foreground">{formatDateTime(item.created_at)}</span>
						</li>
					{/each}
				</ul>
			{/if}
		</section>

		{#if recentRuns.length > 0}
			<section class="rounded-2xl border bg-card/55 p-4 md:p-5" aria-labelledby="history-heading">
				<h2 class="mb-4 text-lg font-semibold" id="history-heading">Historik</h2>
				<div class="overflow-x-auto rounded-xl border bg-card/70">
					<table class="w-full min-w-[36rem] text-left text-sm">
						<thead class="text-xs text-muted-foreground uppercase">
							<tr>
								<th class="px-3 py-2 font-medium">Start</th>
								<th class="px-3 py-2 font-medium">Typ</th>
								<th class="px-3 py-2 font-medium">Status</th>
								<th class="px-3 py-2 text-right font-medium">Serier</th>
								<th class="px-3 py-2 text-right font-medium">Skickade</th>
								<th class="px-3 py-2 text-right font-medium">Fel</th>
							</tr>
						</thead>
						<tbody class="divide-y">
							{#each recentRuns as run (run.id)}
								<tr>
									<td class="px-3 py-2">{formatDateTime(run.started_at)}</td>
									<td class="px-3 py-2">{run.trigger === 'manual' ? 'Manuell' : 'Schemalagd'}</td>
									<td class="px-3 py-2">
										<span class="run-status" data-status={run.status}>
											{runStatusLabels[run.status]}
										</span>
									</td>
									<td class="px-3 py-2 text-right">{run.shows_checked}/{run.shows_total}</td>
									<td class="px-3 py-2 text-right">{run.episodes_sent}</td>
									<td class="px-3 py-2 text-right" class:text-destructive={run.errors > 0}>
										{run.errors}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</section>
		{/if}
	{:else if !statusError}
		<div class="empty-panel">
			<LoaderCircle class="size-7 animate-spin" />
			<p>Hämtar status…</p>
		</div>
	{/if}
</main>

<style>
	.scanner-hero {
		background:
			radial-gradient(
				circle at 85% 20%,
				color-mix(in oklab, var(--primary) 22%, transparent),
				transparent 36%
			),
			linear-gradient(
				135deg,
				color-mix(in oklab, var(--card) 92%, transparent),
				color-mix(in oklab, var(--primary) 7%, var(--card))
			);
	}

	.stat-card {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		border: 1px solid var(--border);
		border-radius: 1.25rem;
		padding: 1.1rem 1.2rem;
		background: color-mix(in oklab, var(--card) 70%, transparent);
	}

	.stat-label {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		margin-bottom: 0.35rem;
		color: var(--muted-foreground);
		font-size: 0.8rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.stat-value {
		font-size: 1.35rem;
		font-weight: 700;
		letter-spacing: -0.01em;
	}

	.run-status,
	.outcome-pill {
		display: inline-flex;
		width: fit-content;
		align-items: center;
		gap: 0.35rem;
		border: 1px solid var(--border);
		border-radius: 999px;
		padding: 0.15rem 0.6rem;
		font-size: 0.75rem;
		font-weight: 600;
		white-space: nowrap;
	}

	.run-status[data-status='succeeded'],
	.outcome-pill[data-outcome='sent'] {
		border-color: color-mix(in oklab, #10b981 45%, transparent);
		background: color-mix(in oklab, #10b981 14%, transparent);
		color: color-mix(in oklab, #10b981 70%, var(--foreground));
	}

	.run-status[data-status='completed_with_errors'],
	.outcome-pill[data-outcome='not_found'] {
		border-color: color-mix(in oklab, #f59e0b 45%, transparent);
		background: color-mix(in oklab, #f59e0b 14%, transparent);
		color: color-mix(in oklab, #f59e0b 65%, var(--foreground));
	}

	.run-status[data-status='failed'],
	.run-status[data-status='interrupted'],
	.outcome-pill[data-outcome='error'] {
		border-color: color-mix(in oklab, var(--destructive) 45%, transparent);
		background: color-mix(in oklab, var(--destructive) 12%, transparent);
		color: var(--destructive);
	}

	.run-status[data-status='running'] {
		border-color: color-mix(in oklab, var(--primary) 45%, transparent);
		background: color-mix(in oklab, var(--primary) 12%, transparent);
		color: var(--primary);
	}

	.outcome-pill {
		max-width: 100%;
		white-space: normal;
	}

	.outcome-pill[data-outcome='skipped'] {
		color: var(--muted-foreground);
	}

	.empty-panel {
		display: flex;
		min-height: 9rem;
		align-items: center;
		justify-content: center;
		flex-direction: column;
		gap: 0.6rem;
		border: 1px dashed var(--border);
		border-radius: 1.25rem;
		padding: 1.5rem;
		text-align: center;
		color: var(--muted-foreground);
	}
</style>
