<script lang="ts">
	import UserTable from '$lib/components/user-data-table.svelte';
	import { page } from '$app/state';
	import * as Card from '$lib/components/ui/card/index.js';
	import { getContext, onMount } from 'svelte';
	import UserSettings from '$lib/components/user-settings.svelte';
	import { Separator } from '$lib/components/ui/separator';
	import * as Sidebar from '$lib/components/ui/sidebar/index.js';
	import * as Breadcrumb from '$lib/components/ui/breadcrumb/index.js';
	import { resolve } from '$app/paths';
	import type { UserRead } from '$lib/api/api';
	import IntegrationSettings from '$lib/components/integration-settings.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Switch } from '$lib/components/ui/switch/index.js';
	import {
		appearanceScopeOptions,
		appearanceThemeOptions,
		applyAppearance,
		getAppearance,
		glassIntensityOptions,
		isGlassTheme,
		ORIGINAL_MEDIAMANAGER_APPEARANCE,
		type AppearanceScope,
		type AppearanceSettings,
		type AppearanceTheme,
		type GlassIntensity
	} from '$lib/appearance';
	import {
		applyAppearancePackages,
		DEFAULT_APPEARANCE_PACKAGES,
		getAppearancePackages,
		packagesFor,
		type AppearancePackageAccess,
		type AppearancePackageCategory,
		type AppearancePackageSettings
	} from '$lib/appearance-packages';
	import {
		applyPosterSize,
		getPosterSize,
		posterSizeOptions,
		type PosterSize
	} from '$lib/poster-size';
	import {
		celebrationSoundOptions,
		celebrationVisualOptions,
		getCelebrationSettings,
		saveCelebrationSettings,
		triggerCelebration,
		type CelebrationSettings,
		type CelebrationSound,
		type CelebrationVisual
	} from '$lib/celebration';
	import {
		applySidebarPreferences,
		DEFAULT_SIDEBAR_PREFERENCES,
		getSidebarPreferences,
		sidebarIconStyleOptions,
		sidebarSizeOptions,
		type SidebarIconStyle,
		type SidebarPreferences,
		type SidebarSize
	} from '$lib/sidebar-preferences';
	import Check from '@lucide/svelte/icons/check';
	import Compass from '@lucide/svelte/icons/compass';
	import PanelLeft from '@lucide/svelte/icons/panel-left';
	import Play from '@lucide/svelte/icons/play';
	import Sparkles from '@lucide/svelte/icons/sparkles';
	import Volume2 from '@lucide/svelte/icons/volume-2';
	import RotateCcw from '@lucide/svelte/icons/rotate-ccw';
	import { toast } from 'svelte-sonner';

	let currentUser: () => UserRead = getContext('user');
	let users: UserRead[] = $derived(
		(page.data.users ?? []).filter((user: UserRead) => user.id !== currentUser().id)
	);
	let posterSize = $state<PosterSize>('medium');
	let appearance = $state<AppearanceSettings>(getAppearance());
	let appearancePackages = $state<AppearancePackageSettings>(getAppearancePackages());
	let celebration = $state<CelebrationSettings>(getCelebrationSettings());
	let sidebarPreferences = $state<SidebarPreferences>(getSidebarPreferences());
	const themePackages = packagesFor('theme');
	const iconPackages = packagesFor('icon');
	const controlPackages = packagesFor('controls');
	const sidebarPackages = packagesFor('sidebar');

	onMount(() => {
		posterSize = getPosterSize();
		appearance = getAppearance();
		applyAppearance(appearance, false);
		appearancePackages = getAppearancePackages();
		applyAppearancePackages(appearancePackages, false);
		celebration = getCelebrationSettings();
		sidebarPreferences = getSidebarPreferences();
		applySidebarPreferences(sidebarPreferences, false);
	});

	function selectTheme(theme: AppearanceTheme): void {
		appearance = applyAppearance({ ...appearance, theme });
	}

	function selectScope(scope: AppearanceScope): void {
		appearance = applyAppearance({ ...appearance, scope });
	}

	function selectIntensity(intensity: GlassIntensity): void {
		appearance = applyAppearance({ ...appearance, intensity });
	}

	function selectPosterSize(size: PosterSize): void {
		posterSize = applyPosterSize(size);
	}

	function selectSidebarSize(size: SidebarSize): void {
		sidebarPreferences = applySidebarPreferences({ ...sidebarPreferences, size });
	}

	function selectSidebarIconStyle(iconStyle: SidebarIconStyle): void {
		sidebarPreferences = applySidebarPreferences({ ...sidebarPreferences, iconStyle });
	}

	function selectAppearancePackage(category: AppearancePackageCategory, id: string): void {
		const next = { ...appearancePackages };
		next[category] = id;
		appearancePackages = applyAppearancePackages(next);
	}

	function packageAccessLabel(access: AppearancePackageAccess): string {
		switch (access) {
			case 'local':
			case 'accessible':
				return 'Ready';
			case 'partially-accessible':
				return 'Partial source';
			case 'needs-node':
				return 'Needs node';
			case 'access-blocked':
				return 'Access blocked';
			case 'rate-limited':
				return 'Figma limit';
		}
	}

	function updateCelebration(settings: Partial<CelebrationSettings>): void {
		celebration = saveCelebrationSettings({ ...celebration, ...settings });
	}

	function selectCelebrationVisual(visual: CelebrationVisual): void {
		updateCelebration({ visual });
	}

	function selectCelebrationSound(sound: CelebrationSound): void {
		updateCelebration({ sound });
	}

	function restoreOriginalAppearance(): void {
		appearance = applyAppearance({ ...ORIGINAL_MEDIAMANAGER_APPEARANCE });
		appearancePackages = applyAppearancePackages({ ...DEFAULT_APPEARANCE_PACKAGES });
		sidebarPreferences = applySidebarPreferences({ ...DEFAULT_SIDEBAR_PREFERENCES });
		console.info('[Appearance] Restored original MediaManager appearance', {
			theme: appearancePackages.theme,
			icons: appearancePackages.icon,
			controls: appearancePackages.controls,
			sidebar: appearancePackages.sidebar
		});
		toast.success('Original MediaManager appearance restored.');
	}
