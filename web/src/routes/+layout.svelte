<script lang="ts">
	import '../app.css';
	import { ModeWatcher } from 'mode-watcher';
	import { Toaster } from '$lib/components/ui/sonner/index.js';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import { initializePosterSize } from '$lib/poster-size';
	import { initializeAppearance } from '$lib/appearance';
	import { initializeAppearancePackages } from '$lib/appearance-packages';
	import CelebrationOverlay from '$lib/components/celebration-overlay.svelte';
	import { initializeSidebarPreferences } from '$lib/sidebar-preferences';

	let { children } = $props();

	onMount(() => {
		initializePosterSize();
		initializeAppearance();
		initializeAppearancePackages();
		initializeSidebarPreferences();
	});
</script>

<svelte:head>
	<title>MediaManager</title>
	<meta content="Smart PVR for movies and TV shows" name="description" />
	<link href={resolve('/logo.svg', {})} rel="icon" type="image/svg" />
</svelte:head>

<ModeWatcher />
<Toaster />
<CelebrationOverlay />
{@render children()}
