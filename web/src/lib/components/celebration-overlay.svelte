<script lang="ts">
	import { confetti } from '@neoconfetti/svelte';
	import { onMount } from 'svelte';
	import {
		getCelebrationSettings,
		MEDIA_ADDED_SUCCESS_EVENT,
		type CelebrationSettings,
		type CelebrationSound,
		type CelebrationVisual,
		type MediaAddedSuccessDetail
	} from '$lib/celebration';

	let visual = $state<CelebrationVisual>('none');
	let runId = $state(0);
	let clearTimer: ReturnType<typeof setTimeout> | null = null;
	let audioContext: AudioContext | null = null;
	const particles = Array.from({ length: 32 }, (_, index) => index);

	function tone(
		context: AudioContext,
		frequency: number,
		start: number,
		duration: number,
		gainValue: number,
		type: OscillatorType = 'sine',
		endFrequency?: number
	): void {
		const oscillator = context.createOscillator();
		const gain = context.createGain();
		oscillator.type = type;
		oscillator.frequency.setValueAtTime(frequency, start);
		if (endFrequency)
			oscillator.frequency.exponentialRampToValueAtTime(endFrequency, start + duration);
		gain.gain.setValueAtTime(0.0001, start);
		gain.gain.exponentialRampToValueAtTime(Math.max(0.0001, gainValue), start + 0.02);
		gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
		oscillator.connect(gain).connect(context.destination);
		oscillator.start(start);
		oscillator.stop(start + duration + 0.03);
	}

	async function readyAudioContext(): Promise<AudioContext | null> {
		if (typeof window === 'undefined') return null;
		const AudioContextClass = window.AudioContext;
		if (!AudioContextClass) return null;
		audioContext ??= new AudioContextClass();
		if (audioContext.state === 'suspended') await audioContext.resume();
		return audioContext;
	}

	function primeAudio(): void {
		if (getCelebrationSettings().sound === 'none') return;
		void readyAudioContext().catch(() => {
			// Browser autoplay policy may still decline; a failed sound never affects Add.
		});
	}

	async function playSound(sound: CelebrationSound, volume: number): Promise<void> {
		if (sound === 'none' || volume <= 0) return;
		const context = await readyAudioContext();
		if (!context) return;
		const now = context.currentTime + 0.015;
		const level = Math.min(1, volume) * 0.22;

		if (sound === 'pop') {
			tone(context, 180, now, 0.13, level, 'sine', 640);
			tone(context, 900, now + 0.035, 0.08, level * 0.45, 'triangle', 420);
		} else if (sound === 'woohoo') {
			tone(context, 300, now, 0.24, level * 0.65, 'sawtooth', 610);
			tone(context, 430, now + 0.16, 0.3, level * 0.55, 'triangle', 880);
		} else {
			[523.25, 659.25, 783.99, 1046.5].forEach((frequency, index) => {
				tone(context, frequency, now + index * 0.105, 0.34, level * 0.55, 'triangle');
			});
		}
	}

	function run(settings: CelebrationSettings): void {
		void playSound(settings.sound, settings.volume).catch(() => {
			// Sound is optional feedback and must never reject the confirmed Add flow.
		});
		const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		visual = reducedMotion ? 'none' : settings.visual;
		runId += 1;
		if (clearTimer) clearTimeout(clearTimer);
		clearTimer = setTimeout(() => (visual = 'none'), 3400);
	}

	onMount(() => {
		const previewListener = (event: Event) =>
			run((event as CustomEvent<CelebrationSettings>).detail);
		const mediaAddedListener = (event: Event) => {
			const detail = (event as CustomEvent<MediaAddedSuccessDetail>).detail;
			if (!detail || detail.count < 1) return;
			const settings = getCelebrationSettings();
			if (settings.enabled) run(settings);
		};
		window.addEventListener('pointerdown', primeAudio, { capture: true });
		window.addEventListener('keydown', primeAudio, { capture: true });
		window.addEventListener('mediamanager:celebrate', previewListener);
		window.addEventListener(MEDIA_ADDED_SUCCESS_EVENT, mediaAddedListener);
		return () => {
			window.removeEventListener('pointerdown', primeAudio, { capture: true });
			window.removeEventListener('keydown', primeAudio, { capture: true });
			window.removeEventListener('mediamanager:celebrate', previewListener);
			window.removeEventListener(MEDIA_ADDED_SUCCESS_EVENT, mediaAddedListener);
			if (clearTimer) clearTimeout(clearTimer);
			if (audioContext) void audioContext.close().catch(() => undefined);
		};
	});
