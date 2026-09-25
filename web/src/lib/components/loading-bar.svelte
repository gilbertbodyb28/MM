<script lang="ts">
	import { Progress } from '$lib/components/ui/progress/index.js';
	import { onMount } from 'svelte';

	let value = $state(0);

	onMount(() => {
		const interval = setInterval(() => {
			value += 1;
		}, 1);

		return () => clearInterval(interval);
	});
</script>

<Progress {value} />