</script>

<svelte:head>
	<title>Settings - MediaManager</title>
	<meta content="Manage your MediaManager settings and user preferences" name="description" />
</svelte:head>

<header class="flex h-16 shrink-0 items-center gap-2">
	<div class="flex items-center gap-2 px-4">
		<Sidebar.Trigger class="-ml-1" />
		<Separator class="mr-2 h-4" orientation="vertical" />
		<Breadcrumb.Root>
			<Breadcrumb.List>
				<Breadcrumb.Item class="hidden md:block">
					<Breadcrumb.Link href={resolve('/dashboard', {})}>MediaManager</Breadcrumb.Link>
				</Breadcrumb.Item>
				<Breadcrumb.Separator class="hidden md:block" />
				<Breadcrumb.Item>
					<Breadcrumb.Page>Settings</Breadcrumb.Page>
				</Breadcrumb.Item>
			</Breadcrumb.List>
		</Breadcrumb.Root>
	</div>
</header>

<main class="mx-auto flex w-full flex-1 flex-col gap-4 p-4 md:max-w-[80em]">
	<h1 class="my-6 scroll-m-20 text-center text-4xl font-extrabold tracking-tight lg:text-5xl">
		Settings
	</h1>
	<Card.Root id="me">
		<Card.Header>
			<Card.Title>You</Card.Title>
			<Card.Description>Change your email or password</Card.Description>
		</Card.Header>
		<Card.Content>
			<UserSettings />
		</Card.Content>
	</Card.Root>
	<Card.Root id="appearance">
		<Card.Header>
			<Card.Title>Appearance</Card.Title>
			<Card.Description>
				Choose one visual theme and exactly where it applies. Your selection is saved in this
				browser and updates immediately.
			</Card.Description>
		</Card.Header>
		<Card.Content class="space-y-8">
			<div class="appearance-recovery flex flex-wrap items-center justify-between gap-4">
				<div class="min-w-0">
					<h3 class="font-semibold">Appearance recovery</h3>
					<p class="text-sm opacity-80">
						Restore the original theme, icons, controls and sidebar if a saved package becomes
						unavailable.
					</p>
				</div>
				<button
					class="appearance-recovery-button"
					type="button"
					onclick={restoreOriginalAppearance}
				>
					<RotateCcw class="size-4" /> Restore Original MediaManager Appearance
				</button>
			</div>
			<section aria-labelledby="theme-heading">
				<div class="mb-3">
					<h3 class="font-semibold" id="theme-heading">Theme</h3>
					<p class="text-sm text-muted-foreground">
						All variants use the same components and semantic tokens.
					</p>
				</div>
				<div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" role="radiogroup" aria-label="Theme">
					{#each appearanceThemeOptions as option (option.value)}
						<button
							class="appearance-choice {appearance.theme === option.value ? 'is-selected' : ''}"
							aria-checked={appearance.theme === option.value}
							data-theme-preview={option.value}
							role="radio"
							type="button"
							onclick={() => selectTheme(option.value)}
						>
							<span class="appearance-preview" aria-hidden="true">
								<span></span><span></span><span></span>
							</span>
							<span class="font-semibold">{option.label}</span>
							<span class="text-xs leading-relaxed text-muted-foreground">{option.description}</span
							>
						</button>
					{/each}
				</div>
				<div class="mt-7 border-t border-border/70 pt-6">
					<div class="mb-3">
						<h4 class="font-semibold">Theme / UI package layer</h4>
						<p class="text-sm text-muted-foreground">
							Existing themes stay protected. A Figma package becomes selectable only after its
							exact source has been inspected and implemented.
						</p>
					</div>
					<div
						class="grid gap-3 md:grid-cols-2 xl:grid-cols-3"
						role="radiogroup"
						aria-label="Theme package"
					>
						{#each themePackages as packageOption (packageOption.id)}
							<button
								class="package-choice {appearancePackages.theme === packageOption.id
									? 'is-selected'
									: ''}"
								aria-checked={appearancePackages.theme === packageOption.id}
								disabled={!packageOption.implemented}
								onclick={() => selectAppearancePackage('theme', packageOption.id)}
								role="radio"
								title={packageOption.limitation ?? packageOption.description}
								type="button"
							>
								<span class="package-checkbox" aria-hidden="true">
									{#if appearancePackages.theme === packageOption.id}<Check />{/if}
								</span>
								<span class="grid min-w-0 gap-1">
									<span class="flex flex-wrap items-center gap-2">
										<span class="font-semibold">{packageOption.name}</span>
										<span class="package-status" data-package-access={packageOption.access}
											>{packageAccessLabel(packageOption.access)}</span
										>
									</span>
									<span class="text-xs leading-relaxed text-muted-foreground"
										>{packageOption.description}</span
									>
									{#if packageOption.limitation}
										<span class="text-[0.7rem] leading-relaxed text-amber-600 dark:text-amber-300"
											>{packageOption.limitation}</span
										>
									{/if}
								</span>
							</button>
						{/each}
					</div>
				</div>
			</section>

			<section aria-labelledby="scope-heading">
				<div class="mb-3">
					<h3 class="font-semibold" id="scope-heading">Theme scope</h3>
					<p class="text-sm text-muted-foreground">
						Only one scope can be active, preventing visual styles from leaking into other views.
					</p>
				</div>
				<div
					class="grid gap-2 sm:grid-cols-2 lg:grid-cols-4"
					role="radiogroup"
					aria-label="Theme scope"
				>
					{#each appearanceScopeOptions as option (option.value)}
						<button
							class="scope-choice {appearance.scope === option.value ? 'is-selected' : ''}"
							aria-checked={appearance.scope === option.value}
							role="radio"
							type="button"
							onclick={() => selectScope(option.value)}
						>
							<span class="scope-checkbox" aria-hidden="true">
								{#if appearance.scope === option.value}<Check />{/if}
							</span>
							<span>{option.label}</span>
						</button>
					{/each}
				</div>
			</section>

			{#if isGlassTheme(appearance.theme)}
				<section aria-labelledby="intensity-heading">
					<div class="mb-3">
						<h3 class="font-semibold" id="intensity-heading">Glass intensity</h3>
						<p class="text-sm text-muted-foreground">
							Frosted matches the supplied visual references most closely.
						</p>
					</div>
					<div class="grid gap-2 sm:grid-cols-4" role="radiogroup" aria-label="Glass intensity">
						{#each glassIntensityOptions as option (option.value)}
							<Button
								aria-checked={appearance.intensity === option.value}
								onclick={() => selectIntensity(option.value)}
								role="radio"
								type="button"
								variant={appearance.intensity === option.value ? 'default' : 'outline'}
							>
								{option.label}
							</Button>
						{/each}
					</div>
				</section>
			{/if}

			<section aria-labelledby="sidebar-package-heading">
				<div class="mb-3">
					<h3 class="font-semibold" id="sidebar-package-heading">Sidebar style</h3>
					<p class="text-sm text-muted-foreground">
						Select the protected MediaManager sidebar or the independently scoped Figma package.
					</p>
				</div>
				<div class="grid gap-3 md:grid-cols-2" role="radiogroup" aria-label="Sidebar package">
					{#each sidebarPackages as packageOption (packageOption.id)}
						<button
							class="package-choice {appearancePackages.sidebar === packageOption.id
								? 'is-selected'
								: ''}"
							aria-checked={appearancePackages.sidebar === packageOption.id}
							disabled={!packageOption.implemented}
							onclick={() => selectAppearancePackage('sidebar', packageOption.id)}
							role="radio"
							title={packageOption.limitation ?? packageOption.description}
							type="button"
						>
							<span class="package-checkbox" aria-hidden="true">
								{#if appearancePackages.sidebar === packageOption.id}<Check />{/if}
							</span>
							<span class="grid min-w-0 gap-1">
								<span class="flex flex-wrap items-center gap-2">
									<span class="font-semibold">{packageOption.name}</span>
									<span class="package-status" data-package-access={packageOption.access}
										>{packageAccessLabel(packageOption.access)}</span
									>
								</span>
								<span class="text-xs leading-relaxed text-muted-foreground"
									>{packageOption.description}</span
								>
							</span>
						</button>
					{/each}
				</div>
			</section>

			<section aria-labelledby="sidebar-size-heading">
				<div class="mb-3">
					<h3 class="flex items-center gap-2 font-semibold" id="sidebar-size-heading">
						<PanelLeft class="size-4" /> Sidebar size
					</h3>
					<p class="text-sm text-muted-foreground">
						Changes the expanded and collapsed width, icon scale, and row spacing together.
					</p>
				</div>
				<div class="grid gap-3 sm:grid-cols-3" role="radiogroup" aria-label="Sidebar size">
					{#each sidebarSizeOptions as option (option.value)}
						<button
							class="appearance-choice {sidebarPreferences.size === option.value
								? 'is-selected'
								: ''}"
							aria-checked={sidebarPreferences.size === option.value}
							onclick={() => selectSidebarSize(option.value)}
							role="radio"
							type="button"
						>
							<span class="sidebar-size-preview" data-sidebar-size-preview={option.value}>
								<span></span><span></span><span></span>
							</span>
							<span class="font-semibold">{option.label}</span>
							<span class="text-xs leading-relaxed text-muted-foreground">{option.description}</span
							>
						</button>
					{/each}
				</div>
			</section>

			<section aria-labelledby="sidebar-icon-heading">
				<div class="mb-3">
					<h3 class="font-semibold" id="sidebar-icon-heading">Icon style</h3>
					<p class="text-sm text-muted-foreground">
						One consistent icon treatment is applied to every main and system navigation item.
					</p>
				</div>
				<div class="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Sidebar icon style">
					{#each sidebarIconStyleOptions as option (option.value)}
						<button
							class="appearance-choice {sidebarPreferences.iconStyle === option.value
								? 'is-selected'
								: ''}"
							aria-checked={sidebarPreferences.iconStyle === option.value}
							onclick={() => selectSidebarIconStyle(option.value)}
							role="radio"
							type="button"
						>
							<span class="mx-auto grid size-14 place-items-center rounded-2xl bg-muted/40">
								<span class="mm-nav-icon" data-icon-preview-style={option.value}><Compass /></span>
							</span>
							<span class="font-semibold">{option.label}</span>
							<span class="text-xs leading-relaxed text-muted-foreground">{option.description}</span
							>
						</button>
					{/each}
				</div>
			</section>

			<section aria-labelledby="icon-package-heading">
				<div class="mb-3">
					<h3 class="font-semibold" id="icon-package-heading">Icon package</h3>
					<p class="text-sm text-muted-foreground">
						Exact Figma assets are required; unavailable sources stay visible but cannot silently
						fall back to a fake package.
					</p>
				</div>
				<div
					class="grid gap-3 md:grid-cols-2 xl:grid-cols-3"
					role="radiogroup"
					aria-label="Icon package"
				>
					{#each iconPackages as packageOption (packageOption.id)}
						<button
							class="package-choice {appearancePackages.icon === packageOption.id
								? 'is-selected'
								: ''}"
							aria-checked={appearancePackages.icon === packageOption.id}
							disabled={!packageOption.implemented}
							onclick={() => selectAppearancePackage('icon', packageOption.id)}
							role="radio"
							title={packageOption.limitation ?? packageOption.description}
							type="button"
						>
							<span class="package-checkbox" aria-hidden="true">
								{#if appearancePackages.icon === packageOption.id}<Check />{/if}
							</span>
							<span class="grid min-w-0 gap-1">
								<span class="flex flex-wrap items-center gap-2">
									<span class="font-semibold">{packageOption.name}</span>
									<span class="package-status" data-package-access={packageOption.access}
										>{packageAccessLabel(packageOption.access)}</span
									>
								</span>
								<span class="text-xs leading-relaxed text-muted-foreground"
									>{packageOption.description}</span
								>
								{#if packageOption.limitation}
									<span class="text-[0.7rem] leading-relaxed text-amber-600 dark:text-amber-300"
										>{packageOption.limitation}</span
									>
								{/if}
							</span>
						</button>
					{/each}
				</div>
			</section>

			<section aria-labelledby="control-package-heading">
				<div class="mb-3">
					<h3 class="font-semibold" id="control-package-heading">
						Button / toggle / control package
					</h3>
					<p class="text-sm text-muted-foreground">
						Control styling is independent from both the global theme and sidebar package.
					</p>
				</div>
				<div class="grid gap-3 md:grid-cols-2" role="radiogroup" aria-label="Control package">
					{#each controlPackages as packageOption (packageOption.id)}
						<button
							class="package-choice {appearancePackages.controls === packageOption.id
								? 'is-selected'
								: ''}"
							aria-checked={appearancePackages.controls === packageOption.id}
							disabled={!packageOption.implemented}
							onclick={() => selectAppearancePackage('controls', packageOption.id)}
							role="radio"
							title={packageOption.limitation ?? packageOption.description}
							type="button"
						>
							<span class="package-checkbox" aria-hidden="true">
								{#if appearancePackages.controls === packageOption.id}<Check />{/if}
							</span>
							<span class="grid min-w-0 gap-1">
								<span class="flex flex-wrap items-center gap-2">
									<span class="font-semibold">{packageOption.name}</span>
									<span class="package-status" data-package-access={packageOption.access}
										>{packageAccessLabel(packageOption.access)}</span
									>
								</span>
								<span class="text-xs leading-relaxed text-muted-foreground"
									>{packageOption.description}</span
								>
								{#if packageOption.limitation}
									<span class="text-[0.7rem] leading-relaxed text-amber-600 dark:text-amber-300"
										>{packageOption.limitation}</span
									>
								{/if}
							</span>
						</button>
					{/each}
				</div>
			</section>

			<section aria-labelledby="poster-size-heading">
				<div class="mb-3">
					<h3 class="font-semibold" id="poster-size-heading">Calendar poster size</h3>
					<p class="text-sm text-muted-foreground" id="poster-size-help">
						Small shows more releases per row; Large gives artwork more room.
					</p>
				</div>
				<div
					aria-describedby="poster-size-help"
					aria-label="Poster size"
					class="grid gap-2 sm:grid-cols-3"
					role="radiogroup"
				>
					{#each posterSizeOptions as option (option.value)}
						<Button
							aria-checked={posterSize === option.value}
							onclick={() => selectPosterSize(option.value)}
							role="radio"
							type="button"
							variant={posterSize === option.value ? 'default' : 'outline'}
						>
							{option.label}
						</Button>
					{/each}
				</div>
			</section>
		</Card.Content>
	</Card.Root>
	<Card.Root id="add-media-celebration">
		<Card.Header>
			<Card.Title class="flex items-center gap-2"
				><Sparkles class="size-5" /> Add Media celebration</Card.Title
			>
			<Card.Description>
				Play a visual and sound together only after MediaManager confirms that a movie or series was
				added.
			</Card.Description>
		</Card.Header>
		<Card.Content class="space-y-7">
			<div class="flex items-center justify-between gap-5 rounded-2xl border bg-muted/20 p-4">
				<div>
					<label class="font-semibold" for="celebration-enabled">Enable celebration</label>
					<p class="text-sm text-muted-foreground">Disable this to add media silently.</p>
				</div>
				<Switch
					checked={celebration.enabled}
					id="celebration-enabled"
					onCheckedChange={(enabled) => updateCelebration({ enabled })}
				/>
			</div>

			<section aria-labelledby="celebration-visual-heading">
				<div class="mb-3 flex items-end justify-between gap-3">
					<div>
						<h3 class="font-semibold" id="celebration-visual-heading">Visual</h3>
						<p class="text-sm text-muted-foreground">
							Motion is automatically suppressed when reduced motion is preferred.
						</p>
					</div>
					<Button
						disabled={celebration.visual === 'none'}
						onclick={() =>
							triggerCelebration({ force: true, visual: celebration.visual, sound: 'none' })}
						size="sm"
						type="button"
						variant="outline"
					>
						<Play /> Preview Effect
					</Button>
				</div>
				<div
					class="grid gap-2 sm:grid-cols-3 xl:grid-cols-5"
					role="radiogroup"
					aria-label="Celebration visual"
				>
					{#each celebrationVisualOptions as option (option.value)}
						<Button
							aria-checked={celebration.visual === option.value}
							onclick={() => selectCelebrationVisual(option.value)}
							role="radio"
							type="button"
							variant={celebration.visual === option.value ? 'default' : 'outline'}
						>
							{option.label}
						</Button>
					{/each}
				</div>
			</section>

			<section aria-labelledby="celebration-sound-heading">
				<div class="mb-3 flex items-end justify-between gap-3">
					<div>
						<h3 class="font-semibold" id="celebration-sound-heading">Sound</h3>
						<p class="text-sm text-muted-foreground">
							The selected sound starts at the same time as the visual.
						</p>
					</div>
					<Button
						disabled={celebration.sound === 'none'}
						onclick={() =>
							triggerCelebration({ force: true, visual: 'none', sound: celebration.sound })}
						size="sm"
						type="button"
						variant="outline"
					>
						<Volume2 /> Preview Sound
					</Button>
				</div>
				<div
					class="grid gap-2 sm:grid-cols-2 xl:grid-cols-4"
					role="radiogroup"
					aria-label="Celebration sound"
				>
					{#each celebrationSoundOptions as option (option.value)}
						<Button
							aria-checked={celebration.sound === option.value}
							onclick={() => selectCelebrationSound(option.value)}
							role="radio"
							type="button"
							variant={celebration.sound === option.value ? 'default' : 'outline'}
						>
							{option.label}
						</Button>
					{/each}
				</div>
			</section>

			<section aria-labelledby="celebration-volume-heading">
				<div class="mb-3 flex items-center justify-between gap-3">
					<div>
						<h3 class="font-semibold" id="celebration-volume-heading">Volume</h3>
						<p class="text-sm text-muted-foreground">Applies to every celebration sound.</p>
					</div>
					<output class="min-w-12 text-right text-sm font-semibold" for="celebration-volume"
						>{Math.round(celebration.volume * 100)}%</output
					>
				</div>
				<input
					aria-labelledby="celebration-volume-heading"
					class="celebration-volume"
					id="celebration-volume"
					max="100"
					min="0"
					oninput={(event) =>
						updateCelebration({ volume: event.currentTarget.valueAsNumber / 100 })}
					step="1"
					type="range"
					value={Math.round(celebration.volume * 100)}
				/>
			</section>
		</Card.Content>
	</Card.Root>
	<IntegrationSettings
		initialMapping={page.data.recommendationMapping}
		initialSettings={page.data.integrations}
		integrationError={page.data.integrationError}
		mappingError={page.data.mappingError}
	/>
	{#if currentUser().is_superuser}
		<Card.Root id="users">
			<Card.Header>
				<Card.Title>Users</Card.Title>
				<Card.Description>Edit, delete or change the permissions of other users</Card.Description>
			</Card.Header>
			<Card.Content>
				<UserTable {users} />
			</Card.Content>
		</Card.Root>
	{/if}
</main>

<style>
	.appearance-recovery {
		border: 1px solid ButtonBorder;
		border-radius: 1rem;
		padding: 1rem;
		color: CanvasText;
		background: Canvas;
	}

	.appearance-recovery-button {
		display: inline-flex;
		min-height: 2.5rem;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		border: 1px solid ButtonBorder;
		border-radius: 0.65rem;
		padding: 0.55rem 0.85rem;
		color: ButtonText;
		background: ButtonFace;
		font-weight: 650;
		cursor: pointer;
	}

	.appearance-recovery-button:focus-visible {
		outline: 3px solid Highlight;
		outline-offset: 2px;
	}

	.sidebar-size-preview {
		display: grid;
		width: 100%;
		height: 4.75rem;
		grid-template-columns: 32% 1fr;
		grid-template-rows: repeat(3, 1fr);
		gap: 0.35rem;
		border: 1px solid var(--border);
		border-radius: 0.8rem;
		padding: 0.55rem;
		background: var(--muted);
	}

	.sidebar-size-preview::before {
		content: '';
		grid-row: 1 / -1;
		border-radius: 0.5rem;
		background: color-mix(in oklab, var(--primary) 22%, var(--card));
	}

	.sidebar-size-preview[data-sidebar-size-preview='small'] {
		grid-template-columns: 22% 1fr;
	}

	.sidebar-size-preview[data-sidebar-size-preview='large'] {
		grid-template-columns: 43% 1fr;
	}

	.sidebar-size-preview > span {
		grid-column: 2;
		border-radius: 0.35rem;
		background: color-mix(in oklab, var(--foreground) 10%, transparent);
	}

	.celebration-volume {
		width: 100%;
		height: 0.42rem;
		border-radius: 999px;
		accent-color: var(--primary);
		cursor: pointer;
	}
</style>
