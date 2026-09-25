<script lang="ts">
	import { onMount } from 'svelte';
	import { env } from '$env/dynamic/public';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { toast } from 'svelte-sonner';
	import * as Breadcrumb from '$lib/components/ui/breadcrumb/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Dialog from '$lib/components/ui/dialog/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Progress } from '$lib/components/ui/progress/index.js';
	import { Separator } from '$lib/components/ui/separator/index.js';
	import * as Sidebar from '$lib/components/ui/sidebar/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import {
		ArrowDownToLine,
		ArrowUpFromLine,
		CircleGauge,
		DownloadCloud,
		HardDrive,
		Infinity as InfinityIcon,
		Link,
		LoaderCircle,
		Pause,
		Play,
		Plus,
		RefreshCw,
		Search,
		Trash2,
		Wifi,
		WifiOff
	} from 'lucide-svelte';

	type QbTorrent = {
		hash: string;
		name: string;
		state: string;
		progress: number;
		download_speed: number;
		upload_speed: number;
		eta: number | null;
		size: number;
		downloaded: number;
		uploaded: number;
		amount_left: number;
		ratio: number;
		seeds: number;
		peers: number;
		category: string;
		added_on: number | null;
		completion_on: number | null;
	};

	type QbServerState = {
		connection_status: string;
		download_speed: number;
		upload_speed: number;
		total_downloaded: number;
		total_uploaded: number;
		free_space: number;
	};

	type QbSyncResponse = {
		rid: number;
		full_update: boolean;
		torrents: Record<string, QbTorrent>;
		removed: string[];
		categories: string[];
		server_state: QbServerState | null;
	};

	type StatusFilter = 'all' | 'active' | 'downloading' | 'completed' | 'paused' | 'stalled';

	const emptyServerState: QbServerState = {
		connection_status: 'disconnected',
		download_speed: 0,
		upload_speed: 0,
		total_downloaded: 0,
		total_uploaded: 0,
		free_space: 0
	};

	let torrents = $state<Record<string, QbTorrent>>({});
	let serverState = $state<QbServerState>({ ...emptyServerState });
	let categories = $state<string[]>([]);
	let rid = 0;
	let initialLoading = $state(true);
	let syncing = $state(false);
	let loadError = $state('');
	let searchQuery = $state('');
	let statusFilter = $state<StatusFilter>('all');
	let categoryFilter = $state('all');
	let pendingHashes = $state<string[]>([]);
	let addDialogOpen = $state(false);
	let magnetUri = $state('');
	let addCategory = $state('');
	let adding = $state(false);
	let deleteDialogOpen = $state(false);
	let deleteTarget = $state<QbTorrent | null>(null);
	let deleting = $state(false);
	let pollTimer: number | undefined;
	let disposed = false;
	let fullSyncQueued = false;

	const torrentList = $derived(
		Object.values(torrents)
			.filter((torrent) => {
				const query = searchQuery.trim().toLowerCase();
				if (query && !torrent.name.toLowerCase().includes(query)) return false;
				if (categoryFilter !== 'all' && torrent.category !== categoryFilter) return false;
				return matchesStatus(torrent, statusFilter);
			})
			.toSorted((left, right) => {
				const leftActive = isActive(left) ? 1 : 0;
				const rightActive = isActive(right) ? 1 : 0;
				if (leftActive !== rightActive) return rightActive - leftActive;
				return (right.added_on ?? 0) - (left.added_on ?? 0);
			})
	);
	const allTorrents = $derived(Object.values(torrents));
	const activeCount = $derived(allTorrents.filter(isActive).length);
	const downloadingCount = $derived(allTorrents.filter(isDownloading).length);
	const completedCount = $derived(allTorrents.filter(isComplete).length);
	const isSuperuser = $derived(Boolean(page.data.user?.is_superuser));
	const isConnected = $derived(serverState.connection_status !== 'disconnected');
	const isFirewalled = $derived(serverState.connection_status === 'firewalled');

	function apiUrl(path: string): string {
		const base = env.PUBLIC_API_URL?.replace(/\/$/, '') ?? '';
		return `${base}${path}`;
	}

	async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
		const response = await fetch(apiUrl(path), {
			credentials: 'include',
			...init,
			headers: {
				...(init?.body ? { 'Content-Type': 'application/json' } : {}),
				...init?.headers
			}
		});
		if (!response.ok) {
			let detail = `Request failed (${response.status})`;
			try {
				const payload = (await response.json()) as { detail?: string };
				if (payload.detail) detail = payload.detail;
			} catch {
				// Keep the status-based message when the server returns no JSON body.
			}
			throw new Error(detail);
		}
		if (response.status === 204) return undefined as T;
		return (await response.json()) as T;
	}

	function schedulePoll(delay = 2_000) {
		if (disposed || !isSuperuser) return;
		if (pollTimer !== undefined) window.clearTimeout(pollTimer);
		pollTimer = window.setTimeout(() => void sync(false), delay);
	}

	async function sync(forceFull: boolean) {
		if (disposed || !isSuperuser) return;
		if (syncing) {
			fullSyncQueued ||= forceFull;
			return;
		}
		if (document.hidden) {
			schedulePoll();
			return;
		}
		syncing = true;
		try {
			const requestedRid = forceFull ? 0 : rid;
			const data = await apiRequest<QbSyncResponse>(
				`/api/v1/downloads/qbittorrent/sync?rid=${requestedRid}`
			);
			const nextTorrents = data.full_update ? {} : { ...torrents };
			for (const [hash, torrent] of Object.entries(data.torrents ?? {})) {
				nextTorrents[hash] = torrent;
			}
			for (const hash of data.removed ?? []) delete nextTorrents[hash];
			torrents = nextTorrents;
			rid = data.rid;
			if (data.server_state) serverState = data.server_state;
			categories = data.categories ?? [];
			loadError = '';
		} catch (error) {
			loadError = error instanceof Error ? error.message : 'Could not reach qBittorrent.';
			serverState = { ...emptyServerState };
		} finally {
			initialLoading = false;
			syncing = false;
			if (fullSyncQueued) {
				fullSyncQueued = false;
				void sync(true);
			} else {
				schedulePoll(loadError ? 5_000 : 2_000);
			}
		}
	}

	function handleVisibilityChange() {
		if (!document.hidden) void sync(true);
	}

	onMount(() => {
		if (!isSuperuser) {
			initialLoading = false;
			return;
		}
		void sync(true);
		document.addEventListener('visibilitychange', handleVisibilityChange);
		return () => {
			disposed = true;
			document.removeEventListener('visibilitychange', handleVisibilityChange);
			if (pollTimer !== undefined) window.clearTimeout(pollTimer);
		};
	});

	function isDownloading(torrent: QbTorrent): boolean {
		return ['downloading', 'forcedDL', 'metaDL', 'forcedMetaDL'].includes(torrent.state);
	}

	function isComplete(torrent: QbTorrent): boolean {
		return torrent.progress >= 1;
	}

	function isPaused(torrent: QbTorrent): boolean {
		return ['pausedDL', 'pausedUP', 'stoppedDL', 'stoppedUP'].includes(torrent.state);
	}

	function isStalled(torrent: QbTorrent): boolean {
		return torrent.state.startsWith('stalled') || torrent.state === 'error';
	}

	function isActive(torrent: QbTorrent): boolean {
		return torrent.download_speed > 0 || torrent.upload_speed > 0 || isDownloading(torrent);
	}

	function matchesStatus(torrent: QbTorrent, filter: StatusFilter): boolean {
		if (filter === 'all') return true;
		if (filter === 'active') return isActive(torrent);
		if (filter === 'downloading') return isDownloading(torrent);
		if (filter === 'completed') return isComplete(torrent);
		if (filter === 'paused') return isPaused(torrent);
		return isStalled(torrent);
	}

	function stateLabel(torrent: QbTorrent): string {
		if (isPaused(torrent)) return isComplete(torrent) ? 'Stopped' : 'Paused';
		if (torrent.state === 'error' || torrent.state === 'missingFiles') return 'Error';
		if (torrent.state.startsWith('stalled')) return 'Stalled';
		if (isDownloading(torrent)) return 'Downloading';
		if (isComplete(torrent) && torrent.upload_speed > 0) return 'Seeding';
		if (isComplete(torrent)) return 'Complete';
		if (torrent.state.startsWith('queued')) return 'Queued';
		if (torrent.state.startsWith('checking')) return 'Checking';
		return torrent.state || 'Unknown';
	}

	function stateClass(torrent: QbTorrent): string {
		if (torrent.state === 'error' || torrent.state === 'missingFiles') {
			return 'border-destructive/30 bg-destructive/10 text-destructive';
		}
		if (isStalled(torrent)) return 'border-amber-500/30 bg-amber-500/10 text-amber-600';
		if (isDownloading(torrent)) return 'border-blue-500/30 bg-blue-500/10 text-blue-600';
		if (isComplete(torrent)) return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600';
		return 'border-border bg-muted text-muted-foreground';
	}

	function progressPercent(torrent: QbTorrent): number {
		return Math.min(100, Math.max(0, torrent.progress * 100));
	}

	function formatPercent(torrent: QbTorrent): string {
		return `${progressPercent(torrent).toFixed(2)}%`;
	}

	function formatBytes(value: number): string {
		if (!Number.isFinite(value) || value <= 0) return '0 B';
		const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
		const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
		const scaled = value / 1024 ** index;
		return `${scaled.toFixed(scaled >= 100 || index === 0 ? 0 : scaled >= 10 ? 1 : 2)} ${units[index]}`;
	}

	function formatRate(value: number): string {
		return `${formatBytes(value)}/s`;
	}

	function formatEta(value: number | null): string {
		if (value == null || value < 0 || value >= 8_640_000) return '∞';
		if (value === 0) return 'Done';
		const days = Math.floor(value / 86_400);
		const hours = Math.floor((value % 86_400) / 3_600);
		const minutes = Math.floor((value % 3_600) / 60);
		const seconds = Math.floor(value % 60);
		if (days > 0) return `${days}d ${hours}h`;
		if (hours > 0) return `${hours}h ${minutes}m`;
		if (minutes > 0) return `${minutes}m ${seconds}s`;
		return `${seconds}s`;
	}

	function formatDate(timestamp: number | null): string {
		if (!timestamp) return 'Unknown';
		return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
			new Date(timestamp * 1_000)
		);
	}

	function setPending(hash: string, pending: boolean) {
		pendingHashes = pending
			? [...new Set([...pendingHashes, hash])]
			: pendingHashes.filter((item) => item !== hash);
	}

	async function runTorrentAction(torrent: QbTorrent, action: 'pause' | 'resume') {
		setPending(torrent.hash, true);
		try {
			await apiRequest<void>(
				`/api/v1/downloads/qbittorrent/${encodeURIComponent(torrent.hash)}/${action}`,
				{
					method: 'POST'
				}
			);
			toast.success(action === 'pause' ? 'Torrent paused.' : 'Torrent resumed.');
			rid = 0;
			await sync(true);
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Torrent action failed.');
		} finally {
			setPending(torrent.hash, false);
		}
	}

	function askToDelete(torrent: QbTorrent) {
		deleteTarget = torrent;
		deleteDialogOpen = true;
	}

	async function deleteTorrent(deleteFiles: boolean) {
		if (!deleteTarget) return;
		deleting = true;
		try {
			await apiRequest<void>(
				`/api/v1/downloads/qbittorrent/${encodeURIComponent(deleteTarget.hash)}?delete_files=${deleteFiles}`,
				{ method: 'DELETE' }
			);
			toast.success(
				deleteFiles ? 'Torrent and downloaded files removed.' : 'Torrent removed; files kept.'
			);
			deleteDialogOpen = false;
			deleteTarget = null;
			rid = 0;
			await sync(true);
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Could not remove torrent.');
		} finally {
			deleting = false;
		}
	}

	async function addMagnet() {
		if (!magnetUri.trim().toLowerCase().startsWith('magnet:?')) {
			toast.error('Paste a valid magnet link.');
			return;
		}
		adding = true;
		try {
			await apiRequest<void>('/api/v1/downloads/qbittorrent/add', {
				method: 'POST',
				body: JSON.stringify({
					magnet_uri: magnetUri.trim(),
					category: addCategory || null
				})
			});
			toast.success('Magnet sent to qBittorrent.');
			addDialogOpen = false;
			magnetUri = '';
			addCategory = '';
			rid = 0;
			await sync(true);
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Could not add magnet.');
		} finally {
			adding = false;
		}
	}
