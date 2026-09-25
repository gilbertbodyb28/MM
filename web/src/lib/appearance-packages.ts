export const APPEARANCE_PACKAGES_STORAGE_KEY = 'mediamanager.appearance-packages';

export type AppearancePackageCategory = 'theme' | 'icon' | 'controls' | 'sidebar';
export type AppearancePackageAccess =
	| 'local'
	| 'accessible'
	| 'partially-accessible'
	| 'needs-node'
	| 'access-blocked'
	| 'rate-limited';

export interface AppearancePackageDefinition {
	id: string;
	name: string;
	category: AppearancePackageCategory;
	scope: 'global' | 'icons' | 'controls' | 'sidebar';
	sourceReference: string | null;
	access: AppearancePackageAccess;
	implemented: boolean;
	description: string;
	limitation?: string;
}

export interface AppearancePackageSettings {
	theme: string;
	icon: string;
	controls: string;
	sidebar: string;
}

export const DEFAULT_APPEARANCE_PACKAGES: AppearancePackageSettings = {
	theme: 'existing-theme',
	icon: 'existing-icons',
	controls: 'existing-controls',
	sidebar: 'existing-sidebar'
};

export const appearancePackageRegistry = [
	{
		id: 'existing-theme',
		name: 'Existing MediaManager themes',
		category: 'theme',
		scope: 'global',
		sourceReference: null,
		access: 'local',
		implemented: true,
		description: 'Uses the protected Light, Dark, Glassmorphism and Liquid Glass choices above.'
	},
	{
		id: 'os26-liquid-glass',
		name: 'OS26 Liquid Glass',
		category: 'theme',
		scope: 'global',
		sourceReference:
			'https://www.figma.com/design/GbBwCxjfOxxCMIxoT85nLC/OS26---Liquid-Glass-Components--Community-?node-id=14-81',
		access: 'partially-accessible',
		implemented: false,
		description: 'OS26 Liquid Glass component language.',
		limitation:
			'The cover node was found, but exact component context was blocked by the Figma MCP limit.'
	},
	{
		id: 'cryptocurrency-dashboard',
		name: 'Cryptocurrency Dashboard',
		category: 'theme',
		scope: 'global',
		sourceReference:
			'https://www.figma.com/design/m7jihClADPEDIwe55cvBqg/Cryptocurrency-Dashboard---FREEBIE--Community-?node-id=301-127',
		access: 'partially-accessible',
		implemented: false,
		description: 'The dashboard visual system without cryptocurrency demo content.',
		limitation:
			'Metadata was accessible; exact component context was blocked by the Figma MCP limit.'
	},
	{
		id: 'dashboard-community',
		name: 'Dashboard Community',
		category: 'theme',
		scope: 'global',
		sourceReference:
			'https://www.figma.com/design/rNCbprehQfSROGIgATATnJ/Dashboard--Community-?node-id=5-2',
		access: 'partially-accessible',
		implemented: false,
		description: 'Dashboard Community visual package.',
		limitation:
			'Metadata was accessible; exact component context was blocked by the Figma MCP limit.'
	},
	{
		id: 'liquid-glass-effect',
		name: 'Liquid Glass Effect',
		category: 'theme',
		scope: 'global',
		sourceReference:
			'https://www.figma.com/design/ZetyznkpWdA4qNJ8WaLe93/Liquid-Glass-Effect--Community-?node-id=0-1',
		access: 'partially-accessible',
		implemented: false,
		description: 'The dedicated Liquid Glass Effect source.',
		limitation:
			'The viewer node was found; exact effects could not be retrieved after the tool limit.'
	},
	{
		id: 'weather-web-ui',
		name: 'Weather Web UI',
		category: 'theme',
		scope: 'global',
		sourceReference:
			'https://www.figma.com/design/VhGkTJ06g4syLD6ApjonSW/Weather-Web-Design-%7C-App-UI--Community-?node-id=1-5045',
		access: 'partially-accessible',
		implemented: false,
		description: 'Weather Web UI material language applied to MediaManager content.',
		limitation:
			'Metadata was accessible; exact component context was blocked by the Figma MCP limit.'
	},
	{
		id: 'apple-liquid-glass',
		name: 'Apple Liquid Glass',
		category: 'theme',
		scope: 'global',
		sourceReference:
			'https://www.figma.com/design/TO8EpoFJgsjEfnc4qtERZn/Apple-Liquid-Glass---Effect--Community-?node-id=0-1',
		access: 'partially-accessible',
		implemented: false,
		description: 'The specific Apple Liquid Glass effect source.',
		limitation: 'The cover node was found, but exact effects were unavailable after the tool limit.'
	},
	{
		id: 'glassy-cards',
		name: 'Glassy Cards',
		category: 'theme',
		scope: 'global',
		sourceReference:
			'https://www.figma.com/design/NK1Xs1NOCGwg19tR7TKxTC/Glassy---12-Trendy-Glassmorphism-Cards---%F0%9F%94%A5--Community-?node-id=0-1',
		access: 'rate-limited',
		implemented: false,
		description: 'Glassy card material package.',
		limitation: 'The Figma Starter-plan MCP call limit was reached before inspection.'
	},
	{
		id: 'glass-morphism-weather-cards',
		name: 'Glass Morphism Weather Cards',
		category: 'theme',
		scope: 'global',
		sourceReference:
			'https://www.figma.com/design/y9BeujHd75zq2ASTNmAWXF/Glass-Morphism---Weather-Cards--Community-?node-id=0-1',
		access: 'rate-limited',
		implemented: false,
		description: 'Independent weather-card glass material package.',
		limitation: 'The Figma Starter-plan MCP call limit was reached before inspection.'
	},
	{
		id: 'glassmorphism-dashboard-ui-kit',
		name: 'Glassmorphism Dashboard UI Kit',
		category: 'theme',
		scope: 'global',
		sourceReference:
			'https://www.figma.com/make/0xEir8LGXvz4PLixzEZliX/Glassmorphism-Dashboard-UI-Kit--Community-',
		access: 'rate-limited',
		implemented: false,
		description: 'Glassmorphism Dashboard UI Kit from Figma Make.',
		limitation: 'Exact Figma Make context could not be retrieved after the tool limit.'
	},
	{
		id: 'vision-ui',
		name: 'Vision UI',
		category: 'theme',
		scope: 'global',
		sourceReference:
			'https://www.figma.com/design/aEJxiRFkxoTJHyzvukJi5u/Vision-UI-Dashboard-Free--Community-?node-id=1601-6435',
		access: 'rate-limited',
		implemented: false,
		description: 'Vision UI Dashboard visual package.',
		limitation: 'The Figma Starter-plan MCP call limit was reached before inspection.'
	},
	{
		id: 'permissions-dashboard',
		name: 'Permissions Dashboard',
		category: 'theme',
		scope: 'global',
		sourceReference:
			'https://www.figma.com/make/FdSKuFRwJs7rHwVEQbwfrv/Glassmorphism-Permissions-Dashboard--Community-',
		access: 'rate-limited',
		implemented: false,
		description: 'Glassmorphism Permissions Dashboard package.',
		limitation: 'Exact Figma Make context could not be retrieved after the tool limit.'
	},
	{
		id: 'finance-glassmorphism',
		name: 'Finance Glassmorphism',
		category: 'theme',
		scope: 'global',
		sourceReference:
			'https://www.figma.com/design/hsszGBcNIJAEApZgKjXOFm/Finance-dashboard--Glassmorphism--Community-?node-id=0-1',
		access: 'rate-limited',
		implemented: false,
		description: 'Finance Dashboard Glassmorphism package.',
		limitation: 'The Figma Starter-plan MCP call limit was reached before inspection.'
	},
	{
		id: 'glassmorphism-all-in-one',
		name: 'Glassmorphism All-in-One',
		category: 'theme',
		scope: 'global',
		sourceReference:
			'https://www.figma.com/design/9XFwYhwyry3fIfEoWeLBF6/Glassmorphism_All-in-one--Community-',
		access: 'needs-node',
		implemented: false,
		description: 'Glassmorphism All-in-One package.',
		limitation: 'A concrete node-specific Figma URL is required.'
	},
	{
		id: 'glassmorphism-community',
		name: 'Glassmorphism Community',
		category: 'theme',
		scope: 'global',
		sourceReference:
			'https://www.figma.com/design/zDo270tWPW47AKxOTsBKHa/Glassmorphism--Community-?node-id=0-1',
		access: 'rate-limited',
		implemented: false,
		description: 'Independent Glassmorphism Community package.',
		limitation: 'The Figma Starter-plan MCP call limit was reached before inspection.'
	},
	{
		id: 'dashboard-glassmorphism',
		name: 'Dashboard Glassmorphism',
		category: 'theme',
		scope: 'global',
		sourceReference:
			'https://www.figma.com/design/ZFQYHhMEUhDb2aMf5qngd7/Dashboard-Glassmorphism--Community-',
		access: 'needs-node',
		implemented: false,
		description: 'Dashboard Glassmorphism package.',
		limitation: 'The supplied URL contains an incomplete node-id value.'
	},
	{
		id: 'glassmorphism-dashboard-ui-kit-second',
		name: 'Glassmorphism Dashboard UI Kit (Second Reference)',
		category: 'theme',
		scope: 'global',
		sourceReference:
			'https://www.figma.com/design/lW0OZUIpcgBqCaYP0a9tOZ/Glassmorphism-Dashboard-UI-Kit--Community-',
		access: 'needs-node',
		implemented: false,
		description: 'Second independent Glassmorphism Dashboard UI Kit reference.',
		limitation: 'A concrete node-specific Figma URL is required.'
	},
	{
		id: 'jaxa-glassmorphism',
		name: 'Jaxa Glassmorphism',
		category: 'theme',
		scope: 'global',
		sourceReference:
			'https://www.figma.com/design/0Y24VrTgODyfdJG797wYo0/Jaxa-Dashboard-Glassmorphism--Community-',
		access: 'needs-node',
		implemented: false,
		description: 'Jaxa Dashboard Glassmorphism package.',
		limitation: 'A concrete node-specific Figma URL is required.'
	},
	{
		id: 'glassmorphism-dashboard-design',
		name: 'Glassmorphism Dashboard Design',
		category: 'theme',
		scope: 'global',
		sourceReference:
			'https://www.figma.com/make/WjfQXrQIAUbW0P1MmJFHRY/Glassmorphism-Dashboard-Design--Community-',
		access: 'rate-limited',
		implemented: false,
		description: 'Glassmorphism Dashboard Design from Figma Make.',
		limitation: 'Exact Figma Make context could not be retrieved after the tool limit.'
	},
	{
		id: 'existing-icons',
		name: 'Existing Icons',
		category: 'icon',
		scope: 'icons',
		sourceReference: null,
		access: 'local',
		implemented: true,
		description: 'Keeps the protected Outline and Glass icon styles already in MediaManager.'
	},
	{
		id: 'frosted-glass-icons',
		name: 'Frosted Glass Icons',
		category: 'icon',
		scope: 'icons',
		sourceReference:
			'https://www.figma.com/design/s7S8nFqn6YHRY3Qt2e2WjF/Frosted-Glass-Icons---Customizable--Community-?node-id=3-2',
		access: 'partially-accessible',
		implemented: false,
		description: 'Frosted vector icon package.',
		limitation:
			'The cover was inspected, but exact icon assets could not be retrieved after the tool limit.'
	},
	{
		id: 'glass-icon-set-a',
		name: 'Glass Icon Set A',
		category: 'icon',
		scope: 'icons',
		sourceReference:
			'https://www.figma.com/design/IGwsTz9HFBLphFxw74CglC/Glassmorphism---Glass-Icon-set--Free---Community-?node-id=0-1',
		access: 'access-blocked',
		implemented: false,
		description: 'Glassmorphism Glass Icon Set Free A.',
		limitation: 'The connected Figma account has no edit access to this file.'
	},
	{
		id: 'glass-icon-set-b',
		name: 'Glass Icon Set B',
		category: 'icon',
		scope: 'icons',
		sourceReference:
			'https://www.figma.com/design/7TeNHg4GQMgz9WNDaQHucd/Glassmorphism---Glass-Icon-set--Free---Community-?node-id=0-1',
		access: 'access-blocked',
		implemented: false,
		description: 'Glassmorphism Glass Icon Set Free B.',
		limitation: 'The connected Figma account has no edit access to this file.'
	},
	{
		id: 'glassmorphism-style-icons',
		name: 'Glassmorphism Style Icons',
		category: 'icon',
		scope: 'icons',
		sourceReference:
			'https://www.figma.com/design/GZGffUX262noDoNgMH1LRg/Glassmorphism-Style-Icons--Community-?node-id=0-1',
		access: 'access-blocked',
		implemented: false,
		description: 'Glassmorphism Style Icons package.',
		limitation: 'The connected Figma account has no edit access to this file.'
	},
	{
		id: 'glass-style-icons-a',
		name: 'Glass Style Icons A',
		category: 'icon',
		scope: 'icons',
		sourceReference:
			'https://www.figma.com/design/3Ifl0XOkWyMEhbQ8VcDj5Q/Glassmorphism--Glass-Style-Icons--Community-?node-id=0-1',
		access: 'access-blocked',
		implemented: false,
		description: 'Glassmorphism Glass Style Icons A.',
		limitation: 'The connected Figma account has no edit access to this file.'
	},
	{
		id: 'glass-style-icons-b',
		name: 'Glass Style Icons B',
		category: 'icon',
		scope: 'icons',
		sourceReference:
			'https://www.figma.com/design/zrPwd6mb3Y5ApAQOfHx0dG/Glassmorphism--Glass-Style-Icons--Community-?node-id=0-1',
		access: 'partially-accessible',
		implemented: false,
		description: 'Glassmorphism Glass Style Icons B.',
		limitation: 'The cover was found, but exact assets could not be retrieved after the tool limit.'
	},
	{
		id: 'glassmorphism-20-icons',
		name: '20 Glassmorphism Icons',
		category: 'icon',
		scope: 'icons',
		sourceReference:
			'https://www.figma.com/design/r6KHJuDinVwv96fK0gjCoY/20-Glassmorphism-icon--Community-?node-id=2-938',
		access: 'partially-accessible',
		implemented: false,
		description: 'Twenty exact glassmorphism source icons.',
		limitation:
			'Icon node names were found, but exact vector assets were blocked after the tool limit.'
	},
	{
		id: 'existing-controls',
		name: 'Existing Controls',
		category: 'controls',
		scope: 'controls',
		sourceReference: null,
		access: 'local',
		implemented: true,
		description:
			'Keeps every protected MediaManager button, toggle and selection control unchanged.'
	},
	{
		id: 'glass-device-access-controls',
		name: 'Glass Device Access Controls',
		category: 'controls',
		scope: 'controls',
		sourceReference:
			'https://www.figma.com/community/file/1223609282777504849/glassmorphisme-card-device-access',
		access: 'needs-node',
		implemented: false,
		description: 'Glass enable, disable and selection controls.',
		limitation: 'A duplicated design URL with a concrete component node is required.'
	},
	{
		id: 'existing-sidebar',
		name: 'Existing Sidebar',
		category: 'sidebar',
		scope: 'sidebar',
		sourceReference: null,
		access: 'local',
		implemented: true,
		description: 'Restores the protected MediaManager sidebar exactly.'
	},
	{
		id: 'figma-sidebar-navigation',
		name: 'Figma Sidebar UI Navigation',
		category: 'sidebar',
		scope: 'sidebar',
		sourceReference:
			'https://www.figma.com/design/t0yVcQTSh4oM6pHe25wMWh/Sidebar-UI-Navigation---For-Web-Apps--Community-?node-id=0-1',
		access: 'accessible',
		implemented: true,
		description:
			'Exact 250/79px frosted sidebar geometry with the source active and collapsed states.'
	}
] as const satisfies ReadonlyArray<AppearancePackageDefinition>;

