import { setMode } from 'mode-watcher';

export const APPEARANCE_STORAGE_KEY = 'mediamanager.appearance';

export type AppearanceTheme =
	| 'light'
	| 'dark'
	| 'glassmorphism'
	| 'liquid-glass-dark'
	| 'liquid-glass-light';
export type AppearanceScope = 'global' | 'sidebar' | 'discover' | 'downloads';
export type GlassIntensity = 'clear' | 'balanced' | 'frosted' | 'extra-frosted';

export interface AppearanceSettings {
	theme: AppearanceTheme;
	scope: AppearanceScope;
	intensity: GlassIntensity;
}

export const DEFAULT_APPEARANCE: AppearanceSettings = {
	theme: 'liquid-glass-dark',
	scope: 'sidebar',
	intensity: 'frosted'
};

export const ORIGINAL_MEDIAMANAGER_APPEARANCE: AppearanceSettings = {
	theme: 'dark',
	scope: 'global',
	intensity: 'frosted'
};

export const appearanceThemeOptions = [
	{
		value: 'light',
		label: 'Light',
		description: 'Bright, clean surfaces with crisp contrast.'
	},
	{
		value: 'dark',
		label: 'Dark',
		description: 'Deep neutral surfaces designed for low-light viewing.'
	},
	{
		value: 'glassmorphism',
		label: 'Glassmorphism',
		description: 'Structured frosted panels with environmental colour bleed.'
	},
	{
		value: 'liquid-glass-dark',
		label: 'Liquid Glass Dark',
		description: 'Luminous dark glass with layered depth and edge highlights.'
	},
	{
		value: 'liquid-glass-light',
		label: 'Liquid Glass Light',
		description: 'Airy translucent glass with bright refraction and soft shadows.'
	}
] as const satisfies ReadonlyArray<{
	value: AppearanceTheme;
	label: string;
	description: string;
}>;

export const appearanceScopeOptions = [
	{ value: 'sidebar', label: 'Sidebar only' },
	{ value: 'discover', label: 'Discover only' },
	{ value: 'downloads', label: 'qBittorrent only' },
	{ value: 'global', label: 'Global' }
] as const satisfies ReadonlyArray<{ value: AppearanceScope; label: string }>;

export const glassIntensityOptions = [
	{ value: 'clear', label: 'Clear' },
	{ value: 'balanced', label: 'Balanced' },
	{ value: 'frosted', label: 'Frosted' },
	{ value: 'extra-frosted', label: 'Extra Frosted' }
] as const satisfies ReadonlyArray<{ value: GlassIntensity; label: string }>;

export function isGlassTheme(theme: AppearanceTheme): boolean {
	return theme === 'glassmorphism' || theme.startsWith('liquid-glass');
}

function isTheme(value: unknown): value is AppearanceTheme {
	return appearanceThemeOptions.some((option) => option.value === value);
}

function isScope(value: unknown): value is AppearanceScope {
	return appearanceScopeOptions.some((option) => option.value === value);
}

function isIntensity(value: unknown): value is GlassIntensity {
	return glassIntensityOptions.some((option) => option.value === value);
}

function migrateLegacySettings(value: unknown): AppearanceSettings | null {
	if (!value || typeof value !== 'object') return null;
	const legacy = value as { style?: unknown; scopes?: unknown };
	if (legacy.style !== 'liquid' && legacy.style !== 'figma') return null;

	const scopes = Array.isArray(legacy.scopes) ? legacy.scopes : [];
	let scope: AppearanceScope = 'sidebar';
	if (scopes.includes('entire')) scope = 'global';
	else if (scopes.includes('sidebar')) scope = 'sidebar';
	else if (scopes.includes('discover')) scope = 'discover';
	else if (scopes.includes('downloads')) scope = 'downloads';

	return {
		theme: legacy.style === 'liquid' ? 'liquid-glass-dark' : 'glassmorphism',
		scope,
		intensity: 'frosted'
	};
}

function normalizeSettings(value: unknown): AppearanceSettings | null {
	if (!value || typeof value !== 'object') return migrateLegacySettings(value);
	const candidate = value as Partial<AppearanceSettings>;
	if (!isTheme(candidate.theme) || !isScope(candidate.scope)) {
		return migrateLegacySettings(value);
	}
	return {
		theme: candidate.theme,
		scope: candidate.scope,
		intensity: isIntensity(candidate.intensity) ? candidate.intensity : 'frosted'
	};
}

export function getAppearance(): AppearanceSettings {
	if (typeof window === 'undefined') return { ...DEFAULT_APPEARANCE };
	try {
		const stored: unknown = JSON.parse(
			window.localStorage.getItem(APPEARANCE_STORAGE_KEY) ?? 'null'
		);
		return normalizeSettings(stored) ?? { ...DEFAULT_APPEARANCE };
	} catch {
		return { ...DEFAULT_APPEARANCE };
	}
}

function baseModeFor(settings: AppearanceSettings): 'light' | 'dark' {
	// Scoped themes need a deterministic original canvas. Returning null here
	// left mode-watcher's previous class in place, so the result depended on the
	// theme that happened to be active before this selection.
	if (settings.scope !== 'global') return 'dark';
	if (settings.theme === 'light' || settings.theme === 'liquid-glass-light') return 'light';
	return 'dark';
}

export function applyAppearance(settings: AppearanceSettings, persist = true): AppearanceSettings {
	const normalized = normalizeSettings(settings) ?? { ...DEFAULT_APPEARANCE };
	if (typeof document !== 'undefined') {
		const root = document.documentElement;
		root.dataset.mmTheme = normalized.theme;
		root.dataset.mmScope = normalized.scope;
		root.dataset.glassIntensity = normalized.intensity;

		// Remove attributes from the recovered, multi-scope implementation. Leaving
		// them behind would let old selectors leak into the newly selected scope.
		delete root.dataset.glassStyle;
		delete root.dataset.glassEntire;
		delete root.dataset.glassSidebar;
		delete root.dataset.glassDiscover;
		delete root.dataset.glassDownloads;

		setMode(baseModeFor(normalized));
	}
	if (persist && typeof window !== 'undefined') {
		try {
			window.localStorage.setItem(APPEARANCE_STORAGE_KEY, JSON.stringify(normalized));
		} catch (error) {
			console.warn('[Appearance] Theme applied, but browser persistence is unavailable', error);
		}
		window.dispatchEvent(
			new CustomEvent<AppearanceSettings>('mediamanager:appearance', { detail: normalized })
		);
	}
	return normalized;
}

export function initializeAppearance(): AppearanceSettings {
	const appearance = getAppearance();
	let migrated = false;
	if (typeof window !== 'undefined') {
		try {
			migrated =
				window.localStorage.getItem(APPEARANCE_STORAGE_KEY) !== JSON.stringify(appearance);
		} catch (error) {
			console.warn('[Appearance] Browser persistence is unavailable; using safe defaults', error);
		}
	}
	return applyAppearance(appearance, migrated);
}
