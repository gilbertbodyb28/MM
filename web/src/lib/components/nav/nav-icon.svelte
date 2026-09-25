<script lang="ts">
	let {
		icon: Icon,
		name
	}: {
		// Lucide's generated component types differ slightly across installed packages.
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		icon: any;
		name: string;
	} = $props();
</script>

<span class="mm-nav-icon" data-icon-name={name.toLowerCase().replaceAll(' ', '-')} aria-hidden="true">
	<Icon />
</span>
