<script lang="ts" module>
	import {
		Bell,
		BrainCircuit,
		CalendarDays,
		CircleDollarSign,
		Clapperboard,
		Compass,
		DownloadCloud,
		Home,
		Info,
		LifeBuoy,
		ListVideo,
		Settings,
		TvIcon
	} from 'lucide-svelte';
	import { resolve } from '$app/paths';

	import { PUBLIC_VERSION } from '$env/static/public';

	const data = {
		navMain: [
			{
				title: 'Dashboard',
				url: resolve('/dashboard', {}),
				icon: Home,
				isActive: true,
				adminOnly: false
			},
			{
				title: 'Discover',
				url: resolve('/dashboard/discover', {}),
				icon: Compass,
				isActive: true,
				adminOnly: false
			},
			{
				title: 'AI Recommendations',
				url: resolve('/dashboard/ai-recommendations', {}),
				icon: BrainCircuit,
				isActive: true,
				adminOnly: false
			},
			{
				title: 'Trakt',
				url: resolve('/dashboard/trakt', {}),
				icon: ListVideo,
				isActive: true,
				adminOnly: false
			},
			{
				title: 'qBittorrent',
				url: resolve('/dashboard/downloads', {}),
				icon: DownloadCloud,
				isActive: true,
				adminOnly: true
			},
			{
				title: 'Calendar',
				url: resolve('/dashboard/calendar', {}),
				icon: CalendarDays,
				isActive: true,
				adminOnly: false
			},
			{
				title: 'TV Shows',
				url: resolve('/dashboard/tv', {}),
				icon: TvIcon,
				isActive: true,
				adminOnly: false,
				items: [
					{
						title: 'Add a show',
						url: resolve('/dashboard/tv/add-show', {})
					},
					{
						title: 'Torrents',
						url: resolve('/dashboard/tv/torrents', {})
					},
					{
						title: 'Avsnittsscanner',
						url: resolve('/dashboard/tv/scanner', {})
					}
				]
			},
			{
				title: 'Movies',
				url: resolve('/dashboard/movies', {}),
				icon: Clapperboard,
				isActive: true,
				adminOnly: false,
				items: [
					{
						title: 'Add a movie',
						url: resolve('/dashboard/movies/add-movie', {})
					},
					{
						title: 'Torrents',
						url: resolve('/dashboard/movies/torrents', {})
					}
				]
			}
		],
		navSecondary: [
			{
				title: 'Notifications',
				url: resolve('/dashboard/notifications', {}),
				icon: Bell
			},
			{
				title: 'Settings',
				url: resolve('/dashboard/settings', {}),
				icon: Settings
			},
			{
				title: 'Support',
				url: 'https://github.com/maxdorninger/MediaManager/issues',
				icon: LifeBuoy
			},
			{
				title: 'Donate',
				url: 'https://github.com/sponsors/maxdorninger',
				icon: CircleDollarSign
			},
			{
				title: 'About',
				url: resolve('/dashboard/about', {}),
				icon: Info
			}
		]
	};
</script>

<script lang="ts">
	import { page } from '$app/state';
	import NavMain from '$lib/components/nav/nav-main.svelte';
	import NavSecondary from '$lib/components/nav/nav-secondary.svelte';
	import * as Sidebar from '$lib/components/ui/sidebar';
	import type { ComponentProps } from 'svelte';
	import logo from '$lib/images/logo.svg';

	let { ref = $bindable(null), ...restProps }: ComponentProps<typeof Sidebar.Root> = $props();
</script>

<Sidebar.Root
	{...restProps}
	bind:ref
	class="mm-app-sidebar"
	collapsible="icon"
	data-theme-region="sidebar"
	variant="floating"
>
	<Sidebar.Header class="mm-sidebar-header">
		<Sidebar.Menu>
			<Sidebar.MenuItem class="relative">
				<Sidebar.MenuButton class="mm-brand-button" size="lg">
					{#snippet child({ props })}
						<a href={resolve('/dashboard', {})} {...props}>
							<span class="mm-brand-mark">
								<img class="size-10" src={logo} alt="Media Manager Logo" />
							</span>
							<div class="grid flex-1 text-left text-sm leading-tight">
								<span class="truncate text-base font-semibold tracking-tight">MediaManager</span>
								<span class="truncate text-[0.68rem] text-sidebar-foreground/60"
									>{PUBLIC_VERSION}</span
								>
							</div>
						</a>
					{/snippet}
				</Sidebar.MenuButton>
				<Sidebar.Trigger class="mm-sidebar-collapse" aria-label="Collapse sidebar" />
			</Sidebar.MenuItem>
		</Sidebar.Menu>
	</Sidebar.Header>
	<Sidebar.Content class="mm-sidebar-content">
		<NavMain
			items={data.navMain.filter((item) => !item.adminOnly || page.data.user?.is_superuser)}
		/>
		<NavSecondary class="mt-auto" items={data.navSecondary} />
	</Sidebar.Content>
	<Sidebar.Rail />
</Sidebar.Root>