export function packagesFor(category: AppearancePackageCategory): AppearancePackageDefinition[] {
	return appearancePackageRegistry.filter((entry) => entry.category === category);
}

function selectableIds(category: AppearancePackageCategory): Set<string> {
	return new Set(
		appearancePackageRegistry
			.filter((entry) => entry.category === category && entry.implemented)
			.map((entry) => entry.id)
	);
}

function normalize(value: unknown): AppearancePackageSettings {
	if (!value || typeof value !== 'object') return { ...DEFAULT_APPEARANCE_PACKAGES };
	const candidate = value as Partial<AppearancePackageSettings>;
	return {
		theme: selectableIds('theme').has(candidate.theme ?? '')
			? candidate.theme!
			: DEFAULT_APPEARANCE_PACKAGES.theme,
		icon: selectableIds('icon').has(candidate.icon ?? '')
			? candidate.icon!
			: DEFAULT_APPEARANCE_PACKAGES.icon,
		controls: selectableIds('controls').has(candidate.controls ?? '')
			? candidate.controls!
			: DEFAULT_APPEARANCE_PACKAGES.controls,
		sidebar: selectableIds('sidebar').has(candidate.sidebar ?? '')
			? candidate.sidebar!
			: DEFAULT_APPEARANCE_PACKAGES.sidebar
	};
}

