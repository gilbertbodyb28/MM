export const SIDEBAR_PREFERENCES_STORAGE_KEY = 'mediamanager.sidebar-preferences';

export type SidebarSize = 'small' | 'medium' | 'large';
export type SidebarIconStyle = 'outline' | 'glass';

export interface SidebarPreferences {
	size: SidebarSize;
	iconStyle: SidebarIconStyle;
}

export const DEFAULT_SIDEBAR_PREFERENCES: SidebarPreferences = {
	size: 'medium',
	iconStyle: 'glass'
};

export const sidebarSizeOptions = [
	{ value: 'small', label: 'Small', description: 'A compact 15rem sidebar.' },
	{ value: 'medium', label: 'Medium', description: 'The current 18rem sidebar.' },
	{ value: 'large', label: 'Large', description: 'A spacious 21rem sidebar.' }
] as const satisfies ReadonlyArray<{
	value: SidebarSize;
	label: string;
	description: string;
}>;

export const sidebarIconStyleOptions = [
	{
		value: 'outline',
		label: 'Outline',
		description: 'Clean Lucide line icons without a surrounding tile.'
	},
	{
		value: 'glass',
		label: 'Glass',
		description: 'Frosted icon tiles with layered highlights and depth.'
	}
] as const satisfies ReadonlyArray<{
	value: SidebarIconStyle;
	label: string;
	description: string;
}>;

function isSidebarSize(value: unknown): value is SidebarSize {
	return sidebarSizeOptions.some((option) => option.value === value);
}

function isIconStyle(value: unknown): value is SidebarIconStyle {
	return sidebarIconStyleOptions.some((option) => option.value === value);
}

function normalize(value: unknown): SidebarPreferences {
	if (!value || typeof value !== 'object') return { ...DEFAULT_SIDEBAR_PREFERENCES };
	const candidate = value as Partial<SidebarPreferences>;
	return {
		size: isSidebarSize(candidate.size) ? candidate.size : DEFAULT_SIDEBAR_PREFERENCES.size,
		iconStyle: isIconStyle(candidate.iconStyle)
			? candidate.iconStyle
			: DEFAULT_SIDEBAR_PREFERENCES.iconStyle
	};
}

export function getSidebarPreferences(): SidebarPreferences {
	if (typeof window === 'undefined') return { ...DEFAULT_SIDEBAR_PREFERENCES };
	try {
		return normalize(
			JSON.parse(window.localStorage.getItem(SIDEBAR_PREFERENCES_STORAGE_KEY) ?? 'null')
		);
	} catch {
		return { ...DEFAULT_SIDEBAR_PREFERENCES };
	}
}

export function applySidebarPreferences(
	preferences: SidebarPreferences,
	persist = true
): SidebarPreferences {
	const normalized = normalize(preferences);
	if (typeof document !== 'undefined') {
		document.documentElement.dataset.sidebarSize = normalized.size;
		document.documentElement.dataset.sidebarIconStyle = normalized.iconStyle;
	}
	if (persist && typeof window !== 'undefined') {
		try {
			window.localStorage.setItem(SIDEBAR_PREFERENCES_STORAGE_KEY, JSON.stringify(normalized));
		} catch (error) {
			console.warn('[Appearance] Sidebar preference applied without browser persistence', error);
		}
		window.dispatchEvent(
			new CustomEvent<SidebarPreferences>('mediamanager:sidebar-preferences', {
				detail: normalized
			})
		);
	}
	return normalized;
}

export function initializeSidebarPreferences(): SidebarPreferences {
	return applySidebarPreferences(getSidebarPreferences(), true);
}
