export const CELEBRATION_STORAGE_KEY = 'mediamanager.add-series-celebration';

export type CelebrationVisual = 'none' | 'confetti' | 'fireworks' | 'sparkles' | 'burst';
export type CelebrationSound = 'none' | 'woohoo' | 'pop' | 'victory';

export interface CelebrationSettings {
	enabled: boolean;
	visual: CelebrationVisual;
	sound: CelebrationSound;
	volume: number;
}

export interface MediaAddedSuccessDetail {
	operationId: string;
	count: number;
	source: string;
}

export const MEDIA_ADDED_SUCCESS_EVENT = 'mediamanager:media-added-success';
const recentSuccessOperations = new Map<string, number>();
const SUCCESS_DEDUPLICATION_WINDOW_MS = 30_000;

export const DEFAULT_CELEBRATION: CelebrationSettings = {
	enabled: true,
	visual: 'confetti',
	sound: 'pop',
	volume: 0.55
};

export const celebrationVisualOptions = [
	{ value: 'none', label: 'None' },
	{ value: 'confetti', label: 'Confetti' },
	{ value: 'fireworks', label: 'Fireworks' },
	{ value: 'sparkles', label: 'Sparkles' },
	{ value: 'burst', label: 'Burst' }
] as const;

export const celebrationSoundOptions = [
	{ value: 'none', label: 'None' },
	{ value: 'woohoo', label: 'Woohoo' },
	{ value: 'pop', label: 'Pop' },
	{ value: 'victory', label: 'Success / Victory' }
] as const;

function isVisual(value: unknown): value is CelebrationVisual {
	return celebrationVisualOptions.some((option) => option.value === value);
}

function isSound(value: unknown): value is CelebrationSound {
	return celebrationSoundOptions.some((option) => option.value === value);
}

function normalize(value: unknown): CelebrationSettings {
	if (!value || typeof value !== 'object') return { ...DEFAULT_CELEBRATION };
	const candidate = value as Partial<CelebrationSettings>;
	return {
		enabled:
			typeof candidate.enabled === 'boolean' ? candidate.enabled : DEFAULT_CELEBRATION.enabled,
		visual: isVisual(candidate.visual) ? candidate.visual : DEFAULT_CELEBRATION.visual,
		sound: isSound(candidate.sound) ? candidate.sound : DEFAULT_CELEBRATION.sound,
		volume:
			typeof candidate.volume === 'number' && Number.isFinite(candidate.volume)
				? Math.min(1, Math.max(0, candidate.volume))
				: DEFAULT_CELEBRATION.volume
	};
}

export function getCelebrationSettings(): CelebrationSettings {
	if (typeof window === 'undefined') return { ...DEFAULT_CELEBRATION };
	try {
		return normalize(JSON.parse(window.localStorage.getItem(CELEBRATION_STORAGE_KEY) ?? 'null'));
	} catch {
		return { ...DEFAULT_CELEBRATION };
	}
}

export function saveCelebrationSettings(settings: CelebrationSettings): CelebrationSettings {
	const normalized = normalize(settings);
	if (typeof window !== 'undefined') {
		try {
			window.localStorage.setItem(CELEBRATION_STORAGE_KEY, JSON.stringify(normalized));
		} catch (error) {
			console.warn('[MediaAdd] Celebration preference applied without browser persistence', error);
		}
		window.dispatchEvent(
			new CustomEvent<CelebrationSettings>('mediamanager:celebration-settings', {
				detail: normalized
			})
		);
	}
	return normalized;
}

export function triggerCelebration(
	overrides?: Partial<CelebrationSettings> & { force?: boolean }
): void {
	if (typeof window === 'undefined') return;
	const force = overrides?.force ?? false;
	const settings = normalize({ ...getCelebrationSettings(), ...overrides });
	if (!force && !settings.enabled) return;
	window.dispatchEvent(
		new CustomEvent<CelebrationSettings>('mediamanager:celebrate', { detail: settings })
	);
}

/**
 * Publish the one semantic success event used by every confirmed media creation.
 * Celebration preferences are intentionally applied by the global listener so
 * callers cannot bypass disabled sound, disabled motion, or reduced-motion.
 */
export function emitMediaAddedSuccess(detail: MediaAddedSuccessDetail): boolean {
	if (typeof window === 'undefined' || detail.count < 1 || !detail.operationId.trim()) return false;

	const now = Date.now();
	for (const [operationId, emittedAt] of recentSuccessOperations) {
		if (now - emittedAt > SUCCESS_DEDUPLICATION_WINDOW_MS) {
			recentSuccessOperations.delete(operationId);
		}
	}
	if (recentSuccessOperations.has(detail.operationId)) return false;

	recentSuccessOperations.set(detail.operationId, now);
	window.dispatchEvent(
		new CustomEvent<MediaAddedSuccessDetail>(MEDIA_ADDED_SUCCESS_EVENT, { detail })
	);
	console.info('[MediaAdd] Celebration emitted', { source: detail.source, count: detail.count });
	return true;
}