</script>

{#if visual !== 'none'}
	<div class="celebration-layer" aria-hidden="true" data-visual={visual}>
		{#key runId}
			{#if visual === 'confetti'}
				<div
					class="celebration-origin"
					use:confetti={{
						particleCount: 180,
						particleSize: 11,
						duration: 3000,
						force: 0.72,
						stageHeight: typeof window === 'undefined' ? 900 : window.innerHeight,
						stageWidth: typeof window === 'undefined' ? 1440 : window.innerWidth,
						colors: ['#67e8f9', '#818cf8', '#f472b6', '#fbbf24', '#ffffff']
					}}
				></div>
			{:else}
				<div class="particle-field">
					{#each particles as particle (particle)}
						<span
							style={`--particle:${particle}; --angle:${particle * 11.25}deg; --burst-delay:${(particle % 5) * 28}ms; --firework-delay:${(particle % 8) * 55}ms; --sparkle-mid:${8 + (particle % 4) * 7}vmin; --sparkle-end:${10 + (particle % 4) * 9}vmin;`}
						></span>
					{/each}
				</div>
			{/if}
		{/key}
	</div>
{/if}

<style>
	.celebration-layer {
		position: fixed;
		inset: 0;
		z-index: 100;
		pointer-events: none;
		overflow: hidden;
	}

	.celebration-origin,
	.particle-field {
		position: absolute;
		left: 50%;
		top: 55%;
		width: 1px;
		height: 1px;
	}

	.particle-field span {
		--distance: 34vmin;
		position: absolute;
		width: 0.65rem;
		height: 0.65rem;
		border-radius: 999px;
		background: hsl(calc(var(--particle) * 41deg) 92% 67%);
		box-shadow: 0 0 18px currentColor;
		animation: celebration-burst 1.35s cubic-bezier(0.17, 0.75, 0.28, 1) both;
		animation-delay: var(--burst-delay);
	}

	[data-visual='sparkles'] .particle-field span {
		width: 0.42rem;
		height: 1.15rem;
		border-radius: 0.1rem;
		background: white;
		transform: rotate(var(--angle));
		animation-name: celebration-sparkle;
		animation-duration: 2.2s;
	}

	[data-visual='fireworks'] .particle-field {
		top: 40%;
	}

	[data-visual='fireworks'] .particle-field span {
		--distance: 26vmin;
		animation-name: celebration-firework;
		animation-duration: 1.7s;
		animation-delay: var(--firework-delay);
	}

	@keyframes celebration-burst {
		0% {
			opacity: 0;
			transform: rotate(var(--angle)) translateX(0) scale(0.2);
		}
		18% {
			opacity: 1;
		}
		100% {
			opacity: 0;
			transform: rotate(var(--angle)) translateX(var(--distance)) scale(0.1);
		}
	}

	@keyframes celebration-sparkle {
		0% {
			opacity: 0;
			transform: rotate(var(--angle)) translateX(8vmin) scale(0);
		}
		28%,
		58% {
			opacity: 1;
			transform: rotate(var(--angle)) translateX(var(--sparkle-mid)) scale(1);
		}
		100% {
			opacity: 0;
			transform: rotate(var(--angle)) translateX(var(--sparkle-end)) scale(0);
		}
	}

	@keyframes celebration-firework {
		0% {
			opacity: 0;
			transform: rotate(var(--angle)) translateX(0) scale(0.15);
		}
		22% {
			opacity: 1;
		}
		70% {
			opacity: 0.9;
			transform: rotate(var(--angle)) translateX(var(--distance)) scale(0.7);
		}
		100% {
			opacity: 0;
			transform: rotate(var(--angle)) translateX(var(--distance)) translateY(18vmin) scale(0.1);
		}
	}
</style>
