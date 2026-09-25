<script lang="ts">
	import { LiquidButton, LiquidGlass } from 'liquid-svelte';
</script>

<div class="page">
	<div class="background-shape shape-1"></div>
	<div class="background-shape shape-2"></div>

	<LiquidGlass
		width={340}
		height={220}
		borderRadius={36}
		bezel={24}
		interactive
	>
		<div class="glass-content">
			<h1>Liquid Glass</h1>
			<p>Media Manager test</p>

			<LiquidButton
				size="lg"
				tone="prominent"
				onclick={() => alert('Liquid fungerar!')}
			>
				Testa Liquid
			</LiquidButton>
		</div>
	</LiquidGlass>
</div>

<style>
	:global(body) {
		margin: 0;
	}

	.page {
		position: relative;
		display: grid;
		place-items: center;
		min-height: 100vh;
		overflow: hidden;
		color: white;
		background:
			radial-gradient(circle at 20% 30%, #5268ff 0%, transparent 35%),
			radial-gradient(circle at 80% 70%, #e24d9d 0%, transparent 35%),
			#0b0d14;
	}

	.background-shape {
		position: absolute;
		width: 300px;
		height: 300px;
		border-radius: 999px;
	}

	.shape-1 {
		top: 15%;
		left: 15%;
		background: #5268ff;
	}

	.shape-2 {
		right: 15%;
		bottom: 15%;
		background: #e24d9d;
	}

	.glass-content {
		display: flex;
		height: 100%;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		text-align: center;
	}

	h1 {
		margin: 0;
		font-size: 2.2rem;
	}

	p {
		margin: 0.5rem 0 1.5rem;
		opacity: 0.7;
	}
</style>