</script>

<svelte:head>
	<title>qBittorrent - MediaManager</title>
	<meta
		name="description"
		content="Monitor and control the connected qBittorrent client from MediaManager"
	/>
</svelte:head>

<header class="flex h-16 shrink-0 items-center gap-2">
	<div class="flex min-w-0 items-center gap-2 px-4">
		<Sidebar.Trigger class="-ml-1" />
		<Separator class="mr-2 h-4" orientation="vertical" />
		<Breadcrumb.Root>
			<Breadcrumb.List>
				<Breadcrumb.Item class="hidden md:block">
					<Breadcrumb.Link href={resolve('/dashboard', {})}>MediaManager</Breadcrumb.Link>
				</Breadcrumb.Item>
				<Breadcrumb.Separator class="hidden md:block" />
				<Breadcrumb.Item><Breadcrumb.Page>qBittorrent</Breadcrumb.Page></Breadcrumb.Item>
			</Breadcrumb.List>
		</Breadcrumb.Root>
	</div>
</header>

{#if !isSuperuser}
	<main class="mx-auto grid w-full max-w-3xl flex-1 place-items-center p-6">
		<section class="w-full rounded-3xl border bg-card p-8 text-center shadow-sm">
			<HardDrive class="mx-auto size-10 text-muted-foreground" aria-hidden="true" />
			<h1 class="mt-4 text-2xl font-black">Administrator access required</h1>
			<p class="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">
				The qBittorrent dashboard can display and control downloads outside MediaManager, so it is
				available only to administrators.
			</p>
		</section>
	</main>
{:else}
	<main
		class="glass-downloads mx-auto flex w-full max-w-[110rem] flex-1 flex-col gap-6 p-4 pt-2 sm:p-6 lg:p-8"
		data-theme-region="downloads"
	>
		<section class="relative overflow-hidden rounded-3xl border bg-card p-5 shadow-sm sm:p-7">
			<div
				class="pointer-events-none absolute -top-28 -right-20 size-72 rounded-full bg-primary/10 blur-3xl"
			></div>
			<div class="relative flex flex-col justify-between gap-5 lg:flex-row lg:items-center">
				<div class="flex min-w-0 items-start gap-4">
					<div
						class="grid size-12 shrink-0 place-items-center rounded-2xl bg-primary text-primary-foreground shadow-sm sm:size-14"
					>
						<DownloadCloud class="size-6 sm:size-7" aria-hidden="true" />
					</div>
					<div class="min-w-0">
						<div class="flex flex-wrap items-center gap-2">
							<h1 class="text-2xl font-black tracking-tight sm:text-3xl">qBittorrent</h1>
							<span
								class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-bold {isConnected
									? isFirewalled
										? 'border-amber-500/30 bg-amber-500/10 text-amber-600'
										: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600'
									: 'border-destructive/30 bg-destructive/10 text-destructive'}"
							>
								{#if isConnected}<Wifi class="size-3.5" />
									{isFirewalled ? 'Firewalled' : 'Connected'}{:else}<WifiOff class="size-3.5" /> Disconnected{/if}
							</span>
						</div>
						<p class="mt-2 max-w-2xl text-sm text-muted-foreground sm:text-base">
							Live progress, transfer speeds and safe controls for the qBittorrent client connected
							in Settings.
						</p>
					</div>
				</div>
				<div class="flex flex-wrap gap-2">
					<Button variant="outline" onclick={() => void sync(true)} disabled={syncing}>
						<RefreshCw class={syncing ? 'animate-spin' : ''} /> Refresh
					</Button>
					<Button onclick={() => (addDialogOpen = true)}>
						<Plus /> Add magnet
					</Button>
				</div>
			</div>
		</section>

		{#if loadError}
			<section
				class="flex flex-col gap-3 rounded-2xl border border-destructive/30 bg-destructive/10 p-4 text-sm sm:flex-row sm:items-center sm:justify-between"
				aria-live="polite"
			>
				<div>
					<p class="font-bold text-destructive">qBittorrent is not available</p>
					<p class="mt-1 text-muted-foreground">{loadError}</p>
				</div>
				<Button variant="outline" onclick={() => void sync(true)} disabled={syncing}
					>Try again</Button
				>
			</section>
		{/if}

		<section class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Transfer summary">
			<Card.Root class="rounded-2xl">
				<Card.Content class="flex items-center justify-between p-5">
					<div>
						<p class="text-xs font-bold tracking-wide text-muted-foreground uppercase">Download</p>
						<p class="mt-2 text-2xl font-black tabular-nums">
							{formatRate(serverState.download_speed)}
						</p>
						<p class="mt-1 text-xs text-muted-foreground">{downloadingCount} downloading</p>
					</div>
					<div class="grid size-11 place-items-center rounded-xl bg-blue-500/10 text-blue-600">
						<ArrowDownToLine class="size-5" />
					</div>
				</Card.Content>
			</Card.Root>
			<Card.Root class="rounded-2xl">
				<Card.Content class="flex items-center justify-between p-5">
					<div>
						<p class="text-xs font-bold tracking-wide text-muted-foreground uppercase">Upload</p>
						<p class="mt-2 text-2xl font-black tabular-nums">
							{formatRate(serverState.upload_speed)}
						</p>
						<p class="mt-1 text-xs text-muted-foreground">{completedCount} complete</p>
					</div>
					<div
						class="grid size-11 place-items-center rounded-xl bg-emerald-500/10 text-emerald-600"
					>
						<ArrowUpFromLine class="size-5" />
					</div>
				</Card.Content>
			</Card.Root>
			<Card.Root class="rounded-2xl">
				<Card.Content class="flex items-center justify-between p-5">
					<div>
						<p class="text-xs font-bold tracking-wide text-muted-foreground uppercase">Active</p>
						<p class="mt-2 text-2xl font-black tabular-nums">{activeCount}</p>
						<p class="mt-1 text-xs text-muted-foreground">of {allTorrents.length} torrents</p>
					</div>
					<div class="grid size-11 place-items-center rounded-xl bg-violet-500/10 text-violet-600">
						<CircleGauge class="size-5" />
					</div>
				</Card.Content>
			</Card.Root>
			<Card.Root class="rounded-2xl">
				<Card.Content class="flex items-center justify-between p-5">
					<div>
						<p class="text-xs font-bold tracking-wide text-muted-foreground uppercase">
							Free space
						</p>
						<p class="mt-2 text-2xl font-black tabular-nums">
							{formatBytes(serverState.free_space)}
						</p>
						<p class="mt-1 text-xs text-muted-foreground">qBittorrent storage</p>
					</div>
					<div class="grid size-11 place-items-center rounded-xl bg-amber-500/10 text-amber-600">
						<HardDrive class="size-5" />
					</div>
				</Card.Content>
			</Card.Root>
		</section>

		<section class="overflow-hidden rounded-3xl border bg-card shadow-sm">
			<div class="flex flex-col gap-3 border-b p-4 lg:flex-row lg:items-center lg:justify-between">
				<div class="relative min-w-0 flex-1 lg:max-w-md">
					<Search
						class="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
					/>
					<Input
						bind:value={searchQuery}
						class="pl-9"
						placeholder="Filter by torrent name…"
						aria-label="Filter torrents by name"
					/>
				</div>
				<div class="grid gap-2 sm:grid-cols-2 lg:flex">
					<select
						bind:value={statusFilter}
						class="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm focus:ring-1 focus:ring-ring focus:outline-none"
						aria-label="Filter by status"
					>
						<option value="all">All statuses</option>
						<option value="active">Active</option>
						<option value="downloading">Downloading</option>
						<option value="completed">Completed</option>
						<option value="paused">Paused / stopped</option>
						<option value="stalled">Stalled / errors</option>
					</select>
					<select
						bind:value={categoryFilter}
						class="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm focus:ring-1 focus:ring-ring focus:outline-none"
						aria-label="Filter by category"
					>
						<option value="all">All categories</option>
						{#each categories as category (category)}
							<option value={category}>{category || 'Uncategorized'}</option>
						{/each}
					</select>
				</div>
			</div>

			{#if initialLoading}
				<div class="grid min-h-72 place-items-center p-8 text-center">
					<div>
						<LoaderCircle class="mx-auto size-8 animate-spin text-primary" />
						<p class="mt-3 text-sm font-semibold">Loading qBittorrent…</p>
					</div>
				</div>
			{:else if torrentList.length === 0}
				<div class="grid min-h-72 place-items-center p-8 text-center">
					<div>
						<DownloadCloud class="mx-auto size-10 text-muted-foreground/60" />
						<h2 class="mt-4 text-lg font-bold">No matching torrents</h2>
						<p class="mt-2 max-w-md text-sm text-muted-foreground">
							{allTorrents.length === 0
								? 'The connected qBittorrent client has no torrents yet.'
								: 'Change the name, status or category filter to see more torrents.'}
						</p>
					</div>
				</div>
			{:else}
				<div class="hidden overflow-x-auto md:block">
					<table class="w-full min-w-[1050px] text-left text-sm">
						<thead
							class="bg-muted/40 text-xs font-bold tracking-wide text-muted-foreground uppercase"
						>
							<tr>
								<th class="px-5 py-3">Torrent</th>
								<th class="px-4 py-3">Status</th>
								<th class="min-w-56 px-4 py-3">Progress</th>
								<th class="px-4 py-3">Speed</th>
								<th class="px-4 py-3">ETA</th>
								<th class="px-4 py-3">Peers</th>
								<th class="px-5 py-3 text-right">Actions</th>
							</tr>
						</thead>
						<tbody class="divide-y">
							{#each torrentList as torrent (torrent.hash)}
								{@const percent = progressPercent(torrent)}
								{@const pending = pendingHashes.includes(torrent.hash)}
								<tr class="transition-colors hover:bg-muted/30">
									<td class="max-w-[28rem] px-5 py-4">
										<p class="truncate font-bold" title={torrent.name}>{torrent.name}</p>
										<div class="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
											<span>{formatBytes(torrent.size)}</span>
											<span>{torrent.category || 'Uncategorized'}</span>
											<span title={formatDate(torrent.added_on)}
												>Added {formatDate(torrent.added_on)}</span
											>
										</div>
									</td>
									<td class="px-4 py-4">
										<span
											class={`inline-flex rounded-full border px-2.5 py-1 text-xs font-bold ${stateClass(torrent)}`}
										>
											{stateLabel(torrent)}
										</span>
									</td>
									<td class="px-4 py-4">
										<div class="flex items-center justify-between gap-3 text-xs">
											<span>{formatBytes(torrent.downloaded)} / {formatBytes(torrent.size)}</span>
											<strong class="tabular-nums">{formatPercent(torrent)}</strong>
										</div>
										<Progress value={percent} class="mt-2 h-2.5" />
									</td>
									<td class="px-4 py-4 text-xs tabular-nums">
										<p class="font-semibold text-blue-600">
											↓ {formatRate(torrent.download_speed)}
										</p>
										<p class="mt-1 font-semibold text-emerald-600">
											↑ {formatRate(torrent.upload_speed)}
										</p>
									</td>
									<td class="px-4 py-4 font-semibold tabular-nums">
										{#if torrent.eta == null || torrent.eta >= 8_640_000}
											<span class="inline-flex items-center gap-1"
												><InfinityIcon class="size-4" /> No ETA</span
											>
										{:else}{formatEta(torrent.eta)}{/if}
									</td>
									<td class="px-4 py-4 text-xs tabular-nums">
										<p>{torrent.seeds} seeds</p>
										<p class="mt-1 text-muted-foreground">{torrent.peers} peers</p>
									</td>
									<td class="px-5 py-4">
										<div class="flex justify-end gap-1">
											<Button
												variant="ghost"
												size="icon"
												disabled={pending}
												onclick={() =>
													void runTorrentAction(torrent, isPaused(torrent) ? 'resume' : 'pause')}
												aria-label={isPaused(torrent)
													? `Resume ${torrent.name}`
													: `Pause ${torrent.name}`}
												title={isPaused(torrent) ? 'Start / resume' : 'Pause / stop'}
											>
												{#if pending}<LoaderCircle
														class="animate-spin"
													/>{:else if isPaused(torrent)}<Play />{:else}<Pause />{/if}
											</Button>
											<Button
												variant="ghost"
												size="icon"
												disabled={pending}
												onclick={() => askToDelete(torrent)}
												aria-label={`Remove ${torrent.name}`}
												title="Remove torrent"
											>
												<Trash2 class="text-destructive" />
											</Button>
										</div>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>

				<div class="grid gap-3 p-3 md:hidden">
					{#each torrentList as torrent (torrent.hash)}
						{@const percent = progressPercent(torrent)}
						{@const pending = pendingHashes.includes(torrent.hash)}
						<article class="rounded-2xl border bg-background p-4 shadow-sm">
							<div class="flex items-start justify-between gap-3">
								<div class="min-w-0">
									<h2 class="line-clamp-2 leading-snug font-bold">{torrent.name}</h2>
									<p class="mt-1 text-xs text-muted-foreground">
										{formatBytes(torrent.size)} · {torrent.category || 'Uncategorized'}
									</p>
								</div>
								<span
									class={`shrink-0 rounded-full border px-2 py-1 text-[11px] font-bold ${stateClass(torrent)}`}
								>
									{stateLabel(torrent)}
								</span>
							</div>
							<div class="mt-4 flex items-center justify-between text-xs">
								<span>{formatBytes(torrent.downloaded)} / {formatBytes(torrent.size)}</span>
								<strong class="tabular-nums">{formatPercent(torrent)}</strong>
							</div>
							<Progress value={percent} class="mt-2 h-2.5" />
							<div
								class="mt-4 grid grid-cols-3 gap-2 rounded-xl bg-muted/50 p-3 text-center text-xs"
							>
								<div>
									<p class="text-muted-foreground">Down</p>
									<p class="mt-1 font-bold text-blue-600">{formatRate(torrent.download_speed)}</p>
								</div>
								<div>
									<p class="text-muted-foreground">Up</p>
									<p class="mt-1 font-bold text-emerald-600">{formatRate(torrent.upload_speed)}</p>
								</div>
								<div>
									<p class="text-muted-foreground">ETA</p>
									<p class="mt-1 font-bold">{formatEta(torrent.eta)}</p>
								</div>
							</div>
							<div class="mt-3 flex justify-end gap-2">
								<Button
									variant="outline"
									size="sm"
									disabled={pending}
									onclick={() =>
										void runTorrentAction(torrent, isPaused(torrent) ? 'resume' : 'pause')}
								>
									{#if pending}<LoaderCircle
											class="animate-spin"
										/>{:else if isPaused(torrent)}<Play /> Start{:else}<Pause /> Pause{/if}
								</Button>
								<Button
									variant="outline"
									size="sm"
									disabled={pending}
									onclick={() => askToDelete(torrent)}
								>
									<Trash2 class="text-destructive" /> Remove
								</Button>
							</div>
						</article>
					{/each}
				</div>
			{/if}
		</section>
	</main>
{/if}

<Dialog.Root bind:open={addDialogOpen}>
	<Dialog.Content class="sm:max-w-lg">
		<Dialog.Header>
			<Dialog.Title class="flex items-center gap-2"
				><Link class="size-5" /> Add magnet link</Dialog.Title
			>
			<Dialog.Description>
				The magnet is sent directly to the connected qBittorrent client. File paths cannot be
				overridden here.
			</Dialog.Description>
		</Dialog.Header>
		<div class="grid gap-4 py-2">
			<div class="grid gap-2">
				<label for="magnet-uri" class="text-sm font-semibold">Magnet link</label>
				<Textarea
					id="magnet-uri"
					bind:value={magnetUri}
					class="min-h-24 resize-y font-mono text-xs"
					placeholder="magnet:?xt=urn:btih:…"
					autocomplete="off"
				/>
			</div>
			<div class="grid gap-2">
				<label for="magnet-category" class="text-sm font-semibold">Category (optional)</label>
				<select
					id="magnet-category"
					bind:value={addCategory}
					class="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm focus:ring-1 focus:ring-ring focus:outline-none"
				>
					<option value="">qBittorrent default</option>
					{#each categories as category (category)}
						<option value={category}>{category || 'Uncategorized'}</option>
					{/each}
				</select>
			</div>
		</div>
		<Dialog.Footer>
			<Button variant="outline" onclick={() => (addDialogOpen = false)} disabled={adding}
				>Cancel</Button
			>
			<Button onclick={() => void addMagnet()} disabled={adding || !magnetUri.trim()}>
				{#if adding}<LoaderCircle class="animate-spin" />{/if} Add to qBittorrent
			</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={deleteDialogOpen}>
	<Dialog.Content class="sm:max-w-lg">
		<Dialog.Header>
			<Dialog.Title>Remove torrent?</Dialog.Title>
			<Dialog.Description>
				Choose whether qBittorrent should keep or permanently delete the downloaded files for “{deleteTarget?.name ??
					''}”.
			</Dialog.Description>
		</Dialog.Header>
		<div
			class="rounded-xl border border-destructive/25 bg-destructive/5 p-3 text-sm text-muted-foreground"
		>
			Deleting downloaded files cannot be undone. MediaManager never selects that option by default.
		</div>
		<Dialog.Footer class="sm:flex-col sm:items-stretch">
			<Button variant="ghost" onclick={() => (deleteDialogOpen = false)} disabled={deleting}
				>Cancel</Button
			>
			<Button variant="outline" onclick={() => void deleteTorrent(false)} disabled={deleting}>
				{#if deleting}<LoaderCircle class="animate-spin" />{/if} Remove torrent, keep files
			</Button>
			<Button variant="destructive" onclick={() => void deleteTorrent(true)} disabled={deleting}>
				<Trash2 /> Remove torrent and delete files
			</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