export function getAppearancePackages(): AppearancePackageSettings {
	if (typeof window === 'undefined') return { ...DEFAULT_APPEARANCE_PACKAGES };
	try {
		return normalize(
			JSON.parse(window.localStorage.getItem(APPEARANCE_PACKAGES_STORAGE_KEY) ?? 'null')
		);
	} catch {
		return { ...DEFAULT_APPEARANCE_PACKAGES };
	}
}

export function applyAppearancePackages(
	settings: AppearancePackageSettings,
	persist = true
): AppearancePackageSettings {
	const normalized = normalize(settings);
	if (typeof document !== 'undefined') {
		const root = document.documentElement;
		root.dataset.themePackage = normalized.theme;
		root.dataset.iconPackage = normalized.icon;
		root.dataset.controlPackage = normalized.controls;
		root.dataset.sidebarPackage = normalized.sidebar;
	}
	if (persist && typeof window !== 'undefined') {
		try {
			window.localStorage.setItem(APPEARANCE_PACKAGES_STORAGE_KEY, JSON.stringify(normalized));
		} catch (error) {
			console.warn('[Appearance] Package selection applied without browser persistence', error);
		}
		window.dispatchEvent(
			new CustomEvent<AppearancePackageSettings>('mediamanager:appearance-packages', {
				detail: normalized
			})
		);
	}
	return normalized;
}

export function initializeAppearancePackages(): AppearancePackageSettings {
	// Persist normalization so a blocked, removed, or corrupt saved package ID
	// cannot reappear on the next startup.
	return applyAppearancePackages(getAppearancePackages(), true);
}
