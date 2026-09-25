import type { RecommendationSchema } from '$lib/api/api';

export type DiscoverMediaType = 'all' | 'movie' | 'tv';

export type DiscoverCategory = 'discover' | 'popular' | 'upcoming' | 'top_rated' | 'trending';

export type DiscoverSort =
	| 'popularity.desc'
	| 'popularity.asc'
	| 'vote_average.desc'
	| 'vote_average.asc'
	| 'release_date.desc'
	| 'release_date.asc';

export interface DiscoverMediaItem {
	id: string | null;
	external_id: number;
	media_type: 'movie' | 'tv';
	name: string;
	original_name: string | null;
	overview: string | null;
	poster_path: string | null;
	backdrop_path: string | null;
	year: number | null;
	release_date: string | null;
	vote_average: number | null;
	vote_count: number;
	popularity: number | null;
	genre_ids: number[];
	original_language: string | null;
	metadata_provider: 'tmdb' | 'tvdb';
	adult: boolean;
	added: boolean;
}

export interface DiscoverPage {
	page: number;
	total_pages: number;
	total_results: number;
	results: DiscoverMediaItem[];
}

export interface DiscoverGenre {
	id: number;
	name: string;
}

export interface DiscoverGenres {
	movie: DiscoverGenre[];
	tv: DiscoverGenre[];
}

export interface DiscoverFilters {
	media_type: DiscoverMediaType;
	year_from: number | null;
	year_to: number | null;
	genres: number[];
	rating_min: number;
	rating_max: number;
	category: DiscoverCategory;
	sort_by: DiscoverSort;
	include_adult: boolean;
}

export type RecommendationItem = RecommendationSchema;
export type ResolvedRecommendationItem = RecommendationItem & {
	external_id: number;
	metadata_provider: 'tmdb' | 'tvdb';
};

export const DISCOVER_CATEGORY_LABELS: Record<DiscoverCategory, string> = {
	discover: 'All catalog',
	popular: 'Popular',
	upcoming: 'Upcoming',
	top_rated: 'Top rated',
	trending: 'Trending'
};

export const DEFAULT_DISCOVER_FILTERS: DiscoverFilters = {
	media_type: 'all',
	year_from: null,
	year_to: null,
	genres: [],
	rating_min: 1,
	rating_max: 10,
	category: 'discover',
	sort_by: 'popularity.desc',
	include_adult: false
};

export function cloneDiscoverFilters(filters: DiscoverFilters): DiscoverFilters {
	return { ...filters, genres: [...filters.genres] };
}

export function hasAdvancedCatalogFilters(filters: DiscoverFilters): boolean {
	return (
		filters.year_from != null ||
		filters.year_to != null ||
		filters.genres.length > 0 ||
		filters.rating_min !== DEFAULT_DISCOVER_FILTERS.rating_min ||
		filters.rating_max !== DEFAULT_DISCOVER_FILTERS.rating_max ||
		filters.sort_by !== DEFAULT_DISCOVER_FILTERS.sort_by ||
		filters.include_adult
	);
}

export function hasResolvedRecommendationMetadata(
	item: RecommendationItem
): item is ResolvedRecommendationItem {
	return (
		typeof item.external_id === 'number' &&
		(item.metadata_provider === 'tmdb' || item.metadata_provider === 'tvdb')
	);
}

export function recommendationToMediaItem(item: RecommendationItem): DiscoverMediaItem | null {
	if (!hasResolvedRecommendationMetadata(item)) return null;

	return {
		id: item.id ?? null,
		external_id: item.external_id,
		media_type: item.media_type === 'show' ? 'tv' : 'movie',
		name: item.name,
		original_name: null,
		overview: item.overview ?? null,
		poster_path: item.poster_path ?? null,
		backdrop_path: null,
		year: item.year ?? null,
		release_date: item.year ? `${item.year}-01-01` : null,
		vote_average: item.vote_average ?? null,
		vote_count: 0,
		popularity: 0,
		genre_ids: [],
		original_language: null,
		metadata_provider: item.metadata_provider,
		adult: false,
		added: item.added
	};
}
