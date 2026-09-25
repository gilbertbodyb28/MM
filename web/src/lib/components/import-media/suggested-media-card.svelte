<script lang="ts">
	import { Button } from '$lib/components/ui/button/index.js';
	import PosterCard from '$lib/components/media/poster-card.svelte';
	import type { MetaDataProviderSearchResult } from '$lib/api/api';

	let {
		result,
		action
	}: {
		result: MetaDataProviderSearchResult;
		action: () => void;
	} = $props();
</script>

<PosterCard title={result.name} year={result.year} posterPath={result.poster_path}>
	{#snippet actions()}
		<Button class="w-full font-semibold" onclick={action}>Import using this metadata</Button>
	{/snippet}
</PosterCard>
