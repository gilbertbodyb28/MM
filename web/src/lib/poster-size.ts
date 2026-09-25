export const POSTER_SIZE_STORAGE_KEY = 'mediamanager.poster-size';

export const posterSizeOptions = [
	{ value: 'small', label: 'Small' },
	{ value: 'medium', label: 'Medium' },
	{ value: 'large', label: 'Large' }
] as const;

export type PosterSize = (typeof posterSizeOptions)[number]['value'];

export const DEFAULT_POSTER_SIZE: PosterSize = 'medium';

export function isPosterSize(value: unknown): value is PosterSize {
	return posterSizeOptions.some((option) => option.value === value);
}

export function getPosterSize(): PosterSize {
	if (typeof window === 'undefined') return DEFAULT_POSTER_SIZE;
	try {
		const storedValue = window.localStorage.getItem(POSTER_SIZE_STORAGE_KEY);
		return isPosterSize(storedValue) ? storedValue : DEFAULT_POSTER_SIZE;
	} catch (error) {
		console.warn('[Appearance] Poster-size persistence is unavailable; using medium', error);
		return DEFAULT_POSTER_SIZE;
	}
}

export function applyPosterSize(size: PosterSize, persist = true): PosterSize {
	if (typeof document !== 'undefined') {
		document.documentElement.dataset.posterSize = size;
	}

	if (persist && typeof window !== 'undefined') {
		try {
			window.localStorage.setItem(POSTER_SIZE_STORAGE_KEY, size);
		} catch (error) {
			console.warn('[Appearance] Poster size applied without browser persistence', error);
		}
		window.dispatchEvent(new CustomEvent<PosterSize>('mediamanager:poster-size', { detail: size }));
	}

	return size;
}

export function initializePosterSize(): PosterSize {
	return applyPosterSize(getPosterSize(), false);
}
